"""Searching the library (§6 "Searching it").

**Hybrid search:** vector similarity (the query encoder against chunk embeddings made
with the same model and version) plus Postgres full-text search, merged with reciprocal
rank fusion (RRF, ``score = Σ 1 / (k + rank)``, k = 60). Embeddings match meaning;
full-text catches exact drug names and doses that embeddings can blur.

**The query** comes from the same population, intervention and outcome fields the PubMed
planner uses (``planning.frame_claim``), written as plain words instead of MeSH syntax.

**Evidence records:** one per document page. The ``evidence_id`` is built by code as
``lib_<document_id>_p<page>``, the ``abstract`` is the matched chunk, and ``source_url``
the internal viewer link that highlights the passage. When several chunks of one page
match, the best one stands for the page. ``relevance_score`` is left empty: the same
reranker that scores PubMed papers sets it.

Library text is untrusted, like abstracts and transcripts (§15).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.core.retrieval.library.config import LibraryConfig
from app.core.retrieval.library.embeddings import Embedder
from app.core.retrieval.library.store import ChunkHit, LibraryStore
from app.core.retrieval.planning import frame_claim, sanitize_query
from app.core.retrieval.schemas import EvidenceRecord

log = logging.getLogger(__name__)

_EVIDENCE_ID = re.compile(r"^lib_([A-Za-z0-9]+)_p(\d+)$")


def library_evidence_id(document_id: str, page: int) -> str:
    return f"lib_{document_id}_p{page}"


def parse_library_evidence_id(evidence_id: str) -> Optional[tuple[str, int]]:
    m = _EVIDENCE_ID.match(evidence_id or "")
    return (m.group(1), int(m.group(2))) if m else None


def library_query(claim_text: str) -> str:
    """Plain-language query from the claim's intervention, outcome and population."""
    frame = frame_claim(claim_text)
    words: list[str] = []

    def add(term: str) -> None:
        t = re.sub(r"\s+", " ", (term or "").lower()).strip()
        t = re.sub(r"^(?:the|a|an) ", "", t)
        if t and t not in words:
            words.append(t)

    for concept in (*frame.intervention, *frame.outcome, *frame.population):
        add(concept.matched_text)
        add(concept.label)
        for s in concept.synonyms[:2]:
            add(s)
    if not frame.has_concepts:
        return sanitize_query(frame.normalized_text)
    # Words the lexicon didn't cover ("lemon water cures cancer" -> "water") still help
    # full-text search.
    covered = " ".join(words)
    for kw in frame.keywords:
        if kw not in covered:
            add(kw)
    return sanitize_query(" ".join(words))


@dataclass(frozen=True)
class LibraryHit:
    record: EvidenceRecord
    chunk_id: str
    rrf_score: float
    vector_rank: Optional[int] = None  # 1-based; None = not in that list
    text_rank: Optional[int] = None


@dataclass
class LibrarySearchResult:
    query: str
    hits: list[LibraryHit] = field(default_factory=list)
    methods: tuple[str, ...] = ()
    errors: list[str] = field(default_factory=list)

    @property
    def records(self) -> list[EvidenceRecord]:
        return [h.record for h in self.hits]


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


class LibrarySearcher:
    def __init__(self, store: LibraryStore, embedder: Embedder, config: LibraryConfig = LibraryConfig()) -> None:
        self.store = store
        self.embedder = embedder
        self.config = config

    def to_evidence(self, hit: ChunkHit, query: str) -> EvidenceRecord:
        d, c = hit.document, hit.chunk
        return EvidenceRecord(
            evidence_id=library_evidence_id(d.document_id, c.page),
            source="library",
            document_id=d.document_id,
            page=c.page,
            title=d.title,
            abstract=c.text,
            doi=d.doi,
            publication_year=d.year,
            publication_type=[d.study_type] if d.study_type else ["Unknown"],
            source_url=self.config.viewer_url.format(document_id=d.document_id, page=c.page, chunk_id=c.chunk_id),
            query=query,
        )

    def search(self, query: str, k: Optional[int] = None) -> LibrarySearchResult:
        s = self.config.search
        k = max(1, min(k or s.default_k, s.max_k))
        q = sanitize_query(query)
        result = LibrarySearchResult(query=q)
        if not q:
            return result
        n = s.candidates_per_method
        vector_hits: list[ChunkHit] = []
        text_hits: list[ChunkHit] = []
        methods = []
        try:
            vec = self.embedder.embed_query(q)
            vector_hits = self.store.vector_search(
                vec, model=self.embedder.model_name, version=self.embedder.model_version, n=n)
            methods.append("vector")
        except Exception as exc:  # noqa: BLE001 - full-text alone still works
            log.warning("library vector search failed: %s", exc)
            result.errors.append(f"vector search failed: {type(exc).__name__}: {exc}"[:300])
        try:
            text_hits = self.store.text_search(q, n=n)
            methods.append("full_text")
        except Exception as exc:  # noqa: BLE001
            log.warning("library full-text search failed: %s", exc)
            result.errors.append(f"full-text search failed: {type(exc).__name__}: {exc}"[:300])
        result.methods = tuple(methods)
        if not methods:
            raise RuntimeError("; ".join(result.errors))

        by_id = {h.chunk.chunk_id: h for h in (*vector_hits, *text_hits)}
        vrank = {h.chunk.chunk_id: i for i, h in enumerate(vector_hits, start=1)}
        trank = {h.chunk.chunk_id: i for i, h in enumerate(text_hits, start=1)}
        fused = reciprocal_rank_fusion(
            [[h.chunk.chunk_id for h in vector_hits], [h.chunk.chunk_id for h in text_hits]], s.rrf_k)
        order = sorted(fused, key=lambda cid: (-fused[cid], cid))
        seen_pages: set[str] = set()
        for cid in order:
            hit = by_id[cid]
            ev_id = library_evidence_id(hit.document.document_id, hit.chunk.page)
            if ev_id in seen_pages:
                continue  # the page's best chunk already stands for it
            seen_pages.add(ev_id)
            result.hits.append(LibraryHit(self.to_evidence(hit, q), cid, round(fused[cid], 6),
                                          vrank.get(cid), trank.get(cid)))
            if len(result.hits) >= k:
                break
        return result


def search_library(query: str, k: int = 10, *, searcher: LibrarySearcher) -> list[EvidenceRecord]:
    """Functional form for the MCP tool (§6 table): ``search_library(query, k)``."""
    return searcher.search(query, k).records
