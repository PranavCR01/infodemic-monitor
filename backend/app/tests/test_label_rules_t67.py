"""T67: critic-budget verdicts and thin contradictions (design §8, §9, §11).

Both changes failed the T67 replay gate (evals/reports/T67/report.md) and ship OFF:
``routing.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED`` and ``judge.THIN_CONTRADICTION_RULE``
are False. These tests pin the default (the T07 / T64 behaviour) and exercise each code
path switched on, so a lead decision to turn one on is a one-line change. No model calls.
"""
from __future__ import annotations

import pytest

from app.core.graph import judge as jg
from app.core.graph import review_policy as rp
from app.core.graph import routing as r
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    GraphClaim,
    NodeError,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX
from app.core.schemas.pipeline import MisinfoLabel
from app.services.review_reasons import REASON_TEXT, parse_reason

ISSUES = ["the cited papers study salt reduction, not elimination"]


def claim(cid: str, text: str = "Eliminating all salt raises blood pressure", category: str = "harm") -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                      source_segment_ids=["t1"], start_seconds=0.0, end_seconds=4.0)


def paper(eid: str, title: str = "Salt and blood pressure", ptypes=("Journal Article",), abstract: str = "") -> EvidenceRecord:
    return EvidenceRecord(evidence_id=eid, source="pubmed", pmid=eid.split("_")[-1], title=title,
                          abstract=abstract, publication_type=list(ptypes))


def state(verdicts: dict[str, VerificationResult], stances: dict[str, Stance], evidence: dict[str, list],
          claims: list[GraphClaim] | None = None, critic: dict[str, CriticDecision] | None = None,
          errors=(), attempts: int = 3) -> dict:
    s = initial_state(job_id="j67", video_id="v67", media_uri="mem://v67", pipeline_version="test")
    claims = claims or [claim(cid) for cid in verdicts]
    s.update(
        claims=claims,
        stance_results={cid: StanceResult(claim_id=cid, stance=st, stance_segment_ids=["t1"]) for cid, st in stances.items()},
        retrieved_evidence=evidence, reranked_evidence=evidence,
        retrieval_attempts={c.claim_id: attempts for c in claims},
        verification_results=verdicts,
        critic_results={cid: CriticResult(claim_id=cid, decision=d, issues=ISSUES) for cid, d in (critic or {}).items()},
        errors=list(errors),
    )
    return s


def contradicted(cid: str, con) -> VerificationResult:
    return VerificationResult(claim_id=cid, verdict=Verdict.CONTRADICTED, contradicting_evidence_ids=list(con))


@pytest.fixture
def change1(monkeypatch):
    monkeypatch.setattr(r, "KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED", True)


@pytest.fixture
def change2(monkeypatch):
    monkeypatch.setattr(jg, "THIN_CONTRADICTION_RULE", True)


# ------------------------------------------------------------------ gate result: both off


def test_both_changes_ship_off_after_the_replay_gate():
    assert r.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED is False
    assert jg.THIN_CONTRADICTION_RULE is False


def exhausted_state(errors=(), con=("ev_1",), evidence=None) -> dict:
    ev = evidence if evidence is not None else {"c1": [paper("ev_1")]}
    return state({"c1": contradicted("c1", con)}, {"c1": Stance.ENDORSES}, ev,
                 critic={"c1": CriticDecision.RETRIEVE_MORE}, errors=errors)


def test_default_withdraws_the_objected_verdict_as_before():
    s = exhausted_state()
    v = r.verdicts_for_judge(s)["c1"]
    assert v.verdict == Verdict.INSUFFICIENT_EVIDENCE and r.ABSTENTION_LIMITATION in v.limitations
    assert r.second_check_disagreed_ids(s) == []
    assert not [x for x in r.critic_review_reasons(s) if x.startswith("second_check_disagreed")]


# ------------------------------------------------------------------ change 1 (on)


def test_change1_keeps_the_stored_verdict_with_the_critics_issues(change1):
    s = exhausted_state()
    v = r.verdicts_for_judge(s)["c1"]
    assert v.verdict == Verdict.CONTRADICTED and v.contradicting_evidence_ids == ["ev_1"]
    assert any(x.startswith(r.SECOND_CHECK_LIMITATION) and ISSUES[0] in x for x in v.limitations)
    assert s["verification_results"]["c1"].limitations == []  # stored verdict unchanged
    reasons = r.critic_review_reasons(s)
    assert "second_check_disagreed:c1" in reasons and "budget_exhausted:c1" in reasons


def test_change1_judge_decides_on_the_kept_verdict_and_review_rule_fires(change1):
    s = exhausted_state()
    final, errors = jg.judge(s)
    assert not errors
    assert final.classification == MisinfoLabel.MISINFO and final.claim_ids == ["c1"]
    s["final_result"], s["validation_errors"] = final, []
    d = rp.evaluate(s)
    assert d.fired["second_check_disagreed"] == ("second_check_disagreed:c1",)
    assert rp.rule_of("second_check_disagreed:c1") == "second_check_disagreed"


@pytest.mark.parametrize("errors, con, why", [
    ((), ("ev_9",), "cites a record not retrieved for the claim"),
    ((NodeError(node=r.VERIFY_CLAIMS, claim_id="c1", message=f"{GUARDRAIL_ERROR_PREFIX}schema bad"),), ("ev_1",),
     "guardrail rejection"),
    ((NodeError(node=r.VERIFY_CLAIMS, claim_id="c1", message="model call failed", retryable=True),), ("ev_1",),
     "verifier error"),
])
def test_change1_still_withdraws_on_hard_failures(change1, errors, con, why):
    s = exhausted_state(errors=errors, con=con)
    assert r.verdict_hard_failure(s, s["verification_results"]["c1"]), why
    assert r.verdicts_for_judge(s)["c1"].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert "second_check_disagreed:c1" not in r.critic_review_reasons(s)


def test_change1_a_repair_that_succeeded_is_not_a_hard_failure(change1):
    s = exhausted_state(errors=(NodeError(node=r.VERIFY_CLAIMS, claim_id="c1", message="repair requested: x"),))
    assert r.verdicts_for_judge(s)["c1"].verdict == Verdict.CONTRADICTED


def test_change1_nothing_cited_keeps_t07_behaviour(change1):
    s = state({"c1": VerificationResult(claim_id="c1", verdict=Verdict.INSUFFICIENT_EVIDENCE)},
              {"c1": Stance.ENDORSES}, {"c1": [paper("ev_1")]}, critic={"c1": CriticDecision.RETRIEVE_MORE})
    assert r.second_check_disagreed_ids(s) == []
    assert r.verdicts_for_judge(s)["c1"].limitations == []


# ------------------------------------------------------------------ change 2 (on)


def test_default_a_single_record_contradiction_still_decides():
    s = state({"c1": contradicted("c1", ["ev_1"])}, {"c1": Stance.ENDORSES}, {"c1": [paper("ev_1")]})
    final, _ = jg.judge(s)
    assert final.classification == MisinfoLabel.MISINFO
    assert not [f for f in final.review_flags if f.startswith(jg.FLAG_THIN_CONTRADICTION)]


def test_change2_thin_endorsed_contradiction_cannot_decide(change2):
    # one on-topic record, no strong type; c2 SUPPORTED would then decide NO_MISINFO
    s = state({"c1": contradicted("c1", ["ev_1"]),
               "c2": VerificationResult(claim_id="c2", verdict=Verdict.SUPPORTED, supporting_evidence_ids=["ev_2"])},
              {"c1": Stance.ENDORSES, "c2": Stance.ENDORSES},
              {"c1": [paper("ev_1", "Salt intake and blood pressure")], "c2": [paper("ev_2")]})
    final, _ = jg.judge(s)
    assert s["verification_results"]["c1"].verdict == Verdict.CONTRADICTED  # verdict stays
    assert final.classification == MisinfoLabel.NO_MISINFO and final.claim_ids == ["c2"]
    assert "thin_contradiction:c1" in final.review_flags


def test_change2_thin_refuted_contradiction_falls_through(change2):
    s = state({"c1": contradicted("c1", ["ev_1"])}, {"c1": Stance.REFUTES}, {"c1": [paper("ev_1")]})
    final, _ = jg.judge(s)
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE and final.claim_ids == []
    assert "thin_contradiction:c1" in final.review_flags


def test_change2_two_on_topic_records_decide(change2):
    ev = [paper("ev_1", "Salt restriction and blood pressure"), paper("ev_2", "Dietary salt in hypertension")]
    s = state({"c1": contradicted("c1", ["ev_1", "ev_2"])}, {"c1": Stance.ENDORSES}, {"c1": ev})
    final, _ = jg.judge(s)
    assert final.classification == MisinfoLabel.MISINFO
    assert "thin_contradiction:c1" not in final.review_flags


def test_change2_one_strong_record_decides_even_off_topic(change2):
    ev = [paper("ev_1", "Sodium and cardiovascular outcomes", ptypes=("Journal Article", "Meta-Analysis"))]
    s = state({"c1": contradicted("c1", ["ev_1"])}, {"c1": Stance.REFUTES}, {"c1": ev})
    final, _ = jg.judge(s)
    assert final.classification == MisinfoLabel.DEBUNKING


def test_change2_off_topic_records_are_thin(change2):
    ev = [paper("ev_1", "Potassium and kidney stones"), paper("ev_2", "Vitamin D and falls")]
    s = state({"c1": contradicted("c1", ["ev_1", "ev_2"])}, {"c1": Stance.ENDORSES}, {"c1": ev})
    final, _ = jg.judge(s)
    assert final.classification != MisinfoLabel.MISINFO and "thin_contradiction:c1" in final.review_flags


# ------------------------------------------------------------------ wording


def test_reason_text_calls_the_critic_a_second_automated_check():
    for code in ("second_check_disagreed", "thin_contradiction"):
        assert code in REASON_TEXT
    v = parse_reason("second_check_disagreed:c3")
    assert v.claim_id == "c3" and "second automated check" in v.text and "critic" not in v.text.lower()
    t = parse_reason("judge:thin_contradiction:c2")
    assert t.code == "thin_contradiction" and t.claim_id == "c2"
    assert "critic" not in jg.flag_text("thin_contradiction:c2").lower()
