"""Real ``plan_retrieval``, ``retrieve_evidence`` (T03, #31) and ``rerank_evidence``
(T05, #32) nodes (§6).

Both are deterministic code over ``app.core.retrieval``; no model is called unless the
caller injects a search assistant into the planner (§6 step 3), and then only when the
rules find no concept in a claim.

- ``plan_retrieval`` (owns ``retrieval_queries``) appends exactly one query per claim
  per round: the critic's suggestion when it asked for more evidence (sanitised, §15),
  otherwise the next rung of the planner's narrow-to-broad ladder that hasn't run.
- ``retrieve_evidence`` (owns ``retrieved_evidence`` and ``retrieval_attempts``) runs
  each claim's newest query, merges the records into what the claim already has
  (PMID/DOI dedup) and counts the round. A PubMed failure is recorded in ``errors`` and
  still counts as a round, so a dead PubMed can't loop a claim forever.
- ``rerank_evidence`` (owns ``reranked_evidence``) re-scores every claim's full
  retrieved set from scratch each round (deterministic, so re-running is idempotent):
  relevance and study type, papers below the relevance threshold dropped, at most 10
  kept (``app.core.retrieval.rerank``). If scoring a claim fails, the error is recorded
  and that claim falls back to its first 10 papers in PubMed's order, unscored. With an
  offline library injected (T12), a claim left with no paper that clears the threshold
  falls back to the library (owns ``library_evidence`` too).
- Authoritative references (T17, §6 "Trusted sources beyond PubMed"): with a
  ``ReferenceSearcher`` injected, ``retrieve_evidence`` also searches the allow-listed
  references for every claim whose ``claim_kind`` is ``fact_of_record``, once, in the
  claim's first round, alongside PubMed (not as a fallback). The ``ref_<hash>`` records
  join the claim's ``retrieved_evidence``, so citation checks, the judge and
  persistence treat them like papers. ``rerank_evidence`` passes the claim's kind to
  the reranker: references first for facts of record, studies first otherwise.
  Research questions never touch the references. A reference failure is recorded in
  ``errors`` and the claim goes on with PubMed.
- "How we searched" (T31): ``retrieve_evidence`` also owns ``search_trail``, one
  ``SearchRound`` per claim per round (the PubMed query run, hits, records after
  filters, whether it came from the cache, the references consulted, what the round
  added). It only observes: what is retrieved, merged and reranked is unchanged.

Use them by overriding the stubs:

    nodes = make_retrieval_nodes(retriever)
    graph = compile_graph(nodes, checkpointer=...)

The default graph keeps the stubs until the integration task (T11) wires these in.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from app.core.graph import routing as r
from app.core.graph.nodes import NodeFn
from app.core.graph.routing import Budgets, DEFAULT_BUDGETS
from app.core.graph.state import NodeError, PipelineState, ReferenceConsulted, SearchRound
from app.core.retrieval.library.fallback import LibraryFallback, merge_library_evidence, should_fire
from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.pubmed import PubMedClient
from app.core.retrieval.references.search import ReferenceSearcher
from app.core.retrieval.rerank import MAX_EVIDENCE_PER_CLAIM, Reranker
from app.core.retrieval.retriever import EvidenceRetriever, merge_evidence


def make_retrieval_nodes(
    retriever: EvidenceRetriever,
    planner: Optional[QueryPlanner] = None,
    budgets: Budgets = DEFAULT_BUDGETS,
    reranker: Optional[Reranker] = None,
    library: Optional[LibraryFallback] = None,
    references: Optional[ReferenceSearcher] = None,
) -> dict[str, NodeFn]:
    planner = planner or QueryPlanner()

    def plan_retrieval(state: PipelineState) -> dict:
        queries = {cid: list(qs) for cid, qs in state.get("retrieval_queries", {}).items()}
        claims = {c.claim_id: c for c in state.get("claims", [])}
        critic = state.get("critic_results", {})
        for cid in r.claims_to_retrieve(state, budgets):
            already = queries.get(cid, [])
            suggestions = ()
            c = critic.get(cid)
            if c is not None and c.decision.value == "RETRIEVE_MORE":
                suggestions = tuple(c.suggested_queries)
            q = planner.next_query(claims[cid].claim_text, already, suggestions)
            if q is None:
                # Every candidate has run: repeat the broadest one. It is served from
                # the cache, and the round still counts toward the budget.
                q = already[-1] if already else claims[cid].claim_text
            queries[cid] = [*already, q]
        return {"retrieval_queries": queries}

    def consulted_view(item) -> ReferenceConsulted:
        config = getattr(references, "config", None)
        source = config.source(item.source_id) if config is not None else None
        site = urlsplit(item.url).hostname if item.url else None
        if site is None and source is not None and source.allowed_hosts:
            site = source.allowed_hosts[0]
        return ReferenceConsulted(
            source_id=item.source_id, source_name=source.name if source else item.source_id,
            publisher=source.publisher if source else "", site=site, item=item.item,
            mode=item.mode, outcome=item.outcome, url=item.url)

    def retrieve_evidence(state: PipelineState) -> dict:
        evidence = {cid: list(recs) for cid, recs in state.get("retrieved_evidence", {}).items()}
        attempts = dict(state.get("retrieval_attempts", {}))
        trail = {cid: list(rounds) for cid, rounds in state.get("search_trail", {}).items()}
        errors: list[NodeError] = []
        claims = {c.claim_id: c for c in state.get("claims", [])}
        for cid in r.claims_to_retrieve(state, budgets):
            planned = state.get("retrieval_queries", {}).get(cid, [])
            first_round = attempts.get(cid, 0) == 0
            attempts[cid] = attempts.get(cid, 0) + 1
            evidence.setdefault(cid, [])
            before = len(evidence[cid])
            step: dict = {"round": attempts[cid]}
            claim = claims.get(cid)
            if (references is not None and first_round and claim is not None
                    and claim.claim_kind == "fact_of_record"):
                try:
                    found = references.search(claim.claim_text)
                except Exception as exc:  # noqa: BLE001 - recorded in state, not raised
                    errors.append(NodeError(
                        node=r.RETRIEVE_EVIDENCE, claim_id=cid, retryable=True,
                        message=f"reference search failed: {type(exc).__name__}: {exc}"[:500],
                    ))
                    step["reference_error"] = type(exc).__name__
                else:
                    evidence[cid] = merge_evidence(evidence[cid], found.records)
                    errors += [
                        NodeError(node=r.RETRIEVE_EVIDENCE, claim_id=cid,
                                  message=f"reference source degraded: {e}"[:500])
                        for e in found.errors
                    ]
                    try:  # the trail only observes: never let it fail the round
                        step["references"] = [consulted_view(i) for i in getattr(found, "consulted", [])]
                    except Exception:  # noqa: BLE001
                        step["references"] = []
                    step["reference_passages"] = len(found.records)
            if not planned:
                errors.append(NodeError(node=r.RETRIEVE_EVIDENCE, claim_id=cid, message="no query planned"))
                trail.setdefault(cid, []).append(SearchRound(**step, new_records=len(evidence[cid]) - before))
                continue
            query = planned[-1]
            step["pubmed_query"] = query
            try:
                result = retriever.retrieve(query)
            except Exception as exc:  # noqa: BLE001 - recorded in state, not raised
                errors.append(
                    NodeError(
                        node=r.RETRIEVE_EVIDENCE, claim_id=cid, retryable=True,
                        message=f"PubMed retrieval failed for query {query!r}: {type(exc).__name__}: {exc}"[:500],
                    )
                )
                step["pubmed_error"] = type(exc).__name__
                trail.setdefault(cid, []).append(SearchRound(**step, new_records=len(evidence[cid]) - before))
                continue
            evidence[cid] = merge_evidence(evidence[cid], result.records)
            requests = getattr(result, "network_requests", None)
            trail.setdefault(cid, []).append(SearchRound(
                **step, pubmed_hits=int(getattr(result, "pmids_found", len(result.records))),
                pubmed_records=len(result.records),
                from_cache=(requests == 0) if isinstance(requests, int) else None,
                new_records=len(evidence[cid]) - before,
            ))
        update: dict = {"retrieved_evidence": evidence, "retrieval_attempts": attempts,
                        "search_trail": trail}
        if errors:
            update["errors"] = errors
        return update

    return {
        r.PLAN_RETRIEVAL: plan_retrieval,
        r.RETRIEVE_EVIDENCE: retrieve_evidence,
        **make_rerank_node(reranker, library),
    }


def make_rerank_node(
    reranker: Optional[Reranker] = None,
    library: Optional[LibraryFallback] = None,
) -> dict[str, NodeFn]:
    """The real ``rerank_evidence`` node on its own, for graphs that keep other stubs.

    With ``library`` (T12), a claim whose PubMed papers all fall below the relevance
    threshold, or that has none, falls back to the offline library (§6 "When it runs"):
    library passages go through the same reranker and cap, and everything the library
    returned is kept in ``library_evidence`` so citations to it can be checked. Without
    ``library`` the node behaves exactly as before.
    """
    reranker = reranker or Reranker()
    if library is not None and library.reranker is not reranker:
        library = LibraryFallback(library.searcher, reranker, library.candidates)

    def rerank_evidence(state: PipelineState) -> dict:
        claims = {c.claim_id: c for c in state.get("claims", [])}
        reranked = {}
        library_evidence = {cid: list(recs) for cid, recs in state.get("library_evidence", {}).items()}
        errors: list[NodeError] = []
        for cid, records in state.get("retrieved_evidence", {}).items():
            claim = claims.get(cid)
            if claim is None:
                continue
            try:
                reranked[cid] = reranker.rerank(claim.claim_text, records, claim.claim_kind).kept
            except Exception as exc:  # noqa: BLE001 - recorded in state, not raised
                errors.append(
                    NodeError(
                        node=r.RERANK_EVIDENCE, claim_id=cid,
                        message=f"reranking failed, kept PubMed order: {type(exc).__name__}: {exc}"[:500],
                    )
                )
                reranked[cid] = list(records)[:MAX_EVIDENCE_PER_CLAIM]
            if library is None or not should_fire(reranked[cid]):
                continue
            try:
                outcome = library.run(claim.claim_text, reranked[cid])
            except Exception as exc:  # noqa: BLE001 - the claim goes on with what PubMed gave
                errors.append(
                    NodeError(
                        node=r.RERANK_EVIDENCE, claim_id=cid,
                        message=f"library fallback failed: {type(exc).__name__}: {exc}"[:500],
                    )
                )
                library_evidence.setdefault(cid, [])
                continue
            library_evidence[cid] = merge_library_evidence(library_evidence.get(cid, []), outcome.candidates)
            reranked[cid] = outcome.kept
            errors += [
                NodeError(node=r.RERANK_EVIDENCE, claim_id=cid, message=f"library search degraded: {e}"[:500])
                for e in outcome.errors
            ]
        update: dict = {"reranked_evidence": reranked}
        if library is not None:
            update["library_evidence"] = library_evidence
        if errors:
            update["errors"] = errors
        return update

    return {r.RERANK_EVIDENCE: rerank_evidence}


def retriever_from_settings(cache=None) -> EvidenceRetriever:
    """A retriever configured from app settings (NCBI key and contact email are
    optional; the key raises the rate limit from 3 to 10 requests a second)."""
    from app.core.config import settings

    client = PubMedClient(api_key=settings.NCBI_API_KEY, email=settings.NCBI_EMAIL)
    return EvidenceRetriever(client, cache, max_results=settings.RETRIEVAL_MAX_RESULTS_PER_QUERY)
