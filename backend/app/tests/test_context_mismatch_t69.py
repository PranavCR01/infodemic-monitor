"""T69: a thin, context-mismatched contradiction can't decide MISINFO alone (design §7, §9).

Switch: ``routing.CONTEXT_MISMATCH_RULE`` (default OFF; the lead turns it on). The v135
production fixture (jobs cf2ea579 / f85f2daa) was not in the repo when this was built, so
``v135_state`` below is a SYNTHETIC stand-in shaped on the queue row's description and the
golden set's own v135 claims (golden NO_MISINFO): c4 "Benzene doesn't get through skin
easily" ENDORSES + CONTRADICTED by two narrative reviews of occupational solvent exposure,
the other claims SUPPORTED. Titles are placeholders, not real papers. No model calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.graph import judge as jg
from app.core.graph import review_policy as rp
from app.core.graph import routing as r
from app.core.graph import verifier as vf
from app.core.graph.state import (
    EvidenceRecord,
    GraphClaim,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.core.schemas.pipeline import MisinfoLabel
from app.services.review_reasons import REASON_TEXT, parse_reason

SETTING = f"{r.CONTEXT_MISMATCH_LIMITATION}:different_exposure_setting"
POPULATION = f"{r.CONTEXT_MISMATCH_LIMITATION}:different_population"
REASON = "judge:contradiction_context_mismatch:c4"


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(r, "CONTEXT_MISMATCH_RULE", True)


def gclaim(cid: str, text: str, category: str = "mechanism") -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                      source_segment_ids=["t1"], start_seconds=0.0, end_seconds=4.0)


def paper(eid: str, ptypes=("Review",), title: str = "Benzene exposure in solvent workers: a review",
          abstract: str = "") -> EvidenceRecord:
    return EvidenceRecord(evidence_id=eid, source="pubmed", pmid=eid.split("_")[-1], title=title,
                          abstract=abstract, publication_type=list(ptypes))


SUPPORTED_SIDE = {
    "c1": "most of them are quite low, but a few might have about 20 parts per million",
    "c3": "benzene is a known carcinogen and little bits add up to increase your risk of cancer",
    "c5": "Benzoyl peroxide has been used for acne for 60 years with no recorded increased cancer",
}


def v135_state(*, c4_limitations=(SETTING, "the reviews study occupational solvent exposure"),
               c4_papers=None, c4_stance=Stance.ENDORSES, extra: dict | None = None) -> dict:
    """SYNTHETIC v135 stand-in (see module docstring)."""
    c4_papers = c4_papers if c4_papers is not None else [paper("ev_101"), paper("ev_102")]
    claims = [gclaim(cid, text) for cid, text in SUPPORTED_SIDE.items()]
    claims.append(gclaim("c4", "Benzene doesn't get through skin easily"))
    evidence = {cid: [paper(f"ev_{cid}", ("Journal Article", "Observational Study"), title="Benzene levels")]
                for cid in SUPPORTED_SIDE}
    evidence["c4"] = c4_papers
    verdicts = {cid: VerificationResult(claim_id=cid, verdict=Verdict.SUPPORTED, supporting_evidence_ids=[f"ev_{cid}"])
                for cid in SUPPORTED_SIDE}
    verdicts["c4"] = VerificationResult(
        claim_id="c4", verdict=Verdict.CONTRADICTED,
        contradicting_evidence_ids=[e.evidence_id for e in c4_papers], limitations=list(c4_limitations))
    stances = {cid: Stance.ENDORSES for cid in SUPPORTED_SIDE} | {"c4": c4_stance}
    for cid, (text, verdict, stance, papers) in (extra or {}).items():
        claims.append(gclaim(cid, text))
        evidence[cid] = papers
        verdicts[cid] = VerificationResult(claim_id=cid, verdict=verdict,
                                           contradicting_evidence_ids=[e.evidence_id for e in papers])
        stances[cid] = stance
    s = initial_state(job_id="j69", video_id="v135", media_uri="mem://v135", pipeline_version="test")
    s.update(
        claims=claims,
        stance_results={cid: StanceResult(claim_id=cid, stance=st, stance_segment_ids=["t1"]) for cid, st in stances.items()},
        retrieved_evidence=evidence, reranked_evidence=evidence,
        retrieval_attempts={c.claim_id: 3 for c in claims},
        verification_results=verdicts,
    )
    return s


def run(state: dict):
    final, errors = jg.judge(state)
    assert not errors
    state = dict(state, final_result=final, validation_errors=[])
    return final, rp.evaluate(state)


# ------------------------------------------------------------------ shipped state


def test_switch_ships_off():
    assert r.CONTEXT_MISMATCH_RULE is False


def test_off_v135_stays_misinfo_as_in_production():
    final, review = run(v135_state())
    assert final.classification == MisinfoLabel.MISINFO and final.claim_ids == ["c4"]
    assert REASON not in review.reasons


def test_off_verifier_request_is_unchanged():
    assert vf.verify_tool() is vf.VERIFY_TOOL
    assert "evidence_context" not in vf.VERIFY_TOOL["input_schema"]["properties"]
    prompt = vf.build_prompt(gclaim("c4", "Benzene doesn't get through skin easily"), [paper("ev_1")], "system")
    assert "evidence_context" not in prompt.render()
    assert vf.build_request(prompt)["tools"] == [vf.VERIFY_TOOL]


# ------------------------------------------------------------------ rule on


def test_on_v135_goes_to_review_instead_of_misinfo(on):
    final, review = run(v135_state())
    assert final.classification == MisinfoLabel.NO_MISINFO  # golden label; falls through to rule 5
    assert "c4" not in final.claim_ids
    assert review.requires_review and REASON in review.reasons
    assert final.misinfo_basis is None


def test_on_population_mismatch_also_counts(on):
    final, review = run(v135_state(c4_limitations=(POPULATION,)))
    assert final.classification != MisinfoLabel.MISINFO and REASON in review.reasons


def test_on_falls_through_to_cannot_recognize_when_nothing_else_is_judged(on):
    s = v135_state()
    for cid in SUPPORTED_SIDE:
        s["verification_results"][cid] = VerificationResult(claim_id=cid, verdict=Verdict.INSUFFICIENT_EVIDENCE)
    final, review = run(s)
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE and REASON in review.reasons


@pytest.mark.parametrize("ptypes", [
    ("Journal Article", "Randomized Controlled Trial"),
    ("Systematic Review",),
    ("Meta-Analysis",),
    ("Practice Guideline",),
    ("Journal Article", "Observational Study"),  # a primary human study
    ("Case Reports",),
    ("Clinical Trial",),
])
def test_on_any_primary_or_strong_record_keeps_misinfo(on, ptypes):
    final, review = run(v135_state(c4_papers=[paper("ev_101"), paper("ev_102", ptypes)]))
    assert final.classification == MisinfoLabel.MISINFO and final.claim_ids == ["c4"]
    assert REASON not in review.reasons


def test_on_lab_or_modelling_records_count_like_narrative_reviews(on):
    model = paper("ev_103", ("Journal Article",), title="An in silico model of dermal benzene uptake",
                  abstract="We built an in silico model of skin permeation.")
    final, review = run(v135_state(c4_papers=[paper("ev_101"), model]))
    assert final.classification == MisinfoLabel.NO_MISINFO and REASON in review.reasons


def test_on_untyped_record_is_not_assumed_narrative(on):
    untyped = paper("ev_104", ("Journal Article",), title="Benzene and workers")
    final, _ = run(v135_state(c4_papers=[paper("ev_101"), untyped]))
    assert final.classification == MisinfoLabel.MISINFO


@pytest.mark.parametrize("limitations", [
    (),  # verifier said nothing structured
    (f"{r.CONTEXT_MISMATCH_LIMITATION}:matches",),
    ("the reviews study a different exposure setting: occupational solvent exposure, not skin",),  # prose only
    ("different_exposure_setting",),  # bare word, not the code
    (f"{r.CONTEXT_MISMATCH_LIMITATION}:somewhere_else",),  # unknown kind
])
def test_on_needs_the_structured_code_never_prose(on, limitations):
    final, review = run(v135_state(c4_limitations=limitations))
    assert final.classification == MisinfoLabel.MISINFO and REASON not in review.reasons


def test_on_not_when_a_second_endorsed_claim_is_contradicted(on):
    other = ("Sunscreen causes cancer", Verdict.CONTRADICTED, Stance.ENDORSES,
             [paper("ev_201", ("Systematic Review",), title="Sunscreen and cancer")])
    final, review = run(v135_state(extra={"c6": other}))
    assert final.classification == MisinfoLabel.MISINFO and set(final.claim_ids) == {"c4", "c6"}
    assert REASON not in review.reasons


def test_on_not_when_the_other_contradicted_claim_is_also_mismatched(on):
    # Two mismatched contradictions: c4 is not the ONLY deciding claim, so no set-aside.
    s = v135_state(extra={"c6": ("Benzene is not absorbed by inhalation", Verdict.CONTRADICTED, Stance.ENDORSES,
                                 [paper("ev_202")])})
    s["verification_results"]["c6"] = s["verification_results"]["c6"].model_copy(update={"limitations": [SETTING]})
    final, _ = run(s)
    assert final.classification == MisinfoLabel.MISINFO and set(final.claim_ids) == {"c4", "c6"}


def test_on_debunking_rule_is_untouched(on):
    final, review = run(v135_state(c4_stance=Stance.REFUTES))
    assert final.classification == MisinfoLabel.DEBUNKING and final.claim_ids == ["c4"]
    assert REASON not in review.reasons


def test_on_other_misinfo_rules_still_decide(on):
    # A claim the speaker denies although supported still makes the video MISINFO.
    s = v135_state()
    s["stance_results"]["c3"] = StanceResult(claim_id="c3", stance=Stance.REFUTES, stance_segment_ids=["t1"])
    final, review = run(s)
    assert final.classification == MisinfoLabel.MISINFO and final.misinfo_basis == jg.BASIS_DENIES_SUPPORTED
    assert REASON in review.reasons  # the set-aside is still shown to the reviewer


def test_reconciled_with_t67_thin_rule_one_mechanism(on, monkeypatch):
    # Thin (one off-topic record) and mismatched: T67's flag is applied first, one reason only.
    monkeypatch.setattr(jg, "THIN_CONTRADICTION_RULE", True)
    off_topic = paper("ev_301", title="Solvent workers' health", abstract="Occupational exposure.")
    final, review = run(v135_state(c4_papers=[off_topic]))
    assert final.classification == MisinfoLabel.NO_MISINFO
    assert "judge:thin_contradiction:c4" in review.reasons and REASON not in review.reasons
    # Not thin (two on-topic reviews): only T69's rule applies.
    final, review = run(v135_state())
    assert REASON in review.reasons and "judge:thin_contradiction:c4" not in review.reasons


def test_set_aside_reason_is_none_when_both_switches_off():
    s = v135_state()
    views, _ = jg.claim_views(s)
    c4 = next(v for v in views if v.claim_id == "c4")
    assert jg.context_mismatched_contradiction(c4)  # the pattern is detectable...
    assert jg.set_aside_reason(c4, sole_endorsed_contradicted=True) is None  # ...but nothing acts on it


# ------------------------------------------------------------------ verifier field


class Caller:
    def __init__(self, answer: dict):
        self.answer, self.calls = answer, []

    def call(self, step, input, *, system=None):
        self.calls.append(input)
        return SimpleNamespace(output=self.answer, record=SimpleNamespace(model="mock", prompt_version="verify_v3"))


def _answer(**kw) -> dict:
    return {"verdict": "CONTRADICTED", "supporting_evidence_ids": [], "contradicting_evidence_ids": ["ev_1"],
            "explanation": "Reviews of solvent workers find benzene is absorbed through skin.",
            "limitations": ["occupational setting"], "raw_confidence": 0.6, **kw}


CLAIM = gclaim("c4", "Benzene doesn't get through skin easily")


def test_on_verifier_offers_the_field_and_records_the_code(on):
    caller = Caller(_answer(evidence_context="different_exposure_setting"))
    out, errors = vf.verify_claim(CLAIM, [paper("ev_1")], caller, "system", "verify_v3")
    assert not [e for e in errors if "guardrail" in e.message]
    assert out.verdict == Verdict.CONTRADICTED and out.limitations[-1] == SETTING
    req = caller.calls[0]
    props = req["tools"][0]["input_schema"]["properties"]
    assert props["evidence_context"]["enum"] == list(r.EVIDENCE_CONTEXT_VALUES)
    assert "evidence_context" not in req["tools"][0]["input_schema"]["required"]
    assert "evidence_context" in req["messages"][0]["content"]
    assert "evidence_context" not in vf.VERIFY_TOOL["input_schema"]["properties"]  # constant not mutated


@pytest.mark.parametrize("answer", [
    _answer(evidence_context="matches"),
    _answer(),
    _answer(verdict="SUPPORTED", supporting_evidence_ids=["ev_1"], contradicting_evidence_ids=[],
            evidence_context="different_population"),
])
def test_on_no_code_unless_contradicted_and_mismatched(on, answer):
    out, _ = vf.verify_claim(CLAIM, [paper("ev_1")], Caller(answer), "system", "verify_v3")
    assert not [x for x in out.limitations if x.startswith(r.CONTEXT_MISMATCH_LIMITATION)]


def test_off_a_stray_field_records_nothing():
    out, _ = vf.verify_claim(CLAIM, [paper("ev_1")], Caller(_answer(evidence_context="different_population")),
                             "system", "verify_v3")
    assert out.verdict == Verdict.CONTRADICTED
    assert out.limitations == ["occupational setting"]


def test_on_verifier_code_feeds_the_judge_end_to_end(on):
    out, _ = vf.verify_claim(CLAIM, [paper("ev_101"), paper("ev_102")],
                             Caller(_answer(contradicting_evidence_ids=["ev_101", "ev_102"],
                                            evidence_context="different_exposure_setting")),
                             "system", "verify_v3")
    s = v135_state()
    s["verification_results"]["c4"] = out
    final, review = run(s)
    assert final.classification == MisinfoLabel.NO_MISINFO and REASON in review.reasons


# ------------------------------------------------------------------ wording


def test_review_reason_text_is_plain():
    assert "contradiction_context_mismatch" in REASON_TEXT
    t = parse_reason(REASON)
    assert t.code == "contradiction_context_mismatch" and t.claim_id == "c4"
    assert "c4" not in t.text and "_" not in t.text
    assert "different" in jg.flag_text("contradiction_context_mismatch:c4")
    assert rp.rule_of(REASON) == "judge_flags"  # counted with the other judge flags (§12)


def test_frontend_vocabulary_has_the_reason():
    vocab = (Path(__file__).resolve().parents[3] / "frontend" / "lib" / "vocabulary.ts")
    if not vocab.exists():
        pytest.skip("frontend not checked out")
    assert "contradiction_context_mismatch" in vocab.read_text()


# ------------------------------------------------------------------ T67-fixed regression


def test_on_t67_3d48e75e_still_cannot_recognize(on):
    from app.tests.test_label_rules_t67 import state_from_3d48e75e

    final, _ = jg.judge(state_from_3d48e75e()[0])
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert final.decision_rule == jg.RULE_ANALYSIS_INCOMPLETE


def test_on_t64_d2bf4179_unchanged(on):
    """The real d2bf4179 rows (T64's regression) through the verify node, judge and review
    rule with the switch on: same label as with it off (NO_MISINFO, T64's fix)."""
    from app.tests import test_unproven_fixes_t64 as t64

    labels = {}
    for flag in (False, True):
        r.CONTEXT_MISMATCH_RULE = flag
        try:
            s = t64.run_job(t64.node_with(ug_guard, sibling=True))
        finally:
            r.CONTEXT_MISMATCH_RULE = True
        labels[flag] = (s["final_result"].classification, tuple(s["review_reasons"]))
    assert labels[True] == labels[False]
    assert labels[True][0] == MisinfoLabel.NO_MISINFO


def ug_guard(c, ev, res):
    from app.core.graph import unproven_guard as ug

    return ug.apply_unproven_guard(c, ev, res)
