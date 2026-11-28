"""T70: claim context, judge each claim as meant in its video (design §4, §6, §7, §9).

Switch ``routing.CLAIM_CONTEXT`` (default OFF). No model or network calls: every model
reply here is hand-written (mocked) or replayed from production rows, so these tests show
what the code does with a reply, never what a model would reply.

The production gate uses the real v135 rows of jobs cf2ea579, f85f2daa and 008c97a3
(``app.evaluation.claim_context_gate``): MISINFO from the skin claim today, never MISINFO
from it with the switch on when the verifier uses the context it is given.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.graph import claim_context as cx
from app.core.graph import claims as cl
from app.core.graph import judge as jg
from app.core.graph import routing as r
from app.core.graph import verifier as vf
from app.core.graph.nodes import NODE_OUTPUTS
from app.core.graph.state import (
    ClaimContext,
    ContextItem,
    EvidenceRecord,
    FusedSegment,
    GraphClaim,
    OcrSegment,
    Stance,
    StanceResult,
    TranscriptSegment,
    Verdict,
    VerificationResult,
    VideoTopic,
    initial_state,
)
from app.core.retrieval.planning import QueryPlanner
from app.evaluation import claim_context_gate as gate
from app.services.review_reasons import REASON_TEXT, parse_reason


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(r, "CLAIM_CONTEXT", True)


# ------------------------------------------------------------------ helpers

SKIN = "Benzene doesn't get through skin easily"
T17 = TranscriptSegment(segment_id="t17", start=48.8, end=52.8,
                        text="So let's compare how much benzene we can get from these products to other sources.")
T18 = TranscriptSegment(segment_id="t18", start=52.8, end=56.2,
                        text="Benzene doesn't get through skin easily, so this is how much you would breathe in")
O10 = OcrSegment(segment_id="o10", start=53.9, end=59.8, confidence=1.0,
                 text="Benzoyl peroxide: worst case scenario / 1 application = 0.5-1.0 g (1-2 finger tip units) "
                      "/ 10-20 µg* in 1 application of 20 ppm product")
FUSED = [FusedSegment(segment_id="f1", start=48.8, end=52.8, spoken=T17.text, sources=["t17"]),
         FusedSegment(segment_id="f2", start=52.8, end=56.2, spoken=T18.text, on_screen=[O10.text],
                      sources=["t18", "o10"])]


def seg_state() -> dict:
    return {"fused_segments": FUSED, "transcript_segments": [T17, T18], "ocr_segments": [O10]}


class Caller:
    def __init__(self, outputs, version):
        self.outputs, self.version, self.calls = list(outputs), version, []

    def route(self, step):
        return SimpleNamespace(prompt=self.version)

    def call(self, step, input, *, system=None):
        self.calls.append(SimpleNamespace(step=step, input=input, system=system))
        out = self.outputs.pop(0)
        return SimpleNamespace(output=out, record=SimpleNamespace(model="mock", prompt_version=self.version))


def skin_reply(**context) -> dict:
    claim = {"claim_text": SKIN, "claim_category": "other", "source_segment_ids": ["f2"]}
    if context:
        claim["context"] = context
    return {"claims": [claim],
            "video_topic": {"text": "how much benzene we can get from these products",
                            "source_segment_ids": ["f1"]}}


GROUNDED = {
    "scope": "specific",
    "subject": {"text": "Benzoyl peroxide", "source_segment_ids": ["f2.screen1"]},
    "exposure": {"text": "1 application = 0.5-1.0 g", "source_segment_ids": ["f2.screen1"]},
    "amount": {"text": "10-20 µg in 1 application of 20 ppm product", "source_segment_ids": ["f2.screen1"]},
    # not in the cited block: dropped
    "population": {"text": "teenagers on prescription retinoids", "source_segment_ids": ["f2"]},
}


def paper(eid, title="Dermal absorption of benzene: implications for work practices", ptypes=("Review",)):
    return EvidenceRecord(evidence_id=eid, source="pubmed", pmid=eid.split("_")[-1], title=title,
                          abstract="Workers' hands in solvent absorb benzene.", publication_type=list(ptypes))


def answer(verdict="CONTRADICTED", con=("ev_1",), **extra) -> dict:
    return {"verdict": verdict, "supporting_evidence_ids": [], "contradicting_evidence_ids": list(con),
            "explanation": "Reviews of solvent exposure report skin absorption.", "limitations": [],
            "raw_confidence": 0.6, **extra}


def specific_ctx(cid="c1") -> ClaimContext:
    return ClaimContext(claim_id=cid, scope="specific",
                        subject=ContextItem(text="Benzoyl peroxide", segment_ids=["o10"]),
                        exposure=ContextItem(text="1 application = 0.5-1.0 g", segment_ids=["o10"]))


# ------------------------------------------------------------------ switch off: unchanged


def test_switch_defaults_off():
    assert r.CLAIM_CONTEXT is False
    assert r.CONTEXT_MISMATCH_RULE is False
    assert r.context_mismatch_rule_on() is False


def test_off_extraction_request_and_output_unchanged():
    """extract_v5 routed with the switch off sends exactly the extract_v4-shaped request:
    no context, no topic, and context in a reply is rejected as an unknown field."""
    caller = Caller([skin_reply()], "extract_v4")
    out = cl.make_extract_claims(caller)(seg_state())
    req = caller.calls[0].input
    assert req["tools"][0] == cl.extract_tool(cl.categories_for("extract_v4"))
    assert "video_topic" not in json.dumps(req)
    assert "VIDEO TOPIC" not in req["messages"][0]["content"]
    assert set(out) == {"claims", "errors"} or set(out) == {"claims"}
    # the reply carried video_topic, which the pre-T70 schema rejects (repair asked)
    assert out.get("errors") and "video_topic" in out["errors"][0].message


def test_off_verifier_tool_and_prompt_unchanged():
    claim = GraphClaim(claim_id="c1", claim_text=SKIN, claim_category="other", source_segment_ids=["t18"],
                       start_seconds=0, end_seconds=1)
    prompt = vf.build_prompt(claim, [paper("ev_1")], "sys")
    assert vf.build_request(prompt)["tools"] == [vf.VERIFY_TOOL]
    assert "SPECIFIC" not in prompt.render() and "UNIVERSAL" not in prompt.render()


@pytest.mark.parametrize("extra", [{"contradicted_as_stated": True}, {"evidence_context": "partial"}])
def test_off_t70_fields_are_rejected_as_before(extra):
    with pytest.raises(vf.InvalidVerification) as exc:
        vf.parse_verification(answer(**extra), ["ev_1"])
    assert exc.value.kind == "output_rejected"


def test_off_planner_and_state_fields_unchanged():
    p = QueryPlanner().plan(SKIN)
    assert [x.kind for x in p.rungs] == ["intervention_only"]
    assert "claim_context" not in p.describe()
    s = {"claim_contexts": {"c1": specific_ctx()}}
    assert cx.context_of(s, "c1") is None  # switch off: never read


def test_ownership_declares_the_new_fields():
    assert {"claims", "claim_contexts", "video_topic"} == set(NODE_OUTPUTS[r.EXTRACT_CLAIMS])


def test_switch_on_needs_context_prompts(on):
    with pytest.raises(ValueError, match="extract_v5"):
        cl.make_extract_claims(Caller([], "extract_v3"))
    with pytest.raises(ValueError, match="verify_v4"):
        vf.make_verify_claims(Caller([], "verify_v3"))
    cl.make_extract_claims(Caller([], "extract_v5"))
    vf.make_verify_claims(Caller([], "verify_v4"))


def test_prompt_files_exist_and_extend_the_previous_versions():
    from app.core.graph.stance import load_prompt

    v4, v5 = load_prompt("extract_v4"), load_prompt("extract_v5")
    assert "9. Context" in v5 and "scope" in v5 and len(v5) > len(v4)
    assert "as meant" in load_prompt("verify_v4") and "contradicted_as_stated" in load_prompt("verify_v4")
    assert "extract_v5" in cl.EVIDENCE_META_PROMPTS


# ------------------------------------------------------------------ (a) (b) extraction


def test_v5_grounded_context_kept_ungrounded_dropped_claim_text_verbatim(on):
    caller = Caller([skin_reply(**GROUNDED)], "extract_v5")
    out = cl.make_extract_claims(caller)(seg_state())
    [c] = out["claims"]
    assert c.claim_text == SKIN  # verbatim: context never edits the claim
    ctx = out["claim_contexts"]["c1"]
    assert ctx.scope == "specific"
    assert ctx.subject.text == "Benzoyl peroxide" and ctx.subject.segment_ids == ["o10"]
    assert ctx.exposure.segment_ids == ["o10"] and ctx.amount is not None
    assert ctx.population is None and ctx.dropped == ["population"]
    assert out["video_topic"] == VideoTopic(text="how much benzene we can get from these products",
                                            segment_ids=["t17"])
    tool = caller.calls[0].input["tools"][0]["input_schema"]
    assert "video_topic" in tool["properties"]
    assert "context" in tool["properties"]["claims"]["items"]["properties"]


def test_context_citing_unknown_blocks_is_dropped_and_scope_falls_to_universal(on):
    bad = {"scope": "specific", "subject": {"text": "Benzoyl peroxide", "source_segment_ids": ["f99"]}}
    out = cl.make_extract_claims(Caller([skin_reply(**bad)], "extract_v5"))(seg_state())
    ctx = out["claim_contexts"]["c1"]
    assert ctx.scope == "universal" and ctx.items() == [] and ctx.dropped == ["subject"]
    assert len(out["claims"]) == 1  # a bad context item costs no repair and drops no claim
    assert cx.context_line(ctx) is None


def test_ungrounded_topic_is_not_stored(on):
    reply = skin_reply()
    reply["video_topic"] = {"text": "miracle cures big pharma hides", "source_segment_ids": ["f1"]}
    out = cl.make_extract_claims(Caller([reply], "extract_v5"))(seg_state())
    assert "video_topic" not in out


def test_topic_is_produced_once_and_shown_fenced_to_later_windows(on):
    late = FusedSegment(segment_id="f3", start=400.0, end=404.0, spoken=T18.text, sources=["t18"])
    state = {**seg_state(), "fused_segments": [*FUSED, late]}
    second = {"claims": []}
    caller = Caller([skin_reply(**GROUNDED), second], "extract_v5")
    out = cl.make_extract_claims(caller, window_seconds=240, overlap_seconds=20)(state)
    assert len(caller.calls) == 2
    first_tool, second_tool = (c.input["tools"][0]["input_schema"]["properties"] for c in caller.calls)
    assert "video_topic" in first_tool and "video_topic" not in second_tool
    text = caller.calls[1].input["messages"][0]["content"]
    assert 'id="video_topic"' in text and "how much benzene we can get" in text
    assert out["video_topic"].text.startswith("how much benzene")


def test_context_follows_the_claim_through_dedup(on):
    dup = {"claims": [
        {"claim_text": SKIN, "claim_category": "other", "source_segment_ids": ["f2"], "context": GROUNDED},
        {"claim_text": SKIN, "claim_category": "other", "source_segment_ids": ["f1", "f2"]},
    ]}
    out = cl.make_extract_claims(Caller([dup], "extract_v5"))(seg_state())
    assert [c.claim_id for c in out["claims"]] == ["c1"]
    assert out["claim_contexts"]["c1"].scope == "specific"


# ------------------------------------------------------------------ (c) planner


def test_planner_adds_context_rungs_first(on):
    hint = cx.planner_hint(specific_ctx())
    p = QueryPlanner().plan(SKIN, claim_context=hint)
    assert [x.kind for x in p.rungs] == ["context", "intervention_only"]
    assert "Skin Absorption" in p.rungs[0].query and "benzene" in p.rungs[0].query
    assert p.describe()["claim_context"] == [{"field": "exposure", "facet": "dermal"}]


def test_planner_uses_context_population_and_condition():
    p = QueryPlanner().plan(gate.VAGUE, claim_context=(("population", "newborn babies"),
                                                       ("outcome", "potentially life threatening bleeding")))
    assert p.rungs[0].kind == "context"
    assert "Infant, Newborn" in p.rungs[0].query and "Hemorrhage" in p.rungs[0].query


def test_universal_claim_gets_no_planner_hint():
    universal = ClaimContext(claim_id="c1", scope="universal",
                             population=ContextItem(text="my nephew", segment_ids=["t1"]))
    assert cx.planner_hint(universal) == ()


# ------------------------------------------------------------------ (d) (e) verifier


def verify(claim, ctx, ans, topic=None):
    caller = Caller([ans, ans], "verify_v4")
    res, errs = vf.verify_claim(claim, [paper("ev_1")], caller, "sys", "verify_v4",
                                context_mode=True, context=ctx, topic=topic)
    return res, errs, caller


SKIN_CLAIM = GraphClaim(claim_id="c1", claim_text=SKIN, claim_category="other", source_segment_ids=["t18"],
                        start_seconds=52.8, end_seconds=56.2)


def test_in_context_prompt_fences_the_context_and_requires_both_fields(on):
    ans = answer("INSUFFICIENT_EVIDENCE", con=(), evidence_context="different_exposure_setting",
                 contradicted_as_stated=True)
    res, errs, caller = verify(SKIN_CLAIM, specific_ctx(), ans, VideoTopic(text="benzene in acne products",
                                                                            segment_ids=["t1"]))
    req = caller.calls[0].input
    text = req["messages"][0]["content"]
    assert 'kind="claim_context" id="c1:context"' in text and "Benzoyl peroxide" in text
    assert "Video topic: benzene in acne products" in text and "SPECIFIC" in text
    schema = req["tools"][0]["input_schema"]
    assert {"evidence_context", "contradicted_as_stated"} <= set(schema["required"])
    assert "partial" in schema["properties"]["evidence_context"]["enum"]
    assert res.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert "setting_match:different" in res.limitations and r.SOFTENED_LIMITATION in res.limitations


def test_missing_structured_answer_is_repaired(on):
    caller = Caller([answer(evidence_context="matches"),
                     answer(evidence_context="matches", contradicted_as_stated=True)], "verify_v4")
    res, errs = vf.verify_claim(SKIN_CLAIM, [paper("ev_1")], caller, "sys", "verify_v4",
                                context_mode=True, context=specific_ctx())
    assert len(caller.calls) == 2 and any("repair requested" in e.message for e in errs)
    assert res.verdict == Verdict.CONTRADICTED and "setting_match:same" in res.limitations
    assert r.SOFTENED_LIMITATION not in res.limitations


def test_contradicted_in_a_different_setting_keeps_t69_code(on):
    res, _, _ = verify(SKIN_CLAIM, specific_ctx(),
                       answer(evidence_context="different_exposure_setting", contradicted_as_stated=True))
    assert f"{r.CONTEXT_MISMATCH_LIMITATION}:different_exposure_setting" in res.limitations
    assert r.SOFTENED_LIMITATION not in res.limitations  # still contradicted as meant


VACCINES = GraphClaim(claim_id="c1", claim_text="vaccines cause autism", claim_category="causation",
                      source_segment_ids=["t1"], start_seconds=0, end_seconds=2)


def test_universal_claim_is_judged_as_stated_and_never_softened(on):
    """(e): no context block, no contradicted_as_stated, and none of the context-derived
    codes survive, even when the model's answer says 'different setting'."""
    ans = answer(evidence_context="different_population")
    res, _, caller = verify(VACCINES, None, ans)
    text = caller.calls[0].input["messages"][0]["content"]
    assert "claim_context" not in text and "UNIVERSAL" in text
    assert "contradicted_as_stated" not in caller.calls[0].input["tools"][0]["input_schema"]["properties"]
    assert res.verdict == Verdict.CONTRADICTED
    assert not any(x.startswith(r.CONTEXT_MISMATCH_LIMITATION) for x in res.limitations)
    assert r.SOFTENED_LIMITATION not in res.limitations
    assert "setting_match:different" in res.limitations  # recorded, never used by the judge


def test_universal_claim_answering_softening_field_is_rejected(on):
    caller = Caller([answer(evidence_context="matches", contradicted_as_stated=True)] * 2, "verify_v4")
    res, errs = vf.verify_claim(VACCINES, [paper("ev_1")], caller, "sys", "verify_v4", context_mode=True)
    assert res.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert any(e.message.startswith("guardrail:output_rejected") for e in errs)


def test_verify_node_reads_context_only_for_specific_claims(on):
    s = initial_state(job_id="j", video_id="v", media_uri="m", pipeline_version="t")
    s.update(claims=[SKIN_CLAIM, VACCINES.model_copy(update={"claim_id": "c2"})],
             claim_contexts={"c1": specific_ctx(), "c2": ClaimContext(claim_id="c2", scope="universal")},
             reranked_evidence={"c1": [paper("ev_1")], "c2": [paper("ev_1")]},
             retrieval_attempts={"c1": 1, "c2": 1})
    ans1 = answer("INSUFFICIENT_EVIDENCE", con=(), evidence_context="different_exposure_setting",
                  contradicted_as_stated=True)
    ans2 = answer(evidence_context="matches")
    caller = gate.RecordedVerifier({"c1": ans1, "c2": ans2}, "verify_v4")
    out = vf.make_verify_claims(caller, prompt_version="verify_v4")(s)
    by = {q["claim_id"]: q["input"]["messages"][0]["content"] for q in caller.requests}
    assert "c1:context" in by["c1"] and "c2:context" not in by["c2"]
    assert r.SOFTENED_LIMITATION in out["verification_results"]["c1"].limitations


# ------------------------------------------------------------------ judge


def judged(verdicts: dict, stances: dict, evidence: dict) -> tuple:
    claims = [GraphClaim(claim_id=cid, claim_text=f"claim {cid}", claim_category="other",
                         source_segment_ids=["t1"], start_seconds=0, end_seconds=1) for cid in verdicts]
    s = initial_state(job_id="j", video_id="v", media_uri="m", pipeline_version="t")
    s.update(claims=claims, verification_results=verdicts, reranked_evidence=evidence,
             retrieved_evidence=evidence, retrieval_attempts={c: 1 for c in verdicts},
             stance_results={c: StanceResult(claim_id=c, stance=st, stance_segment_ids=["t1"])
                             for c, st in stances.items()})
    return gate.judge_and_route(s)


def test_softened_claim_is_set_aside_and_always_reviewed(on):
    vr = {"c1": VerificationResult(claim_id="c1", verdict=Verdict.SUPPORTED, supporting_evidence_ids=["ev_1"],
                                   limitations=["setting_match:different", r.SOFTENED_LIMITATION]),
          "c2": VerificationResult(claim_id="c2", verdict=Verdict.INSUFFICIENT_EVIDENCE)}
    out = judged(vr, {"c1": Stance.REFUTES, "c2": Stance.ENDORSES}, {"c1": [paper("ev_1")], "c2": []})
    # a REFUTES + SUPPORTED claim would be MISINFO (denies supported); set aside, it decides nothing
    assert out["final"].classification.value == "CANNOT_RECOGNIZE"
    assert "judge:softened_by_context:c1" in out["reasons"] and out["review"]


def test_softened_code_is_ignored_with_the_switch_off():
    vr = {"c1": VerificationResult(claim_id="c1", verdict=Verdict.SUPPORTED, supporting_evidence_ids=["ev_1"],
                                   limitations=[r.SOFTENED_LIMITATION])}
    out = judged(vr, {"c1": Stance.ENDORSES}, {"c1": [paper("ev_1")]})
    assert out["final"].classification.value == "NO_MISINFO"
    assert not any("softened" in x for x in out["reasons"])


def test_t69_set_aside_runs_under_claim_context(on):
    code = f"{r.CONTEXT_MISMATCH_LIMITATION}:different_exposure_setting"
    vr = {"c1": VerificationResult(claim_id="c1", verdict=Verdict.CONTRADICTED, contradicting_evidence_ids=["ev_1"],
                                   limitations=[code]),
          "c2": VerificationResult(claim_id="c2", verdict=Verdict.SUPPORTED, supporting_evidence_ids=["ev_2"])}
    ev = {"c1": [paper("ev_1")], "c2": [paper("ev_2", "Benzene in sunscreen", ("Journal Article",))]}
    out = judged(vr, {"c1": Stance.ENDORSES, "c2": Stance.ENDORSES}, ev)
    assert out["final"].classification.value == "NO_MISINFO"
    assert "judge:contradiction_context_mismatch:c1" in out["reasons"]


def test_vaccines_cause_autism_stays_misinfo_end_to_end(on):
    """(e) end to end: the extraction model marks the claim universal (its context items
    are ignored), the verifier answers 'different population', the video is MISINFO."""
    t1 = TranscriptSegment(segment_id="t1", start=0, end=3, text="Vaccines cause autism, my nephew got his shots")
    fused = [FusedSegment(segment_id="f1", start=0, end=3, spoken=t1.text, sources=["t1"])]
    reply = {"claims": [{"claim_text": "Vaccines cause autism", "claim_category": "causation",
                         "source_segment_ids": ["f1"],
                         "context": {"scope": "universal",
                                     "population": {"text": "my nephew", "source_segment_ids": ["f1"]}}}]}
    s = initial_state(job_id="j", video_id="v", media_uri="m", pipeline_version="t")
    s.update(fused_segments=fused, transcript_segments=[t1])
    s.update(cl.make_extract_claims(Caller([reply], "extract_v5"))(s))
    assert s["claim_contexts"]["c1"].scope == "universal" and cx.context_of(s, "c1") is None
    ev = [paper("ev_9", "MMR vaccine and autism: a nationwide cohort study", ("Journal Article",))]
    s.update(stance_results={"c1": StanceResult(claim_id="c1", stance=Stance.ENDORSES, stance_segment_ids=["t1"])},
             reranked_evidence={"c1": ev}, retrieved_evidence={"c1": ev}, retrieval_attempts={"c1": 1})
    caller = gate.RecordedVerifier({"c1": answer(con=("ev_9",), evidence_context="different_population")},
                                   "verify_v4")
    s.update(vf.make_verify_claims(caller, prompt_version="verify_v4")(s))
    out = gate.judge_and_route(s)
    assert (out["final"].classification.value, out["final"].misinfo_basis) == ("MISINFO", "contradicted")
    assert not any("softened" in x or "context_mismatch" in x for x in out["reasons"])


def test_a_sweeping_claim_marked_specific_is_never_softened_silently(on):
    """The residual risk: the extraction model wrongly marks a universal claim specific
    with grounded context, and the verifier softens it. The label can change, but only
    with ``softened_by_context`` in the review reasons (a person checks it)."""
    vr = {"c1": VerificationResult(claim_id="c1", verdict=Verdict.INSUFFICIENT_EVIDENCE,
                                   limitations=["setting_match:different", r.SOFTENED_LIMITATION])}
    out = judged(vr, {"c1": Stance.ENDORSES}, {"c1": []})
    assert out["review"] and "judge:softened_by_context:c1" in out["reasons"]


def test_review_reason_wording():
    assert "softened_by_context" in REASON_TEXT
    t = parse_reason("judge:softened_by_context:c4")
    assert t.code == "softened_by_context" and t.claim_id == "c4" and "_" not in t.text
    assert "as the video means it" in jg.flag_text("softened_by_context:c4")
    assert jg.FLAG_SOFTENED_BY_CONTEXT in jg.RULE_REVIEW_FLAGS


# ------------------------------------------------------------------ (h) production gate


@pytest.mark.parametrize("job", sorted(gate.V135))
def test_v135_fixture_is_misinfo_from_the_skin_claim_today(job):
    fx = gate.load(gate.V135[job])
    assert fx["_provenance"].startswith("COPIED FROM PRODUCTION") and fx["golden_label"] == "NO_MISINFO"
    stored = gate.stored_replay(fx)
    assert stored["label"] == fx["result"]["label"] == "MISINFO"
    assert stored["deciding"] == [SKIN]
    off = gate.run(fx, flag_on=False)
    assert (off.label, off.deciding_text) == ("MISINFO", [SKIN])


@pytest.mark.parametrize("scenario", ["as_meant", "contradicted_flagged"])
@pytest.mark.parametrize("job", sorted(gate.V135))
def test_v135_with_context_is_never_misinfo_from_the_skin_claim(job, scenario):
    fx = gate.load(gate.V135[job])
    contexts, topic = gate.v135_context(fx)
    on = gate.run(fx, flag_on=True, contexts=contexts, topic=topic, answer_for=gate.skin_scenario(scenario))
    assert SKIN not in on.deciding_text
    assert on.label in ("NO_MISINFO", "CANNOT_RECOGNIZE") and on.review
    flag = "softened_by_context" if scenario == "as_meant" else "contradiction_context_mismatch"
    assert any(x.startswith(f"judge:{flag}:") for x in on.reasons)
    assert on.dropped_claims == []  # every stored claim survives extract_v5 grounding verbatim
    ctx = on.contexts[SKIN]
    assert ctx["scope"] == "specific" and "population" in ctx["dropped"]
    assert on.plans[SKIN][0]["kind"] == "context"
    universal = [t for t, c in on.contexts.items() if t.startswith("it is a known carcinogen")]
    assert universal and on.contexts[universal[0]]["scope"] == "universal"
    assert not any(cx.is_context_code(x) and x != "setting_match:same" for x in on.limitations[universal[0]])


@pytest.mark.parametrize("job", sorted(gate.V135))
def test_v135_failure_mode_a_mock_cannot_rule_out(job):
    """If the verifier reads the context but still says the reviews match the setting,
    the video stays MISINFO: only a paid run measures how often that happens."""
    fx = gate.load(gate.V135[job])
    contexts, topic = gate.v135_context(fx)
    on = gate.run(fx, flag_on=True, contexts=contexts, topic=topic, answer_for=gate.skin_scenario("ignores_context"))
    assert (on.label, on.deciding_text) == ("MISINFO", [SKIN])


@pytest.mark.parametrize("job", sorted(gate.VITAMIN_K))
def test_vitamin_k_fixtures_unchanged_with_context(job):
    fx = gate.load(gate.VITAMIN_K[job])
    off = gate.run(fx, flag_on=False)
    contexts, topic = gate.vitamin_k_context(fx)
    on = gate.run(fx, flag_on=True, contexts=contexts, topic=topic)
    assert on.summary() == off.summary()
    assert off.label == "NO_MISINFO"  # T64 behaviour on these rows, kept
    assert on.contexts[gate.VAGUE]["scope"] == "specific"
    assert on.plans[gate.VAGUE][0]["kind"] == "context"
    # T64 (c): the claim's own words name no outcome; context does not reopen UNSUPPORTED
    assert on.verdicts[gate.VAGUE] == off.verdicts[gate.VAGUE] == "INSUFFICIENT_EVIDENCE"


# ------------------------------------------------------------------ (f) report / API


def _row(text, sources, trail=None, limitations=()):
    from app.db.models.claim import ClaimRow, VerificationResultRow

    row = ClaimRow(id="row1", job_id="j", claim_id="c1", text=text, category="other", start_seconds=53.9,
                   end_seconds=59.8, source_segment_ids=list(sources), requires_verification=True,
                   search_trail=trail, deciding=False)
    row.verification = VerificationResultRow(verdict="INSUFFICIENT_EVIDENCE", explanation="", revisions=0,
                                             retrieval_attempts=1, limitations=list(limitations))
    return row


def _index():
    from app.api.result_models import SegmentView

    return {"t18": SegmentView(segment_id="t18", source="speech", start_seconds=52.8, end_seconds=56.2,
                               text=T18.text),
            "o10": SegmentView(segment_id="o10", source="screen", start_seconds=53.9, end_seconds=59.8,
                               text=O10.text)}


def test_api_view_unchanged_without_context():
    from app.services.result_view_service import claim_view

    v = claim_view(_row("1 application of 20 ppm product", ["o10"]), _index())
    data = v.model_dump(mode="json")
    for key in ("context", "context_text", "quote_source", "screen_quote"):
        assert key not in data


def test_api_in_context_line_and_setting_match_from_stored_payload():
    from app.services.pipeline_result_service import _with_claim_context
    from app.services.result_view_service import claim_view

    state = {"claim_contexts": {"c1": specific_ctx()},
             "video_topic": VideoTopic(text="benzene in acne products", segment_ids=["t1"])}
    trail = _with_claim_context({"recorded": "graph"}, state, "c1")
    assert set(trail) == {"recorded", "claim_context"}
    assert _with_claim_context({"recorded": "graph"}, {}, "c1") == {"recorded": "graph"}
    v = claim_view(_row(SKIN, ["t18"], trail, ["Narrative reviews only", "setting_match:different",
                                               r.SOFTENED_LIMITATION]), _index())
    assert v.context_text == ("In context: subject or product: Benzoyl peroxide; "
                              "exposure route or setting: 1 application = 0.5-1.0 g.")
    assert v.context.setting_match == "different" and v.context.softened
    assert v.context.video_topic == "benzene in acne products"
    assert v.limitations == ["Narrative reviews only"]  # codes are never shown to readers
    assert v.quote_source == "speech" and v.speaker_quote


def test_api_screen_only_claim_says_on_screen(on):
    from app.services.result_view_service import claim_view

    v = claim_view(_row("10-20 µg in 1 application of 20 ppm product", ["o10"]), _index())
    data = v.model_dump(mode="json")
    assert v.modality == "screen" and v.quote_source == "screen"
    assert v.speaker_quote is None and "20 ppm product" in v.screen_quote
    assert "context" not in data  # nothing stored for this claim
