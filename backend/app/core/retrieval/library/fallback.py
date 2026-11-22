"""When the library runs (§6 "When it runs").

The library is a fallback, not a parallel search. It runs for a claim only when PubMed
came up short:

- PubMed returned nothing after the full budget (the initial search plus 2 broader
  reformulations; the graph only reaches reranking with an empty set once that budget is
  spent, or PubMed kept failing), **or**
- no PubMed paper cleared the reranker's relevance threshold. Forty off-topic papers are
  the same failure as none.

Both cases are "the reranker kept nothing". Library passages then go through the same
reranker (relevance and study-type scoring, same threshold) and count toward the same cap
of 10 per claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.core.retrieval.library.search import LibrarySearcher, library_query
from app.core.retrieval.rerank import MAX_EVIDENCE_PER_CLAIM, Reranker, RerankConfig
from app.core.retrieval.schemas import EvidenceRecord


def merge_library_evidence(existing: Sequence[EvidenceRecord], new: Sequence[EvidenceRecord]) -> list[EvidenceRecord]:
    """``existing`` then the new passages, deduplicated by evidence ID only. (PubMed's
    DOI dedup would wrongly merge two pages of one document, which share a DOI.)"""
    out = {r.evidence_id: r for r in existing}
    for r in new:
        out.setdefault(r.evidence_id, r)
    return list(out.values())


def should_fire(pubmed_kept: Sequence[EvidenceRecord]) -> bool:
    return not any(r.source == "pubmed" for r in pubmed_kept)


@dataclass
class FallbackOutcome:
    fired: bool
    query: str = ""
    candidates: list[EvidenceRecord] = field(default_factory=list)  # everything the library returned
    kept: list[EvidenceRecord] = field(default_factory=list)  # PubMed kept + library kept, ≤ 10
    errors: list[str] = field(default_factory=list)


class LibraryFallback:
    def __init__(self, searcher: LibrarySearcher, reranker: Optional[Reranker] = None,
                 candidates: int = MAX_EVIDENCE_PER_CLAIM) -> None:
        self.searcher = searcher
        self.reranker = reranker or Reranker()
        self.candidates = candidates

    def run(self, claim_text: str, pubmed_kept: Sequence[EvidenceRecord]) -> FallbackOutcome:
        if not should_fire(pubmed_kept):
            return FallbackOutcome(fired=False, kept=list(pubmed_kept))
        query = library_query(claim_text)
        result = self.searcher.search(query, self.candidates)
        room = MAX_EVIDENCE_PER_CLAIM - len(pubmed_kept)
        cfg = self.reranker.config
        capped = Reranker(
            RerankConfig(max_results=max(0, min(room, cfg.max_results)), min_relevance=cfg.min_relevance,
                         relevance_weight=cfg.relevance_weight, quality_weight=cfg.quality_weight),
            self.reranker.relevance_model,
        )
        kept = capped.rerank(claim_text, result.records).kept if result.records else []
        return FallbackOutcome(True, result.query, result.records, [*pubmed_kept, *kept], list(result.errors))
