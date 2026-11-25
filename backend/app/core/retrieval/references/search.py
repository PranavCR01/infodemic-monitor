"""Search the authoritative references for one fact-of-record claim (§6 "Trusted sources
beyond PubMed").

Two backends, both limited to the allow-list in ``config/reference_sources.yaml``:

- **catalogue**: a fixed list of pages per source (CDC and WHO schedules, FDA/EMA/EFSA
  limits, WHO/CDC/NHS/ECDC fact sheets, USDA FoodData). A page is a candidate when its
  keyword phrases appear in the claim; the best matches are used. A page is either
  fetched live, or, when its publisher blocks scripted requests (``retrieval: stored``,
  CDC first), read from the stored, versioned snapshot archive (``stored.py``), which a
  script refreshes; it is never requested at claim time.
- **bookshelf**: NCBI Bookshelf (e.g. StatPearls) through E-utilities only, never the
  website (which serves a reCAPTCHA to scripts). ``efetch`` on ``db=books`` returns no
  text (only ID lists; full records are refused with HTTP 400), so chapters are found
  the way PubMed indexes them: ESearch on ``db=pubmed`` restricted to
  ``booksdocs[filter]`` (Bookshelf documents), then EFetch ``db=pubmed`` XML, whose
  ``PubmedBookArticle`` carries the chapter's accession (``NBK…``), book, title and
  summary text. The citation link is the chapter's Bookshelf URL, built from a checked
  accession and never fetched.

Each fetched page is stored as a snapshot (its text and SHA-256), the passage that
best matches the claim is quoted, and the record is cited like a paper:
``evidence_id`` is ``ref_<hash>`` built by code from the URL, the snapshot hash and the
passage, ``source`` is ``"reference"``, plus the URL, the publisher and the date
retrieved. A page with no passage that shares enough of the claim's words gives no
record: an off-topic official page is not evidence about the claim.

No model is involved anywhere here, and nothing a model writes can name a page.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from app.core.retrieval.cache import InMemoryQueryCache, QueryCache
from app.core.retrieval.planning import content_words, normalize_claim
from app.core.retrieval.references.config import CataloguePage, ReferenceConfig, ReferenceSource
from app.core.retrieval.references.fetcher import FetchedPage, ReferenceFetcher, ReferenceFetchError
from app.core.retrieval.references.passages import best_passage
from app.core.retrieval.references.fetcher import text_sha256
from app.core.retrieval.references.snapshots import InMemorySnapshotStore, SnapshotStore
from app.core.retrieval.references.stored import StoredSnapshots
from app.core.retrieval.schemas import EvidenceRecord

REFERENCE_PUBLICATION_TYPE = "Authoritative Reference"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BOOKS_PAGE = "https://www.ncbi.nlm.nih.gov/books/{accession}/"
_ACCESSION = re.compile(r"^NBK\d{1,9}$")
_REF_ID = re.compile(r"^ref_[0-9a-f]{16}$")
BOOKS_FILTER = "booksdocs[filter]"  # PubMed's subset of NCBI Bookshelf documents
EUTILS_TOOL = "who_infodemic_monitor"
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def reference_evidence_id(url: str, snapshot_sha256: str, passage: str) -> str:
    """``ref_<hash>``: built by code from what is cited, so the same passage of the same
    page version always gets the same ID, and a changed page gets a new one."""
    digest = hashlib.sha256(f"{url}\n{snapshot_sha256}\n{passage}".encode("utf-8")).hexdigest()
    return f"ref_{digest[:16]}"


def is_reference_evidence_id(evidence_id: str) -> bool:
    return bool(_REF_ID.match(evidence_id or ""))


def _phrase_in(phrase: str, text: str) -> bool:
    p = normalize_claim(phrase)
    return bool(p) and re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", text) is not None


def match_catalogue(claim_text: str, config: ReferenceConfig) -> list[tuple[CataloguePage, int]]:
    """Catalogue pages whose keyword phrases appear in the claim, most hits first
    (ties in config order), with at least ``min_keyword_hits``."""
    text = normalize_claim(claim_text)
    scored = []
    for i, page in enumerate(config.catalogue):
        hits = sum(1 for k in page.keywords if _phrase_in(k, text))
        if hits >= config.min_keyword_hits:
            scored.append((page, hits, i))
    scored.sort(key=lambda x: (-x[1], x[2]))
    return [(p, h) for p, h, _ in scored]


@dataclass(frozen=True)
class BookChapter:
    pmid: str
    accession: str
    title: str
    book_title: str
    text: str

    @property
    def citation_title(self) -> str:
        if self.book_title and self.book_title != self.title:
            return f"{self.title} ({self.book_title})" if self.title else self.book_title
        return self.title or self.book_title


def _itertext(el: Optional[ET.Element]) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def parse_book_chapters(xml_text: str) -> list[BookChapter]:
    """``PubmedBookArticle`` records from an EFetch ``db=pubmed`` reply. The accession is
    the document's own ``bookaccession`` id (not one from its reference list) and must
    look like ``NBK<digits>``, or the record is dropped: it is never turned into a URL.
    The text is the chapter's summary (``AbstractText``, labelled sections kept as
    ``Label: text`` paragraphs); a chapter with no summary has nothing to quote."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ReferenceFetchError("http", f"efetch returned invalid XML: {exc}") from exc
    out: list[BookChapter] = []
    for art in root.iter("PubmedBookArticle"):
        doc = art.find("BookDocument")
        if doc is None:
            continue
        pmid = (doc.findtext("PMID") or "").strip()
        acc = ""
        for aid in doc.findall("ArticleIdList/ArticleId"):
            if aid.get("IdType") == "bookaccession":
                acc = (aid.text or "").strip()
        if not pmid.isdigit() or not _ACCESSION.match(acc):
            continue
        paras = []
        for t in doc.findall("Abstract/AbstractText"):
            body = _itertext(t)
            if body:
                label = (t.get("Label") or "").strip()
                paras.append(f"{label}: {body}" if label and label.upper() != "UNLABELLED" else body)
        title = _itertext(doc.find("ArticleTitle"))
        if not paras:
            continue
        out.append(BookChapter(pmid=pmid, accession=acc, title=title,
                               book_title=_itertext(doc.find("Book/BookTitle")), text="\n\n".join(paras)))
    return out


def bookshelf_query(claim_text: str) -> str:
    """Plain search terms from the claim's content words (no field tags, no URLs)."""
    words = content_words(normalize_claim(claim_text))
    return " ".join(w for w in words if re.fullmatch(r"[\w'+.%-]+", w))[:200]


@dataclass(frozen=True)
class ConsultedItem:
    """One allow-listed page, stored snapshot or Bookshelf search the searcher tried
    for a claim (T31, "How we searched"). ``item`` is the catalogue page ID, the NBK
    accession, or ``"search"`` for a Bookshelf search itself. ``url`` is the
    allow-listed page URL (never an E-utilities request URL, which can carry the API
    key). ``outcome``: ``passage`` (a quotable passage was found), ``no_passage``,
    ``no_results`` (a search that returned nothing) or ``error``."""

    source_id: str
    item: str
    mode: str  # live | stored | search
    outcome: str
    url: Optional[str] = None


@dataclass
class ReferenceResult:
    records: list[EvidenceRecord]
    errors: list[str] = field(default_factory=list)
    pages_fetched: int = 0  # live pages and Bookshelf chapters
    stored_pages: int = 0  # stored snapshots cited instead of a request
    candidates: list[str] = field(default_factory=list)  # page IDs / NBK accessions tried
    consulted: list[ConsultedItem] = field(default_factory=list)  # T31, in the order tried


class ReferenceSearcher:
    """Facts of record → reference evidence records. Inject the fetcher (over a mock
    transport serving recorded pages) and the snapshot store in tests."""

    def __init__(
        self,
        config: ReferenceConfig,
        fetcher: Optional[ReferenceFetcher] = None,
        snapshots: Optional[SnapshotStore] = None,
        cache: Optional[QueryCache] = None,
        *,
        rate_limiter: Any = None,
        stored: Optional[StoredSnapshots] = None,
        api_key: str = "",
        eutils_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.config = config
        self.stored = stored if stored is not None else StoredSnapshots()
        self.api_key = api_key
        self.eutils_attempts = max(1, eutils_attempts)
        self._sleep = sleep
        self._now = now
        self.fetcher = fetcher or ReferenceFetcher(config)
        self.snapshots: SnapshotStore = snapshots if snapshots is not None else InMemorySnapshotStore()
        self.cache: QueryCache = cache if cache is not None else InMemoryQueryCache()
        # NCBI's limit covers Bookshelf too: share PubMed's limiter when one is given.
        self.rate_limiter = rate_limiter

    # ---------------------------------------------------------------- pages

    def _page(self, url: str, source: ReferenceSource, title: str = "") -> FetchedPage:
        key = "ref_page:" + hashlib.sha256(url.encode()).hexdigest()
        cached = self.cache.get(key)
        if cached is not None:
            page = FetchedPage.from_json(cached)
        else:
            if self.rate_limiter is not None and source.backend == "bookshelf":
                self.rate_limiter.acquire()
            page = self.fetcher.fetch(url, source, title=title)
            self.cache.set(key, page.to_json(), ttl=self.config.cache_ttl_seconds)
        self.snapshots.save(page)
        return page

    def _record(self, claim_text: str, page: FetchedPage, source: ReferenceSource,
                query: str) -> Optional[EvidenceRecord]:
        passage = best_passage(claim_text, page.text, title=page.title,
                               max_chars=self.config.max_passage_chars,
                               min_overlap=self.config.min_passage_overlap)
        if passage is None:
            return None
        return EvidenceRecord(
            evidence_id=reference_evidence_id(page.url, page.sha256, passage.text),
            source="reference",
            title=page.title,
            abstract=passage.text,
            publication_type=[REFERENCE_PUBLICATION_TYPE],
            source_url=page.url,
            query=query,
            publisher=source.publisher,
            retrieved_at=page.retrieved_at,
            snapshot_sha256=page.sha256,
        )

    # ---------------------------------------------------------------- bookshelf

    def _eutils(self, endpoint: str, source: ReferenceSource, params: dict) -> httpx.Response:
        """One E-utilities call (allow-listed, size-capped), spaced by the shared NCBI
        limiter, retried with backoff on 429 and 5xx (NCBI answers 429 when the shared
        egress IP goes over 3 requests a second)."""
        params = {"tool": EUTILS_TOOL, **params}
        if self.api_key:
            params["api_key"] = self.api_key
        for attempt in range(self.eutils_attempts):
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            try:
                return self.fetcher.get(f"{EUTILS}/{endpoint}", source, params=params)
            except ReferenceFetchError as exc:
                if exc.status not in _RETRY_STATUS or attempt + 1 >= self.eutils_attempts:
                    raise
                self._sleep(min(8.0, 0.5 * 2 ** attempt))
        raise AssertionError("unreachable")

    def bookshelf_chapters(self, query: str, source: ReferenceSource) -> list[FetchedPage]:
        """Bookshelf chapters for a search, in relevance order, as citable pages (the
        chapter summary as text, the Bookshelf URL as the link)."""
        if not query:
            return []
        key = "ref_books_v2:" + hashlib.sha256(f"{query}|{source.max_results}".encode()).hexdigest()
        cached = self.cache.get(key)
        if cached is not None:
            return [FetchedPage.from_json(d) for d in cached]
        resp = self._eutils("esearch.fcgi", source, {
            "db": "pubmed", "term": f"({query}) AND {BOOKS_FILTER}", "retmax": source.max_results,
            "sort": "relevance", "retmode": "json"})
        try:
            found = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ReferenceFetchError("http", "esearch returned invalid JSON") from exc
        if found.get("error") or (found.get("esearchresult") or {}).get("ERROR"):
            raise ReferenceFetchError("http", f"esearch error: {found.get('error') or found['esearchresult']['ERROR']}"[:200])
        ids = [str(i) for i in (found.get("esearchresult") or {}).get("idlist", []) if str(i).isdigit()]
        pages: list[FetchedPage] = []
        if ids:
            xml = self._eutils("efetch.fcgi", source, {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
            by_pmid = {c.pmid: c for c in parse_book_chapters(xml.text)}
            now = self.fetcher.now()
            for pmid in ids:
                ch = by_pmid.get(pmid)
                if ch is None:
                    continue
                pages.append(FetchedPage(url=BOOKS_PAGE.format(accession=ch.accession), title=ch.citation_title,
                                         text=ch.text, sha256=text_sha256(ch.text), retrieved_at=now))
        self.cache.set(key, [p.to_json() for p in pages], ttl=self.config.cache_ttl_seconds)
        return pages

    # ---------------------------------------------------------------- stored pages

    def _stored_page(self, page: CataloguePage, result: "ReferenceResult") -> Optional[FetchedPage]:
        """The current stored version of a page whose publisher blocks scripted
        requests. No request is made. Missing or mismatched snapshots are errors;
        an old one is still cited but reported as stale."""
        version = self.stored.current(page.id)
        if version is None:
            result.errors.append(f"{page.id}: no stored snapshot; run scripts/refresh_reference_snapshots.py")
            return None
        if version.url != page.url:
            result.errors.append(f"{page.id}: stored snapshot is of {version.url}, not the catalogue URL; refresh it")
            return None
        age = version.age_days(self._now())
        if age > self.config.stored_snapshot_max_age_days:
            result.errors.append(f"{page.id}: stored snapshot {version.sha256[:12]} is stale "
                                 f"({int(age)} days old); cited anyway, refresh it")
        return version.page()

    # ---------------------------------------------------------------- search

    def search(self, claim_text: str) -> ReferenceResult:
        result = ReferenceResult(records=[])
        seen: set[str] = set()

        def add(rec: Optional[EvidenceRecord]) -> str:
            if rec is None:
                return "no_passage"
            if rec.evidence_id not in seen:
                seen.add(rec.evidence_id)
                result.records.append(rec)
            return "passage"

        def consulted(source_id: str, item: str, mode: str, outcome: str, url: Optional[str] = None) -> None:
            result.consulted.append(ConsultedItem(source_id, item, mode, outcome, url))

        for page, _hits in match_catalogue(claim_text, self.config)[: self.config.max_pages_per_claim]:
            source = self.config.source(page.source)
            assert source is not None  # checked when the config loaded
            result.candidates.append(page.id)
            if self.config.retrieval(page) == "stored":
                try:
                    stored = self._stored_page(page, result)
                except Exception as exc:  # noqa: BLE001 - a broken archive entry must not stop the others
                    result.errors.append(f"{page.id}: {type(exc).__name__}: {exc}"[:300])
                    consulted(source.id, page.id, "stored", "error", page.url)
                    continue
                if stored is None:
                    consulted(source.id, page.id, "stored", "error", page.url)
                    continue
                self.snapshots.save(stored)
                result.stored_pages += 1
                outcome = add(self._record(claim_text, stored, source, f"stored:{page.id}@{stored.sha256[:12]}"))
                consulted(source.id, page.id, "stored", outcome, page.url)
                continue
            try:
                fetched = self._page(page.url, source, title=page.title)
            except Exception as exc:  # noqa: BLE001 - one dead page must not stop the others
                result.errors.append(f"{page.id}: {type(exc).__name__}: {exc}"[:300])
                consulted(source.id, page.id, "live", "error", page.url)
                continue
            result.pages_fetched += 1
            outcome = add(self._record(claim_text, fetched, source, f"catalogue:{page.id}"))
            consulted(source.id, page.id, "live", outcome, page.url)

        query = bookshelf_query(claim_text)
        for source in (s for s in self.config.sources if s.backend == "bookshelf"):
            try:
                chapters = self.bookshelf_chapters(query, source)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{source.id} search: {type(exc).__name__}: {exc}"[:300])
                consulted(source.id, "search", "search", "error")
                continue
            if not chapters:
                consulted(source.id, "search", "search", "no_results" if query else "skipped")
            for chapter in chapters:
                accession = chapter.url.rstrip("/").rsplit("/", 1)[-1]
                result.candidates.append(accession)
                self.snapshots.save(chapter)
                result.pages_fetched += 1
                outcome = add(self._record(claim_text, chapter, source, f"bookshelf:{query}"))
                consulted(source.id, accession, "live", outcome, chapter.url)

        result.records = result.records[: self.config.max_records_per_claim]
        return result
