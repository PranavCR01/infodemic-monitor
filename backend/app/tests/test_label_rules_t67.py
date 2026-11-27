"""T67: critic-budget verdicts, thin contradictions, analysis_incomplete (design §8, §9, §11).

Changes 1 and 2 failed the T67 replay gate (evals/reports/T67/report.md) and ship OFF:
``routing.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED`` and ``judge.THIN_CONTRADICTION_RULE``
are False. These tests pin the default (the T07 / T64 behaviour) and exercise each code
path switched on, so a lead decision to turn one on is a one-line change. Change 3
(``judge.ANALYSIS_INCOMPLETE_RULE``, lead addendum) passed and ships ON; its regression is
production job 3d48e75e (verifier unreachable for 10 of 11 claims). No model calls.
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


# ------------------------------------------------------------------ shipped state


def test_shipped_state_change1_on_change2_off():
    # Change 1 on by lead decision (2026-11-27); change 2 off (made v88, v119, v177 worse).
    assert r.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED is True
    assert jg.THIN_CONTRADICTION_RULE is False


def exhausted_state(errors=(), con=("ev_1",), evidence=None) -> dict:
    ev = evidence if evidence is not None else {"c1": [paper("ev_1")]}
    return state({"c1": contradicted("c1", con)}, {"c1": Stance.ENDORSES}, ev,
                 critic={"c1": CriticDecision.RETRIEVE_MORE}, errors=errors)


def test_withdrawal_mode_withdraws_the_objected_verdict_as_before(monkeypatch):
    monkeypatch.setattr(r, "KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED", False)
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


# ------------------------------------------------------------------ change 3 (on): analysis_incomplete

import json  # noqa: E402
from pathlib import Path  # noqa: E402

FIXTURE_3D48 = Path(__file__).parent / "fixtures" / "prod_3d48e75e" / "vitamin_k_verifier_down.report.json"


def state_from_3d48e75e() -> dict:
    """The coordinator's fixture of production job 3d48e75e (built from its exported report,
    see ``_provenance``) as judge input. Only the fixture's own fields are used: claim text,
    stance, verdict, cited records, and ``verification_failed`` as the pipeline records it
    (a retryable ``verify_claims`` error for the claim)."""
    raw = json.loads(FIXTURE_3D48.read_text())
    claims, stances, verdicts, evidence, errors = [], {}, {}, {}, []
    for c in raw["claims"]:
        cid = c["claim_id"]
        claims.append(GraphClaim(claim_id=cid, claim_text=c["text"], claim_category="unknown",
                                 source_segment_ids=["t1"], start_seconds=c["start_seconds"],
                                 end_seconds=c["end_seconds"]))
        stances[cid] = StanceResult(claim_id=cid, stance=Stance(c["stance"]), stance_segment_ids=["t1"])
        recs = [EvidenceRecord(evidence_id=f"ev_{e['pmid']}", source="pubmed", pmid=e["pmid"], title=e["title"],
                               study_type=e.get("study_type") or "unknown") for e in c.get("evidence") or []]
        evidence[cid] = recs
        sup = [r.evidence_id for r, e in zip(recs, c.get("evidence") or []) if e.get("relation") == "SUPPORTS"]
        con = [r.evidence_id for r, e in zip(recs, c.get("evidence") or []) if e.get("relation") == "CONTRADICTS"]
        verdicts[cid] = VerificationResult(claim_id=cid, verdict=Verdict(c["verdict"]), limitations=c["limitations"],
                                           supporting_evidence_ids=sup, contradicting_evidence_ids=con)
        if c.get("verification_failed"):
            errors.append(NodeError(node=r.VERIFY_CLAIMS, claim_id=cid, retryable=True,
                                    message="model call failed: BadRequestError: credit balance too low"))
    s = initial_state(job_id="3d48e75e", video_id="vk", media_uri="mem://vk", pipeline_version="test")
    s.update(claims=claims, stance_results=stances, verification_results=verdicts, retrieved_evidence=evidence,
             reranked_evidence=evidence, retrieval_attempts={c.claim_id: 1 for c in claims}, errors=errors)
    return s, raw


def test_3d48e75e_reproduces_production_without_the_rule(monkeypatch):
    monkeypatch.setattr(jg, "ANALYSIS_INCOMPLETE_RULE", False)
    s, raw = state_from_3d48e75e()
    final, _ = jg.judge(s)
    assert final.classification.value == raw["production_label"] == "NO_MISINFO"
    assert final.decision_rule == raw["production_rule"]


def test_3d48e75e_is_cannot_recognize_analysis_incomplete():
    assert jg.ANALYSIS_INCOMPLETE_RULE is True  # passed the T67 gate; ships on
    s, raw = state_from_3d48e75e()
    final, errors = jg.judge(s)
    assert not errors
    assert raw["expected_after_T67"] == "CANNOT_RECOGNIZE (analysis_incomplete)"
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert final.decision_rule == jg.RULE_ANALYSIS_INCOMPLETE and final.claim_ids == []
    assert "analysis_incomplete" in final.review_flags
    assert "10 of 11 claims" in final.explanation
    s["final_result"], s["validation_errors"] = final, []
    d = rp.evaluate(s)
    assert d.requires_review and "judge:analysis_incomplete" in d.reasons
    assert parse_reason("judge:analysis_incomplete").text == REASON_TEXT["analysis_incomplete"]


def _failed_state(n_failed: int, n: int, extra_verdict=Verdict.CONTRADICTED) -> dict:
    verdicts = {f"c{i}": VerificationResult(claim_id=f"c{i}", verdict=Verdict.INSUFFICIENT_EVIDENCE)
                for i in range(1, n_failed + 1)}
    for i in range(n_failed + 1, n + 1):
        verdicts[f"c{i}"] = contradicted(f"c{i}", ["ev_1"])
    errors = [NodeError(node=r.VERIFY_CLAIMS, claim_id=f"c{i}", message="model call failed", retryable=True)
              for i in range(1, n_failed + 1)]
    return state(verdicts, {cid: Stance.ENDORSES for cid in verdicts},
                 {cid: [paper("ev_1")] for cid in verdicts}, errors=errors)


@pytest.mark.parametrize("n_failed, n, incomplete", [(1, 2, True), (2, 4, True), (1, 3, False), (0, 2, False)])
def test_analysis_incomplete_threshold_is_half(n_failed, n, incomplete):
    final, _ = jg.judge(_failed_state(n_failed, n))
    assert (final.decision_rule == jg.RULE_ANALYSIS_INCOMPLETE) is incomplete
    assert final.classification == (MisinfoLabel.CANNOT_RECOGNIZE if incomplete else MisinfoLabel.MISINFO)


def test_analysis_incomplete_ignores_a_repair_that_succeeded():
    s = _failed_state(0, 2)
    s["errors"] = [NodeError(node=r.VERIFY_CLAIMS, claim_id="c1", message="repair requested: x")]
    assert jg.judge(s)[0].decision_rule != jg.RULE_ANALYSIS_INCOMPLETE
