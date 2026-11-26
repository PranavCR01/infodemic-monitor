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

FIXTURE = Path(__file__).parent / "fixtures" / "prod_5cc07f48" / "vitamin_k_job.json"


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
    assert on_topic(rec("c", "Effects of vitamin-K antagonists on bone"), t)  # hyphen reads as a space


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
    return json.loads(FIXTURE.read_text())


class RecordedVerifier:
    """Replays the verifier answers recorded in the fixture, keyed by claim id."""

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
        stances[cid] = StanceResult(claim_id=cid, stance=Stance(c["stance"]), stance_segment_ids=[f"t_{cid}"])
        evidence[cid] = [EvidenceRecord.model_validate(e) for e in c["evidence"]]
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
    return {c["claim_id"]: c["verifier_answer"] for c in job["claims"] if c["verifier_answer"]}


def test_fixture_is_marked_reconstructed_and_matches_the_reported_facts():
    job = load_job()
    assert job["_provenance"].startswith("RECONSTRUCTED")
    by = {c["claim_id"]: c for c in job["claims"]}
    assert len(by) == 13
    assert by["c13"]["evidence"] == [] and all(t["retrieved"] == 0 for t in by["c13"]["search_trail"])
    titles = [e["title"].lower() for e in by["c11"]["evidence"]]
    assert titles and all("vitamin d" in t and "vitamin k" not in t for t in titles)
    assert {c["claim_id"] for c in job["claims"] if c["production_verdict"] == "UNSUPPORTED"} == {"c11", "c13"}


def test_reproduces_the_production_label_without_the_guard():
    job = load_job()
    out = verify_and_judge(job_state(job), without_guard(RecordedVerifier(answers(job))))
    got = {cid: v.verdict.value for cid, v in out["verification_results"].items()}
    assert got == {c["claim_id"]: c["production_verdict"] for c in job["claims"]}
    final = out["final_result"]
    assert (final.classification.value, final.misinfo_basis) == (job["production_label"], job["production_misinfo_basis"])


def test_vitamin_k_video_is_cannot_recognize_with_the_guard():
    job = load_job()
    caller = RecordedVerifier(answers(job))
    out = verify_and_judge(job_state(job), vf.make_verify_claims(caller, prompt_version="verify_v3"))
    vr = out["verification_results"]
    for cid in ("c11", "c13"):
        assert vr[cid].verdict == Verdict.INSUFFICIENT_EVIDENCE
        assert vr[cid].limitations[-1] == OFF_TOPIC_LIMITATION
    assert sorted(caller.calls) == ["c1", "c11"]  # c13 had nothing to read: no model call
    assert not any(v.verdict == Verdict.UNSUPPORTED for v in vr.values())
    final = out["final_result"]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE and final.misinfo_basis is None
    assert out["requires_human_review"] is True
    assert "judge:nothing_judged" in out["review_reasons"]
    assert not any("unproven_claim" in x for x in out["review_reasons"])
