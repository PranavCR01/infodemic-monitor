""""How we searched" per claim (T31; design §6, §8, §12).

Recorded by ``retrieve_evidence`` as ``search_trail``, summarised by code at persist
time onto ``claims.search_trail`` and returned on every claim by the result API.
No network and no models: PubMed and the reference pages come from recorded
fixtures through ``httpx.MockTransport``; every model call is scripted.
"""
from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import jobs as jobs_router
from app.api.routers import results as results_router
from app.auth.dependencies import get_current_user
from app.core.graph import routing as r
from app.core.graph.retrieval_nodes import make_rerank_node, make_retrieval_nodes
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    GraphClaim,
    SearchRound,
    assert_checkpoint_safe,
)
from app.core.inference.providers import graph_provider as gp
from app.core.retrieval.library.fallback import LibraryFallback
from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.references import load_reference_config
from app.core.retrieval.retriever import EvidenceRetriever
from app.core.retrieval.schemas import EvidenceRecord
from app.core.schemas.search_trail import SearchTrailView
from app.db.base import Base
from app.db.models.claim import ClaimRow
from app.db.models.job import Job, JobStatus
from app.db.models.video import Video
from app.db.session import get_db
from app.services.pipeline_result_service import persist_outcome
from app.services.search_trail import build_search_trail
from app.tests.pubmed_fixtures import RecordedPubMed
from app.tests.reference_fixtures import RecordedReferences
from app.tests.test_graph_integration import BACKEND, FakeSingleCall, ScriptedClient, fusion, make_router

P = QueryPlanner()
HOT = "Drinking hot water every morning cures the flu."
GARLIC = "Some people say garlic stops colds. That's a myth."
MMR = "Children only need one dose of the MMR vaccine, at 10 years old."
SECRET = "sk-test-NEVER-IN-THE-TRAIL-0123456789"
ALICE = {"sub": "alice", "email": "alice@example.org", "role": "authenticated"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _claim(cid, text, kind="research_question"):
    return GraphClaim(claim_id=cid, claim_text=text, claim_category="treatment_efficacy",
                      source_segment_ids=["t1"], start_seconds=0, end_seconds=1, claim_kind=kind)


def _state(*claims):
    return {"claims": list(claims), "retrieval_queries": {}, "retrieved_evidence": {}, "retrieval_attempts": {}}


def _rounds(nodes, state, n):
    for _ in range(n):
        state.update(nodes[r.PLAN_RETRIEVAL](state))
        state.update(nodes[r.RETRIEVE_EVIDENCE](state))
    return state


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    import app.db.models  # noqa: F401

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ------------------------------------------------------------ recorded in the graph


def test_each_round_records_the_pubmed_query_actually_run_and_what_it_returned():
    server = RecordedPubMed()
    nodes = make_retrieval_nodes(EvidenceRetriever(server.client()))
    state = _rounds(nodes, _state(_claim("c1", HOT), _claim("c2", GARLIC)), 1)
    # c1's first query found nothing; run the broader one for c1 only
    state.update(nodes[r.PLAN_RETRIEVAL]({**state, "claims": [state["claims"][0]]}))
    state.update(nodes[r.RETRIEVE_EVIDENCE]({**state, "claims": [state["claims"][0]]}))

    c1 = state["search_trail"]["c1"]
    assert [x.pubmed_query for x in c1] == state["retrieval_queries"]["c1"] == P.ladder(HOT)[:2]
    assert [x.round for x in c1] == [1, 2]
    assert c1[0].pubmed_hits == 0 and c1[0].new_records == 0
    assert c1[1].pubmed_hits == 2 and c1[1].pubmed_records == 2 and c1[1].new_records == 2
    assert all(x.from_cache is False and x.pubmed_error is None for x in c1)

    c2 = state["search_trail"]["c2"]
    assert len(c2) == 1 and c2[0].pubmed_query == P.ladder(GARLIC)[0]
    # ESearch returned more PMIDs than survived the retraction filter and DOI dedup.
    assert c2[0].pubmed_hits > c2[0].pubmed_records >= c2[0].new_records == len(state["retrieved_evidence"]["c2"])
    assert_checkpoint_safe(state["search_trail"])


def test_ladder_that_runs_out_stops_and_is_reported_not_repeated():
    """T50 d: every round runs a different, broader query; when the ladder runs out the
    search stops and the trail says so (before T50 rounds 2-3 repeated the query)."""
    server = RecordedPubMed()
    nodes = make_retrieval_nodes(EvidenceRetriever(server.client()))
    state = _rounds(nodes, _state(_claim("c1", "Bananas are amazing for your skin")), 3)
    rounds = state["search_trail"]["c1"]
    assert len(rounds) == 3 and state["retrieval_attempts"]["c1"] == 3
    assert [x.pubmed_query for x in rounds] == ["bananas skin", "bananas", None]
    assert [x.query_kind for x in rounds] == ["keywords", "keywords", None]
    assert [x.ladder_exhausted for x in rounds] == [False, False, True]
    assert rounds[0].plan["language"] == "en" and rounds[1].plan is None
    state["reranked_evidence"] = {"c1": []}
    trail = build_search_trail(state, "c1")
    SearchTrailView.model_validate(trail)
    assert [q["repeat"] for q in trail["pubmed_queries"]] == [False, False]
    assert [q["kind"] for q in trail["pubmed_queries"]] == ["keywords", "keywords"]
    assert trail["counts"] == {"retrieved": 0, "screened": 0, "kept": 0}
    assert trail["budget"] == {"rounds_used": 3, "rounds_max": 3, "exhausted": True, "evidence_cap": 10,
                               "ladder_exhausted": True}


def test_a_failed_search_records_the_error_type_only_never_the_message_or_key():
    server = RecordedPubMed()
    server.fail_next = [RuntimeError(f"GET https://eutils.ncbi.nlm.nih.gov/esearch?api_key={SECRET}")] * 5
    nodes = make_retrieval_nodes(EvidenceRetriever(server.client(api_key=SECRET)))
    state = _rounds(nodes, _state(_claim("c1", HOT)), 1)
    (rnd,) = state["search_trail"]["c1"]
    assert rnd.pubmed_error and rnd.pubmed_hits is None and rnd.new_records == 0
    state["reranked_evidence"] = {"c1": []}
    trail = build_search_trail(state, "c1")
    assert trail["pubmed_queries"][0]["failed"] is True
    assert SECRET not in json.dumps(trail) and "eutils" not in json.dumps(trail)


def test_references_consulted_are_recorded_with_source_publisher_and_site():
    cfg = load_reference_config()
    refs = RecordedReferences(books=True).searcher(cfg, api_key=SECRET)
    nodes = make_retrieval_nodes(EvidenceRetriever(RecordedPubMed().client(api_key=SECRET)), references=refs)
    state = _rounds(nodes, _state(_claim("c1", MMR, "fact_of_record"), _claim("c2", HOT)), 1)
    # a second round for c1, as after the critic's RETRIEVE_MORE (§8)
    state["critic_results"] = {"c1": CriticResult(claim_id="c1", decision=CriticDecision.RETRIEVE_MORE)}
    state.update(nodes[r.PLAN_RETRIEVAL](state))
    state.update(nodes[r.RETRIEVE_EVIDENCE](state))
    first, second = state["search_trail"]["c1"]
    assert first.references and first.reference_passages == sum(
        1 for x in state["retrieved_evidence"]["c1"] if x.source == "reference")
    assert second.references == [] and second.reference_passages is None  # first round only (§6)
    assert state["search_trail"]["c2"][0].references == []  # research questions never touch them
    for ref in first.references:
        src = cfg.source(ref.source_id)
        assert ref.source_name == src.name and ref.publisher == src.publisher
        assert ref.site in src.allowed_hosts
        assert ref.url is None or ref.url.startswith("https://")

    state.update(nodes[r.RERANK_EVIDENCE](state))
    trail = build_search_trail(state, "c1")
    SearchTrailView.model_validate(trail)
    cdc = [s for s in trail["references"] if s["source_id"] == cfg.source(first.references[0].source_id).id][0]
    assert cdc["name"] and cdc["sites"] and cdc["items"]
    assert sum(s["passages"] for s in trail["references"]) == first.reference_passages
    assert SECRET not in json.dumps(trail)
    assert "eutils" not in json.dumps(trail)  # Bookshelf is recorded by its pages, not API URLs


def test_counts_retrieved_screened_kept():
    server = RecordedPubMed()
    nodes = make_retrieval_nodes(EvidenceRetriever(server.client()))
    state = _rounds(nodes, _state(_claim("c2", GARLIC)), 1)
    state.update(nodes[r.RERANK_EVIDENCE](state))
    trail = build_search_trail(state, "c2")
    rnd = state["search_trail"]["c2"][0]
    assert trail["counts"]["retrieved"] == rnd.pubmed_hits
    assert trail["counts"]["screened"] == len(state["retrieved_evidence"]["c2"])
    assert trail["counts"]["kept"] == len(state["reranked_evidence"]["c2"])
    assert trail["counts"]["retrieved"] >= trail["counts"]["screened"] >= trail["counts"]["kept"]
    assert trail["budget"]["rounds_used"] == 1 and trail["budget"]["exhausted"] is False
    assert trail["library"] is None  # no library configured for this run


class _FakeLibrarySearcher:
    def __init__(self, records):
        self.records = records

    def search(self, query, k):
        return SimpleNamespace(query=query, records=list(self.records), errors=[])


def test_library_fallback_is_recorded_and_counted():
    passage = EvidenceRecord(evidence_id="lib_doc1_p4", source="library", title="Lab report on bananas",
                             abstract="Bananas and skin health in a small cohort.", document_id="doc1", page=4,
                             publication_type=["Unknown"])
    library = LibraryFallback(_FakeLibrarySearcher([passage]))
    nodes = make_retrieval_nodes(EvidenceRetriever(RecordedPubMed().client()), library=library)
    state = _rounds(nodes, _state(_claim("c1", "Bananas are amazing for your skin"), _claim("c2", GARLIC)), 1)
    state.update(nodes[r.RERANK_EVIDENCE](state))
    t1 = build_search_trail(state, "c1")
    assert t1["library"] == {"fired": True, "passages": 1}
    assert t1["counts"]["screened"] == 1 and t1["counts"]["retrieved"] == 1
    assert t1["counts"]["kept"] == len(state["reranked_evidence"]["c1"])
    if state["reranked_evidence"]["c2"]:  # PubMed was enough: the fallback never ran
        assert build_search_trail(state, "c2")["library"] == {"fired": False, "passages": 0}


def test_unsearched_claims_have_no_trail_and_old_checkpoints_fall_back_to_queries():
    assert build_search_trail({"claims": []}, "c1") is None
    old = {"retrieval_queries": {"c1": ["hot drinks AND influenza", "hot drinks"]},
           "retrieval_attempts": {"c1": 2}, "retrieved_evidence": {"c1": []}, "reranked_evidence": {"c1": []}}
    trail = build_search_trail(old, "c1")
    assert trail["recorded"] == "queries_only"
    assert [q["query"] for q in trail["pubmed_queries"]] == old["retrieval_queries"]["c1"]
    assert all(q["results"] is None for q in trail["pubmed_queries"])
    assert trail["counts"]["retrieved"] is None and trail["budget"]["rounds_used"] == 2


def test_rerank_node_alone_ignores_the_trail():
    """The trail is written only by retrieve_evidence; rerank never reads it."""
    rec = EvidenceRecord(evidence_id="ev_1", source="pubmed", pmid="1", title="Garlic for the common cold",
                         abstract="Garlic supplementation and common cold incidence.", publication_type=["Review"])
    base = {"claims": [_claim("c1", GARLIC)], "retrieved_evidence": {"c1": [rec]}}
    junk = {**base, "search_trail": {"c1": [SearchRound(round=9, pubmed_query="anything", new_records=99)]}}
    node = make_rerank_node()[r.RERANK_EVIDENCE]
    assert node(base) == node(junk)


# ------------------------------------------------------------ results unchanged


def _provider(**kw):
    from app.core.retrieval.retriever import EvidenceRetriever as ER

    return gp.GraphProvider(caller=make_router(ScriptedClient()), retriever=ER(RecordedPubMed().client()),
                            fallback=FakeSingleCall(), **kw)


def test_recording_the_trail_does_not_change_retrieval_or_verdicts():
    with_trail = _provider().run(fusion(), job_id="job-a", video_id="vid-1")
    inner = gp.build_nodes(make_router(ScriptedClient()), EvidenceRetriever(RecordedPubMed().client()))
    plain = inner[r.RETRIEVE_EVIDENCE]

    def no_trail(state):
        out = plain(state)
        out.pop("search_trail", None)
        return out

    without = _provider(node_overrides={r.RETRIEVE_EVIDENCE: no_trail}).run(fusion(), job_id="job-b", video_id="vid-1")
    assert not with_trail.fallback_used and not without.fallback_used
    assert with_trail.state["search_trail"] and "search_trail" not in without.state
    for key in ("retrieval_queries", "retrieved_evidence", "retrieval_attempts", "reranked_evidence",
                "verification_results", "critic_results", "final_result", "requires_human_review"):
        assert with_trail.state.get(key) == without.state.get(key), key
    assert with_trail.classification.label == without.classification.label


# ------------------------------------------------------------ stored and returned


@pytest.fixture()
def persisted():
    db = _session()
    db.add(Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    # Owned by the caller once T28's jobs.user_id exists (#81); before that, no owner.
    owner = {"user_id": ALICE["sub"]} if hasattr(Job, "user_id") else {}
    db.add(Job(id="job-1", video_id="vid-1", status=JobStatus.STARTED, **owner))
    db.commit()
    outcome = _provider().run(fusion(), job_id="job-1", video_id="vid-1")
    persist_outcome(db, "job-1", fusion(), outcome)
    app = FastAPI()
    app.include_router(jobs_router.router)
    app.include_router(results_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: ALICE
    return {"db": db, "client": TestClient(app), "state": outcome.state}


def test_trail_is_stored_with_the_claim_result(persisted):
    rows = persisted["db"].query(ClaimRow).filter_by(job_id="job-1").all()
    assert rows
    for row in rows:
        # T65 (f): the stored trail also carries the sources' journal / date ("source_meta").
        stored = {k: v for k, v in row.search_trail.items() if k != "source_meta"}
        assert stored == build_search_trail(persisted["state"], row.claim_id)
        trail = SearchTrailView.model_validate(row.search_trail)
        assert trail.recorded == "graph"
        assert [q.query for q in trail.pubmed_queries] == persisted["state"]["retrieval_queries"][row.claim_id]
        assert trail.budget.rounds_used == persisted["state"]["retrieval_attempts"][row.claim_id]
        assert trail.counts.kept == len(persisted["state"]["reranked_evidence"][row.claim_id])


def test_trail_is_returned_by_every_result_endpoint(persisted):
    client = persisted["client"]
    legacy = client.get("/jobs/job-1/result").json()
    v1 = client.get("/v1/videos/vid-1/results").json()
    claims = client.get("/v1/videos/vid-1/claims").json()["claims"]
    for body in (legacy["claims"], v1["claims"], claims):
        assert body and all(c["search_trail"] for c in body)
        for c in body:
            t = c["search_trail"]
            assert set(t) == {"version", "recorded", "pubmed_queries", "references", "library", "counts", "budget",
                              "planning", "find_study", "shared_studies", "screened_out",
                              "screened_out_truncated"}  # T50, T57
            assert set(t["counts"]) == {"retrieved", "screened", "kept"}
            assert t["pubmed_queries"] and t["pubmed_queries"][0]["query"]
    # existing T11/T26 claim fields are still there, unchanged
    assert {"claim_id", "text", "verdict", "evidence", "retrieval_attempts", "critic"} <= set(claims[0])


def test_rows_without_a_trail_return_null_and_keep_working(persisted):
    db = persisted["db"]
    for row in db.query(ClaimRow).filter_by(job_id="job-1"):
        row.search_trail = None
    db.commit()
    claims = persisted["client"].get("/v1/videos/vid-1/claims").json()["claims"]
    assert claims and all(c["search_trail"] is None for c in claims)


def test_a_trail_written_by_a_later_version_is_left_out_not_an_error(persisted):
    db = persisted["db"]
    row = db.query(ClaimRow).filter_by(job_id="job-1").first()
    row.search_trail = {"version": 99, "something": "else"}
    db.commit()
    resp = persisted["client"].get("/v1/videos/vid-1/claims")
    assert resp.status_code == 200
    by_id = {c["claim_id"]: c for c in resp.json()["claims"]}
    assert by_id[row.claim_id]["search_trail"] is None


def test_openapi_documents_the_trail(persisted):
    schemas = persisted["client"].get("/openapi.json").json()["components"]["schemas"]
    assert {"SearchTrailView", "PubMedQueryView", "ReferenceSourceView", "SearchCountsView",
            "SearchBudgetView"} <= set(schemas)


# ------------------------------------------------------------ migration


def test_migration_0012_upgrades_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    url = f"sqlite:///{tmp_path / 't31.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0012")
    cols = {c["name"] for c in inspect(create_engine(url)).get_columns("claims")}
    assert "search_trail" in cols
    command.downgrade(cfg, "0011")
    cols = {c["name"] for c in inspect(create_engine(url)).get_columns("claims")}
    assert "search_trail" not in cols


def test_trail_round_trips_through_checkpoints_under_strict_msgpack():
    """``search_trail`` lives in graph checkpoints: its records are registered with the
    serializer and read back as the same typed values (strict mode, warnings as errors)."""
    import os
    import subprocess
    import sys

    code = (
        "import warnings; warnings.simplefilter('error');"
        "from app.core.graph.checkpoint import make_serde;"
        "from app.core.graph.state import SearchRound, ReferenceConsulted;"
        "v = {'c1': [SearchRound(round=1, pubmed_query='q', pubmed_hits=3, pubmed_records=2, from_cache=False,"
        " new_records=2, references=[ReferenceConsulted(source_id='cdc', source_name='CDC', item='p',"
        " mode='live', outcome='passage', site='www.cdc.gov')], reference_passages=1)]};"
        "s = make_serde(); assert s.loads_typed(s.dumps_typed(v)) == v; print('ok')"
    )
    env = {**os.environ, "LANGGRAPH_STRICT_MSGPACK": "true"}
    proc = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(BACKEND),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().endswith("ok")
