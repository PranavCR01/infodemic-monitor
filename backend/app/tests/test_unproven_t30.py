"""T30: the unproven-claim verdict (decision D1 = B; target design §7, §9, §11, §12).

UNSUPPORTED is the verdict for an *efficacy* claim (treatment_efficacy / prevention)
that the full search budget found no evidence for or against. An endorsed one makes the
video MISINFO with ``misinfo_basis`` ``unproven``, shown as "MISINFO (unproven)" and
always reviewed. Every other no-evidence claim stays INSUFFICIENT_EVIDENCE.
"""
from __future__ import annotations

import re
import pytest

from app.core.graph import critic as cr
from app.core.graph import judge as jg
from app.core.graph import routing as r
from app.core.graph import severity as sev
from app.core.graph.nodes import make_stub_nodes
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    NodeError,
    Stance as S,
    Verdict as V,
    VerificationResult,
)
from app.core.graph.validation import validate
from app.core.schemas.pipeline import MisinfoLabel
from app.tests.test_judge import FakeCaller, make_state, run_judge

E, RF, Q, N, U = S.ENDORSES, S.REFUTES, S.QUOTES, S.NEUTRAL, S.UNCLEAR
SUP, CON, MIX, INS, NV, UNS = (
    V.SUPPORTED, V.CONTRADICTED, V.MIXED, V.INSUFFICIENT_EVIDENCE, V.NOT_VERIFIABLE, V.UNSUPPORTED,
)
FULL = r.DEFAULT_BUDGETS.max_retrieval_attempts


def state(*rows, category: str = "treatment_efficacy", attempts: int = FULL, **extra) -> dict:
    """``make_state`` with every claim searched ``attempts`` times; ``category`` applies
    to every claim unless a row carries its own as a third item."""
    plain = [row[:2] for row in rows]
    s = make_state(*plain, **extra)
    s["claims"] = [
        c.model_copy(update={"claim_category": row[2] if len(row) > 2 else category})
        for c, row in zip(s["claims"], rows)
    ]
    s.setdefault("retrieval_attempts", {c.claim_id: attempts for c in s["claims"]})
    return s


def reviewed(s: dict) -> dict:
    """Judge, validate and run the real review rule, as the graph does."""
    s["final_result"] = run_judge(s)[0]
    s["validation_errors"] = [str(i) for i in validate(s)]
    s["validation_attempts"] = 1
    return make_stub_nodes()[r.ROUTE_FOR_REVIEW](s)


# ------------------------------------------------------------ acceptance criteria


def test_unproven_efficacy_claim_is_misinfo_unproven_and_reviewed():
    s = state((E, UNS))
    final = run_judge(s)[0]
    assert final.classification == MisinfoLabel.MISINFO
    assert final.misinfo_basis == jg.BASIS_UNPROVEN
    assert final.decision_rule == jg.RULE_ENDORSED_UNSUPPORTED
    assert final.claim_ids == ["c1"] and final.evidence_ids == []
    assert f"{jg.FLAG_UNPROVEN}:c1" in final.review_flags
    assert jg.display_label(final.classification, final.misinfo_basis) == "MISINFO (unproven)"

    out = reviewed(s)
    assert out["requires_human_review"] is True
    assert f"judge:{jg.FLAG_UNPROVEN}:c1" in out["review_reasons"]
    assert "weak_evidence:c1" in out["review_reasons"]  # §11: UNSUPPORTED deciding claim


@pytest.mark.parametrize("category", ["prevention", "treatment_efficacy"])
def test_both_efficacy_categories_qualify(category):
    final = run_judge(state((E, UNS), category=category))[0]
    assert final.misinfo_basis == jg.BASIS_UNPROVEN


@pytest.mark.parametrize("category", ["side_effects", "mechanism", "causation", "health_claim", "other"])
def test_unproven_harm_or_other_claim_stays_insufficient_and_cannot_recognize(category):
    """Even if an UNSUPPORTED verdict reached state for such a claim, the judge sees
    INSUFFICIENT_EVIDENCE (no evidence of harm is not evidence of harm)."""
    s = state((E, UNS), category=category)
    assert r.verdicts_for_judge(s)["c1"].verdict == INS
    final = run_judge(s)[0]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert final.decision_rule == jg.RULE_NOTHING_JUDGED and final.misinfo_basis is None


def test_contradicted_still_wins_over_unsupported():
    final = run_judge(state((E, UNS), (E, CON)))[0]
    assert final.classification == MisinfoLabel.MISINFO
    assert final.misinfo_basis == jg.BASIS_CONTRADICTED
    assert final.decision_rule == jg.RULE_ENDORSED_CONTRADICTED and final.claim_ids == ["c2"]
    # the unproven claim still raises its review reason (§9: from every claim)
    assert f"{jg.FLAG_UNPROVEN}:c1" in final.review_flags


def test_denies_supported_comes_before_unproven():
    final = run_judge(state((E, UNS), (RF, SUP)))[0]
    assert (final.misinfo_basis, final.claim_ids) == (jg.BASIS_DENIES_SUPPORTED, ["c2"])
    assert {f"{jg.FLAG_UNPROVEN}:c1", f"{jg.FLAG_DENIES_SUPPORTED}:c2"} <= set(final.review_flags)


@pytest.mark.parametrize("other", [Q, N, U, None])
def test_debunking_still_wins_when_nothing_is_endorsed(other):
    final = run_judge(state((other, UNS), (RF, CON)))[0]
    assert final.classification == MisinfoLabel.DEBUNKING and final.misinfo_basis is None
    assert not any(f.startswith(jg.FLAG_UNPROVEN) for f in final.review_flags)


def test_unproven_beats_debunking_and_the_video_is_mixed():
    """§9: mixed_video also when an unproven claim is endorsed and a false one refuted."""
    final = run_judge(state((E, UNS), (RF, CON)))[0]
    assert final.classification == MisinfoLabel.MISINFO and final.misinfo_basis == jg.BASIS_UNPROVEN
    assert jg.FLAG_MIXED_VIDEO in final.review_flags
    assert jg.FLAG_MIXED_VIDEO in jg.decide(jg.claim_views(state((E, UNS), (RF, CON)))[0]).rule_review_reasons


def test_unproven_beats_no_misinfo():
    final = run_judge(state((E, SUP), (E, UNS)))[0]
    assert final.misinfo_basis == jg.BASIS_UNPROVEN and final.claim_ids == ["c2"]


def test_refuted_unproven_claim_is_a_possible_debunk_not_misinfo():
    """A speaker refuting an untested cure: CANNOT_RECOGNIZE, reviewed as a possible
    debunk (the flag it raised as INSUFFICIENT_EVIDENCE before T30)."""
    final = run_judge(state((RF, UNS)))[0]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert final.decision_rule == jg.RULE_REFUTED_UNSETTLED
    assert f"{jg.FLAG_POSSIBLE_DEBUNK}:c1" in final.review_flags


def test_existing_labels_unchanged_without_unsupported():
    """Additive: the four labels and their basis-free rules are as before."""
    assert run_judge(state((E, CON)))[0].misinfo_basis == jg.BASIS_CONTRADICTED
    for rows, label in [([(RF, CON)], MisinfoLabel.DEBUNKING), ([(E, SUP)], MisinfoLabel.NO_MISINFO),
                        ([(E, INS)], MisinfoLabel.CANNOT_RECOGNIZE)]:
        final = run_judge(state(*rows))[0]
        assert final.classification == label and final.misinfo_basis is None


# ------------------------------------------------------------------ the gate


def test_unsupported_needs_the_full_search_budget():
    s = state((E, UNS), attempts=FULL - 1)
    v = r.verdicts_for_judge(s)["c1"]
    assert v.verdict == INS and v.limitations[-1] == r.UNPROVEN_DOWNGRADE_LIMITATION
    assert run_judge(s)[0].classification == MisinfoLabel.CANNOT_RECOGNIZE


def test_unsupported_with_citations_is_not_allowed():
    s = state((E, UNS))
    s["verification_results"]["c1"] = s["verification_results"]["c1"].model_copy(
        update={"supporting_evidence_ids": ["ev_c1"]})
    assert r.verdicts_for_judge(s)["c1"].verdict == INS


@pytest.mark.parametrize("node", [r.PLAN_RETRIEVAL, r.RETRIEVE_EVIDENCE, r.RERANK_EVIDENCE])
def test_a_search_error_rules_out_unproven(node):
    """An outage must never be read as "nothing was found"."""
    s = state((E, UNS), errors=[NodeError(node=node, claim_id="c1", message="PubMed retrieval failed")])
    assert r.verdicts_for_judge(s)["c1"].verdict == INS
    assert run_judge(s)[0].classification == MisinfoLabel.CANNOT_RECOGNIZE
    # another claim's error doesn't matter
    s = state((E, UNS), errors=[NodeError(node=node, claim_id="c9", message="x")])
    assert r.verdicts_for_judge(s)["c1"].verdict == UNS


def test_exhausted_unsupported_keeps_its_verdict():
    """The critic still wanted more search when the budget ran out: for an UNSUPPORTED
    claim that is exactly "the full search found nothing", so it is not withheld."""
    s = state((E, UNS))
    s["critic_results"] = {"c1": CriticResult(claim_id="c1", decision=CriticDecision.RETRIEVE_MORE)}
    assert "c1" in r.exhausted_claim_ids(s)
    assert r.verdicts_for_judge(s)["c1"].verdict == UNS
    assert run_judge(s)[0].misinfo_basis == jg.BASIS_UNPROVEN


def test_critic_asks_for_another_search_while_budget_is_left():
    v = VerificationResult(claim_id="c1", verdict=UNS)
    c = make_state((E, INS))["claims"][0]
    res, _ = cr.review_claim(c, None, v, [], None, attempts=1)
    assert res.decision == CriticDecision.RETRIEVE_MORE and "code:search_budget" in res.checks
    res, _ = cr.review_claim(c, None, v, [], None, attempts=FULL)
    assert res.decision == CriticDecision.APPROVE
    cited = v.model_copy(update={"supporting_evidence_ids": ["ev_1"]})
    assert any(f.check == "strength" for f in cr.code_checks(cited, []))


# ------------------------------------------------------------ wording (§7, T30)


_ENUM = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b")


def _assert_display_wording(text: str, claim_ids: list[str]) -> None:
    assert not _ENUM.search(text), text
    for cid in claim_ids:
        assert not re.search(rf"\b{cid}\b", text), (cid, text)


def test_unproven_explanation_says_no_evidence_supports_it_never_false():
    s = state((E, UNS))
    final = run_judge(s)[0]
    text = final.explanation
    assert "no evidence supports this claim" in text
    assert "MISINFO (unproven)" in text
    assert "false" not in text.lower()
    assert 'the first claim ("Claim number 1 cures the flu")' in text
    _assert_display_wording(text, ["c1"])


@pytest.mark.parametrize("rows", [
    [], [(E, INS)], [(E, NV), (Q, MIX)], [(E, CON)], [(RF, SUP)], [(E, UNS)], [(RF, CON)],
    [(RF, INS)], [(E, SUP), (Q, CON)], [(U, CON), (E, SUP)], [(E, CON), (RF, CON), (E, MIX)],
    [(E, UNS), (RF, CON), (RF, INS)],
])
def test_template_uses_display_wording_for_every_rule(rows):
    s = state(*rows)
    final = run_judge(s)[0]
    _assert_display_wording(final.explanation, [c.claim_id for c in s["claims"]])
    assert not final.explanation.startswith(("CANNOT", "NO_MISINFO", "DEBUNKING:", "MISINFO:"))


def test_claims_are_named_by_position():
    s = state((E, SUP), (Q, CON), (E, SUP))
    text = run_judge(s)[0].explanation
    assert "the first claim, the third claim" in text and "the second claim (the speaker quotes it)" in text
    assert jg.claim_reference(11) == "claim 11"


@pytest.mark.parametrize("text,why", [
    ("MISINFO (unproven): the first claim is false.", "described as false"),
    ("MISINFO because claim c1 has no evidence.", "names claims by ID"),
    ("MISINFO because the evidence is INSUFFICIENT_EVIDENCE.", "internal name"),
])
def test_model_explanation_breaking_the_wording_rules_falls_back(text, why):
    final, errors = run_judge(state((E, UNS)), FakeCaller({"explanation": text}))
    assert why in errors[0].message
    assert final.model is None and "no evidence supports this claim" in final.explanation


def test_model_explanation_in_display_wording_is_kept_and_review_note_appended():
    text = "MISINFO (unproven): the speaker presents the first claim as a cure, but no evidence supports it."
    caller = FakeCaller({"explanation": text})
    final, errors = run_judge(state((E, UNS)), caller)
    assert errors == [] and final.explanation.startswith(text)
    assert final.explanation.endswith(
        "Needs review: no evidence supports the first claim, which the speaker presents as working.")
    content = caller.calls[0].input["messages"][0]["content"]
    assert "MISINFO (unproven)" in content and "call it: the first claim" in content


def test_explain_prompt_v2_tells_the_writer_the_rules():
    from app.core.graph.stance import load_prompt

    text = load_prompt(jg.DEFAULT_PROMPT_VERSION)
    assert "NEVER by claim ID" in text and "no evidence supports this claim" in text


def test_unproven_result_passes_validation():
    s = state((E, UNS), (RF, CON))
    s["final_result"] = run_judge(s)[0]
    assert validate(s) == []


# ------------------------------------------------------------ per-claim, severity


@pytest.mark.parametrize("stance,label", [
    (E, MisinfoLabel.MISINFO), (RF, MisinfoLabel.CANNOT_RECOGNIZE), (Q, MisinfoLabel.CANNOT_RECOGNIZE),
])
def test_claim_label_for_unsupported(stance, label):
    assert jg.claim_label(stance, UNS) == label


def test_unproven_claim_counts_towards_severity():
    assert sev.misinfo_relevant(E, UNS) is True
    assert sev.misinfo_relevant(RF, UNS) is False


@pytest.mark.parametrize("label,basis,shown", [
    ("MISINFO", "unproven", "MISINFO (unproven)"), ("MISINFO", "contradicted", "MISINFO"),
    ("MISINFO", None, "MISINFO"), ("CANNOT_RECOGNIZE", None, "CANNOT RECOGNIZE"),
    ("NO_MISINFO", None, "NO MISINFO"), ("DEBUNKING", None, "DEBUNKING"),
    (MisinfoLabel.MISINFO, "unproven", "MISINFO (unproven)"),
])
def test_display_label(label, basis, shown):
    assert jg.display_label(label, basis) == shown


def test_reason_text_for_unproven_claim():
    from app.services.review_reasons import parse_reason

    view = parse_reason("judge:unproven_claim:c1")
    assert view.code == "unproven_claim" and view.claim_id == "c1"
    assert "no evidence supports this claim" in view.text and "false" not in view.text.lower()


def test_the_four_labels_are_unchanged():
    assert {m.value for m in MisinfoLabel} == {"MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"}


# ------------------------------------------------- stored result and the API (T26 models)

from app.api.routers import jobs as jobs_router  # noqa: E402
from app.db.models.job import Job, JobStatus  # noqa: E402
from app.db.models.result import Result  # noqa: E402
from app.db.models.video import Video  # noqa: E402
from app.tests.test_result_api_t26 import ALICE, LEGACY_RESULT_KEYS, _session, env  # noqa: E402,F401


def _make_unproven(db, job_id="job-a"):
    res = db.query(Result).filter_by(job_id=job_id).one()
    res.decision_rule, res.misinfo_basis = jg.RULE_ENDORSED_UNSUPPORTED, jg.BASIS_UNPROVEN
    db.commit()


def test_result_api_returns_misinfo_basis_and_display_label(env):
    out = env["client"].get("/jobs/job-a/result").json()
    assert LEGACY_RESULT_KEYS <= set(out)  # existing responses keep working
    assert out["label"] == "MISINFO" and out["misinfo_basis"] is None and out["label_display"] == "MISINFO"
    _make_unproven(env["db"])
    out = env["client"].get("/jobs/job-a/result").json()
    assert out["label"] == "MISINFO"  # the label itself is unchanged
    assert out["misinfo_basis"] == "unproven" and out["label_display"] == "MISINFO (unproven)"
    assert out["decision_rule"] == "endorsed_unsupported"


def test_jobs_list_returns_misinfo_basis_and_display_label(env):
    _make_unproven(env["db"])
    (row,) = env["client"].get("/jobs").json()
    assert row["label"] == "MISINFO" and row["misinfo_basis"] == "unproven"
    assert row["label_display"] == "MISINFO (unproven)"
    # filtering by label still uses the four labels
    assert len(env["client"].get("/jobs", params={"label": "MISINFO"}).json()) == 1


def test_jobs_list_without_a_result_has_null_basis(env):
    db = env["db"]
    db.add(Job(id="job-p", video_id="vid-1", status=JobStatus.PENDING))
    db.commit()
    rows = {r["job_id"]: r for r in env["client"].get("/jobs").json()}
    assert rows["job-p"]["misinfo_basis"] is None and rows["job-p"]["label_display"] is None


def test_persisted_unproven_outcome_end_to_end():
    """Through the real graph (mocked models, nothing found by search) and the real
    persist path: the stored result carries the basis and the case goes to review."""
    from app.db.models.review import HumanReview
    from app.services.pipeline_result_service import persist_outcome
    from app.tests.test_graph_integration import NOTHING_FOUND, fusion, make_provider

    db = _session()
    db.add(Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id="job-1", video_id="vid-1", status=JobStatus.STARTED))
    db.commit()
    outcome = make_provider(node_overrides=NOTHING_FOUND).run(fusion(), job_id="job-1", video_id="vid-1")
    persist_outcome(db, "job-1", fusion(), outcome)
    res = db.query(Result).filter_by(job_id="job-1").one()
    assert (res.label, res.misinfo_basis, res.decision_rule) == ("MISINFO", "unproven", "endorsed_unsupported")
    assert db.get(Job, "job-1").status == JobStatus.REVIEW_REQUIRED
    case = db.query(HumanReview).filter_by(job_id="job-1").one()
    assert any(x.startswith("judge:unproven_claim:") for x in case.reasons)
    out = jobs_router.get_result("job-1", db=db, current_user=ALICE)
    assert out["label_display"] == "MISINFO (unproven)"
    assert {c["verdict"] for c in out["claims"]} == {"UNSUPPORTED"}
    assert "false" not in out["explanation"].lower()


# ------------------------------------------------------------ judge cross-check (T24)


def test_crosscheck_backend_side_handles_unsupported():
    """The golden set will carry UNSUPPORTED after the D1 re-derivation: the backend side
    of the cross-check must treat a golden UNSUPPORTED as final (full search done)."""
    from app.evaluation import judge_crosscheck as xc

    video = xc.GoldenVideo(
        video_id="vx", out_of_scope=False, recorded_label="MISINFO", recorded_review_reasons=(),
        claims=(xc.GoldenClaim("c1", "ENDORSES", "UNSUPPORTED"), xc.GoldenClaim("c2", "REFUTES", "CONTRADICTED")),
    )
    out = xc.run_backend(video)
    assert out.label == "MISINFO" and out.deciding == ("c1",)
    assert {"unproven_claim:c1", "mixed_video", "weak_evidence:c1"} <= out.reasons
    harm = xc.GoldenVideo(
        video_id="vy", out_of_scope=False, recorded_label="CANNOT_RECOGNIZE", recorded_review_reasons=(),
        claims=(xc.GoldenClaim("c1", "ENDORSES", "UNSUPPORTED", claim_category="side_effects"),),
    )
    assert xc.run_backend(harm).label == "CANNOT_RECOGNIZE"
    assert xc.from_fixture(xc.to_fixture([harm]))[0].claims[0].claim_category == "side_effects"
