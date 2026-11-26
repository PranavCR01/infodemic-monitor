"""T49: no UNSUPPORTED from an empty or off-topic search (design §7).

The production case: job 5cc07f48 ("Download (4).mp4", vitamin K video, 2026-11-26),
an accurate pro-vitamin-K video labelled MISINFO (unproven) because c13's search found
nothing and c11's found only vitamin D / osteoporosis papers. The fixture is
RECONSTRUCTED from the queue's description (see its ``_provenance``); the lead should
replace it with the production rows.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.graph import judge as jg
from app.core.graph import routing as r
from app.core.graph import verifier as vf
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.state import (
    EvidenceRecord,
    GraphClaim,
    Stance,
    StanceResult,
    TranscriptSegment,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.core.graph.unproven_guard import (
    OFF_TOPIC_LIMITATION,
    apply_unproven_guard,
    intervention_terms,
    on_topic,
    on_topic_ids,
)
from app.core.graph.validation import validate
from app.core.schemas.pipeline import MisinfoLabel

from app.tests.vitamin_k_fixture import evidence_of, load_real, stance_of, verifier_answer  # noqa: E402


def rec(eid: str, title: str, abstract: str = "") -> EvidenceRecord:
    return EvidenceRecord(evidence_id=eid, source="pubmed", title=title, abstract=abstract)


def gclaim(text: str, cid: str = "c1", category: str = "treatment_efficacy") -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                      source_segment_ids=["t1"], start_seconds=0.0, end_seconds=1.0)


UNS = VerificationResult(claim_id="c1", verdict=Verdict.UNSUPPORTED, explanation="No evidence supports this claim.")


# ------------------------------------------------------------------ the on-topic check


def test_vitamin_k_never_shrinks_to_vitamin():
    t = intervention_terms("Vitamin K helps keep calcium in your bones and prevents osteoporosis")
    # T50 added vitamin K to the MeSH lexicon: a concept now, with its other names.
    assert t.terms[0] == "vitamin k" and t.source == "concept" and "vitamin" not in t.terms
    assert "vitamins" not in t.terms  # never the parent heading
    assert not on_topic(rec("a", "Vitamin D supplementation and fracture risk in osteoporosis"), t)
    assert on_topic(rec("b", "Vitamin K2 and bone", "Menaquinone (vitamin K) intake and fractures."), t)
    assert on_topic(rec("c", "Vitamin-K status and bone turnover"), t)  # hyphen reads as a space
    # T50 review: vitamin K antagonists are warfarin-type drugs, not vitamin K.
    assert not on_topic(rec("d", "Effects of vitamin-K antagonists on bone"), t)


def test_recognised_concept_any_name_counts_but_not_its_parent_heading():
    t = intervention_terms("Turmeric cures arthritis")
    assert t.source == "concept" and not t.require_all
    assert on_topic(rec("a", "Curcumin in knee osteoarthritis: a randomised trial"), t)
    v = intervention_terms("Vitamin D prevents covid")
    assert "vitamins" not in v.terms  # parent heading "Vitamins" would match every vitamin paper
    assert not on_topic(rec("b", "Vitamins and minerals in older adults"), v)


def test_fallback_needs_every_intervention_word_and_drops_conditions():
    # Mullein is not in the lexicon (sea moss was, until T50 added it), so the
    # label's words are the terms and all of them must appear.
    t = intervention_terms("Mullein Leaf: Cures Thyroid Issues")
    assert t.terms == ("mullein", "leaf") and t.require_all
    assert not on_topic(rec("a", "Leaf extracts and the thyroid"), t)
    assert on_topic(rec("b", "Mullein (Verbascum thapsus) leaf composition"), t)
    sea_moss = intervention_terms("Irish Sea Moss: Cures Thyroid Issues")
    assert sea_moss.source == "concept" and "irish moss" in sea_moss.terms
    assert not on_topic(rec("c", "Iodine in seaweed and the thyroid"), sea_moss)
    soap = intervention_terms("A soap that treats skin cancer")
    assert "cancer" not in " ".join(soap.terms)  # a condition is not the intervention
    assert not on_topic(rec("c", "Angiogenesis in cancer"), soap)


def test_plural_and_case_and_whole_words():
    t = intervention_terms("Eggs prevent macular degeneration")
    assert on_topic(rec("a", "EGG consumption and lutein"), t)
    assert not on_topic(rec("b", "Eggplant extracts"), t)


def test_a_claim_without_intervention_words_is_never_on_topic():
    t = intervention_terms("it is what it is")
    assert t.terms == () and not on_topic(rec("a", "anything"), t)


def test_cited_records_count_as_on_topic():
    c = gclaim("Sea moss gel cures thyroid disease")
    ev = [rec("ev_1", "Iodine content of seaweed products")]
    assert on_topic_ids(c, ev) == []
    assert on_topic_ids(c, ev, cited=["ev_1"]) == ["ev_1"]


# ------------------------------------------------------------------ the guard


def test_empty_search_unsupported_becomes_insufficient():
    out = apply_unproven_guard(gclaim("Garlic cures the flu"), [], UNS)
    assert out.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert out.limitations[-1] == OFF_TOPIC_LIMITATION
    assert "no evidence supports" not in out.explanation.lower() and "false" not in out.explanation.lower()


def test_off_topic_search_unsupported_becomes_insufficient():
    ev = [rec("ev_1", "Vitamin D and influenza in children")]
    assert apply_unproven_guard(gclaim("Garlic cures the flu"), ev, UNS).verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_on_topic_search_keeps_unsupported():
    ev = [rec("ev_1", "Vitamin D and influenza"), rec("ev_2", "Allicin content of garlic supplements")]
    assert apply_unproven_guard(gclaim("Garlic cures the flu"), ev, UNS) == UNS


@pytest.mark.parametrize("verdict", [v for v in Verdict if v != Verdict.UNSUPPORTED])
def test_other_verdicts_pass_through_untouched(verdict):
    v = VerificationResult(claim_id="c1", verdict=verdict)
    assert apply_unproven_guard(gclaim("Garlic cures the flu"), [], v) is v


# ------------------------------------------------------------------ production replay


def load_job() -> dict:
    return load_real()


class RecordedVerifier:
    """Replays the verifier answers stored in production, keyed by claim id."""

    def __init__(self, answers: dict[str, dict]):
        self.answers = answers
        self.calls: list[str] = []

    def call(self, step, input, *, system=None):
        import re

        cid = re.search(r"Judge claim (\S+) ", input["messages"][0]["content"]).group(1)
        self.calls.append(cid)
        return SimpleNamespace(output=self.answers[cid], record=SimpleNamespace(model="recorded", prompt_version="verify_v3"))


def job_state(job: dict) -> dict:
    s = initial_state(job_id=job["job_id_prefix"], video_id="vid", media_uri="mem://vid", pipeline_version="test")
    claims, stances, evidence, transcript = [], {}, {}, []
    for c in job["claims"]:
        cid = c["claim_id"]
        claims.append(GraphClaim(
            claim_id=cid, claim_text=c["text"], claim_category=c["category"], claim_kind=c["claim_kind"],
            source_segment_ids=[f"t_{cid}"], start_seconds=c["start_seconds"], end_seconds=c["end_seconds"],
        ))
        transcript.append(TranscriptSegment(segment_id=f"t_{cid}", start=c["start_seconds"],
                                            end=c["end_seconds"], text=c["text"]))
        stances[cid] = StanceResult(claim_id=cid, stance=Stance(stance_of(c)), stance_segment_ids=[f"t_{cid}"])
        evidence[cid] = evidence_of(c)
    s.update(
        claims=claims, stance_results=stances, retrieved_evidence=evidence, reranked_evidence=evidence,
        transcript_segments=transcript,
        retrieval_attempts={c["claim_id"]: c["retrieval_attempts"] for c in job["claims"]},
    )
    return s


def verify_and_judge(s: dict, verify_node) -> dict:
    s = {**s, **verify_node(s)}
    s["final_result"] = jg.make_judge_classification(None)(s)["final_result"]
    s["validation_errors"] = [str(i) for i in validate(s)]
    s["validation_attempts"] = 1
    return {**s, **make_stub_nodes()[r.ROUTE_FOR_REVIEW](s)}


def without_guard(caller):
    """The verifier node as it was before T49 (for the reproduction)."""
    def node(state):
        out = {}
        for c in state["claims"]:
            out[c.claim_id], _ = vf.verify_claim(
                c, state["reranked_evidence"][c.claim_id], caller, "system", "verify_v3",
                allow_unsupported=r.unproven_eligible(state, c.claim_id))
        return {"verification_results": out}
    return node


def answers(job: dict) -> dict:
    return {c["claim_id"]: a for c in job["claims"] if (a := verifier_answer(c))}


def test_fixture_is_the_real_production_job():
    job = load_job()
    assert job["_provenance"].startswith("COPIED FROM PRODUCTION")
    by = {c["claim_id"]: c for c in job["claims"]}
    assert len(by) == 13
    assert by["c13"]["evidence"] in (None, []) and by["c13"]["verdict"] == "UNSUPPORTED"
    titles = [e["title"].lower() for e in by["c11"]["evidence"]]
    assert titles and not any("vitamin k" in t for t in titles)  # vitamin D, osteoporosis, falls ...
    assert {c["claim_id"] for c in job["claims"] if c["verdict"] == "UNSUPPORTED"} == {"c11", "c13"}
    assert (job["result"]["label"], job["result"]["misinfo_basis"]) == ("MISINFO", "unproven")
    assert sorted(job["result"]["deciding_claim_ids"]) == ["c11", "c13"]


def test_reproduces_the_production_label_without_the_guard():
    job = load_job()
    out = verify_and_judge(job_state(job), without_guard(RecordedVerifier(answers(job))))
    got = {cid: v.verdict.value for cid, v in out["verification_results"].items()}
    assert got == {c["claim_id"]: c["verdict"] for c in job["claims"]}
    final = out["final_result"]
    assert (final.classification.value, final.misinfo_basis) == ("MISINFO", "unproven")
    assert sorted(final.claim_ids) == ["c11", "c13"]


def test_vitamin_k_video_is_no_longer_misinfo_with_the_guard():
    """T49 asserted CANNOT_RECOGNIZE on the reconstructed fixture. On the real rows the
    guard still removes both UNSUPPORTED verdicts (c11's papers are vitamin D / falls /
    osteoporosis; c13 retrieved nothing), and the stored SUPPORTED verdict on c8 ("bleeding
    in the brain can cause permanent neurological damage or death", endorsed) then makes
    the video NO_MISINFO under the unchanged §9 rules. Either way: not MISINFO (unproven)."""
    job = load_job()
    caller = RecordedVerifier(answers(job))
    out = verify_and_judge(job_state(job), vf.make_verify_claims(caller, prompt_version="verify_v3"))
    vr = out["verification_results"]
    for cid in ("c11", "c13"):
        assert vr[cid].verdict == Verdict.INSUFFICIENT_EVIDENCE
        assert vr[cid].limitations[-1] == OFF_TOPIC_LIMITATION
    # Real rows: c1, c8, c10, c11 had papers; c13 had nothing to read (no model call).
    # T65 (a): a stored explanation that names evidence ids (ev_...) gets one repair call,
    # so a claim may appear twice; the set of claims called is unchanged.
    assert sorted(set(caller.calls)) == ["c1", "c10", "c11", "c8"]
    assert not any(v.verdict == Verdict.UNSUPPORTED for v in vr.values())
    assert vr["c8"].verdict == Verdict.SUPPORTED
    final = out["final_result"]
    assert final.classification == MisinfoLabel.NO_MISINFO and final.misinfo_basis is None
    assert not any("unproven_claim" in x for x in out["review_reasons"])


def test_without_the_supported_claim_the_video_is_cannot_recognize():
    """T49's original assertion, on the real rows minus c8: nothing judged → CANNOT_RECOGNIZE
    with the nothing_judged review reason."""
    job = load_job()
    job = {**job, "claims": [c for c in job["claims"] if c["claim_id"] != "c8"]}
    out = verify_and_judge(job_state(job), vf.make_verify_claims(RecordedVerifier(answers(job)),
                                                                prompt_version="verify_v3"))
    final = out["final_result"]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE and final.misinfo_basis is None
    assert out["requires_human_review"] is True
    assert "judge:nothing_judged" in out["review_reasons"]
