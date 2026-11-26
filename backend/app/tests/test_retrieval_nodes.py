"""plan_retrieval and retrieve_evidence in the graph (T03, issue #31, design §6).

The real retrieval nodes run inside the skeleton graph with the other nodes stubbed,
against recorded PubMed fixtures. No network, no models.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from collections import Counter

import pytest

from app.core.graph import routing as r
from app.core.graph.builder import compile_graph, run_config
from app.core.graph.checkpoint import memory_checkpointer
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.retrieval_nodes import make_retrieval_nodes
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    GraphClaim,
    assert_checkpoint_safe,
    initial_state,
)
from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.retriever import EvidenceRetriever
from app.tests.pubmed_fixtures import RecordedPubMed

P = QueryPlanner()
HOT_CLAIM = "Drinking hot water every morning cures the flu."
GARLIC_CLAIM = "Some people say garlic stops colds. That's a myth."
HOT = P.ladder(HOT_CLAIM)
GARLIC = P.ladder(GARLIC_CLAIM)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def claims_node(*texts):
    def extract_claims(state):
        return {"claims": [
            GraphClaim(claim_id=f"c{i}", claim_text=t, claim_category="treatment_efficacy",
                       source_segment_ids=["t1"], start_seconds=0.0, end_seconds=1.0)
            for i, t in enumerate(texts, start=1)
        ]}
    return extract_claims


def run(server, *, extra=None, job="job-t03", checkpointer=None):
    calls: Counter[str] = Counter()
    nodes = make_stub_nodes()
    nodes.update(make_retrieval_nodes(EvidenceRetriever(server.client())))
    nodes.update(extra or {})

    def counted(name, fn):
        def wrapped(state):
            calls[name] += 1
            return fn(state)
        return wrapped

    nodes = {k: counted(k, v) for k, v in nodes.items()}
    graph = compile_graph(nodes, checkpointer=checkpointer or memory_checkpointer())
    state = initial_state(job_id=job, video_id="vid-1", media_uri="videos/vid-1/video.mp4",
                          pipeline_version="t03-test")
    return graph, graph.invoke(state, run_config(job)), calls


def test_sample_video_retrieves_real_records_and_broadens_empty_search():
    server = RecordedPubMed()
    _, out, calls = run(server)  # the skeleton's sample video: hot water (c1), garlic (c2)
    assert server.unknown_queries == []
    # c1: the first query found nothing, so planning broadened once (§6).
    assert out["retrieval_queries"]["c1"] == HOT[:2]
    assert out["retrieval_attempts"]["c1"] == 2
    assert [e.evidence_id for e in out["retrieved_evidence"]["c1"]] == ["ev_99000101", "ev_99000102"]
    # c2: found on the first query; DOI duplicate and retracted paper removed.
    assert out["retrieval_queries"]["c2"] == GARLIC[:1]
    assert out["retrieval_attempts"]["c2"] == 1
    assert [e.pmid for e in out["retrieved_evidence"]["c2"]] == ["99000201", "99000204"]
    # Every ID and URL came from the fixtures (the PubMed response).
    for recs in out["retrieved_evidence"].values():
        for e in recs:
            assert e.evidence_id == f"ev_{e.pmid}"
            assert e.source_url == f"https://pubmed.ncbi.nlm.nih.gov/{e.pmid}/"
            assert e.abstract or e.pmid == "99000204"
    assert calls[r.PLAN_RETRIEVAL] == 2 and calls[r.RETRIEVE_EVIDENCE] == 2
    assert calls[r.RERANK_EVIDENCE] == 1
    assert out["errors"] == []
    assert out["persisted_result_ref"]


def test_claim_with_no_results_stops_at_the_budget():
    server = RecordedPubMed()
    _, out, calls = run(server, extra={r.EXTRACT_CLAIMS: claims_node("Bananas are amazing for your skin")})
    assert out["retrieval_attempts"]["c1"] == 3  # the budget is used up
    assert out["retrieved_evidence"]["c1"] == []
    # T50 d: two distinct keyword queries, then the ladder ran out: the search stopped
    # and said so instead of re-running a query from the cache.
    assert out["retrieval_queries"]["c1"] == ["bananas skin", "bananas"]
    assert server.calls["esearch"] == 2
    assert [x.ladder_exhausted for x in out["search_trail"]["c1"]] == [False, False, True]
    assert out["verification_results"]["c1"].verdict.value == "INSUFFICIENT_EVIDENCE"
    assert calls[r.RERANK_EVIDENCE] == 1


def test_critic_retrieve_more_uses_its_suggestion_and_dedups_across_rounds():
    server = RecordedPubMed()
    vax = P.ladder("Vaccines cause autism in children")
    seen = Counter()

    def critic(state):
        res = dict(state.get("critic_results", {}))
        for cid in r.claims_to_critique(state):
            seen[cid] += 1
            more = seen[cid] == 1
            res[cid] = CriticResult(
                claim_id=cid,
                decision=CriticDecision.RETRIEVE_MORE if more else CriticDecision.APPROVE,
                # Untrusted model text: the URL is stripped before it reaches PubMed.
                suggested_queries=[vax[1] + " https://evil.test/x"] if more else [],
            )
        return {"critic_results": res}

    _, out, _ = run(server, extra={
        r.EXTRACT_CLAIMS: claims_node("Vaccines cause autism in children"),
        r.CRITIQUE_VERIFICATION: critic,
    })
    assert server.unknown_queries == []
    assert out["retrieval_queries"]["c1"] == vax[:2]
    assert out["retrieval_attempts"]["c1"] == 2
    # 99000302 was found by both queries and appears once, with the first query.
    recs = out["retrieved_evidence"]["c1"]
    assert [e.pmid for e in recs] == ["99000302", "99000304", "99000301"]
    assert recs[0].query == vax[0]


def test_pubmed_outage_is_recorded_and_bounded():
    server = RecordedPubMed()
    server.fail_next = [503] * 100
    nodes = make_retrieval_nodes(EvidenceRetriever(server.client(max_attempts=2)))
    nodes[r.EXTRACT_CLAIMS] = claims_node(GARLIC_CLAIM)
    graph = compile_graph(nodes, checkpointer=memory_checkpointer())
    out = graph.invoke(
        initial_state(job_id="j", video_id="v", media_uri="m", pipeline_version="p"), run_config("j")
    )
    assert out["retrieval_attempts"]["c1"] == 3
    assert out["retrieved_evidence"]["c1"] == []
    errs = [e for e in out["errors"] if e.node == r.RETRIEVE_EVIDENCE]
    assert len(errs) == 3 and all(e.retryable and e.claim_id == "c1" for e in errs)
    assert server.calls["esearch"] == 6  # 3 rounds x 2 attempts, then the claim moves on
    assert out["persisted_result_ref"]


def test_no_verifiable_claims_means_no_pubmed_calls():
    server = RecordedPubMed()
    _, out, calls = run(server, extra={r.EXTRACT_CLAIMS: lambda s: {"claims": []}})
    assert server.requests == [] and calls[r.PLAN_RETRIEVAL] == 0
    assert out["final_result"].classification.value == "CANNOT_RECOGNIZE"


def test_checkpoints_are_small_and_resumable():
    server = RecordedPubMed()
    saver = memory_checkpointer()
    graph, out, _ = run(server, checkpointer=saver, job="job-ckpt")
    assert_checkpoint_safe(dict(out))
    for snap in graph.get_state_history(run_config("job-ckpt")):
        assert_checkpoint_safe(dict(snap.values))
    # Re-running the same job id with a cache-cold retriever makes no extra calls: the
    # run is already complete in the checkpoint.
    server2 = RecordedPubMed()
    graph2 = compile_graph(make_retrieval_nodes(EvidenceRetriever(server2.client())), checkpointer=saver)
    graph2.invoke(None, run_config("job-ckpt"))
    assert server2.requests == []


def test_planning_is_deterministic():
    a, b = RecordedPubMed(), RecordedPubMed()
    _, out_a, _ = run(a, job="ja")
    _, out_b, _ = run(b, job="jb")
    assert out_a["retrieval_queries"] == out_b["retrieval_queries"]
    assert out_a["retrieved_evidence"] == out_b["retrieved_evidence"]


def test_retrieval_package_has_no_langgraph_dependency():
    code = (
        "import sys, app.core.retrieval as m; "
        "bad = [k for k in sys.modules if k.startswith(('langgraph', 'app.core.graph', 'mcp'))]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=__file__.rsplit("/app/", 1)[0])


def test_retriever_from_settings_reads_ncbi_config(monkeypatch):
    from app.core.config import settings
    from app.core.graph.retrieval_nodes import retriever_from_settings

    monkeypatch.setattr(settings, "NCBI_API_KEY", "key")
    monkeypatch.setattr(settings, "RETRIEVAL_MAX_RESULTS_PER_QUERY", 7)
    ret = retriever_from_settings()
    assert ret.max_results == 7 and ret.client._api_key == "key"
    assert ret.client._limiter.interval == pytest.approx(1 / 9.0)
    ret.client.close()
