"""Search the authoritative references for one fact-of-record claim (§6 "Trusted sources
beyond PubMed").

Two backends, both limited to the allow-list in ``config/reference_sources.yaml``:

- **catalogue**: a fixed list of pages per source (CDC and WHO schedules, FDA/EMA/EFSA
  limits, WHO/CDC/NHS/ECDC fact sheets, USDA FoodData). A page is a candidate when its
  keyword phrases appear in the claim; the best matches are fetched.
- **bookshelf**: NCBI Bookshelf (e.g. StatPearls) through the same E-utilities API as
  PubMed: ESearch and ESummary on ``db=books``, then the book page itself on
  ``www.ncbi.nlm.nih.gov/books/``.

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
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.retrieval.cache import InMemoryQueryCache, QueryCache
from app.core.retrieval.planning import content_words, normalize_claim
from app.core.retrieval.references.config import CataloguePage, ReferenceConfig, ReferenceSource
from app.core.retrieval.references.fetcher import FetchedPage, ReferenceFetcher, ReferenceFetchError
from app.core.retrieval.references.passages import best_passage
from app.core.retrieval.references.snapshots import InMemorySnapshotStore, SnapshotStore
from app.core.retrieval.schemas import EvidenceRecord

REFERENCE_PUBLICATION_TYPE = "Authoritative Reference"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BOOKS_PAGE = "https://www.ncbi.nlm.nih.gov/books/{accession}/"
_ACCESSION = re.compile(r"^NBK\d{1,9}$")
_REF_ID = re.compile(r"^ref_[0-9a-f]{16}$")


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


def bookshelf_query(claim_text: str) -> str:
    """Plain search terms from the claim's content words (no field tags, no URLs)."""
    words = content_words(normalize_claim(claim_text))
    return " ".join(w for w in words if re.fullmatch(r"[\w'+.%-]+", w))[:200]


@dataclass
class ReferenceResult:
    records: list[EvidenceRecord]
    errors: list[str] = field(default_factory=list)
    pages_fetched: int = 0
    candidates: list[str] = field(default_factory=list)  # page IDs / NBK accessions tried


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
    ) -> None:
        self.config = config
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

    def _eutils(self, endpoint: str, source: ReferenceSource, params: dict) -> dict:
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        resp = self.fetcher.get(f"{EUTILS}/{endpoint}", source,
                                params={"db": "books", "retmode": "json", "tool": "who_infodemic_monitor", **params})
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ReferenceFetchError("http", f"{endpoint} returned invalid JSON") from exc

    def bookshelf_accessions(self, query: str, source: ReferenceSource) -> list[tuple[str, str]]:
        """``[(accession, title)]`` for a Bookshelf search, in relevance order."""
        if not query:
            return []
        key = "ref_books:" + hashlib.sha256(f"{query}|{source.max_results}".encode()).hexdigest()
        cached = self.cache.get(key)
        if cached is not None:
            return [(a, t) for a, t in cached]
        found = self._eutils("esearch.fcgi", source,
                             {"term": query, "retmax": source.max_results, "sort": "relevance"})
        ids = [str(i) for i in (found.get("esearchresult") or {}).get("idlist", []) if str(i).isdigit()]
        out: list[tuple[str, str]] = []
        if ids:
            summary = self._eutils("esummary.fcgi", source, {"id": ",".join(ids)})
            result = summary.get("result") or {}
            for uid in ids:
                doc = result.get(uid) or {}
                acc = str(doc.get("chapteraccessionid") or doc.get("accessionid") or "")
                if not _ACCESSION.match(acc):
                    continue
                title = str(doc.get("title") or doc.get("booktitle") or "").strip()
                book = str(doc.get("booktitle") or "").strip()
                if book and book != title:
                    title = f"{title} ({book})" if title else book
                out.append((acc, title))
        self.cache.set(key, out, ttl=self.config.cache_ttl_seconds)
        return out

    # ---------------------------------------------------------------- search

    def search(self, claim_text: str) -> ReferenceResult:
        result = ReferenceResult(records=[])
        seen: set[str] = set()

        def add(rec: Optional[EvidenceRecord]) -> None:
            if rec is not None and rec.evidence_id not in seen:
                seen.add(rec.evidence_id)
                result.records.append(rec)

        for page, _hits in match_catalogue(claim_text, self.config)[: self.config.max_pages_per_claim]:
            source = self.config.source(page.source)
            assert source is not None  # checked when the config loaded
            result.candidates.append(page.id)
            try:
                fetched = self._page(page.url, source, title=page.title)
            except Exception as exc:  # noqa: BLE001 - one dead page must not stop the others
                result.errors.append(f"{page.id}: {type(exc).__name__}: {exc}"[:300])
                continue
            result.pages_fetched += 1
            add(self._record(claim_text, fetched, source, f"catalogue:{page.id}"))

        query = bookshelf_query(claim_text)
        for source in (s for s in self.config.sources if s.backend == "bookshelf"):
            try:
                hits = self.bookshelf_accessions(query, source)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{source.id} search: {type(exc).__name__}: {exc}"[:300])
                continue
            for acc, title in hits:
                result.candidates.append(acc)
                try:
                    fetched = self._page(BOOKS_PAGE.format(accession=acc), source, title=title)
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"{acc}: {type(exc).__name__}: {exc}"[:300])
                    continue
                result.pages_fetched += 1
                add(self._record(claim_text, fetched, source, f"bookshelf:{query}"))

        result.records = result.records[: self.config.max_records_per_claim]
        return result
