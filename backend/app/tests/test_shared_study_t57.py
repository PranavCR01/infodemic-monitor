"""T57: a study the video cites, shared across the video's claims (design §6).

Offline. The vitamin K job's searches, records and find_study answers are replayed from
the recorded paid run (``evals/reports/T50/vitk_paid.json``); the finder is a replay of
what the model answered there, and its candidates are verified against the recorded
E-utilities responses in ``fixtures/find_study``. No model, no web search, no network.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.core.graph import routing as r
from app.core.graph.retrieval_nodes import make_rerank_node
from app.core.graph.shared_study import (
    CITATION_MISMATCH, KEPT, NOT_KEPT, OFF_TOPIC, claim_order, share_cited_studies, shared_pool,
)
from app.core.graph.state import EvidenceRecord, GraphClaim, SearchRound
from app.core.graph.unproven_guard import on_topic_ids
from app.core.retrieval.find_study import FinderAnswer, FindStudyStep, StudyVerifier, parse_candidates
from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.rerank import Reranker
from app.services.search_trail import build_search_trail
from app.tests.pubmed_fixtures import RecordedPubMed
from app.tests.vitamin_k_fixture import load_real

FIX = Path(__file__).parent / "fixtures"
PAID = Path(__file__).resolve().parents[3] / "evals" / "reports" / "T50" / "vitk_paid.json"
JAMA_PMID = "42986716"
JAMA_ID = f"ev_{JAMA_PMID}"


# ------------------------------------------------------------------ the recorded run


@pytest.fixture(scope="module")
def paid() -> dict:
    return json.loads(PAID.read_text())


def _claims() -> list[GraphClaim]:
    return [GraphClaim(claim_id=c["claim_id"], claim_text=c["text"], claim_category=c["category"],
                       claim_kind=c["claim_kind"], source_segment_ids=[f"t_{c['claim_id']}"],
                       start_seconds=c["start_seconds"], end_seconds=c["end_seconds"])
            for c in load_real()["claims"]]


class ReplayFinder:
    """The find_study model's recorded answers (vitk_paid.json), keyed by claim text.
    A claim the paid run didn't ask about gets no candidate."""

    def __init__(self, paid: dict):
        self.answers = {c["text"]: [{"pmid": x["pmid"], "doi": x["doi"]} for x in c["find_study"]["candidates"]]
                        for c in paid["claims"].values() if c.get("find_study")}
        self.calls: list[str] = []

    def __call__(self, text, cue):
        self.calls.append(text)
        cands = parse_candidates(json.dumps({"candidates": self.answers.get(text, [])}))
        return FinderAnswer(candidates=[c.__dict__ for c in cands], web_queries=["replayed"], web_searches=0)


def _verifier() -> StudyVerifier:
    return StudyVerifier(RecordedPubMed(FIX / "find_study").client())


def _state(paid: dict, claims: list[GraphClaim]) -> dict:
    """The vitamin K state after 3 retrieval rounds, from the recorded searches: each
    claim's retrieved records, in the order the rounds found them, and its trail."""
    retrieved, trail = {}, {}
    planner = QueryPlanner()
    context = tuple(c.claim_text for c in claims)
    for claim in claims:
        rec = paid["claims"][claim.claim_id]
        plan = planner.plan(claim.claim_text, claim_kind=claim.claim_kind, context=context)
        recs, seen, rounds = [], set(), []
        for rnd in rec["rounds"]:
            if "query" not in rnd:
                rounds.append(SearchRound(round=rnd["round"], ladder_exhausted=True))
                continue
            rounds.append(SearchRound(round=rnd["round"], pubmed_query=rnd["query"], pubmed_hits=rnd["hits"],
                                      pubmed_records=len(rnd["ids"]), query_kind=plan.kind_of(rnd["query"])))
            for eid in rnd["ids"]:
                if eid in seen:
                    continue
                seen.add(eid)
                v = rec["records"][eid]
                recs.append(EvidenceRecord(evidence_id=eid, source="pubmed", pmid=v["pmid"], title=v["title"],
                                           abstract=v.get("abstract") or "", publication_year=v.get("year"),
                                           query=rnd["query"]))
        retrieved[claim.claim_id] = recs
        trail[claim.claim_id] = rounds
    return {"claims": claims, "retrieved_evidence": retrieved, "search_trail": trail,
            "retrieval_attempts": {c.claim_id: 3 for c in claims}}


def _paid_find_study(paid: dict, claims: list[GraphClaim]) -> tuple[dict, ReplayFinder]:
    """find_study as the paid run ran it (forced on c2-c5), replayed and re-verified."""
    finder = ReplayFinder(paid)
    step = FindStudyStep(finder, _verifier())
    texts = {c.claim_id: c.claim_text for c in claims}
    found = {cid: step.run(texts[cid], "forced").records for cid in ("c2", "c3", "c4", "c5")}
    return {cid: recs for cid, recs in found.items() if recs}, finder


def _kept(out: dict) -> dict[str, list[str]]:
    return {cid: [e.evidence_id for e in recs] for cid, recs in out["reranked_evidence"].items()}


@pytest.fixture(scope="module")
def replayed(paid):
    claims = _claims()
    state = _state(paid, claims)
    found, finder = _paid_find_study(paid, claims)
    state["found_study_evidence"] = found
    out = make_rerank_node()[r.RERANK_EVIDENCE](state)
    return state, out, finder


# ------------------------------------------------------------------ the vitamin K job


def test_paid_run_replay_verifies_the_jama_paper_for_c2_and_c4_only(replayed):
    state, _, _ = replayed
    assert {cid: [e.pmid for e in recs] for cid, recs in state["found_study_evidence"].items()} == {
        "c2": [JAMA_PMID], "c4": [JAMA_PMID]}


def test_c3_and_c5_keep_the_jama_paper_shared_from_c2(replayed):
    state, out, _ = replayed
    kept = _kept(out)
    for cid in ("c3", "c5"):
        assert JAMA_ID in kept[cid], cid
        (entry,) = [e for e in out["shared_study_trail"][cid] if e.evidence_id == JAMA_ID]
        assert entry.shared_from == "c2" and entry.outcome == KEPT and entry.relevance_score >= 0.4
    # c2 and c4 still keep it (their own verified record, pinned first as before).
    for cid in ("c2", "c4"):
        assert kept[cid][0] == JAMA_ID, cid
        assert all(e.evidence_id != JAMA_ID for e in out["shared_study_trail"].get(cid, []))


def test_no_vitamin_k_claim_keeps_an_off_topic_shared_record(replayed):
    state, out, _ = replayed
    claims = {c.claim_id: c for c in state["claims"]}
    kept_shared = {}
    for cid, entries in out["shared_study_trail"].items():
        kept_ids = {e.evidence_id for e in out["reranked_evidence"][cid]}
        for e in entries:
            assert (e.evidence_id in kept_ids) == (e.outcome == KEPT), (cid, e)
            if e.outcome == KEPT:
                rec = next(x for x in out["reranked_evidence"][cid] if x.evidence_id == e.evidence_id)
                assert on_topic_ids(claims[cid], [rec]) == [e.evidence_id], cid
                kept_shared.setdefault(cid, []).append(e.evidence_id)
    # Which claims the shared JAMA paper reached, and why the others didn't (pinned
    # down so a change shows up here). c6, c11: on topic, but the reranker scored it
    # below the threshold. c8 ("bleeding in the brain ...") and c12 ("the studies are
    # observational ..."): no recognised intervention, so the strict T49 fallback words
    # decide, and the paper lacks them.
    assert kept_shared == {cid: [JAMA_ID] for cid in ("c1", "c3", "c5", "c7", "c9", "c10", "c13")}
    outcomes = {cid: [e.outcome for e in entries] for cid, entries in out["shared_study_trail"].items()}
    assert outcomes["c6"] == outcomes["c11"] == [NOT_KEPT]
    assert outcomes["c8"] == outcomes["c12"] == [OFF_TOPIC]
    assert set(outcomes) == {f"c{i}" for i in range(1, 14)} - {"c2", "c4"}
    # The shared paper is the only record any claim gained; at most one of a claim's
    # own picks made way for it (cap of 10), and their order is unchanged.
    for cid, ids in _kept(out).items():
        claim = claims[cid]
        own = [e.evidence_id for e in Reranker().rerank(claim.claim_text, state["retrieved_evidence"][cid],
                                                         claim.claim_kind).kept if e.evidence_id != JAMA_ID]
        rest = [i for i in ids if i != JAMA_ID]
        assert rest == own[: len(rest)] and len(rest) >= len(own) - 1, cid


def test_sharing_makes_no_model_call_and_no_web_search(replayed):
    _, _, finder = replayed
    assert len(finder.calls) == 4  # the paid run's four forced calls, nothing added by sharing


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_result_does_not_depend_on_claim_order(paid, replayed, seed):
    _, out, _ = replayed
    claims = _claims()
    random.Random(seed).shuffle(claims)
    state = _state(paid, claims)
    state["retrieved_evidence"] = dict(reversed(list(state["retrieved_evidence"].items())))
    found, _ = _paid_find_study(paid, claims)
    state["found_study_evidence"] = dict(reversed(list(found.items())))
    again = make_rerank_node()[r.RERANK_EVIDENCE](state)
    assert _kept(again) == _kept(out)
    assert {k: [e.model_dump() for e in v] for k, v in again["shared_study_trail"].items()} == \
        {k: [e.model_dump() for e in v] for k, v in out["shared_study_trail"].items()}


def test_with_the_find_study_step_in_the_node_c2_to_c5_keep_the_paper(paid):
    """The node's own trigger (no forcing): c2 cites a study, so find_study runs for it
    and the verified paper is shared in the same round."""
    claims = _claims()
    state = _state(paid, claims)
    finder = ReplayFinder(paid)
    out = make_rerank_node(find_study=FindStudyStep(finder, _verifier()))[r.RERANK_EVIDENCE](state)
    kept = _kept(out)
    assert all(JAMA_ID in kept[cid] for cid in ("c2", "c3", "c4", "c5"))
    assert out["find_study_trail"]["c2"].reason == "cites_study"
    for cid in ("c3", "c4", "c5"):
        assert [e.shared_from for e in out["shared_study_trail"][cid] if e.evidence_id == JAMA_ID] == ["c2"]
    # A second round re-shares the same way and calls no model again.
    calls = len(finder.calls)
    state.update(out)
    again = make_rerank_node(find_study=FindStudyStep(finder, _verifier()))[r.RERANK_EVIDENCE](state)
    assert len(finder.calls) == calls and _kept(again) == kept


def test_search_trail_view_shows_where_a_shared_record_came_from(replayed):
    state, out, _ = replayed
    view = build_search_trail({**state, **out, "retrieval_queries": {}}, "c3")
    (shared,) = [s for s in view["shared_studies"] if s["evidence_id"] == JAMA_ID]
    assert shared["shared_from"] == "c2" and shared["outcome"] == KEPT and shared["pmid"] == JAMA_PMID
    assert view["version"] == 3


# ------------------------------------------------------------------ unit tests


def _claim(cid, text, kind="research_question"):
    return GraphClaim(claim_id=cid, claim_text=text, claim_category="treatment_efficacy", claim_kind=kind,
                      source_segment_ids=["s1"], start_seconds=0, end_seconds=1)


JAMA = EvidenceRecord(
    evidence_id=JAMA_ID, source="pubmed", pmid=JAMA_PMID, doi="10.1001/jama.2026.21764", publication_year=2026,
    title="Nonreceipt of Newborn Vitamin K and Risk of Bleeding.",
    abstract="Infants who did not receive vitamin K had higher risk of bleeding.", query="find_study:cites_study")
GARLIC = EvidenceRecord(evidence_id="ev_1", source="pubmed", pmid="1", title="Garlic for the common cold",
                        abstract="Randomised trial of garlic supplements to prevent the common cold.",
                        publication_type=["Randomized Controlled Trial"])


def _rerank(claim, recs):
    return Reranker().rerank(claim.claim_text, recs, claim.claim_kind).kept


def test_a_shared_record_is_rejected_for_an_off_topic_claim():
    claims = {"c1": _claim("c1", "A 2026 JAMA study found newborns without vitamin K bleed more"),
              "c2": _claim("c2", "Garlic prevents the common cold")}
    reranked = {"c1": [JAMA], "c2": [GARLIC]}
    trail = share_cited_studies(claims, reranked, {"c1": [], "c2": [GARLIC]}, {"c1": [JAMA]}, {}, _rerank)
    (entry,) = trail["c2"]
    assert entry.outcome == OFF_TOPIC and entry.shared_from == "c1" and entry.evidence_id == JAMA_ID
    assert [e.evidence_id for e in reranked["c2"]] == ["ev_1"]  # unchanged
    assert "c1" not in trail  # nothing offered back to its own source


def test_the_on_topic_check_runs_even_when_the_reranker_would_keep_the_record():
    # A reranker that keeps everything: the T49 check alone must still refuse.
    claims = {"c1": _claim("c1", "A 2026 JAMA study found newborns without vitamin K bleed more"),
              "c2": _claim("c2", "Garlic prevents the common cold")}
    reranked = {"c1": [JAMA], "c2": [GARLIC]}
    trail = share_cited_studies(claims, reranked, {}, {"c1": [JAMA]}, {}, lambda c, recs: list(recs))
    assert [e.outcome for e in trail["c2"]] == [OFF_TOPIC] and JAMA_ID not in {e.evidence_id for e in reranked["c2"]}


def test_the_reranker_can_refuse_an_on_topic_shared_record():
    claims = {"c1": _claim("c1", "A 2026 JAMA study found newborns without vitamin K bleed more"),
              "c2": _claim("c2", "Vitamin K is a vitamin that helps prevent a potentially devastating condition")}
    reranked = {"c1": [JAMA], "c2": []}
    trail = share_cited_studies(claims, reranked, {}, {"c1": [JAMA]}, {}, lambda c, recs: [])
    assert [e.outcome for e in trail["c2"]] == [NOT_KEPT] and reranked["c2"] == []


def test_a_claim_naming_another_journal_or_year_refuses_the_shared_record():
    claims = {"c1": _claim("c1", "A 2026 JAMA study found newborns without vitamin K bleed more"),
              "c2": _claim("c2", "A Lancet study found newborns without vitamin K bleed more"),
              "c3": _claim("c3", "A 2019 study found newborns without vitamin K bleed more")}
    reranked = {"c1": [JAMA], "c2": [], "c3": []}
    trail = share_cited_studies(claims, reranked, {}, {"c1": [JAMA]}, {}, _rerank)
    assert [e.outcome for e in trail["c2"]] == [CITATION_MISMATCH]
    assert [e.outcome for e in trail["c3"]] == [CITATION_MISMATCH]
    assert reranked["c2"] == reranked["c3"] == []


def test_only_verified_records_are_shared_never_a_claims_ordinary_search_results():
    vk = EvidenceRecord(evidence_id="ev_2", source="pubmed", pmid="2", title="Vitamin K deficiency bleeding in infants",
                        abstract="Vitamin K prophylaxis prevents bleeding.", query="vitamin k AND bleeding")
    claims = {"c1": _claim("c1", "Vitamin K prevents bleeding in newborns"),
              "c2": _claim("c2", "Babies without vitamin K bleed more")}
    # c1 kept an on-topic paper from its ordinary search; nothing is verified anywhere.
    assert shared_pool(claims, {}, {"c1": [vk], "c2": []}, {}) == []
    reranked = {"c1": [vk], "c2": []}
    assert share_cited_studies(claims, reranked, {}, {}, {}, _rerank) == {} and reranked["c2"] == []


def test_the_citation_lookups_best_record_is_shared():
    cq = '"JAMA"[ta] AND 2026[dp] AND vitamin k'
    hit = JAMA.model_copy(update={"query": cq})
    older = EvidenceRecord(evidence_id="ev_3", source="pubmed", pmid="3", publication_year=2019, query=cq,
                           title="Vitamin K and newborn bleeding", abstract="Vitamin K in infants.")
    claims = {"c1": _claim("c1", "A 2026 JAMA study found newborns without vitamin K bleed more"),
              "c2": _claim("c2", "Babies who didn't receive vitamin K had a higher risk of bleeding")}
    trail_rounds = {"c1": [SearchRound(round=1, pubmed_query=cq, query_kind="citation")]}
    # The year rules out the 2019 paper; the 2026 one is the cited study.
    pool = shared_pool(claims, {}, {"c1": [older, hit]}, trail_rounds)
    assert [(c.record.evidence_id, c.shared_from) for c in pool] == [(JAMA_ID, "c1")]
    reranked = {"c1": [older, hit], "c2": []}
    trail = share_cited_studies(claims, reranked, {}, {}, trail_rounds, _rerank)
    assert [(e.evidence_id, e.outcome) for e in trail["c2"]] == [(JAMA_ID, KEPT)]
    # A record from an ordinary query of the same claim is not the citation lookup's.
    assert shared_pool(claims, {}, {"c1": [older.model_copy(update={"query": "x"})]}, trail_rounds) == []


def test_pool_order_and_shared_from_follow_natural_claim_order():
    assert sorted(["c10", "c2", "c1"], key=claim_order) == ["c1", "c2", "c10"]
    claims = {cid: _claim(cid, "A 2026 JAMA study found newborns without vitamin K bleed more")
              for cid in ("c10", "c2")}
    pool = shared_pool(claims, {"c10": [JAMA], "c2": [JAMA]}, {}, {})
    assert [c.shared_from for c in pool] == ["c2"]


def test_without_any_cited_study_the_node_output_is_unchanged():
    node = make_rerank_node()[r.RERANK_EVIDENCE]
    out = node({"claims": [_claim("c1", "Garlic prevents the common cold")],
                "retrieved_evidence": {"c1": [GARLIC]}, "retrieval_attempts": {"c1": 1}})
    assert set(out) == {"reranked_evidence"}


def test_a_reranker_failure_while_sharing_is_recorded_and_the_claim_keeps_its_own_evidence():
    class Flaky(Reranker):
        def rerank(self, claim_text, records, claim_kind=None):
            if any(rec.evidence_id == JAMA_ID for rec in records) and "Babies" in claim_text:
                raise RuntimeError("boom")
            return super().rerank(claim_text, records, claim_kind)

    vk = EvidenceRecord(evidence_id="ev_2", source="pubmed", pmid="2", title="Vitamin K deficiency bleeding in infants",
                        abstract="Vitamin K prophylaxis prevents bleeding.")
    claims = [_claim("c1", "A 2026 JAMA study found newborns without vitamin K bleed more"),
              _claim("c2", "Babies without vitamin K bleed more")]
    out = make_rerank_node(Flaky())[r.RERANK_EVIDENCE]({
        "claims": claims, "retrieved_evidence": {"c1": [], "c2": [vk]}, "retrieval_attempts": {"c1": 3, "c2": 3},
        "found_study_evidence": {"c1": [JAMA]}})
    assert [e.evidence_id for e in out["reranked_evidence"]["c2"]] == ["ev_2"]
    assert any("shared cited studies" in e.message and e.claim_id == "c2" for e in out["errors"])
