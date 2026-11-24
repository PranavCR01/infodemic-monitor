"""Tests for the ``nothing_judged`` review reason (T37; target design §9, §11, §12).

When no claim could be judged and any claim is INSUFFICIENT_EVIDENCE, the judge adds the
review reason ``nothing_judged``. Videos with no checkable claims (no claims, or all
NOT_VERIFIABLE) are not sent for it. A case carrying it is LOW whatever the severity
table says, and the queue puts it after everything else.

No network, no model: states are built by hand, the judge is the real rule code, the
database is in-memory SQLite.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.graph import judge as jg
from app.core.graph import review_policy as rp
from app.core.graph import severity as sv
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
from app.services.review_reasons import parse_reason

S, V = Stance, Verdict
REASON = "judge:nothing_judged"
TEXT = "No claim in this video could be checked against the evidence."


def make_state(*rows, job_id: str = "job-t37") -> dict:
    """One claim per row ``(text, category, stance, verdict)``; judge and review rule
    are the real code."""
    s = initial_state(job_id=job_id, video_id="v1", media_uri="mem://v1", pipeline_version="test",
                      video_duration_seconds=60.0)
    claims, stances, verdicts, evidence = [], {}, {}, {}
    for i, (text, category, stance, verdict) in enumerate(rows, start=1):
        cid, eid = f"c{i}", f"ev_c{i}"
        claims.append(GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                                 source_segment_ids=["t1"], start_seconds=1.0, end_seconds=2.0))
        stances[cid] = StanceResult(claim_id=cid, stance=stance, stance_segment_ids=["t1"])
        evidence[cid] = [EvidenceRecord(evidence_id=eid, source="pubmed", pmid=str(i), title="P",
                                        abstract="A trial.", publication_type=["Randomized Controlled Trial"])]
        verdicts[cid] = VerificationResult(
            claim_id=cid, verdict=verdict,
            supporting_evidence_ids=[eid] if verdict in (V.SUPPORTED, V.MIXED) else [],
            contradicting_evidence_ids=[eid] if verdict == V.CONTRADICTED else [],
        )
    s.update(claims=claims, stance_results=stances, verification_results=verdicts,
             retrieved_evidence=evidence, reranked_evidence=evidence)
    s.update(jg.make_judge_classification()(s))
    s["validation_errors"] = []  # validation passed
    s.update(rp.make_route_for_review()(s))
    return s


def row(verdict, stance=S.ENDORSES, text="Ginger tea helps with nausea", category="other"):
    return (text, category, stance, verdict)


# ------------------------------------------------------------------ the judge (§9)


@pytest.mark.parametrize("verdicts", [
    [V.INSUFFICIENT_EVIDENCE],
    [V.INSUFFICIENT_EVIDENCE, V.NOT_VERIFIABLE],
    [V.NOT_VERIFIABLE, V.INSUFFICIENT_EVIDENCE, V.MIXED],
    [V.INSUFFICIENT_EVIDENCE, V.UNSUPPORTED],  # QUOTES + UNSUPPORTED below: not unproven
])
def test_nothing_judged_with_an_insufficient_claim_adds_the_reason(verdicts):
    s = make_state(*(row(v, stance=S.QUOTES) for v in verdicts))
    final = s["final_result"]
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert final.decision_rule == jg.RULE_NOTHING_JUDGED
    assert final.claim_ids == []
    assert "nothing_judged" in final.review_flags
    assert s["requires_human_review"] and REASON in s["review_reasons"]


def test_endorsed_insufficient_claim_also_adds_it():
    s = make_state(row(V.INSUFFICIENT_EVIDENCE, stance=S.ENDORSES))
    assert "nothing_judged" in s["final_result"].review_flags


def test_reason_is_one_of_the_rules_own_reasons():
    views = [_view("c1", S.NEUTRAL, V.INSUFFICIENT_EVIDENCE)]
    d = jg.decide(views)
    assert d.rule == jg.RULE_NOTHING_JUDGED
    assert d.rule_review_reasons == ["nothing_judged"]


def _view(cid, stance, verdict) -> jg.ClaimView:
    c = GraphClaim(claim_id=cid, claim_text="x", claim_category="other", source_segment_ids=[],
                   start_seconds=0.0, end_seconds=1.0)
    return jg.ClaimView(claim=c, stance=stance,
                        verification=VerificationResult(claim_id=cid, verdict=verdict),
                        allowed_evidence_ids=frozenset(), position=1)


@pytest.mark.parametrize("verdicts", [[V.NOT_VERIFIABLE], [V.NOT_VERIFIABLE, V.NOT_VERIFIABLE]])
def test_all_not_verifiable_is_not_sent(verdicts):
    s = make_state(*(row(v) for v in verdicts))
    assert s["final_result"].decision_rule == jg.RULE_NOTHING_JUDGED
    assert "nothing_judged" not in s["final_result"].review_flags
    assert REASON not in s["review_reasons"]
    assert not s["requires_human_review"]


def test_no_claims_is_not_sent():
    s = make_state()
    assert s["final_result"].decision_rule == jg.RULE_NO_CLAIMS
    assert "nothing_judged" not in s["final_result"].review_flags
    assert not s["requires_human_review"]


def test_mixed_without_insufficient_does_not_add_it():
    """The reason is about too little evidence; MIXED alone is sent already (weak
    evidence, mixed evidence), without ``nothing_judged``. (An UNSUPPORTED verdict that
    fails T30's gate becomes INSUFFICIENT_EVIDENCE and so does add it.)"""
    s = make_state(row(V.MIXED, stance=S.QUOTES), row(V.NOT_VERIFIABLE, stance=S.NEUTRAL))
    assert s["final_result"].decision_rule == jg.RULE_NOTHING_JUDGED
    assert "nothing_judged" not in s["final_result"].review_flags


@pytest.mark.parametrize("rows,rule", [
    ([row(V.SUPPORTED), row(V.INSUFFICIENT_EVIDENCE)], jg.RULE_JUDGED),
    ([row(V.CONTRADICTED), row(V.INSUFFICIENT_EVIDENCE)], jg.RULE_ENDORSED_CONTRADICTED),
    ([row(V.INSUFFICIENT_EVIDENCE, stance=S.REFUTES)], jg.RULE_REFUTED_UNSETTLED),
    ([row(V.INSUFFICIENT_EVIDENCE, stance=S.REFUTES), row(V.INSUFFICIENT_EVIDENCE)], jg.RULE_REFUTED_UNSETTLED),
])
def test_only_the_last_branch_adds_it(rows, rule):
    s = make_state(*rows)
    assert s["final_result"].decision_rule == rule
    assert "nothing_judged" not in s["final_result"].review_flags


def test_no_label_change():
    for rows in ([row(V.INSUFFICIENT_EVIDENCE)], [row(V.NOT_VERIFIABLE)], []):
        assert make_state(*rows)["final_result"].classification == MisinfoLabel.CANNOT_RECOGNIZE


def test_template_explanation_names_it_in_plain_words():
    final = make_state(row(V.INSUFFICIENT_EVIDENCE))["final_result"]
    assert "no claim in this video could be checked against the evidence" in final.explanation.lower()
    assert "nothing_judged" not in final.explanation


# ------------------------------------------------------------------ the reason text (§12)


def test_plain_language_text():
    r = parse_reason(REASON)
    assert r.code == "nothing_judged"
    assert r.rule == "judge_flags"
    assert r.claim_id is None
    assert r.text == TEXT


# ------------------------------------------------------------------ severity (§12)

# A table-HIGH topic, endorsed and unsettled: misinfo-relevant, so without T37 it is HIGH.
HIGH_INSUFFICIENT = ("Cut sugar to starve your cancer", "nutrition", S.ENDORSES, V.INSUFFICIENT_EVIDENCE)


def test_case_severity_is_low_regardless_of_the_table():
    s = make_state(HIGH_INSUFFICIENT)
    a = sv.assess(s)
    assert a.claims["c1"]["severity"] == "HIGH" and a.claims["c1"]["misinfo_relevant"]
    assert a.severity == sv.Severity.LOW
    assert sv.video_severity(a.claims) == sv.Severity.HIGH  # the table's view is unchanged


def test_case_severity_helper():
    claims = {"c1": {"severity": "HIGH", "misinfo_relevant": True}}
    assert sv.case_severity(claims, [REASON]) == sv.Severity.LOW
    assert sv.case_severity(claims, ["nothing_judged"]) == sv.Severity.LOW
    assert sv.case_severity(claims, ["weak_evidence:c1"]) == sv.Severity.HIGH
    assert sv.case_severity({}, [REASON]) == sv.Severity.LOW
    assert sv.case_severity({}, None) is None


@pytest.fixture()
def db():
    from app.db.base import Base
    import app.db.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _open(db, job_id, *rows, created_at=None, extra_reasons=()):
    from app.db.models.job import Job, JobStatus
    from app.db.models.video import Video
    from app.services.review_service import open_review_case

    db.add(Video(id=f"vid-{job_id}", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id=job_id, video_id=f"vid-{job_id}", status=JobStatus.STARTED))
    db.commit()
    s = make_state(*rows, job_id=job_id)
    if extra_reasons:
        s["review_reasons"] = [*s["review_reasons"], *extra_reasons]
        s["requires_human_review"] = True
    case = open_review_case(db, job_id, s)
    if created_at is not None:
        case.created_at = created_at
        db.commit()
    return case


LOW_ROW = ("Legs up the wall improves circulation", "other", S.ENDORSES, V.CONTRADICTED)
HIGH_ROW = ("Cut sugar to starve your cancer", "nutrition", S.ENDORSES, V.CONTRADICTED)
NONE_ROW = ("Garlic stops colds", "prevention", S.REFUTES, V.MIXED)  # possible debunk, no severity


def test_open_case_stores_low_and_the_reason(db):
    case = _open(db, "nj", HIGH_INSUFFICIENT)
    assert case.severity == "LOW"
    assert REASON in case.reasons
    assert case.claim_severities["c1"]["severity"] == "HIGH"


def test_queue_puts_nothing_judged_after_everything_else(db):
    from app.services.review_service import review_queue_page, review_queue

    t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
    names = {}
    for name, r, age in [
        ("nj_oldest", HIGH_INSUFFICIENT, -10), ("high", HIGH_ROW, 3), ("low", LOW_ROW, 2),
        ("none", NONE_ROW, 1), ("nj_new", row(V.INSUFFICIENT_EVIDENCE), 5),
    ]:
        extra = () if name.startswith("nj") else ("judge:mixed_video",)  # send the others too
        names[_open(db, name, r, created_at=t0 + timedelta(hours=age), extra_reasons=extra).id] = name
    expected = ["high", "low", "none", "nj_oldest", "nj_new"]
    assert [names[c.id] for c in review_queue(db)] == expected
    page, total = review_queue_page(db)
    assert [names[c.id] for c in page] == expected and total == 5
    low, _ = review_queue_page(db, severities=["LOW"])
    assert [names[c.id] for c in low] == ["low", "nj_oldest", "nj_new"]


def test_override_and_refresh_keep_it_low(db):
    from app.services.review_service import open_review_case, override_claim_severity

    case = _open(db, "nj", row(V.INSUFFICIENT_EVIDENCE))
    case = override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="HIGH", reason="dangerous")
    assert case.claim_severities["c1"]["override"]["severity"] == "HIGH"
    assert case.severity == "LOW"
    again = open_review_case(db, "nj", make_state(row(V.INSUFFICIENT_EVIDENCE), job_id="nj"))
    assert again.claim_severities["c1"]["override"]["severity"] == "HIGH"
    assert again.severity == "LOW"
