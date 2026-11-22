"""PubMed E-utilities client (§6 "Calling PubMed").

- ``search``: ESearch with ``sort=relevance`` → PMIDs. Without the flag PubMed returns
  newest first (#25 / PR #26).
- ``fetch``: EFetch (``rettype=abstract``, XML) → title, abstract, year, journal,
  publication types and DOI. ESummary has no abstracts, which is why it isn't used.
- **Rate limits.** NCBI allows about 3 requests a second without an API key and 10
  with one. Every request passes one process-wide ``RateLimiter``; NCBI errors (HTTP
  429 and 5xx, transport errors, and the ``API rate limit exceeded`` body NCBI
  sometimes sends with a 200) are retried with exponential backoff via tenacity.
- **Limits** (§15 "Tools"): request timeout, response size cap, PMIDs per fetch, and
  only the two fixed E-utilities endpoints are ever called.

Everything the client returns comes from NCBI's response. Abstracts are untrusted
text (§15); this module only parses them, it never interprets them.

No LangGraph or MCP code here: the graph nodes and the future MCP server share it.
"""
from __future__ import annotations

import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.retrieval.schemas import SearchFilters

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"
TOOL_NAME = "who-infodemic-monitor"
USER_AGENT = "WHO-Infodemic-Monitor/1.0 (research tool)"

MAX_RESPONSE_BYTES = 5_000_000
MAX_PMIDS_PER_FETCH = 50
MAX_ABSTRACT_CHARS = 8_000  # keeps evidence records well under the checkpoint cap
MAX_TITLE_CHARS = 1_000


class PubMedError(RuntimeError):
    """PubMed could not be reached or returned something unusable."""


class RetryablePubMedError(PubMedError):
    """Rate-limited or a server-side failure; worth retrying."""


# ------------------------------------------------------------------ rate limit


class RateLimiter:
    """Spaces calls at least ``1 / rate`` seconds apart (thread-safe).

    One instance per process per rate, shared by every client, so parallel claims
    don't add up past NCBI's limit. Across processes, ``app.mcp_server.quota`` has the
    shared Redis token bucket (the MCP server uses it; ``pipeline_ncbi_limiter`` is the
    pipeline's drop-in, not wired until T11). Until then each worker process stays
    under the limit on its own, and Celery runs one worker by default
    (``CELERY_CONCURRENCY=1``).
    """

    def __init__(
        self,
        rate_per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate must be positive")
        self.interval = 1.0 / rate_per_second
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self._next - now
            if wait > 0:
                self._sleep(wait)
                now += wait
            self._next = now + self.interval


_LIMITERS: dict[float, RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def shared_rate_limiter(has_api_key: bool) -> RateLimiter:
    # Slightly under NCBI's published limits, to leave room for clock jitter.
    rate = 9.0 if has_api_key else 2.5
    with _LIMITERS_LOCK:
        if rate not in _LIMITERS:
            _LIMITERS[rate] = RateLimiter(rate)
        return _LIMITERS[rate]


# ------------------------------------------------------------------- records


@dataclass(frozen=True)
class PubMedArticle:
    """One parsed EFetch article. Plain data, cacheable as JSON."""

    pmid: str
    title: str
    abstract: str = ""
    doi: Optional[str] = None
    publication_year: Optional[int] = None
    journal: Optional[str] = None
    publication_types: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return {
            "pmid": self.pmid, "title": self.title, "abstract": self.abstract,
            "doi": self.doi, "publication_year": self.publication_year,
            "journal": self.journal, "publication_types": list(self.publication_types),
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "PubMedArticle":
        return cls(
            pmid=str(d["pmid"]), title=d["title"], abstract=d.get("abstract", ""),
            doi=d.get("doi"), publication_year=d.get("publication_year"),
            journal=d.get("journal"), publication_types=tuple(d.get("publication_types", ())),
        )


# -------------------------------------------------------------------- parsing

_PMID_RE = re.compile(r"^\d{1,9}$")
_YEAR_RE = re.compile(r"(1[89]\d\d|20\d\d)")


def parse_esearch(payload: dict[str, Any]) -> list[str]:
    """PMIDs from an ESearch JSON response, in PubMed's relevance order."""
    if not isinstance(payload, dict):
        raise PubMedError("ESearch response is not a JSON object")
    if "error" in payload:
        msg = str(payload["error"])
        if "rate limit" in msg.lower():
            raise RetryablePubMedError(msg)
        raise PubMedError(msg)
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        raise PubMedError("ESearch response has no esearchresult")
    if "ERROR" in result:
        raise PubMedError(str(result["ERROR"]))
    ids = result.get("idlist", [])
    out: list[str] = []
    for pmid in ids:
        pmid = str(pmid).strip()
        if _PMID_RE.match(pmid) and pmid not in out:
            out.append(pmid)
    return out


def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _year(article: ET.Element) -> Optional[int]:
    for path in (
        "MedlineCitation/Article/Journal/JournalIssue/PubDate/Year",
        "MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate",
        "MedlineCitation/Article/ArticleDate/Year",
        "PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year",
    ):
        m = _YEAR_RE.search(_text(article.find(path)))
        if m:
            return int(m.group(1))
    return None


def _doi(article: ET.Element) -> Optional[str]:
    for el in article.findall("PubmedData/ArticleIdList/ArticleId"):
        if el.get("IdType") == "doi" and _text(el):
            return _text(el).lower()
    for el in article.findall("MedlineCitation/Article/ELocationID"):
        if el.get("EIdType") == "doi" and _text(el):
            return _text(el).lower()
    return None


def _abstract(article: ET.Element) -> str:
    parts = []
    for el in article.findall("MedlineCitation/Article/Abstract/AbstractText"):
        body = _text(el)
        if not body:
            continue
        label = el.get("Label")
        parts.append(f"{label}: {body}" if label else body)
    text = "\n".join(parts)
    if len(text) > MAX_ABSTRACT_CHARS:
        text = text[: MAX_ABSTRACT_CHARS - 1].rstrip() + "…"
    return text


def parse_efetch(xml_text: str) -> list[PubMedArticle]:
    """Articles from an EFetch ``PubmedArticleSet``. Book records (``PubmedBookArticle``)
    and articles with no PMID or title are skipped."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PubMedError(f"EFetch returned invalid XML: {exc}") from exc
    if root.tag != "PubmedArticleSet":
        err = _text(root.find(".//ERROR")) or root.tag
        raise PubMedError(f"unexpected EFetch response: {err}")
    out: list[PubMedArticle] = []
    for art in root.findall("PubmedArticle"):
        pmid = _text(art.find("MedlineCitation/PMID"))
        title = _text(art.find("MedlineCitation/Article/ArticleTitle"))[:MAX_TITLE_CHARS]
        if not _PMID_RE.match(pmid) or not title:
            continue
        types = tuple(
            dict.fromkeys(
                _text(pt)
                for pt in art.findall("MedlineCitation/Article/PublicationTypeList/PublicationType")
                if _text(pt)
            )
        )
        out.append(
            PubMedArticle(
                pmid=pmid,
                title=title,
                abstract=_abstract(art),
                doi=_doi(art),
                publication_year=_year(art),
                journal=_text(art.find("MedlineCitation/Article/Journal/Title")) or None,
                publication_types=types,
            )
        )
    return out


# --------------------------------------------------------------------- client


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RetryablePubMedError):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


def filter_term(filters: SearchFilters) -> str:
    """The ``[pt]`` clause ANDed onto a query for publication-type filters."""
    if not filters.publication_types:
        return ""
    return "(" + " OR ".join(f'"{t}"[pt]' for t in filters.publication_types) + ")"


def _guarded_http(timeout: float):
    from app.core.guardrails.config import load_guardrails
    from app.core.guardrails.tools import GuardedHttpClient

    limits = load_guardrails().tools.model_copy(
        update={"timeout_seconds": timeout, "max_response_bytes": MAX_RESPONSE_BYTES}
    )
    return GuardedHttpClient(limits, headers={"User-Agent": USER_AGENT})


class PubMedClient:
    """Synchronous E-utilities client. Inject ``http`` (an ``httpx.Client``) in tests,
    e.g. with ``httpx.MockTransport`` serving recorded responses."""

    def __init__(
        self,
        http: Optional[httpx.Client] = None,
        *,
        api_key: str = "",
        email: str = "",
        rate_limiter: Optional[RateLimiter] = None,
        max_attempts: int = 4,
        backoff_min: float = 1.0,
        backoff_max: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 15.0,
    ) -> None:
        # Default: the §15 guarded client (HTTPS to the E-utilities host only, no
        # redirects, body read with a byte cap). Tests inject their own client.
        self._http = http or _guarded_http(timeout)
        self._api_key = api_key
        self._email = email
        self._limiter = rate_limiter or shared_rate_limiter(bool(api_key))
        self._retrying = dict(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=backoff_min, min=backoff_min, max=backoff_max),
            retry=retry_if_exception(_is_retryable),
            sleep=sleep,
            reraise=True,
        )
        self.request_count = 0  # every HTTP request sent, retries included

    def _common(self) -> dict[str, str]:
        params = {"db": "pubmed", "tool": TOOL_NAME}
        if self._email:
            params["email"] = self._email
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    def _get(self, url: str, params: dict[str, Any]) -> httpx.Response:
        """One request: rate-limited, size-capped, fixed endpoints only. No retry."""
        if url not in (ESEARCH_URL, EFETCH_URL):  # §15: fixed functions only
            raise PubMedError(f"refusing to call {url}")
        self._limiter.acquire()
        self.request_count += 1
        resp = self._http.get(url, params={**self._common(), **params})
        resp.raise_for_status()
        if len(resp.content) > MAX_RESPONSE_BYTES:
            raise PubMedError(f"response of {len(resp.content)} bytes exceeds the cap")
        return resp

    def _with_retry(self, fn: Callable[[], Any]) -> Any:
        for attempt in Retrying(**self._retrying):
            with attempt:
                return fn()
        raise PubMedError("unreachable")  # pragma: no cover

    def search(
        self, query: str, max_results: int = 20, filters: SearchFilters = SearchFilters()
    ) -> list[str]:
        """ESearch, ``sort=relevance``. Returns PMIDs in relevance order."""
        term = query.strip()
        if not term:
            return []
        extra = filter_term(filters)
        if extra:
            term = f"({term}) AND {extra}"
        params: dict[str, Any] = {
            "term": term,
            "retmax": max(1, min(int(max_results), 100)),
            "retmode": "json",
            "sort": "relevance",
        }
        if filters.min_year or filters.max_year:
            params.update(
                datetype="pdat",
                mindate=str(filters.min_year or 1800),
                maxdate=str(filters.max_year or 3000),
            )

        def call() -> list[str]:
            resp = self._get(ESEARCH_URL, params)
            try:
                payload = resp.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise PubMedError("ESearch returned invalid JSON") from exc
            return parse_esearch(payload)

        # Retry covers the request and the parse: NCBI can put a rate-limit error in a 200.
        return self._with_retry(call)

    def fetch(self, pmids: list[str]) -> list[PubMedArticle]:
        """EFetch abstracts for ``pmids`` (batched). Order follows ``pmids``."""
        wanted = [p for p in dict.fromkeys(str(p) for p in pmids) if _PMID_RE.match(p)]
        found: dict[str, PubMedArticle] = {}
        for i in range(0, len(wanted), MAX_PMIDS_PER_FETCH):
            batch = wanted[i : i + MAX_PMIDS_PER_FETCH]
            params = {"id": ",".join(batch), "rettype": "abstract", "retmode": "xml"}
            articles = self._with_retry(lambda: parse_efetch(self._get(EFETCH_URL, params).text))
            for art in articles:
                found[art.pmid] = art
        return [found[p] for p in wanted if p in found]

    def close(self) -> None:
        self._http.close()
