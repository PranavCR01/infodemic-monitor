"""Build the "How we searched" record for one claim from the graph state (T31).

Pure code over state the retrieval nodes already wrote (``search_trail``,
``retrieval_queries``, ``retrieved_evidence``, ``library_evidence``,
``reranked_evidence``, ``retrieval_attempts``). It reads, never writes, so it cannot
change retrieval results or verdicts. The shape is ``SearchTrailView``
(``app.core.schemas.search_trail``); see that module for what each count means.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.retrieval.rerank import MAX_EVIDENCE_PER_CLAIM
from app.core.schemas.search_trail import (
    MAX_SCREENED_OUT,
    FindStudyView,
    LibrarySearchView,
    PlanningView,
    ScreenedOutView,
    PubMedQueryView,
    ReferenceItemView,
    ReferenceSourceView,
    SearchBudgetView,
    SearchCountsView,
    SearchTrailView,
)

MAX_QUERY_CHARS = 500


def _references(rounds: list) -> list[ReferenceSourceView]:
    by_source: dict[str, ReferenceSourceView] = {}
    for rnd in rounds:
        for ref in getattr(rnd, "references", None) or []:
            view = by_source.get(ref.source_id)
            if view is None:
                view = by_source[ref.source_id] = ReferenceSourceView(
                    source_id=ref.source_id, name=ref.source_name, publisher=ref.publisher)
            if ref.site and ref.site not in view.sites:
                view.sites.append(ref.site)
            view.items.append(ReferenceItemView(item=ref.item, url=ref.url, mode=ref.mode, outcome=ref.outcome))
            if ref.outcome == "passage":
                view.passages += 1
    return list(by_source.values())


def build_search_trail(state: dict, claim_id: str, budgets: Budgets = DEFAULT_BUDGETS) -> Optional[dict]:
    """The claim's search trail as JSON, or ``None`` when the claim was never searched
    (e.g. ``requires_verification`` false, or a stub run with no retrieval)."""
    rounds = list((state.get("search_trail") or {}).get(claim_id, []))
    queries = list((state.get("retrieval_queries") or {}).get(claim_id, []))
    attempts = int((state.get("retrieval_attempts") or {}).get(claim_id, 0))
    retrieved_set = (state.get("retrieved_evidence") or {}).get(claim_id)
    if not rounds and not queries and not attempts and retrieved_set is None:
        return None

    library_state = state.get("library_evidence")
    library: Optional[LibrarySearchView] = None
    library_records: list[Any] = []
    if library_state is not None:  # the offline library was configured for this run
        if claim_id in library_state:
            library_records = list(library_state[claim_id])
            library = LibrarySearchView(fired=True, passages=len(library_records))
        else:
            library = LibrarySearchView(fired=False)

    pubmed: list[PubMedQueryView] = []
    seen_queries: set[str] = set()
    retrieved: Optional[int]
    if rounds:
        retrieved = 0
        for rnd in rounds:
            if rnd.pubmed_query is not None:
                repeat = rnd.pubmed_query in seen_queries
                seen_queries.add(rnd.pubmed_query)
                pubmed.append(PubMedQueryView(
                    round=rnd.round, query=rnd.pubmed_query[:MAX_QUERY_CHARS], results=rnd.pubmed_hits,
                    after_filters=rnd.pubmed_records, new_records=rnd.new_records, from_cache=rnd.from_cache,
                    failed=rnd.pubmed_error is not None, error_type=rnd.pubmed_error, repeat=repeat,
                    kind=getattr(rnd, "query_kind", None)))
                if not repeat:
                    retrieved += int(rnd.pubmed_hits or 0)
            retrieved += int(rnd.reference_passages or 0)
        retrieved += len(library_records)
        recorded = "graph"
    else:
        # No per-round record (a checkpoint from before T31): the planned queries are
        # known, what each returned is not.
        for i, q in enumerate(queries[:attempts] if attempts else queries, start=1):
            pubmed.append(PubMedQueryView(round=i, query=q[:MAX_QUERY_CHARS], repeat=q in seen_queries))
            seen_queries.add(q)
        retrieved = None
        recorded = "queries_only"

    found_records = list((state.get("found_study_evidence") or {}).get(claim_id, []))
    screened = len(retrieved_set or []) + len(library_records)
    kept_records = list((state.get("reranked_evidence") or {}).get(claim_id, []))
    kept = len(kept_records)
    rounds_used = attempts or len(rounds)
    kept_ids = {e.evidence_id for e in kept_records}
    kept_pmids = {e.pmid for e in kept_records if getattr(e, "pmid", None)}
    screened_out: list[ScreenedOutView] = []
    seen_out: set[str] = set()
    for rec in [*(retrieved_set or []), *library_records, *found_records]:
        if rec.evidence_id in kept_ids or rec.evidence_id in seen_out or (rec.pmid and rec.pmid in kept_pmids):
            continue
        seen_out.add(rec.evidence_id)
        screened_out.append(ScreenedOutView(evidence_id=rec.evidence_id, pmid=rec.pmid, title=(rec.title or "")[:300],
                                            year=rec.publication_year, source=rec.source))
    planning = None
    plan = next((rnd.plan for rnd in rounds if getattr(rnd, "plan", None)), None)
    if plan:
        planning = PlanningView(**{k: plan.get(k) for k in PlanningView.model_fields if plan.get(k) is not None})
    study = (state.get("find_study_trail") or {}).get(claim_id)
    find_study = FindStudyView.model_validate(study.model_dump()) if study is not None else None
    trail = SearchTrailView(
        recorded=recorded,
        pubmed_queries=pubmed,
        references=_references(rounds),
        library=library,
        counts=SearchCountsView(retrieved=retrieved, screened=screened, kept=kept),
        budget=SearchBudgetView(
            rounds_used=rounds_used, rounds_max=budgets.max_retrieval_attempts,
            exhausted=rounds_used >= budgets.max_retrieval_attempts, evidence_cap=MAX_EVIDENCE_PER_CLAIM,
            ladder_exhausted=any(getattr(rnd, "ladder_exhausted", False) for rnd in rounds)),
        planning=planning,
        find_study=find_study,
        screened_out=screened_out[:MAX_SCREENED_OUT],
        screened_out_truncated=len(screened_out) > MAX_SCREENED_OUT,
    )
    return trail.model_dump(mode="json")
