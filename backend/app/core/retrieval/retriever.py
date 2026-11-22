"""Search + fetch + filter + dedup → ``EvidenceRecord`` list (§6, issue #31).

``EvidenceRetriever.retrieve(query)`` runs one PubMed query end to end, through the
query cache. ``merge_evidence`` adds a round's records to what a claim already has,
deduplicating by PMID and by DOI (§6 "Deduplicate").

Every field of an ``EvidenceRecord`` comes from the PubMed response: ``evidence_id``
is ``ev_<pmid>`` and ``source_url`` the PubMed page of that PMID (§6 "Each evidence
record"). ``relevance_score`` is left empty: the reranker (T05) sets it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.core.retrieval.cache import (
    DEFAULT_TTL_SECONDS,
    EMPTY_RESULT_TTL_SECONDS,
    InMemoryQueryCache,
    QueryCache,
    record_key,
    search_key,
)
from app.core.retrieval.pubmed import PubMedArticle, PubMedClient
from app.core.retrieval.schemas import EvidenceRecord, SearchFilters

DEFAULT_MAX_RESULTS = 20  # per query; the reranker cuts to 10 per claim (§6 "Cap")


def pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def to_evidence(article: PubMedArticle, query: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=f"ev_{article.pmid}",
        source="pubmed",
        pmid=article.pmid,
        doi=article.doi,
        title=article.title,
        abstract=article.abstract,
        publication_year=article.publication_year,
        publication_type=list(article.publication_types),
        source_url=pubmed_url(article.pmid),
        query=query,
    )


def _dedup_keys(rec: EvidenceRecord) -> set[str]:
    keys = set()
    if rec.pmid:
        keys.add(f"pmid:{rec.pmid}")
    if rec.doi:
        keys.add(f"doi:{rec.doi.lower()}")
    keys.add(f"id:{rec.evidence_id}")
    return keys


def merge_evidence(
    existing: Iterable[EvidenceRecord], new: Iterable[EvidenceRecord]
) -> list[EvidenceRecord]:
    """``existing`` followed by the records of ``new`` not already present by PMID,
    DOI or evidence ID. The first copy wins, so a record keeps the query that first
    found it."""
    out: list[EvidenceRecord] = []
    seen: set[str] = set()
    for rec in [*existing, *new]:
        keys = _dedup_keys(rec)
        if keys & seen:
            continue
        seen |= keys
        out.append(rec)
    return out


@dataclass
class RetrievalResult:
    query: str
    records: list[EvidenceRecord]
    pmids_found: int = 0
    filtered_out: list[str] = field(default_factory=list)  # PMIDs dropped by type filters
    network_requests: int = 0


class EvidenceRetriever:
    """One PubMed query → evidence records, cached by query and by PMID."""

    def __init__(
        self,
        client: PubMedClient,
        cache: Optional[QueryCache] = None,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        filters: SearchFilters = SearchFilters(),
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.client = client
        self.cache: QueryCache = cache if cache is not None else InMemoryQueryCache()
        self.max_results = max_results
        self.filters = filters
        self.ttl = ttl

    def search(self, query: str) -> list[str]:
        key = search_key(query, self.max_results, self.filters.cache_key())
        cached = self.cache.get(key)
        if cached is not None:
            return [str(p) for p in cached]
        pmids = self.client.search(query, self.max_results, self.filters)
        self.cache.set(key, pmids, ttl=self.ttl if pmids else EMPTY_RESULT_TTL_SECONDS)
        return pmids

    def articles(self, pmids: list[str]) -> list[PubMedArticle]:
        found: dict[str, PubMedArticle] = {}
        missing: list[str] = []
        for pmid in pmids:
            cached = self.cache.get(record_key(pmid))
            if cached is not None:
                found[pmid] = PubMedArticle.from_json(cached)
            else:
                missing.append(pmid)
        if missing:
            for art in self.client.fetch(missing):
                self.cache.set(record_key(art.pmid), art.to_json(), ttl=self.ttl)
                found[art.pmid] = art
        return [found[p] for p in pmids if p in found]

    def retrieve(self, query: str) -> RetrievalResult:
        before = self.client.request_count
        pmids = self.search(query)
        kept: list[EvidenceRecord] = []
        dropped: list[str] = []
        excluded = {t.lower() for t in self.filters.exclude_types}
        for art in self.articles(pmids):
            if excluded & {t.lower() for t in art.publication_types}:
                dropped.append(art.pmid)
                continue
            if self.filters.min_year and art.publication_year and art.publication_year < self.filters.min_year:
                dropped.append(art.pmid)
                continue
            if self.filters.max_year and art.publication_year and art.publication_year > self.filters.max_year:
                dropped.append(art.pmid)
                continue
            kept.append(to_evidence(art, query))
        return RetrievalResult(
            query=query,
            records=merge_evidence([], kept),
            pmids_found=len(pmids),
            filtered_out=dropped,
            network_requests=self.client.request_count - before,
        )
