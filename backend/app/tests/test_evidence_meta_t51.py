"""T51: statements about study design, quality or quantity are not efficacy claims.

Production job 5cc07f48 ("Download (4).mp4", vitamin K video, 2026-11-26), real rows
(``vitamin_k_job.real.json``, copied from production by the coordinating session; T50
replaced T49's reconstructed fixture). c12 "the studies are observational, so they
cannot prove that every bleeding event was caused by skipping vitamin K" asserts no
effect: category ``evidence_meta`` (prompt extract_v4, plus fixed rules that override
the model for every prompt version), never UNSUPPORTED. c13 "the evidence supporting
the preventive vitamin K injection for newborns is overwhelming" is, after the PR #122
review, an efficacy claim in an evidence wrapper: it keeps its efficacy category and
stays eligible for UNSUPPORTED, and T49's on-topic guard is what stops its empty search
from producing it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.claim_category import EVIDENCE_META, is_evidence_meta, is_support_statement, resolve_claim_category
from app.core.graph import claims as cl
from app.core.graph import judge as jg
from app.core.graph import routing as r
from app.core.graph import verifier as vf
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.stance import load_prompt
from app.core.graph.unproven_guard import OFF_TOPIC_LIMITATION
from app.core.graph.state import (
    FusedSegment,
    GraphClaim,
    Stance,
    StanceResult,
    TranscriptSegment,
    Verdict,
    initial_state,
)
from app.core.graph.validation import validate
from app.core.schemas.pipeline import MisinfoLabel
from app.evaluation.routing_experiment.items import efficacy_category
from app.tests.vitamin_k_fixture import evidence_of, load_real, stance_of, verifier_answer

def job() -> dict:
    return load_real()


def prod_claim(cid: str) -> dict:
    return next(c for c in job()["claims"] if c["claim_id"] == cid)


C12 = prod_claim("c12")["text"]
C13 = prod_claim("c13")["text"]


def test_fixture_is_the_real_job_and_c13_was_tagged_as_efficacy():
    j = job()
    assert j["_provenance"].startswith("COPIED FROM PRODUCTION")
    assert C12.startswith("the studies are observational")
    assert C13 == "the evidence supporting the preventive vitamin K injection for newborns is overwhelming"
    assert prod_claim("c13")["category"] == "treatment_efficacy"
    assert prod_claim("c13")["verdict"] == "UNSUPPORTED"


# ------------------------------------------------------------------ the fixed rules

EVIDENCE_STATEMENTS = [
    C12,
    "These studies on newborns are observational",
    "the sample was small",
    "it's only one study",
    "the trials weren't randomised",
    "the evidence that turmeric cures cancer is weak",
    "The research on turmeric is still very preliminary",
    "There is little good evidence for detox teas",
    "there's no evidence that energy drinks cause strokes",
    "That was just a mouse study",
    "The study was funded by the sugar industry",
    "This supplement has never been tested in humans",
    "the data we have is weak",
    "Most of these trials were small",
    "Les études sont observationnelles",
    "Hay pocos estudios sobre el colágeno",
]

# Support statements and reported findings: an efficacy claim in an evidence wrapper
# keeps its category, so an unproven remedy can't escape UNSUPPORTED by saying "the
# evidence is overwhelming" or "studies show" (PR #122 review).
SUPPORT_STATEMENTS = [
    C13,
    "the evidence supporting this preventive injection is overwhelming",
    "the evidence for this detox tea is overwhelming",
    "the evidence that turmeric cures cancer is overwhelming",
    "There is overwhelming evidence that garlic kills viruses",
    "La evidencia es abrumadora",
    "Studies show that almonds can help you lose weight",
    "Clinically proven to cure acne",
]

NOT_EVIDENCE_STATEMENTS = [*SUPPORT_STATEMENTS,
    "Studies show that almonds can help you lose weight",
    "this study didn't find higher benzene levels in people who use sunscreen",
    "Clinically proven to cure acne",
    "Research proves garlic kills viruses",
    "The evidence is clear that sugar causes cancer",
    "The proof is clear: garlic kills cancer",
    "Research shows turmeric is strong medicine",
    "The study was done in 2018 and found that coffee prevents cancer",
    "Vitamin K helps keep calcium in your bones and prevents osteoporosis",
    "Ginger is a strong anti-inflammatory",
    "Your immune system is weak",
    "The vaccine is safe and effective",
    "",
]


@pytest.mark.parametrize("text", EVIDENCE_STATEMENTS)
def test_evidence_statements_are_recognised(text):
    assert is_evidence_meta(text)


@pytest.mark.parametrize("text", NOT_EVIDENCE_STATEMENTS)
def test_reported_findings_and_plain_claims_are_not(text):
    assert not is_evidence_meta(text)


@pytest.mark.parametrize("text", SUPPORT_STATEMENTS)
def test_support_statements_keep_an_efficacy_category_even_if_the_model_says_evidence_meta(text):
    assert is_support_statement(text)
    assert resolve_claim_category(EVIDENCE_META, text, cl.CATEGORIES) in r.UNPROVEN_CATEGORIES


def test_rules_override_the_model_category():
    known = cl.CATEGORIES
    assert resolve_claim_category("other", C12, known) == EVIDENCE_META
    assert resolve_claim_category("treatment_efficacy", C12, known) == EVIDENCE_META
    assert resolve_claim_category("treatment_efficacy", C13, known) == "treatment_efficacy"  # production's tag
    assert resolve_claim_category(EVIDENCE_META, C13, known) == "prevention"  # the implied effect
    assert resolve_claim_category(EVIDENCE_META, "the evidence for this detox tea is overwhelming",
                                  known) == "treatment_efficacy"
    assert resolve_claim_category("prevention", "Vitamin K prevents bleeding", known) == "prevention"
    assert resolve_claim_category("bogus", "Vitamin K prevents bleeding", known) == "other"
    # A model may tag evidence_meta where the rules don't fire; it is kept.
    assert resolve_claim_category(EVIDENCE_META, "Nobody has looked at this properly", known) == EVIDENCE_META


def test_prompt_examples_agree_with_the_rules():
    for text in ["these trials were tiny", "the sample was small", "it's only one study",
                 "the trials weren't randomised", "that was a rat study",
                 "the research on cold plunges is still thin", "the study was paid for by a juice company",
                 "this powder has never been tested in people", "there is very little good data on collagen"]:
        assert is_evidence_meta(text), text
    for text in ["The evidence that flossing prevents gum disease is strong",
                 "the evidence for this sleep spray is overwhelming",
                 "there is clear evidence that zinc lozenges shorten colds",
                 "studies show beetroot juice lowers blood pressure", "clinically proven to clear acne"]:
        assert not is_evidence_meta(text) and is_support_statement(text), text


# ------------------------------------------------------------------ prompts and requests


def test_extract_v4_describes_evidence_meta_and_v3_is_unchanged():
    v4 = " ".join(load_prompt("extract_v4").split())
    v3 = " ".join(load_prompt("extract_v3").split())
    assert "evidence_meta" in v4 and "evidence_meta" not in v3
    assert "design, quality or quantity of the evidence that assert no effect" in v4
    assert "Not evidence_meta: a statement that the evidence FOR something is strong" in v4
    # v4 is v3 plus the evidence_meta section: every v3 rule is still there.
    for rule in ("Quote in the original language", "State the myth, not the correction",
                 "One predicate with a list of objects or outcomes is ONE claim"):
        assert rule in v3 and rule in v4
    # The examples are invented, not golden-set text.
    assert C13.lower() not in v4.lower() and C12.lower() not in v4.lower()


class StepCaller:
    def __init__(self, outputs, prompt="extract_v4"):
        self.outputs = list(outputs)
        self.calls: list = []
        self.prompt = prompt

    def route(self, step):
        return SimpleNamespace(prompt=self.prompt)

    def call(self, step, input, *, system=None):
        self.calls.append(SimpleNamespace(step=step, input=input, system=system))
        return SimpleNamespace(output=self.outputs.pop(0), record=SimpleNamespace(model="m", prompt_version=self.prompt))


def seg(i: int, text: str, start: float) -> tuple[FusedSegment, TranscriptSegment]:
    return (FusedSegment(segment_id=f"f{i}", start=start, end=start + 6, spoken=text, sources=[f"t{i}"]),
            TranscriptSegment(segment_id=f"t{i}", start=start, end=start + 6, text=text))


def extract(prompt: str, model_categories: tuple[str, str]):
    """Run the extractor on c12/c13 with a scripted model that tags them as production
    did (c12 other, c13 treatment_efficacy) unless told otherwise."""
    (f12, t12), (f13, t13) = seg(12, C12, 80.0), seg(13, C13, 87.0)
    caller = StepCaller([{"claims": [
        {"claim_text": C12, "claim_category": model_categories[0], "source_segment_ids": ["f12"],
         "claim_kind": "research_question"},
        {"claim_text": C13, "claim_category": model_categories[1], "source_segment_ids": ["f13"],
         "claim_kind": "research_question"},
    ]}], prompt=prompt)
    state = {"fused_segments": [f12, f13], "transcript_segments": [t12, t13], "ocr_segments": []}
    return cl.make_extract_claims(caller)(state), caller


@pytest.mark.parametrize("prompt", ["extract_v2", "extract_v3", "extract_v4"])
def test_extractor_tags_c12_evidence_meta_and_c13_keeps_its_efficacy_category(prompt):
    out, caller = extract(prompt, ("treatment_efficacy", "treatment_efficacy"))
    cats = {c.claim_text: c.claim_category for c in out["claims"]}
    assert cats == {C12: EVIDENCE_META, C13: "treatment_efficacy"}
    assert all(c.claim_kind == "research_question" for c in out["claims"])
    # Only extract_v4 explains evidence_meta to the model; the rules cover older prompts.
    assert ("evidence_meta" in caller.calls[0].system) == (prompt == "extract_v4")


def test_tool_enum_offers_evidence_meta_only_from_extract_v4():
    def enum(caller):
        tool = caller.calls[0].input["tools"][0]
        return tool["input_schema"]["properties"]["claims"]["items"]["properties"]["claim_category"]["enum"]

    _, v3 = extract("extract_v3", ("other", "other"))
    _, v4 = extract("extract_v4", ("evidence_meta", "evidence_meta"))
    assert enum(v3) == list(cl.LEGACY_CATEGORIES)
    assert v3.calls[0].input["tools"][0] == cl.EXTRACT_TOOL  # older prompts: same request as before
    assert enum(v4) == list(cl.CATEGORIES) and EVIDENCE_META in enum(v4)
    assert EVIDENCE_META not in r.UNPROVEN_CATEGORIES


# ------------------------------------------------------------------ the UNSUPPORTED gate


def claim(cid: str, text: str, category: str) -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                      source_segment_ids=[f"t_{cid}"], start_seconds=0.0, end_seconds=1.0)


def test_gate_refuses_design_statements_but_not_support_statements():
    s = initial_state(job_id="j", video_id="v", media_uri="mem://v", pipeline_version="test")
    s["claims"] = [claim("c12", C12, "treatment_efficacy"),  # an older run's tag: the rules still refuse it
                   claim("c12b", C12, EVIDENCE_META),
                   claim("c13", C13, "prevention"),
                   claim("t1", "the evidence that turmeric cures cancer is overwhelming", "treatment_efficacy"),
                   claim("t2", "the evidence for this detox tea is overwhelming", "treatment_efficacy"),
                   claim("c11", "Vitamin K prevents osteoporosis", "prevention")]
    assert not r.unproven_eligible(s, "c12")
    assert not r.unproven_eligible(s, "c12b")
    for cid in ("c13", "t1", "t2", "c11"):
        assert r.unproven_eligible(s, cid), cid


def test_frozen_eval_categoriser_agrees():
    assert efficacy_category(C13) != EVIDENCE_META  # the eval's own cue words decide the rest
    assert efficacy_category(C12) == EVIDENCE_META
    assert efficacy_category("Vitamin K prevents osteoporosis") == "prevention"


# ------------------------------------------------------------------ c12 / c13 replay


def replay(c_ids: tuple[str, ...], recorded: bool = False) -> dict:
    """c12/c13 through the verifier (T49 guard included), the judge and validation,
    as stored in the fixture: empty searches, full budget spent, endorsed."""
    claims_ = [c for c in job()["claims"] if c["claim_id"] in c_ids]
    s = initial_state(job_id="5cc07f48", video_id="vid", media_uri="mem://vid", pipeline_version="test")
    s.update(
        claims=[GraphClaim(claim_id=c["claim_id"], claim_text=c["text"],
                           claim_category=c["category"],
                           claim_kind=c["claim_kind"], source_segment_ids=[f"t_{c['claim_id']}"],
                           start_seconds=c["start_seconds"], end_seconds=c["end_seconds"]) for c in claims_],
        transcript_segments=[TranscriptSegment(segment_id=f"t_{c['claim_id']}", start=c["start_seconds"],
                                               end=c["end_seconds"], text=c["text"]) for c in claims_],
        stance_results={c["claim_id"]: StanceResult(claim_id=c["claim_id"], stance=Stance(stance_of(c)),
                                                    stance_segment_ids=[f"t_{c['claim_id']}"]) for c in claims_},
        retrieved_evidence={c["claim_id"]: evidence_of(c) for c in claims_},
        reranked_evidence={c["claim_id"]: evidence_of(c) for c in claims_},
        retrieval_attempts={c["claim_id"]: c["retrieval_attempts"] for c in claims_},
    )

    answers = {c["claim_id"]: a for c in claims_ if (a := verifier_answer(c))}

    class Recorded:
        def call(self, step, input, *, system=None):
            import re
            assert recorded, "nothing was retrieved: the verifier must not call a model"
            cid = re.search(r"Judge claim (\S+) ", input["messages"][0]["content"]).group(1)
            return SimpleNamespace(output=answers[cid], record=SimpleNamespace(model="recorded",
                                                                               prompt_version="verify_v3"))

    s = {**s, **vf.make_verify_claims(Recorded(), prompt_version="verify_v3")(s)}
    s["final_result"] = jg.make_judge_classification(None)(s)["final_result"]
    s["validation_errors"] = [str(i) for i in validate(s)]
    s["validation_attempts"] = 1
    return {**s, **make_stub_nodes()[r.ROUTE_FOR_REVIEW](s)}


def test_c12_is_insufficient_and_c13_is_stopped_by_the_t49_guard():
    out = replay(("c12", "c13"))
    vr = out["verification_results"]
    assert {cid: v.verdict for cid, v in vr.items()} == {
        "c12": Verdict.INSUFFICIENT_EVIDENCE, "c13": Verdict.INSUFFICIENT_EVIDENCE}
    assert OFF_TOPIC_LIMITATION not in vr["c12"].limitations  # never offered UNSUPPORTED
    assert vr["c13"].limitations[-1] == OFF_TOPIC_LIMITATION  # eligible; the empty search stops it
    final = out["final_result"]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE and final.misinfo_basis is None
    assert "judge:nothing_judged" in out["review_reasons"]
    assert not any("unproven_claim" in x for x in out["review_reasons"])


def test_the_full_real_job_with_c13_kept_as_efficacy():
    # On the real rows the stored SUPPORTED c8 decides (T50 review): NO_MISINFO. What T51
    # adds: c13 reaches the guard as an efficacy claim and is downgraded there.
    out = replay(tuple(c["claim_id"] for c in job()["claims"]), recorded=True)
    vr = out["verification_results"]
    assert vr["c13"].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert vr["c13"].limitations[-1] == OFF_TOPIC_LIMITATION
    assert not any(v.verdict == Verdict.UNSUPPORTED for v in vr.values())
    assert out["final_result"].classification == MisinfoLabel.NO_MISINFO
