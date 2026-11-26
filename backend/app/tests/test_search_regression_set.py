"""D8 regression set (T50): real production search misses, replayed offline.

Each case runs the real ``plan_retrieval`` / ``retrieve_evidence`` / ``rerank_evidence``
nodes over recorded E-utilities answers (``fixtures/pubmed_regression``) for the full
search budget and checks what the claims keep. A planner change that makes a query
leave its fixture shows up as an unknown query, and is re-recorded deliberately.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.graph import routing as r
from app.core.graph.retrieval_nodes import make_retrieval_nodes
from app.core.graph.state import GraphClaim
from app.core.retrieval.retriever import EvidenceRetriever
from app.tests.pubmed_fixtures import RecordedPubMed
from app.tests.vitamin_k_fixture import claims_as_job, load_real

FIX = Path(__file__).parent / "fixtures"
VITK_DIR = FIX / "pubmed_regression" / "vitamin_k_5cc07f48"
VITK_JOB = {"claims": claims_as_job(load_real())}  # the real production rows
EXPECTED_VITK = ("c1", "c3", "c4", "c5", "c6", "c7", "c9", "c12")  # coordinator review of #124
_VITK = re.compile(r"vitamin[\s-]*k(?![a-z])|phytonadione|phylloquinone|vkdb", re.I)


def _run_job(job: dict, root: Path):
    server = RecordedPubMed(root)
    nodes = make_retrieval_nodes(EvidenceRetriever(server.client()))
    claims = [GraphClaim(claim_id=c["claim_id"], claim_text=c["text"], claim_category=c["category"],
                         claim_kind=c["claim_kind"], source_segment_ids=["s1"], start_seconds=c["start_seconds"],
                         end_seconds=c["end_seconds"]) for c in job["claims"]]
    state: dict = {"claims": claims}
    for _ in range(3):  # the full budget, as if the critic asked for more every round
        state.update(nodes[r.PLAN_RETRIEVAL](state))
        state.update(nodes[r.RETRIEVE_EVIDENCE](state))
        state.update(nodes[r.RERANK_EVIDENCE](state))
        state["critic_results"] = {}
        for cid in [c.claim_id for c in claims]:
            if state["retrieval_attempts"].get(cid, 0) < 3:
                from app.core.graph.state import CriticDecision, CriticResult

                state["critic_results"][cid] = CriticResult(claim_id=cid, decision=CriticDecision.RETRIEVE_MORE)
    return state, server


@pytest.fixture(scope="module")
def vitk():
    return _run_job(VITK_JOB, VITK_DIR)


def test_every_query_has_a_recorded_answer(vitk):
    _, server = vitk
    assert server.unknown_queries == [], "planner changed: re-record with t50_vitamin_k_regression.py"


@pytest.mark.parametrize("cid", EXPECTED_VITK)
def test_vitamin_k_job_claims_keep_vitamin_k_papers(vitk, cid):
    state, _ = vitk
    kept = state["reranked_evidence"][cid]
    assert any(_VITK.search(f"{e.title} {e.abstract}") for e in kept), cid


def test_vitamin_k_job_never_searches_bare_vitamin_and_never_repeats(vitk):
    state, _ = vitk
    for cid, rounds in state["search_trail"].items():
        queries = [x.pubmed_query for x in rounds if x.pubmed_query]
        assert len(queries) == len(set(queries)), cid
        for q in queries:
            assert q.strip().lower() not in ("vitamin", "vitamin osteoporosis")
            # every "vitamin" in a query is "vitamin k" (T50 a: never shrunk to "vitamin")
            assert re.findall(r"vitamins?\b(?! k\b)", q.lower()) == [], (cid, q)


def test_c11_keeps_vitamin_k_papers_not_the_vitamin_d_ones_production_kept(vitk):
    """The production miss: c11 kept vitamin D / falls / osteoporosis papers. Now its
    search returns vitamin K papers only; the reranker keeps none of them, because the
    claim names no outcome they could test ("a potentially devastating condition"), so
    nothing off topic reaches the verifier (find-the-study would run next)."""
    state, _ = vitk
    retrieved = state["retrieved_evidence"]["c11"]
    assert retrieved and all(_VITK.search(f"{e.title} {e.abstract}") or "anticoagulant" in e.title.lower()
                             for e in retrieved)
    kept = state["reranked_evidence"]["c11"]
    prod = {f"ev_{e['pmid']}" for c in load_real()["claims"] if c["claim_id"] == "c11" for e in c["evidence"]}
    assert not prod & {e.evidence_id for e in kept}


def test_c2_named_study_gets_a_citation_lookup_in_jama(vitk):
    state, _ = vitk
    first = state["search_trail"]["c2"][0]
    assert first.query_kind == "citation" and first.pubmed_query.startswith('"JAMA"[ta] AND ')
