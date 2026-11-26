"""T51: statements about the state or strength of evidence are not efficacy claims.

Production job 5cc07f48 ("Download (4).mp4", vitamin K video, 2026-11-26): c13 "The
evidence that the vitamin K shot prevents dangerous bleeding in newborns is
overwhelming" was tagged treatment_efficacy and became UNSUPPORTED; c12 "These studies
on newborns are observational" is the same kind of statement. Both claims come from
T49's fixture, which is RECONSTRUCTED from the queue's description (no production DB
access in the build env; see its ``_provenance``).

The fix: category ``evidence_meta`` (prompt extract_v4 and fixed rules that override
the model for every prompt version), and the UNSUPPORTED gate refuses such statements.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.claim_category import EVIDENCE_META, is_evidence_meta, resolve_claim_category
from app.core.graph import claims as cl
from app.core.graph import judge as jg
from app.core.graph import routing as r
from app.core.graph import verifier as vf
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.stance import load_prompt
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

FIXTURE = Path(__file__).parent / "fixtures" / "prod_5cc07f48" / "vitamin_k_job.json"


def job() -> dict:
    return json.loads(FIXTURE.read_text())


def prod_claim(cid: str) -> dict:
    return next(c for c in job()["claims"] if c["claim_id"] == cid)


C12 = prod_claim("c12")["text"]
C13 = prod_claim("c13")["text"]


def test_fixture_is_reconstructed_and_c13_was_tagged_as_efficacy():
    j = job()
    assert j["_provenance"].startswith("RECONSTRUCTED")
    assert C12 == "These studies on newborns are observational"
    assert prod_claim("c13")["category"] == "treatment_efficacy"
    assert prod_claim("c13")["production_verdict"] == "UNSUPPORTED"


# ------------------------------------------------------------------ the fixed rules

EVIDENCE_STATEMENTS = [
    C12,
    C13,
    "The research on turmeric is still very preliminary",
    "There is little good evidence for detox teas",
    "there's no evidence that energy drinks cause strokes",
    "That was just a mouse study",
    "The study was funded by the sugar industry",
    "This supplement has never been tested in humans",
    "the data we have is weak",
    "Most of these trials were small",
    "Les études sont observationnelles",
    "La evidencia es abrumadora",
    "The evidence is overwhelming.",
]

# Reported findings: an efficacy claim in an evidence wrapper keeps its category,
# so an unproven remedy can't escape UNSUPPORTED by saying "studies show".
NOT_EVIDENCE_STATEMENTS = [
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


def test_rules_override_the_model_category():
    known = cl.CATEGORIES
    assert resolve_claim_category("treatment_efficacy", C13, known) == EVIDENCE_META
    assert resolve_claim_category("other", C12, known) == EVIDENCE_META
    assert resolve_claim_category("prevention", "Vitamin K prevents bleeding", known) == "prevention"
    assert resolve_claim_category("bogus", "Vitamin K prevents bleeding", known) == "other"
    # A model may tag evidence_meta where the rules don't fire; it is kept.
    assert resolve_claim_category(EVIDENCE_META, "Nobody has looked at this properly", known) == EVIDENCE_META


def test_prompt_examples_agree_with_the_rules():
    for text in ["the evidence that flossing prevents gum disease is strong",
                 "the research on cold plunges is still thin", "these trials were tiny",
                 "that was a rat study", "the study was paid for by a juice company",
                 "this powder has never been tested in people", "there is very little good data on collagen"]:
        assert is_evidence_meta(text), text
    for text in ["Studies show beetroot juice lowers blood pressure", "clinically proven to clear acne",
                 "research proves garlic kills viruses"]:
        assert not is_evidence_meta(text), text


# ------------------------------------------------------------------ prompts and requests


def test_extract_v4_describes_evidence_meta_and_v3_is_unchanged():
    v4 = " ".join(load_prompt("extract_v4").split())
    v3 = " ".join(load_prompt("extract_v3").split())
    assert "evidence_meta" in v4 and "evidence_meta" not in v3
    assert "never treatment_efficacy or prevention" in v4
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
def test_extractor_tags_c12_and_c13_evidence_meta_even_when_the_model_says_efficacy(prompt):
    out, caller = extract(prompt, ("other", "treatment_efficacy"))
    cats = {c.claim_text: c.claim_category for c in out["claims"]}
    assert cats == {C12: EVIDENCE_META, C13: EVIDENCE_META}
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


def test_gate_refuses_evidence_statements_whatever_their_category():
    s = initial_state(job_id="j", video_id="v", media_uri="mem://v", pipeline_version="test")
    s["claims"] = [claim("c12", C12, "other"), claim("c13", C13, "treatment_efficacy"),
                   claim("c13b", C13, EVIDENCE_META),
                   claim("c11", "Vitamin K prevents osteoporosis", "prevention")]
    assert not r.unproven_eligible(s, "c12")
    assert not r.unproven_eligible(s, "c13")  # an older run's claim, still tagged efficacy
    assert not r.unproven_eligible(s, "c13b")
    assert r.unproven_eligible(s, "c11")  # a real prevention claim is unaffected


def test_frozen_eval_categoriser_agrees():
    assert efficacy_category(C13) == EVIDENCE_META
    assert efficacy_category(C12) == EVIDENCE_META
    assert efficacy_category("Vitamin K prevents osteoporosis") == "prevention"


# ------------------------------------------------------------------ c12 / c13 replay


def replay(c_ids: tuple[str, ...], category_override: dict[str, str] | None = None) -> dict:
    """c12/c13 through the verifier (T49 guard included), the judge and validation,
    as stored in the fixture: empty searches, full budget spent, endorsed."""
    claims_ = [c for c in job()["claims"] if c["claim_id"] in c_ids]
    s = initial_state(job_id="5cc07f48", video_id="vid", media_uri="mem://vid", pipeline_version="test")
    s.update(
        claims=[GraphClaim(claim_id=c["claim_id"], claim_text=c["text"],
                           claim_category=(category_override or {}).get(c["claim_id"], c["category"]),
                           claim_kind=c["claim_kind"], source_segment_ids=[f"t_{c['claim_id']}"],
                           start_seconds=c["start_seconds"], end_seconds=c["end_seconds"]) for c in claims_],
        transcript_segments=[TranscriptSegment(segment_id=f"t_{c['claim_id']}", start=c["start_seconds"],
                                               end=c["end_seconds"], text=c["text"]) for c in claims_],
        stance_results={c["claim_id"]: StanceResult(claim_id=c["claim_id"], stance=Stance(c["stance"]),
                                                    stance_segment_ids=[f"t_{c['claim_id']}"]) for c in claims_},
        retrieved_evidence={c["claim_id"]: [] for c in claims_},
        reranked_evidence={c["claim_id"]: [] for c in claims_},
        retrieval_attempts={c["claim_id"]: c["retrieval_attempts"] for c in claims_},
    )

    class NoModel:
        def call(self, *a, **k):
            raise AssertionError("nothing was retrieved: the verifier must not call a model")

    s = {**s, **vf.make_verify_claims(NoModel(), prompt_version="verify_v3")(s)}
    s["final_result"] = jg.make_judge_classification(None)(s)["final_result"]
    s["validation_errors"] = [str(i) for i in validate(s)]
    s["validation_attempts"] = 1
    return {**s, **make_stub_nodes()[r.ROUTE_FOR_REVIEW](s)}


@pytest.mark.parametrize("override", [None, {"c13": EVIDENCE_META}])
def test_c12_and_c13_never_become_unsupported(override):
    # None: c13 still carries production's treatment_efficacy tag (the gate's own
    # check); {"c13": evidence_meta}: what the T51 extractor now stores.
    out = replay(("c12", "c13"), override)
    vr = out["verification_results"]
    assert {cid: v.verdict for cid, v in vr.items()} == {
        "c12": Verdict.INSUFFICIENT_EVIDENCE, "c13": Verdict.INSUFFICIENT_EVIDENCE}
    final = out["final_result"]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE and final.misinfo_basis is None
    assert not any("unproven_claim" in x for x in out["review_reasons"])


def test_a_real_efficacy_claim_with_the_same_empty_search_still_can_be_unsupported():
    # Control: T51 narrows UNSUPPORTED to non-evidence statements only. The same empty
    # search on a plain efficacy claim still offers it (the T49 guard then decides).
    s = initial_state(job_id="j", video_id="v", media_uri="mem://v", pipeline_version="test")
    s["claims"] = [claim("c1", "The vitamin K shot prevents dangerous bleeding in newborns", "prevention")]
    s["retrieval_attempts"] = {"c1": 3}
    assert r.unproven_eligible(s, "c1")
