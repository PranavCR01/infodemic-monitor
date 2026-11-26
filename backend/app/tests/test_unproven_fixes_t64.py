"""T64: unproven-label fixes (design §7, §9; production job d2bf4179).

The production case: the re-analysis of the vitamin K video (job d2bf4179, main 91a7a13,
2026-11-26) was still MISINFO (unproven), decided by c12 "vitamin K is a vitamin that
helps prevent a potentially devastating condition", UNSUPPORTED on ONE kept record (a
brodifacoum case report), while c14 ("the evidence supporting the preventive vitamin K
injection for newborns is overwhelming") was SUPPORTED by two systematic reviews.

Built (lead decision 2026-11-26): (a) search too thin, (b) sibling claim, (c) outcome
unspecified, (e) reranker antagonist demotion, (f) main_claims_unchecked. (d) extraction
context resolution is deferred until after the demo.

The fixture ``fixtures/prod_d2bf4179/vitamin_k_rerun.real.json`` holds the real production
rows (commit 90823dc) and is used as-is. Its evidence rows carry PMID, title, year,
publication type, study type and the verifier's relation, not abstracts; the verifier's
answers are rebuilt from the stored verdict, explanation, limitations and relations.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.graph import judge as jg
from app.core.graph import routing as r
from app.core.graph import unproven_guard as ug
from app.core.graph import verifier as vf
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.severity import assess
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
from app.core.graph.validation import validate
from app.core.retrieval.rerank import Reranker
from app.core.schemas.pipeline import MisinfoLabel
from app.services.review_reasons import parse_reason

REAL = Path(__file__).parent / "fixtures" / "prod_d2bf4179" / "vitamin_k_rerun.real.json"


def load_real() -> dict:
    return json.loads(REAL.read_text())


def rec(eid: str, title: str, abstract: str = "", study_type: str | None = None, pt=()) -> EvidenceRecord:
    return EvidenceRecord(evidence_id=eid, source="pubmed", title=title, abstract=abstract,
                          study_type=study_type, publication_type=list(pt))


def gclaim(text: str, cid: str = "c1", category: str = "treatment_efficacy") -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                      source_segment_ids=["t1"], start_seconds=0.0, end_seconds=1.0)


def uns(cid: str = "c1") -> VerificationResult:
    return VerificationResult(claim_id=cid, verdict=Verdict.UNSUPPORTED, explanation="No evidence supports this claim.")


GARLIC = [rec(f"ev_{i}", f"Garlic intake survey {i}") for i in range(1, 4)]


# ------------------------------------------------------------------ (a) search too thin


def test_one_or_two_on_topic_records_are_too_thin():
    for n in (1, 2):
        out = ug.apply_unproven_guard(gclaim("Garlic cures the flu"), GARLIC[:n], uns())
        assert out.verdict == Verdict.INSUFFICIENT_EVIDENCE
        assert out.limitations[-1] == ug.THIN_SEARCH_LIMITATION
        assert "false" not in out.explanation.lower()


def test_three_on_topic_records_keep_unsupported():
    assert ug.apply_unproven_guard(gclaim("Garlic cures the flu"), GARLIC, uns()).verdict == Verdict.UNSUPPORTED


def test_off_topic_records_do_not_count_towards_three():
    ev = [GARLIC[0], rec("x1", "Vitamin D and influenza"), rec("x2", "Zinc and colds")]
    out = ug.apply_unproven_guard(gclaim("Garlic cures the flu"), ev, uns())
    assert out.limitations[-1] == ug.THIN_SEARCH_LIMITATION


@pytest.mark.parametrize("kw", [
    {"study_type": "systematic_review"}, {"study_type": "rct"}, {"study_type": "guideline"},
    {"pt": ["Meta-Analysis"]}, {"pt": ["Randomized Controlled Trial"]}, {"pt": ["Practice Guideline"]},
])
def test_one_on_topic_review_trial_or_guideline_is_enough(kw):
    ev = [rec("ev_1", "Garlic for the common cold", **kw)]
    assert ug.apply_unproven_guard(gclaim("Garlic cures the flu"), ev, uns()).verdict == Verdict.UNSUPPORTED


def test_an_off_topic_review_does_not_count():
    ev = [GARLIC[0], rec("x1", "Vitamin C for the common cold", study_type="systematic_review")]
    assert ug.apply_unproven_guard(gclaim("Garlic cures the flu"), ev, uns()).verdict == Verdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("st", ["case_report", "observational", "narrative_review", "animal", "unknown"])
def test_weaker_designs_need_three(st):
    ev = [rec("ev_1", "Garlic and influenza", study_type=st), rec("ev_2", "Garlic and colds", study_type=st)]
    assert ug.apply_unproven_guard(gclaim("Garlic cures the flu"), ev, uns()).verdict == Verdict.INSUFFICIENT_EVIDENCE


# ------------------------------------------------------------------ (c) outcome unspecified


@pytest.mark.parametrize("text", [
    "vitamin K is a vitamin that helps prevent a potentially devastating condition",
    "Garlic cures many diseases",
    "Sea moss helps with lots of health problems",
    "This tea prevents all kinds of illnesses",
])
def test_vague_outcome_is_unspecified(text):
    assert ug.outcome_unspecified(text)


@pytest.mark.parametrize("text", [
    "Turmeric cures arthritis", "this tea prevents heart disease", "Garlic cures the flu",
    "Burdock Root: Rids Kidney & Gallbladder Stones", "Mullein Leaf: Cures Thyroid Issues",
    "the evidence supporting the preventive vitamin K injection for newborns is overwhelming",
    "Eggs are high in antioxidants, which is really good to prevent something called macular degeneration",
    "il vient d'inventer un savon qui traite le cancer de la peau",
])
def test_named_outcome_is_not_unspecified(text):
    assert not ug.outcome_unspecified(text)


def test_unspecified_outcome_is_enforced_in_code_even_with_enough_evidence():
    claim = gclaim("Garlic cures many diseases")
    out = ug.apply_unproven_guard(claim, GARLIC, uns())
    assert out.verdict == Verdict.INSUFFICIENT_EVIDENCE and out.limitations[-1] == ug.OUTCOME_UNSPECIFIED_LIMITATION


class Caller:
    def __init__(self, answer: dict):
        self.answer, self.calls = answer, []

    def call(self, step, input, *, system=None):
        self.calls.append(input)
        return SimpleNamespace(output=self.answer, record=SimpleNamespace(model="mock", prompt_version="verify_v3"))


def _answer(**kw) -> dict:
    return {"verdict": "UNSUPPORTED", "supporting_evidence_ids": [], "contradicting_evidence_ids": [],
            "explanation": "No evidence supports this claim.", "limitations": [], "raw_confidence": 0.5, **kw}


def test_verifier_prompt_offers_the_flag_and_honours_it():
    claim = gclaim("Garlic cures the flu")  # a named outcome: only the model's flag fires
    caller = Caller(_answer(outcome_unspecified=True))
    out, _ = vf.verify_claim(claim, GARLIC, caller, "system", "verify_v3", allow_unsupported=True)
    assert out.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert out.limitations[-1] == ug.OUTCOME_UNSPECIFIED_LIMITATION
    assert "outcome_unspecified" in caller.calls[0]["messages"][0]["content"]
    assert "outcome_unspecified" in vf.VERIFY_TOOL["input_schema"]["properties"]
    assert "outcome_unspecified" not in vf.VERIFY_TOOL["input_schema"]["required"]


def test_flag_false_or_missing_changes_nothing():
    for ans in (_answer(), _answer(outcome_unspecified=False)):
        out, _ = vf.verify_claim(gclaim("Garlic cures the flu"), GARLIC, Caller(ans), "s", "verify_v3",
                                 allow_unsupported=True)
        assert out.verdict == Verdict.UNSUPPORTED


def test_flag_on_another_verdict_is_ignored():
    ans = _answer(verdict="SUPPORTED", supporting_evidence_ids=["ev_1"], outcome_unspecified=True)
    out, _ = vf.verify_claim(gclaim("Garlic cures the flu"), GARLIC, Caller(ans), "s", "verify_v3",
                             allow_unsupported=True)
    assert out.verdict == Verdict.SUPPORTED


# ------------------------------------------------------------------ (b) sibling claims


def test_sibling_supported_efficacy_claim_demotes_unsupported():
    claims = [gclaim("Garlic cures the flu", "c1"), gclaim("Garlic prevents the flu in adults", "c2", "prevention")]
    results = {"c1": uns("c1"), "c2": VerificationResult(claim_id="c2", verdict=Verdict.SUPPORTED,
                                                          supporting_evidence_ids=["ev_1"])}
    out = ug.apply_sibling_rule(claims, results)
    assert out["c1"].verdict == Verdict.INSUFFICIENT_EVIDENCE and out["c1"].limitations[-1] == ug.SIBLING_LIMITATION
    assert out["c2"] is results["c2"]


@pytest.mark.parametrize("sibling, category, verdict", [
    ("Turmeric cures the flu", "treatment_efficacy", Verdict.SUPPORTED),  # other intervention
    ("Garlic prevents the flu", "mechanism", Verdict.SUPPORTED),  # not an efficacy category
    ("Garlic prevents the flu", "prevention", Verdict.INSUFFICIENT_EVIDENCE),  # not supported
    ("Garlic prevents colds", "prevention", Verdict.SUPPORTED),  # a different named outcome
])
def test_sibling_rule_needs_same_intervention_efficacy_and_supported(sibling, category, verdict):
    claims = [gclaim("Garlic cures the flu", "c1"), gclaim(sibling, "c2", category)]
    sup = ["ev_1"] if verdict == Verdict.SUPPORTED else []
    results = {"c1": uns("c1"), "c2": VerificationResult(claim_id="c2", verdict=verdict, supporting_evidence_ids=sup)}
    assert ug.apply_sibling_rule(claims, results)["c1"].verdict == Verdict.UNSUPPORTED


def test_tune_v22_supported_claim_about_another_outcome_is_not_a_sibling():
    """Tune v22 (golden MISINFO unproven): "eggs prevent fatty liver" being SUPPORTED says
    nothing about "eggs prevent macular degeneration". The queue row's literal rule
    (same intervention only) demoted it; the narrowed rule keeps it."""
    claims = [
        gclaim("Eggs are high in antioxidants, which is really good to prevent something called "
               "macular degeneration", "c2", "prevention"),
        gclaim("Eggs are also high in something called choline, which is really good to prevent a "
               "fatty liver", "c3", "prevention"),
    ]
    assert ug.same_intervention(*claims) and not ug.same_outcome(*claims)
    results = {"c2": uns("c2"), "c3": VerificationResult(claim_id="c3", verdict=Verdict.SUPPORTED,
                                                          supporting_evidence_ids=["ev_1"])}
    assert ug.apply_sibling_rule(claims, results)["c2"].verdict == Verdict.UNSUPPORTED


def test_vitamin_k_c12_and_c14_are_siblings():
    job = load_real()
    by = {c["claim_id"]: gclaim(c["text"], c["claim_id"], c["category"]) for c in job["claims"]}
    assert ug.same_intervention(by["c12"], by["c14"]) and ug.same_outcome(by["c12"], by["c14"])


def test_sibling_demoted_claim_keeps_its_review_reason_but_no_longer_decides():
    claims = [gclaim("Garlic cures the flu", "c1"), gclaim("Garlic prevents the flu", "c2", "prevention")]
    s = initial_state(job_id="j", video_id="v", media_uri="mem://v", pipeline_version="t")
    v1 = ug.apply_sibling_rule(claims, {"c1": uns("c1"), "c2": VerificationResult(
        claim_id="c2", verdict=Verdict.SUPPORTED, supporting_evidence_ids=["ev_1"])})
    s.update(claims=claims, verification_results=v1,
             stance_results={c.claim_id: StanceResult(claim_id=c.claim_id, stance=Stance.ENDORSES,
                                                      stance_segment_ids=["t1"]) for c in claims},
             retrieved_evidence={"c2": [rec("ev_1", "Garlic and colds")]},
             retrieval_attempts={"c1": 3, "c2": 3})
    final, _ = jg.judge(s)
    assert final.classification == MisinfoLabel.NO_MISINFO and final.misinfo_basis is None
    assert f"{jg.FLAG_UNPROVEN}:c1" in final.review_flags


# ------------------------------------------------------------------ (f) main_claims_unchecked


def views(*rows):
    """rows: (stance, verdict, category)"""
    out = []
    for i, (stance, verdict, cat) in enumerate(rows, start=1):
        c = gclaim(f"claim {i}", f"c{i}", cat)
        sup = [f"ev_{i}"] if verdict in (Verdict.SUPPORTED, Verdict.MIXED) else []
        con = [f"ev_{i}"] if verdict in (Verdict.CONTRADICTED,) else []
        out.append(jg.ClaimView(claim=c, stance=stance, position=i, allowed_evidence_ids=frozenset({f"ev_{i}"}),
                                verification=VerificationResult(claim_id=c.claim_id, verdict=verdict,
                                                                supporting_evidence_ids=sup,
                                                                contradicting_evidence_ids=con)))
    return out


E, RF = Stance.ENDORSES, Stance.REFUTES
SUP, INS, CON = Verdict.SUPPORTED, Verdict.INSUFFICIENT_EVIDENCE, Verdict.CONTRADICTED


@pytest.mark.parametrize("rows, fires", [
    ([(E, SUP, "other"), (E, INS, "prevention")], True),  # 1/1
    ([(E, SUP, "treatment_efficacy"), (E, INS, "prevention")], True),  # 1/2 = half
    ([(E, SUP, "treatment_efficacy"), (E, SUP, "prevention"), (E, INS, "prevention")], False),  # 1/3
    ([(E, SUP, "other"), (E, INS, "mechanism")], False),  # no main claim
    ([(E, SUP, "other"), (RF, INS, "prevention")], False),  # refuted, not endorsed
    ([(E, SUP, "other"), (Stance.QUOTES, INS, "treatment_efficacy")], False),
])
def test_main_claims_unchecked_rule(rows, fires):
    d = jg.decide(views(*rows))
    assert d.label == MisinfoLabel.NO_MISINFO
    assert (jg.FLAG_MAIN_CLAIMS_UNCHECKED in d.review_flags) is fires
    assert (jg.FLAG_MAIN_CLAIMS_UNCHECKED in d.rule_review_reasons) is fires


@pytest.mark.parametrize("rows", [
    [(E, CON, "treatment_efficacy"), (E, INS, "prevention")],  # MISINFO
    [(E, INS, "prevention")],  # CANNOT_RECOGNIZE (nothing judged)
])
def test_main_claims_unchecked_only_on_no_misinfo(rows):
    d = jg.decide(views(*rows))
    assert d.label != MisinfoLabel.NO_MISINFO and jg.FLAG_MAIN_CLAIMS_UNCHECKED not in d.review_flags


def test_main_claims_unchecked_has_plain_text():
    reason = parse_reason(f"judge:{jg.FLAG_MAIN_CLAIMS_UNCHECKED}")
    assert reason.code == "main_claims_unchecked" and reason.claim_id is None
    assert "could not be checked" in reason.text and "_" not in reason.text
    assert "could not be checked" in jg.flag_text(jg.FLAG_MAIN_CLAIMS_UNCHECKED)


def test_frontend_has_plain_text_for_main_claims_unchecked():
    ts = (Path(__file__).resolve().parents[3] / "frontend" / "lib" / "vocabulary.ts")
    if not ts.exists():
        pytest.skip("frontend not checked out")
    assert re.search(r"main_claims_unchecked:\s*\n?\s*\"", ts.read_text())


# ------------------------------------------------------------------ (e) reranker


def test_reranker_demotes_vitamin_k_antagonist_only_records():
    rr = Reranker()
    claim = "Vitamin K prevents bleeding in newborns"
    recs = [
        rec("a", "Vitamin K antagonists and intracranial hemorrhage after thrombectomy"),
        rec("b", "Anticoagulation reversal in vitamin K antagonist-associated intracerebral hemorrhage"),
        rec("c", "Vitamin K prophylaxis and late vitamin K deficiency bleeding in newborns"),
        rec("d", "Reversal of vitamin K antagonists with intravenous vitamin K in bleeding newborns"),
    ]
    kept = [k.evidence_id for k in rr.rerank(claim, recs).kept]
    assert "c" in kept and "d" in kept  # a plain vitamin K mention still counts
    assert "a" not in kept and "b" not in kept


def test_c13_anticoagulant_papers_are_demoted():
    """Regression on the real c13 rows of job d2bf4179: the three papers whose only
    vitamin K match is "vitamin K antagonist(s)" were kept with relevance 1.0 in
    production; on their titles they now score 0 for vitamin K and are dropped. (The
    fixture has no abstracts, so this checks titles only.)"""
    job = load_real()
    c13 = next(c for c in job["claims"] if c["claim_id"] == "c13")
    ev = evidence_of(c13)
    antagonist_only = {e.evidence_id for e in ev if "antagonist" in e.title.lower()}
    assert len(antagonist_only) == 3
    prod_relevance = {f"ev_{e['pmid']}": e["relevance"] for e in c13["evidence"]}
    assert all(prod_relevance[i] == 1 for i in antagonist_only)  # kept at the top in production
    kept = {k.evidence_id for k in Reranker().rerank(c13["text"], ev, c13["claim_kind"]).kept}
    assert not kept & antagonist_only
    # A title that names vitamin K itself (deficiency bleeding in infancy) is still kept.
    assert any("deficiency" in e.title.lower() and e.evidence_id in kept for e in ev)


# ------------------------------------------------------------------ production replay (d2bf4179)


def evidence_of(c: dict) -> list[EvidenceRecord]:
    return [EvidenceRecord(
        evidence_id=f"ev_{e['pmid']}", source="pubmed", pmid=e["pmid"], title=e["title"],
        publication_year=e.get("year"), publication_type=list(e.get("publication_type") or []),
        study_type=e.get("study_type"), source_url=f"https://pubmed.ncbi.nlm.nih.gov/{e['pmid']}/",
    ) for e in c.get("evidence") or []]


def verifier_answer(c: dict) -> dict | None:
    if not c.get("evidence"):
        return None
    rel = lambda x: [f"ev_{e['pmid']}" for e in c["evidence"] if e.get("relation") == x]  # noqa: E731
    return {"verdict": c["verdict"], "supporting_evidence_ids": rel("SUPPORTS"),
            "contradicting_evidence_ids": rel("CONTRADICTS"), "explanation": c.get("explanation") or "",
            "limitations": list(c.get("limitations") or []), "raw_confidence": 0.6}


class RecordedVerifier:
    def __init__(self, answers: dict[str, dict]):
        self.answers, self.calls = answers, []

    def call(self, step, input, *, system=None):
        cid = re.search(r"Judge claim (\S+) ", input["messages"][0]["content"]).group(1)
        self.calls.append(cid)
        return SimpleNamespace(output=self.answers[cid], record=SimpleNamespace(model="recorded", prompt_version="verify_v3"))


def job_state(job: dict) -> dict:
    s = initial_state(job_id=job["job_id_prefix"], video_id="vid", media_uri="mem://vid", pipeline_version="test")
    claims, stances, evidence = [], {}, {}
    for c in job["claims"]:
        cid = c["claim_id"]
        claims.append(GraphClaim(
            claim_id=cid, claim_text=c["text"], claim_category=c["category"], claim_kind=c["claim_kind"],
            source_segment_ids=[f"t_{cid}"], start_seconds=c["start_seconds"], end_seconds=c["end_seconds"]))
        stances[cid] = StanceResult(claim_id=cid, stance=Stance(c["stances"][0]["stance"]),
                                    stance_segment_ids=[f"t_{cid}"])
        evidence[cid] = evidence_of(c)
    transcript = [TranscriptSegment(segment_id=f"t_{c['claim_id']}", start=c["start_seconds"],
                                    end=c["end_seconds"], text=c["text"]) for c in job["claims"]]
    s.update(claims=claims, stance_results=stances, retrieved_evidence=evidence, reranked_evidence=evidence,
             transcript_segments=transcript,
             retrieval_attempts={c["claim_id"]: c["retrieval_attempts"] for c in job["claims"]})
    return s


def run_job(node, job=None) -> dict:
    job = job or load_real()
    s = job_state(job)
    s = {**s, **node(s)}
    s["final_result"] = jg.make_judge_classification(None)(s)["final_result"]
    s["validation_errors"] = [str(i) for i in validate(s)]
    s["validation_attempts"] = 1
    return {**s, **make_stub_nodes()[r.ROUTE_FOR_REVIEW](s)}


def answers(job: dict) -> dict:
    return {c["claim_id"]: a for c in job["claims"] if (a := verifier_answer(c))}


def node_with(guard, sibling: bool):
    """The verify node with a chosen per-claim guard and with/without the sibling rule."""
    def node(state):
        caller = RecordedVerifier(answers(load_real()))
        out = {}
        for c in state["claims"]:
            ev = state["reranked_evidence"][c.claim_id]
            res, _ = vf.verify_claim(c, ev, caller, "system", "verify_v3",
                                     allow_unsupported=r.unproven_eligible(state, c.claim_id))
            out[c.claim_id] = guard(c, ev, res)
        if sibling:
            out = ug.apply_sibling_rule(state["claims"], out)
        return {"verification_results": out}
    return node


def t49_only(c, ev, res):
    """The T49 guard as it ran in production (91a7a13): UNSUPPORTED with an on-topic record
    stands. Production's c12 record passed the on-topic check (its abstract, not in the
    fixture, names vitamin K; the stored UNSUPPORTED reached the judge), so this replay
    treats every kept record as on topic."""
    return res


@pytest.fixture
def production_on_topic(monkeypatch):
    """As in production: c12's one kept record passed the T49 on-topic check (the fixture
    has titles only; the brodifacoum title doesn't say vitamin K, the abstract did)."""
    monkeypatch.setattr(ug, "on_topic_ids", lambda claim, evidence, cited=(): [e.evidence_id for e in evidence])


def test_fixture_is_the_real_production_job():
    job = load_real()
    assert job["_provenance"].startswith("COPIED FROM PRODUCTION") and job["job_id_prefix"] == "d2bf4179"
    by = {c["claim_id"]: c for c in job["claims"]}
    assert len(by) == 14
    assert by["c12"]["verdict"] == "UNSUPPORTED" and len(by["c12"]["evidence"]) == 1
    assert by["c12"]["evidence"][0]["study_type"] == "case_report"
    assert by["c14"]["verdict"] == "SUPPORTED" and by["c14"]["category"] == "treatment_efficacy"
    assert (job["result"]["label"], job["result"]["misinfo_basis"]) == ("MISINFO", "unproven")
    assert job["result"]["deciding_claim_ids"] == ["c12"]


def test_reproduces_the_production_label_without_t64():
    out = run_job(node_with(t49_only, sibling=False))
    got = {cid: v.verdict.value for cid, v in out["verification_results"].items()}
    assert got == {c["claim_id"]: c["verdict"] for c in load_real()["claims"]}
    final = out["final_result"]
    assert (final.classification.value, final.misinfo_basis, final.claim_ids) == ("MISINFO", "unproven", ["c12"])


def test_vitamin_k_rerun_is_not_misinfo_with_t64():
    """The real rows through the real verify node (all T49 + T64 checks) and judge."""
    caller = RecordedVerifier(answers(load_real()))
    out = run_job(vf.make_verify_claims(caller, prompt_version="verify_v3"))
    final = out["final_result"]
    assert final.classification == MisinfoLabel.NO_MISINFO and final.misinfo_basis is None
    vr = out["verification_results"]
    assert vr["c12"].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert not any(v.verdict == Verdict.UNSUPPORTED for v in vr.values())
    # (f): c12 (prevention) unchecked, c14 (treatment_efficacy) supported: half → reviewed.
    assert "judge:main_claims_unchecked" in out["review_reasons"] and out["requires_human_review"]
    # Severity still comes from the claims: the same with or without the new reason.
    sev = assess(out).severity
    assert sev is not None and sev == assess({**out, "review_reasons": []}).severity


@pytest.mark.parametrize("rule, limitation", [
    ("c", ug.OUTCOME_UNSPECIFIED_LIMITATION),
    ("a", ug.THIN_SEARCH_LIMITATION),
    ("b", ug.SIBLING_LIMITATION),
])
def test_each_rule_alone_clears_the_production_label(production_on_topic, rule, limitation):
    """With c12's record on topic, as in production, each of (a), (b), (c) on its own
    turns c12 into INSUFFICIENT_EVIDENCE and the video into NO_MISINFO."""
    def guard(c, ev, res):
        if res.verdict != Verdict.UNSUPPORTED:
            return res
        if rule == "c" and ug.outcome_unspecified(c.claim_text):
            return ug._insufficient(res, ug.OUTCOME_UNSPECIFIED_EXPLANATION, limitation)
        if rule == "a" and ug.thin_search(ev):
            return ug._insufficient(res, ug.THIN_SEARCH_EXPLANATION, limitation)
        return res

    out = run_job(node_with(guard, sibling=rule == "b"))
    c12 = out["verification_results"]["c12"]
    assert c12.verdict == Verdict.INSUFFICIENT_EVIDENCE and c12.limitations[-1] == limitation
    final = out["final_result"]
    assert final.classification == MisinfoLabel.NO_MISINFO and final.misinfo_basis is None
    assert "judge:main_claims_unchecked" in out["review_reasons"]
    # (b) keeps the review reason of the claim it demotes.
    assert ("judge:unproven_claim:c12" in out["review_reasons"]) is (rule == "b")


def test_full_t64_node_with_production_on_topic_check(production_on_topic):
    caller = RecordedVerifier(answers(load_real()))
    out = run_job(vf.make_verify_claims(caller, prompt_version="verify_v3"))
    c12 = out["verification_results"]["c12"]
    assert c12.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert c12.limitations[-1] == ug.OUTCOME_UNSPECIFIED_LIMITATION  # (c) fires first in the guard
    assert out["final_result"].classification == MisinfoLabel.NO_MISINFO


# ------------------------------------------------------------------ judge cross-check note


def test_crosscheck_classifies_main_claims_unchecked_as_a_known_backend_only_kind():
    from app.evaluation import judge_crosscheck as xc

    video = xc.GoldenVideo(video_id="vx", out_of_scope=False, recorded_label="NO_MISINFO",
                           recorded_review_reasons=(), claims=(
                               xc.GoldenClaim("c1", "ENDORSES", "SUPPORTED", ("PMID:1",), (), "other"),
                               xc.GoldenClaim("c2", "ENDORSES", "INSUFFICIENT_EVIDENCE", (), (), "prevention")))
    backend = xc.run_backend(video)
    assert backend.label == "NO_MISINFO" and "main_claims_unchecked" in backend.reasons
    golden = xc.JudgeOutput(label="NO_MISINFO", deciding=("c1",), reasons=frozenset())
    kind = xc.classify_difference("main_claims_unchecked", "backend", video, golden)
    assert kind == "main_claims_unchecked_not_in_golden_judge" and kind in xc.DIFFERENCE_KINDS


def test_golden_set_without_categories_never_raises_main_claims_unchecked():
    """Why the T24 cross-check is unchanged: no categories in the golden set."""
    from app.evaluation import judge_crosscheck as xc

    video = xc.GoldenVideo(video_id="vy", out_of_scope=False, recorded_label="NO_MISINFO",
                           recorded_review_reasons=(), claims=(
                               xc.GoldenClaim("c1", "ENDORSES", "SUPPORTED", ("PMID:1",)),
                               xc.GoldenClaim("c2", "ENDORSES", "INSUFFICIENT_EVIDENCE")))
    assert "main_claims_unchecked" not in xc.run_backend(video).reasons
