"""Tests for deterministic validation, the review rule and review persistence
(T09, issue #36, target design §10–§12).

No network, no real model: the explanation writer is a fake ``StepCaller``; the
database is in-memory SQLite.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.graph import judge as jg
from app.core.graph import review_policy as rp
from app.core.graph import routing as r
from app.core.graph import validation as val
from app.core.graph.builder import compile_graph, run_config
from app.core.graph.checkpoint import memory_checkpointer
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    FinalClassification,
    GraphClaim,
    NodeError,
    OcrSegment,
    ReviewStatus,
    Stance,
    StanceResult,
    TranscriptSegment,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.core.schemas.pipeline import MisinfoLabel

S, V = Stance, Verdict
JOB = "job-t09"

# ------------------------------------------------------------------ fixtures


def paper(eid: str, *, types=("Randomized Controlled Trial",), study_type=None) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=eid, source="pubmed", pmid=eid.split("_")[-1], title=f"Paper {eid}",
        abstract="A trial in adults.", publication_type=list(types), study_type=study_type,
    )


def base_state(*rows, duration: Optional[float] = 30.0, judge: bool = True, **extra) -> dict:
    """One claim per row ``(stance, verdict)``: claim cN is said in tN (and shown in oN
    for c1), cites its own paper ev_cN. The judge's real output is filled in."""
    s = initial_state(job_id=JOB, video_id="v1", media_uri="mem://v1", pipeline_version="test",
                      video_duration_seconds=duration)
    claims, stances, verdicts, evidence, transcript = [], {}, {}, {}, []
    for i, (stance, verdict) in enumerate(rows, start=1):
        cid, eid = f"c{i}", f"ev_c{i}"
        t0 = 5.0 * i
        transcript.append(TranscriptSegment(segment_id=f"t{i}", start=t0, end=t0 + 4,
                                            text=f"Claim number {i} cures the flu, believe me."))
        claims.append(GraphClaim(
            claim_id=cid, claim_text=f"Claim number {i} cures the flu", claim_category="treatment_efficacy",
            source_segment_ids=[f"t{i}"], start_seconds=t0, end_seconds=t0 + 4,
        ))
        if stance is not None:
            stances[cid] = StanceResult(claim_id=cid, stance=stance, stance_segment_ids=[f"t{i}"])
        evidence[cid] = [paper(eid)]
        verdicts[cid] = VerificationResult(
            claim_id=cid, verdict=verdict,
            supporting_evidence_ids=[eid] if verdict == V.SUPPORTED else [],
            contradicting_evidence_ids=[eid] if verdict == V.CONTRADICTED else [],
        )
    s.update(transcript_segments=transcript, ocr_segments=[], claims=claims, stance_results=stances,
             verification_results=verdicts, retrieved_evidence=evidence, reranked_evidence=evidence)
    s.update(extra)
    if judge:
        s.update(jg.make_judge_classification()(s))
    return s


def codes(state) -> list[str]:
    return [i.code for i in val.validate(state)]


def checks(state) -> set[str]:
    return {i.check for i in val.validate(state)}


def with_final(state, **update) -> dict:
    return {**state, "final_result": state["final_result"].model_copy(update=update)}


# ------------------------------------------------------------- validation: pass


def test_clean_output_passes_every_check():
    s = base_state((S.ENDORSES, V.CONTRADICTED), (S.REFUTES, V.CONTRADICTED))
    assert val.validate(s) == []


def test_stub_graph_sample_passes_validation():
    out = Harness().run()
    assert out["validation_errors"] == []
    assert out["validation_attempts"] == 1


# ------------------------------------------------------- validation: each rule


def test_schema_label_outside_allowed_set():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    bad = FinalClassification.model_construct(**{**dict(s["final_result"]), "classification": "PROBABLY_FINE"})
    assert any(c.startswith("schema:judge_classification") for c in codes({**s, "final_result": bad}))


def test_schema_unknown_stance_and_dict_records():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["stance_results"] = {"c1": {"claim_id": "c1", "stance": "PROMOTES", "stance_segment_ids": ["t1"]}}
    assert "schema:analyze_stance:c1" in codes(s)


def test_schema_record_stored_under_wrong_claim():
    s = base_state((S.ENDORSES, V.CONTRADICTED), (S.ENDORSES, V.CONTRADICTED))
    s["verification_results"] = {**s["verification_results"], "c2": s["verification_results"]["c1"]}
    assert "schema:verify_claims:c2" in codes(s)


def test_schema_missing_result_wrong_video_and_empty_explanation():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    assert "schema:judge_classification" in codes({k: v for k, v in s.items() if k != "final_result"})
    msgs = [str(i) for i in val.check_schema(with_final(s, video_id="other", explanation=" ", decision_rule=None))]
    assert any("not this run's video" in m for m in msgs)
    assert any("explanation is empty" in m for m in msgs)
    assert any("decision_rule missing" in m for m in msgs)


def test_fabricated_evidence_id_in_verifier_output_is_caught():
    """Issue #36 acceptance criterion: a fabricated evidence ID in model output."""
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    forged = s["verification_results"]["c1"].model_copy(update={"contradicting_evidence_ids": ["ev_c1", "ev_pmid_99999999"]})
    s["verification_results"] = {"c1": forged}
    issues = val.check_citations(s)
    assert [i.code for i in issues] == ["citation_membership:verify_claims:c1"]
    assert "ev_pmid_99999999" in issues[0].message
    assert not issues[0].repairable  # the verifier already had its repair (T06)


def test_fabricated_evidence_id_in_final_result_is_caught_and_repairable():
    s = with_final(base_state((S.ENDORSES, V.CONTRADICTED)), evidence_ids=["ev_c1", "ev_invented"])
    issues = val.check_citations(s)
    assert [i.code for i in issues] == ["citation_membership:judge_classification"]
    assert "any claim" in issues[0].message and issues[0].repairable


def test_citation_retrieved_for_another_claim_is_misattributed():
    s = base_state((S.ENDORSES, V.CONTRADICTED), (S.REFUTES, V.CONTRADICTED))
    v1 = s["verification_results"]["c1"].model_copy(update={"contradicting_evidence_ids": ["ev_c2"]})
    s["verification_results"] = {**s["verification_results"], "c1": v1}
    assert "citation_membership:verify_claims:c1" in codes(s)
    s2 = with_final(base_state((S.ENDORSES, V.CONTRADICTED), (S.REFUTES, V.CONTRADICTED)), evidence_ids=["ev_c2"])
    msg = [str(i) for i in val.check_citations(s2)]
    assert msg and "a deciding claim" in msg[0]


def test_invented_quote_in_explanation_is_caught():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s = with_final(s, explanation=s["final_result"].explanation + ' The speaker also says "stop taking your insulin today".')
    assert codes(s) == ["quote_membership:judge_classification"]


def test_quotes_from_speech_captions_and_claims_pass_case_insensitively():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["ocr_segments"] = [OcrSegment(segment_id="o1", start=5.0, end=8.0, text="HOT WATER = NO FLU", confidence=0.9)]
    s = with_final(s, explanation=(
        'MISINFO because claim c1 ("Claim number 1 cures the flu") is endorsed; the caption reads '
        '"hot water = no flu" and the speaker says “claim number 1 cures the flu, believe me”. "ok"'
    ))
    assert val.check_quotes(s) == []
    # A truncated quote (judge's "…") matches as a prefix.
    s = with_final(s, explanation='MISINFO because "Claim number 1 cures th…" is endorsed.')
    assert val.check_quotes(s) == []


def test_invented_quote_in_stance_rationale_is_caught():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    st = s["stance_results"]["c1"].model_copy(update={"rationale": 'The speaker said "this is definitely a myth".'})
    s["stance_results"] = {"c1": st}
    assert "quote_membership:analyze_stance:c1" in codes(s)


def test_unknown_segment_ids_in_claims_and_stances():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    claim = s["claims"][0].model_copy(update={"source_segment_ids": ["t1", "t99"]})
    stance = s["stance_results"]["c1"].model_copy(update={"stance_segment_ids": ["o42"]})
    s.update(claims=[claim], stance_results={"c1": stance})
    got = codes(s)
    assert "source_ids:extract_claims:c1" in got
    assert "source_ids:analyze_stance:c1" in got


def test_unknown_claim_ids_and_duplicates():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["claims"] = [*s["claims"], s["claims"][0]]
    s["stance_results"] = {**s["stance_results"], "c7": StanceResult(claim_id="c7", stance=S.ENDORSES, stance_segment_ids=["t1"])}
    s = with_final(s, claim_ids=["c1", "c9"])
    msgs = [str(i) for i in val.check_source_ids(s)]
    assert any("duplicate claim_id" in m for m in msgs)
    assert any("unknown claim" in m and "c7" in m for m in msgs)
    assert any("unknown claim 'c9'" in m for m in msgs)


def test_merge_of_speech_and_far_away_caption_is_implausible():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["ocr_segments"] = [OcrSegment(segment_id="o1", start=25.0, end=27.0, text="CLAIM ONE", confidence=0.9)]
    claim = s["claims"][0].model_copy(update={"source_segment_ids": ["t1", "o1"]})
    s["claims"] = [claim]
    assert "merge_plausibility:extract_claims:c1" in codes(s)
    # Within the gap tolerance is fine.
    s["ocr_segments"] = [OcrSegment(segment_id="o1", start=10.5, end=12.0, text="CLAIM ONE", confidence=0.9)]
    assert "merge_plausibility:extract_claims:c1" not in codes(s)


def test_claim_time_outside_its_segments_is_implausible():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["claims"] = [s["claims"][0].model_copy(update={"start_seconds": 20.0, "end_seconds": 22.0})]
    assert "merge_plausibility:extract_claims:c1" in codes(s)


def test_timestamps_order_sign_and_duration():
    s = base_state((S.ENDORSES, V.CONTRADICTED), duration=8.0)
    msgs = [str(i) for i in val.check_timestamps(s)]
    assert any("after the video's 8.00s" in m for m in msgs)  # t1/c1 end at 9 s
    s = base_state((S.ENDORSES, V.CONTRADICTED), duration=None)
    s["claims"] = [s["claims"][0].model_copy(update={"start_seconds": 9.0, "end_seconds": 5.0})]
    s["transcript_segments"] = [*s["transcript_segments"],
                                TranscriptSegment(segment_id="t9", start=-1.0, end=2.0, text="x")]
    msgs = [str(i) for i in val.check_timestamps(s)]
    assert any("not before end" in m and m.startswith("timestamps:extract_claims:c1") for m in msgs)
    assert any("negative time" in m for m in msgs)
    # Without a duration, only order and sign are checked; zero-length segments are fine.
    s = base_state((S.ENDORSES, V.CONTRADICTED), duration=None)
    s["transcript_segments"] = [*s["transcript_segments"], TranscriptSegment(segment_id="t9", start=2.0, end=2.0, text="x")]
    assert val.check_timestamps(s) == []


def test_label_inconsistent_with_rules_is_caught():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    issues = val.check_consistency(with_final(s, classification=MisinfoLabel.NO_MISINFO))
    assert [i.code for i in issues] == ["consistency:judge_classification"]
    assert "rules give MISINFO" in issues[0].message
    issues = val.check_consistency(with_final(s, claim_ids=[]))
    assert issues and "deciding claims" in issues[0].message
    s2 = base_state((S.ENDORSES, V.CONTRADICTED), (S.REFUTES, V.CONTRADICTED))  # mixed video
    issues = val.check_consistency(with_final(s2, review_flags=[]))
    assert issues and "review flags missing" in issues[0].message


def test_length_limits():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s = with_final(s, explanation="MISINFO " + "x" * 2000, limitations=["l"] * 11)
    msgs = [str(i) for i in val.check_lengths(s)]
    assert any("explanation is" in m for m in msgs)
    assert any("11 limitations" in m for m in msgs)
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["stance_results"] = {"c1": s["stance_results"]["c1"].model_copy(update={"rationale": "y" * 600})}
    assert "length_limits:analyze_stance:c1" in codes(s)


def test_issue_strings_round_trip():
    i = val.ValidationIssue(val.CHECK_CITATIONS, r.VERIFY_CLAIMS, "verdict cites 'ev_x': not retrieved", "c1")
    assert val.parse_issue(str(i)) == i
    assert val.parse_issue("evidence ev_x was not retrieved") is None


# ------------------------------------------------------------ repair (graph)


class Harness:
    def __init__(self, overrides=None):
        self.calls: Counter[str] = Counter()
        base = make_stub_nodes()
        base.update(overrides or {})
        self.nodes = {n: self._count(n, f) for n, f in base.items()}

    def _count(self, name, fn):
        def wrapped(state):
            self.calls[name] += 1
            return fn(state)
        return wrapped

    def run(self, **input_extra):
        graph = compile_graph(self.nodes, checkpointer=memory_checkpointer())
        inp = initial_state(job_id=JOB, video_id="vid-1", media_uri="videos/vid-1/video.mp4",
                            pipeline_version="test", **input_extra)
        return graph.invoke(inp, run_config(JOB))


class FakeWriter:
    """Explanation model returning a fixed text."""

    def __init__(self, text: str):
        self.text, self.calls = text, 0

    def call(self, step: str, input: Any, *, system: Optional[str] = None):
        self.calls += 1
        return SimpleNamespace(output={"explanation": self.text},
                               record=SimpleNamespace(model="fake-writer", prompt_version="explain_v1"))


def test_invalid_explanation_is_repaired_once_with_the_template():
    # The model invents a quote. Validation catches it; the judge is re-run once, uses
    # the template (no second model call), and the result passes.
    writer = FakeWriter('MISINFO because the speaker says "garlic water cures every cancer".')
    h = Harness({r.JUDGE_CLASSIFICATION: jg.make_judge_classification(writer)})
    out = h.run()
    assert h.calls[r.JUDGE_CLASSIFICATION] == 2
    assert h.calls[r.VALIDATE_RESULT] == 2
    assert writer.calls == 1
    assert out["validation_attempts"] == 2
    assert out["validation_errors"] == []
    assert out["final_result"].model is None  # template text
    assert not any(x.startswith("validation_failed") for x in out["review_reasons"])


def test_validation_that_fails_again_after_repair_goes_to_review():
    real = make_stub_nodes()[r.JUDGE_CLASSIFICATION]

    def lying_judge(state):
        out = real(state)
        return {"final_result": out["final_result"].model_copy(update={"classification": MisinfoLabel.NO_MISINFO})}

    h = Harness({r.JUDGE_CLASSIFICATION: lying_judge})
    out = h.run()
    assert h.calls[r.JUDGE_CLASSIFICATION] == 2  # one repair, no more
    assert h.calls[r.VALIDATE_RESULT] == 2
    assert out["requires_human_review"] is True
    assert "validation_failed:consistency" in out["review_reasons"]
    assert out["review_status"] == ReviewStatus.REVIEW_REQUIRED
    assert h.calls[r.PERSIST_RESULT] == 1  # persisted as a review case, never as final


def test_upstream_fault_is_not_repaired_and_goes_straight_to_review():
    real = make_stub_nodes()[r.EXTRACT_CLAIMS]

    def bad_claims(state):
        claims = real(state)["claims"]
        return {"claims": [claims[0].model_copy(update={"source_segment_ids": ["t1", "t404"]}), *claims[1:]]}

    h = Harness({r.EXTRACT_CLAIMS: bad_claims})
    out = h.run()
    assert h.calls[r.JUDGE_CLASSIFICATION] == 1
    assert "validation_failed:source_ids:c1" in out["review_reasons"]
    assert h.calls[r.HUMAN_REVIEW] == 1


def test_timestamp_past_duration_goes_to_review():
    out = Harness().run(video_duration_seconds=10.0)  # the sample's speech runs to 12 s
    assert any(x.startswith("validation_failed:timestamps") for x in out["review_reasons"])


def test_validation_cannot_be_bypassed():
    # A graph whose validator was replaced with a no-op that writes nothing still gets
    # a review reason: invalid output never goes straight to the dashboard.
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s.pop("validation_errors", None)
    assert "validation_failed:not_run" in rp.evaluate(s).reasons
    h = Harness({r.VALIDATE_RESULT: lambda state: {}})
    out = h.run()
    assert "validation_failed:not_run" in out["review_reasons"]


def test_repair_router_bounds():
    s = {"validation_errors": ["consistency:judge_classification: wrong label"], "validation_attempts": 1}
    assert r.route_after_validation(s) == r.JUDGE_CLASSIFICATION
    assert r.route_after_validation({**s, "validation_attempts": 2}) == r.ROUTE_FOR_REVIEW
    assert r.route_after_validation({**s, "validation_attempts": 0}) == r.ROUTE_FOR_REVIEW
    assert r.route_after_validation({"validation_errors": [], "validation_attempts": 1}) == r.ROUTE_FOR_REVIEW
    upstream = {"validation_errors": ["source_ids:extract_claims:c1: x"], "validation_attempts": 1}
    assert r.route_after_validation(upstream) == r.ROUTE_FOR_REVIEW


# ------------------------------------------------------------ review rules


CFG = rp.ReviewPolicyConfig(high_risk_categories=frozenset({"treatment_efficacy"}))


def reasons(state, cfg=CFG) -> list[str]:
    st = {**state}
    st.setdefault("validation_errors", [])
    return list(rp.evaluate(st, cfg).reasons)


def test_clean_case_needs_no_review():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    d = rp.evaluate({**s, "validation_errors": []}, CFG)
    assert d.requires_review is False and d.reasons == () and d.fired == {}


def test_rule_weak_evidence_on_abstention():
    s = base_state((S.ENDORSES, V.INSUFFICIENT_EVIDENCE), (S.NEUTRAL, V.MIXED), (S.ENDORSES, V.NOT_VERIFIABLE))
    assert s["final_result"].decision_rule == jg.RULE_NOTHING_JUDGED
    got = rp.rule_weak_evidence(rp.ReviewContext.build(s, CFG, r.DEFAULT_BUDGETS))
    assert got == ["weak_evidence:c1", "weak_evidence:c2"]  # NOT_VERIFIABLE alone doesn't fire


def test_rule_weak_evidence_on_a_deciding_claim():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    v = s["verification_results"]["c1"].model_copy(update={"verdict": V.MIXED, "supporting_evidence_ids": ["ev_c1"]})
    s["verification_results"] = {"c1": v}  # final_result still names c1 as deciding
    assert "weak_evidence:c1" in reasons(s)


def test_no_claims_video_is_not_sent_to_review():
    s = base_state(judge=False)
    s.update(jg.make_judge_classification()(s))
    assert s["final_result"].decision_rule == jg.RULE_NO_CLAIMS
    assert reasons(s) == []


def test_rule_conflicting_evidence():
    s = base_state((S.ENDORSES, V.SUPPORTED))
    s["retrieved_evidence"] = {"c1": [paper("ev_c1"), paper("ev_c1b")]}
    s["reranked_evidence"] = s["retrieved_evidence"]
    v = s["verification_results"]["c1"].model_copy(update={"contradicting_evidence_ids": ["ev_c1b"]})
    s["verification_results"] = {"c1": v}
    s.update(jg.make_judge_classification()(s))
    assert "conflicting_evidence:c1" in reasons(s)


def test_rule_weak_study_types():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    animal = [paper("ev_c1", types=("Journal Article",), study_type="animal")]
    s.update(retrieved_evidence={"c1": animal}, reranked_evidence={"c1": animal})
    assert "weak_study_types:c1" in reasons(s)
    # Untyped by the reranker: publication type is looked up (a case report is weak).
    case = [paper("ev_c1", types=("Case Reports",))]
    s.update(retrieved_evidence={"c1": case}, reranked_evidence={"c1": case})
    assert "weak_study_types:c1" in reasons(s)
    # One human trial among them is enough.
    mixed = [paper("ev_c1", study_type="animal"), paper("ev_c1b", study_type="rct")]
    v = s["verification_results"]["c1"].model_copy(update={"contradicting_evidence_ids": ["ev_c1", "ev_c1b"]})
    s.update(retrieved_evidence={"c1": mixed}, reranked_evidence={"c1": mixed}, verification_results={"c1": v})
    s.update(jg.make_judge_classification()(s))
    assert not any(x.startswith("weak_study_types") for x in reasons(s))


def test_rule_unclear_stance_including_missing_stance():
    s = base_state((S.UNCLEAR, V.SUPPORTED), (None, V.SUPPORTED))
    got = reasons(s)
    assert "unclear_stance:c1" in got and "unclear_stance:c2" in got


def test_rule_critic_escalated():
    s = base_state((S.ENDORSES, V.CONTRADICTED), critic_results={
        "c1": CriticResult(claim_id="c1", decision=CriticDecision.ESCALATE),
    })
    assert "critic_escalated:c1" in reasons(s)
    s["critic_results"] = {"c1": CriticResult(claim_id="c1", decision=CriticDecision.APPROVE, requires_review=True)}
    assert "critic_escalated:c1" in reasons(s)


def test_rule_budget_exhausted():
    s = base_state((S.ENDORSES, V.CONTRADICTED), retrieval_attempts={"c1": 3}, critic_results={
        "c1": CriticResult(claim_id="c1", decision=CriticDecision.RETRIEVE_MORE),
    })
    assert "budget_exhausted:c1" in reasons(s)


def test_rule_validation_failed_names_the_check():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    s["validation_errors"] = [
        "citation_membership:verify_claims:c1: verdict cites 'ev_x'",
        "consistency:judge_classification: wrong label",
        "consistency:judge_classification: wrong rule",
    ]
    got = list(rp.evaluate(s, CFG).reasons)
    assert got[:2] == ["validation_failed:citation_membership:c1", "validation_failed:consistency"]


def test_rule_low_confidence_only_with_a_calibrated_number():
    s = base_state((S.ENDORSES, V.CONTRADICTED))
    assert "low_confidence" not in reasons(s)  # None: uncalibrated, never compared
    assert "low_confidence" in reasons(with_final(s, confidence=0.55))
    assert "low_confidence" not in reasons(with_final(s, confidence=0.70))
    strict = rp.ReviewPolicyConfig(confidence_threshold=0.9)
    assert "low_confidence" in reasons(with_final(s, confidence=0.8), strict)


def test_rule_high_risk_uncertain():
    s = base_state((S.ENDORSES, V.SUPPORTED), (S.ENDORSES, V.NOT_VERIFIABLE), (S.QUOTES, V.INSUFFICIENT_EVIDENCE))
    got = reasons(s)
    assert "high_risk_uncertain:c2" in got
    assert "high_risk_uncertain:c3" not in got  # quoted, not endorsed
    other = rp.ReviewPolicyConfig(high_risk_categories=frozenset({"nutrition"}))
    assert not any(x.startswith("high_risk") for x in reasons(s, other))


def test_judge_flags_and_guardrail_reasons_are_kept():
    s = base_state((S.ENDORSES, V.CONTRADICTED), (S.REFUTES, V.CONTRADICTED))
    s["errors"] = [NodeError(node=r.VERIFY_CLAIMS, claim_id="c1", message="guardrail:fabricated_citation x")]
    got = reasons(s)
    assert "judge:mixed_video" in got
    assert "guardrail:verify_claims:fabricated_citation:c1" in got


def test_every_rule_is_counted_and_reasons_map_back_to_rules():
    s = base_state((S.UNCLEAR, V.SUPPORTED))
    s = with_final(s, confidence=0.1)
    d = rp.evaluate({**s, "validation_errors": ["schema:judge_classification: x"]}, CFG)
    assert {"unclear_stance", "low_confidence", "validation_failed"} <= set(d.fired)
    for rule, rs in d.fired.items():
        assert all(rp.rule_of(x) == rule for x in rs)
    assert rp.rule_of("prompt_injection_suspected:transcript:t3") == "guardrails"


def test_review_policy_config_file_loads():
    cfg = rp.load_review_policy()
    assert cfg.confidence_threshold == pytest.approx(0.70)
    assert {"animal", "in_vitro", "case_report"} == set(cfg.weak_study_types)
    assert "treatment_efficacy" in cfg.high_risk_categories
    with pytest.raises(Exception):
        rp.ReviewPolicyConfig(confidence_threshold=1.5)


def test_review_rule_names_no_model():
    import re as _re

    for mod in (rp, val):
        src = Path(mod.__file__).read_text()
        assert not _re.search(r"claude-|gpt-|gemini", src)


# ------------------------------------------------------------ persistence


@pytest.fixture()
def db():
    from app.db.base import Base
    import app.db.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _job(db, job_id=JOB):
    from app.db.models.job import Job, JobStatus
    from app.db.models.video import Video

    db.add(Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id=job_id, video_id="vid-1", status=JobStatus.STARTED))
    db.commit()


def test_review_required_state_and_reasons_are_persisted(db):
    from app.db.models.job import Job, JobStatus
    from app.db.models.review import HumanReview, ReviewCaseStatus
    from app.services.review_service import open_review_case

    _job(db)
    state = Harness().run()  # the sample is a mixed video → review
    assert state["requires_human_review"]
    case = open_review_case(db, JOB, state)
    db.expire_all()
    stored = db.query(HumanReview).one()
    assert db.get(Job, JOB).status == JobStatus.REVIEW_REQUIRED
    assert stored.status == ReviewCaseStatus.OPEN
    assert stored.reasons == ["judge:mixed_video"]
    assert stored.rules_fired == [{"rule": "judge_flags", "reasons": ["judge:mixed_video"]}]
    assert stored.proposed_label == "MISINFO"
    assert stored.proposed_result["decision_rule"] == "endorsed_contradicted"
    assert stored.policy_version == "review_v1"
    # Idempotent: a re-run refreshes the open case.
    again = open_review_case(db, JOB, {**state, "review_reasons": ["judge:mixed_video", "unclear_stance:c1"]})
    assert again.id == case.id and db.query(HumanReview).count() == 1
    assert again.reasons[-1] == "unclear_stance:c1"


def test_open_review_case_refuses_runs_that_passed(db):
    from app.services.review_service import ReviewError, open_review_case

    _job(db)
    with pytest.raises(ReviewError):
        open_review_case(db, JOB, {"requires_human_review": False})


@pytest.mark.parametrize("action,label,job_status,error_code", [
    ("APPROVE", None, "SUCCESS", None),
    ("CORRECT", "DEBUNKING", "SUCCESS", None),
    ("MARK_INSUFFICIENT", None, "SUCCESS", None),
    ("REJECT", None, "FAILED", "REVIEW_REJECTED"),
    ("REQUEST_REANALYSIS", None, "REVIEW_REQUIRED", None),
])
def test_reviewer_decisions_record_who_when_why(db, action, label, job_status, error_code):
    from app.db.models.job import Job
    from app.db.models.result import Result
    from app.db.models.review import ReviewCaseStatus
    from app.services.review_service import open_review_case, record_review_decision

    _job(db)
    case = open_review_case(db, JOB, Harness().run())
    db.add(Result(job_id=JOB, label="MISINFO", confidence=0.0, explanation="x", evidence_snippets=[],
                  combined_content="", provider="graph", model_used="none", latency_ms=1))
    db.commit()
    done = record_review_decision(db, case.id, reviewer_id="reviewer-1", action=action,
                                  reason="checked the papers", corrected_label=label)
    assert done.status == ReviewCaseStatus.RESOLVED
    assert done.reviewer_id == "reviewer-1" and done.decision_reason == "checked the papers"
    assert done.decided_at is not None and done.action.value == action
    job = db.get(Job, JOB)
    assert job.status.value == job_status and job.error_code == error_code
    result = db.query(Result).one()
    expected = {"CORRECT": "DEBUNKING", "MARK_INSUFFICIENT": "CANNOT_RECOGNIZE"}.get(action, "MISINFO")
    assert result.label == expected


def test_reviewer_decision_rules(db):
    from app.services.review_service import ReviewError, open_review_case, record_review_decision

    _job(db)
    case = open_review_case(db, JOB, Harness().run())
    with pytest.raises(ReviewError, match="reason"):
        record_review_decision(db, case.id, reviewer_id="r1", action="APPROVE", reason="  ")
    with pytest.raises(ReviewError, match="CORRECT needs"):
        record_review_decision(db, case.id, reviewer_id="r1", action="CORRECT", reason="x")
    with pytest.raises(ValueError):
        record_review_decision(db, case.id, reviewer_id="r1", action="CORRECT", reason="x", corrected_label="FAKE")
    with pytest.raises(ReviewError, match="does not take"):
        record_review_decision(db, case.id, reviewer_id="r1", action="APPROVE", reason="x", corrected_label="MISINFO")
    record_review_decision(db, case.id, reviewer_id="r1", action="APPROVE", reason="fine")
    with pytest.raises(ReviewError, match="already resolved"):
        record_review_decision(db, case.id, reviewer_id="r2", action="REJECT", reason="no")
    with pytest.raises(ReviewError, match="already resolved"):
        open_review_case(db, JOB, Harness().run())


def test_migration_0007_upgrades_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "app" / "db" / "migrations"))
    command.upgrade(cfg, "0007")
    insp = inspect(create_engine(url))
    cols = {c["name"] for c in insp.get_columns("human_reviews")}
    assert {"job_id", "status", "reasons", "rules_fired", "reviewer_id", "action", "decision_reason", "decided_at"} <= cols
    command.downgrade(cfg, "0006")
    assert "human_reviews" not in inspect(create_engine(url)).get_table_names()


def test_job_status_has_review_required():
    from app.db.models.job import JobStatus

    assert JobStatus("REVIEW_REQUIRED") is JobStatus.REVIEW_REQUIRED
