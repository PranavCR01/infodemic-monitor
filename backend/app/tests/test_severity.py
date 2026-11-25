"""Tests for severity-based review priority (T22, target design §12 "Severity").

No network, no model: states are built by hand, the judge is the real rule code, the
database is in-memory SQLite.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.graph import judge as jg
from app.core.graph import severity as sv
from app.core.graph.review_policy import default_review_policy
from app.core.graph.state import (
    EvidenceRecord,
    GraphClaim,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)

S, V, H, M, L = Stance, Verdict, sv.Severity.HIGH, sv.Severity.MEDIUM, sv.Severity.LOW
CFG = sv.default_severity_config()


def claim(text: str, category: str = "other", cid: str = "c1") -> GraphClaim:
    return GraphClaim(claim_id=cid, claim_text=text, claim_category=category,
                      source_segment_ids=["t1"], start_seconds=1.0, end_seconds=2.0)


def state(*rows, job_id: str = "job-t22") -> dict:
    """One claim per row ``(text, category, stance, verdict)``; the judge's real output
    is filled in."""
    s = initial_state(job_id=job_id, video_id="v1", media_uri="mem://v1", pipeline_version="test",
                      video_duration_seconds=60.0)
    claims, stances, verdicts, evidence = [], {}, {}, {}
    for i, (text, category, stance, verdict) in enumerate(rows, start=1):
        cid, eid = f"c{i}", f"ev_c{i}"
        claims.append(claim(text, category, cid))
        stances[cid] = StanceResult(claim_id=cid, stance=stance, stance_segment_ids=["t1"])
        evidence[cid] = [EvidenceRecord(evidence_id=eid, source="pubmed", pmid=str(i), title="P",
                                        abstract="A trial.", publication_type=["Randomized Controlled Trial"])]
        verdicts[cid] = VerificationResult(
            claim_id=cid, verdict=verdict,
            supporting_evidence_ids=[eid] if verdict == V.SUPPORTED else [],
            contradicting_evidence_ids=[eid] if verdict == V.CONTRADICTED else [],
        )
    s.update(claims=claims, stance_results=stances, verification_results=verdicts,
             retrieved_evidence=evidence, reranked_evidence=evidence)
    s.update(jg.make_judge_classification()(s))
    return s


# ------------------------------------------------------------------ the table


def test_table_is_marked_draft_and_not_signed_off():
    raw = yaml.safe_load(sv.DEFAULT_SEVERITY_PATH.read_text())
    assert raw["status"] == "draft" and CFG.is_draft
    assert not any(raw["sign_off"].values())
    assert "DRAFT. Not for real triage" in sv.DEFAULT_SEVERITY_PATH.read_text()


def test_table_is_seeded_from_the_review_rules_high_risk_list():
    high_risk = default_review_policy().high_risk_categories
    assert high_risk, "T09's list should not be empty"
    for category in high_risk:
        assert CFG.categories[category] == H, category


def test_every_extractor_category_is_mapped():
    from app.core.graph.claims import CATEGORIES

    assert set(CATEGORIES) <= set(CFG.categories)


def test_approved_status_needs_all_three_sign_offs(tmp_path):
    base = {"version": "x", "categories": {"other": "LOW"}}
    with pytest.raises(ValueError, match="signed it off"):
        sv.SeverityConfig.model_validate({**base, "status": "approved",
                                          "sign_off": {"project_lead": True, "dr_brooks": True}})
    ok = sv.SeverityConfig.model_validate({**base, "status": "approved", "sign_off": {
        "project_lead": True, "dr_brooks": True, "who_confirmed": True}})
    assert not ok.is_draft
    with pytest.raises(ValueError, match="status"):
        sv.SeverityConfig.model_validate({**base, "status": "final"})
    with pytest.raises(ValueError):
        sv.SeverityConfig.model_validate({**base, "categories": {"other": "CRITICAL"}})
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump({**base, "status": "draft"}))
    assert sv.load_severity_config(p).categories["other"] == L


# ------------------------------------------------------------------ claims


@pytest.mark.parametrize("text,category,level,basis", [
    # §12's own examples
    ("Cut sugar to starve your cancer", "nutrition", H, "topic:cancer"),
    ("Skip the MMR, it causes autism", "causation", H, "topic:vaccines"),
    ("Detox tea can replace a balanced diet", "nutrition", M, "topic:supplements_and_detox"),
    ("Legs up the wall improves circulation", "other", L, "category:other"),
    # category alone
    ("Hot water cures the flu", "treatment_efficacy", H, "category:treatment_efficacy"),
    ("Garlic prevents colds", "prevention", M, "category:prevention"),
    ("Half of adults sleep badly", "statistic", L, "category:statistic"),
    # the other §12 HIGH topics
    ("Stop taking your insulin and drink lemon water", "other", H, "topic:medication_and_treatment"),
    ("This tea is safe for pregnant women", "safety", H, "topic:pregnancy_and_children"),
    ("Fasting for a week fixes anorexia", "other", H, "topic:self_harm_and_eating_disorders"),
])
def test_claim_severity_examples(text, category, level, basis):
    got = sv.claim_severity(claim(text, category), CFG)
    assert got.severity == level
    assert basis in got.basis


def test_highest_of_category_and_topics_wins():
    # LOW category, HIGH topic → HIGH; basis names only what set the level.
    got = sv.claim_severity(claim("Vitamin D supplements cure cancer", "statistic"), CFG)
    assert got.severity == H and got.basis == ("topic:cancer",)


def test_unmapped_category_gets_the_default_not_low():
    got = sv.claim_severity(claim("Something about sleep", "brand_new_category"), CFG)
    assert got.severity == CFG.default_severity == M and got.basis == ("default",)


@pytest.mark.parametrize("text", [
    "Kidney beans are good for you",    # not "kids"
    "Jabbering helps digestion",        # not "jab"
    "Doses... of sunshine",             # matches "doses" (sanity check below)
])
def test_topics_match_whole_words_only(text):
    got = sv.claim_severity(claim(text, "other"), CFG)
    expected = H if "Doses" in text else L
    assert got.severity == expected


# ------------------------------------------------------------------ MISINFO-relevant


@pytest.mark.parametrize("stance,verdict,relevant", [
    (S.ENDORSES, V.CONTRADICTED, True),
    (S.ENDORSES, V.MIXED, True),
    (S.ENDORSES, V.INSUFFICIENT_EVIDENCE, True),
    (S.ENDORSES, V.NOT_VERIFIABLE, True),
    (S.ENDORSES, V.SUPPORTED, False),
    (S.REFUTES, V.SUPPORTED, True),        # denies a supported claim → MISINFO (§9)
    (S.REFUTES, V.CONTRADICTED, False),    # a debunk
    (S.REFUTES, V.MIXED, False),
    (S.QUOTES, V.CONTRADICTED, False),
    (S.NEUTRAL, V.CONTRADICTED, False),
    (S.UNCLEAR, V.CONTRADICTED, False),
    (None, V.CONTRADICTED, False),
    (S.ENDORSES, None, False),
])
def test_misinfo_relevant(stance, verdict, relevant):
    assert sv.misinfo_relevant(stance, verdict) is relevant


# ------------------------------------------------------------------ video


def test_video_severity_is_the_highest_among_misinfo_relevant_claims():
    s = state(
        ("Legs up the wall improves circulation", "other", S.ENDORSES, V.CONTRADICTED),   # LOW, relevant
        ("Detox tea replaces a diet", "nutrition", S.ENDORSES, V.INSUFFICIENT_EVIDENCE),  # MEDIUM, relevant
        ("Chemo is poison, cancer is cured by juice", "other", S.REFUTES, V.CONTRADICTED),  # HIGH, a debunk
        ("Vaccines are tested", "vaccination", S.ENDORSES, V.SUPPORTED),                 # HIGH, true
    )
    a = sv.assess(s, CFG)
    assert a.severity == M
    assert [c["misinfo_relevant"] for c in a.claims.values()] == [True, True, False, False]
    assert a.claims["c3"]["severity"] == "HIGH"
    assert a.table_version == CFG.version and a.table_status == "draft"


def test_video_with_no_misinfo_relevant_claim_has_no_severity():
    s = state(("Skip the MMR, it causes autism", "causation", S.REFUTES, V.CONTRADICTED))
    assert s["final_result"].classification.value == "DEBUNKING"
    assert sv.assess(s, CFG).severity is None
    assert sv.assess(state(), CFG).severity is None


def test_denying_a_supported_high_risk_claim_is_high():
    s = state(("The MMR vaccine prevents measles", "prevention", S.REFUTES, V.SUPPORTED))
    assert s["final_result"].classification.value == "MISINFO"
    assert sv.assess(s, CFG).severity == H


def test_severity_never_changes_the_label_or_verdicts():
    rows = [("Cut sugar to starve your cancer", "nutrition", S.ENDORSES, V.CONTRADICTED),
            ("Garlic stops colds", "prevention", S.REFUTES, V.CONTRADICTED)]
    s = state(*rows)
    before = copy.deepcopy(s)
    everything_low = CFG.model_copy(update={"categories": {}, "topics": (), "default_severity": L})
    everything_low.model_post_init(None)
    assert sv.assess(s, CFG).severity == H
    assert sv.assess(s, everything_low).severity == L
    assert s == before  # nothing written back into state
    # The judge doesn't read severity: the same claims give the same label and claims.
    again = state(*rows)
    assert again["final_result"] == s["final_result"]
    assert again["verification_results"] == s["verification_results"]


def test_severity_names_no_model():
    src = Path(sv.__file__).read_text()
    for token in ("anthropic", "openai", "StepCaller", "ModelRouter", "claude-", "gpt-"):
        assert token not in src


# ------------------------------------------------------------------ persistence


@pytest.fixture()
def db():
    from app.db.base import Base
    import app.db.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _job(db, job_id: str):
    from app.db.models.job import Job, JobStatus
    from app.db.models.video import Video

    db.add(Video(id=f"vid-{job_id}", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id=job_id, video_id=f"vid-{job_id}", status=JobStatus.STARTED))
    db.commit()


def _open(db, job_id: str, *rows, created_at=None):
    from app.services.review_service import open_review_case

    _job(db, job_id)
    s = state(*rows, job_id=job_id)
    s.update(requires_human_review=True, review_reasons=["judge:mixed_video"])
    case = open_review_case(db, job_id, s)
    if created_at is not None:
        case.created_at = created_at
        db.commit()
    return case, s


HIGH_ROW = ("Cut sugar to starve your cancer", "nutrition", S.ENDORSES, V.CONTRADICTED)
MED_ROW = ("Detox tea replaces a diet", "nutrition", S.ENDORSES, V.CONTRADICTED)
LOW_ROW = ("Legs up the wall improves circulation", "other", S.ENDORSES, V.CONTRADICTED)
NONE_ROW = ("Garlic stops colds", "prevention", S.REFUTES, V.MIXED)


def test_open_review_case_stores_severity(db):
    case, _ = _open(db, "j1", HIGH_ROW, LOW_ROW)
    assert case.severity == "HIGH"
    assert case.severity_table_version == CFG.version
    assert case.claim_severities["c1"] == {
        "severity": "HIGH", "basis": ["topic:cancer"], "stance": "ENDORSES",
        "verdict": "CONTRADICTED", "misinfo_relevant": True,
    }
    assert case.claim_severities["c2"]["severity"] == "LOW"


def test_queue_sorts_by_severity_then_age(db):
    from app.services.review_service import record_review_decision, review_queue

    t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
    ids = {}
    for name, row, age in [
        ("low_old", LOW_ROW, 0), ("high_new", HIGH_ROW, 5), ("none_oldest", NONE_ROW, -1),
        ("med", MED_ROW, 3), ("high_old", HIGH_ROW, 1), ("low_new", LOW_ROW, 9),
    ]:
        case, _ = _open(db, name, row, created_at=t0 + timedelta(hours=age))
        ids[case.id] = name
    order = [ids[c.id] for c in review_queue(db)]
    assert order == ["high_old", "high_new", "med", "low_old", "low_new", "none_oldest"]
    # Resolved cases leave the open queue; status=None lists everything.
    first = review_queue(db)[0]
    record_review_decision(db, first.id, reviewer_id="r1", action="APPROVE", reason="ok")
    assert [ids[c.id] for c in review_queue(db)][0] == "high_new"
    assert len(review_queue(db, status=None)) == 6
    assert len(review_queue(db, limit=2)) == 2
    assert [ids[c.id] for c in review_queue(db, status="RESOLVED")] == ["high_old"]


def test_reviewer_override_is_logged_and_reorders_the_queue(db):
    from app.db.models.job import Job, JobStatus
    from app.services.review_service import review_queue, override_claim_severity, severity_overrides

    t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
    low, _ = _open(db, "low", LOW_ROW, created_at=t0 + timedelta(hours=2))
    med, _ = _open(db, "med", MED_ROW, created_at=t0)
    proposed = copy.deepcopy(low.proposed_result)
    assert [c.job_id for c in review_queue(db)] == ["med", "low"]

    at = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
    done = override_claim_severity(db, low.id, "c1", reviewer_id="dr-b", severity="high",
                                   reason="  advice aimed at people with leg ulcers  ", now=at)
    assert done.severity == "HIGH"
    assert done.claim_severities["c1"]["severity"] == "LOW"  # the table's value is kept
    assert done.claim_severities["c1"]["override"] == {
        "severity": "HIGH", "reason": "advice aimed at people with leg ulcers",
        "reviewer_id": "dr-b", "at": at.isoformat(),
    }
    assert [c.job_id for c in review_queue(db)] == ["low", "med"]

    log = severity_overrides(db)
    assert len(log) == 1
    e = log[0]
    assert (e.actor_id, e.action, e.entity_type, e.entity_id, e.job_id) == (
        "dr-b", "severity_override", "claim", "low:c1", "low")
    assert e.reason == "advice aimed at people with leg ulcers"
    assert e.details["from"] == "LOW" and e.details["to"] == "HIGH"
    assert e.details["video_severity_before"] == "LOW" and e.details["video_severity_after"] == "HIGH"
    assert e.details["severity_table_version"] == CFG.version
    assert e.created_at.replace(tzinfo=timezone.utc) == at
    assert severity_overrides(db, job_id="med") == []

    # Never changes the label, the proposed result, the decision or the job's state.
    assert done.proposed_label == "MISINFO" and done.proposed_result == proposed
    assert done.action is None and done.corrected_label is None
    assert db.get(Job, "low").status == JobStatus.REVIEW_REQUIRED


def test_override_of_a_claim_that_is_not_misinfo_relevant_is_logged_but_not_counted(db):
    from app.services.review_service import override_claim_severity, severity_overrides

    case, _ = _open(db, "mix", LOW_ROW, ("Chemo cures cancer", "other", S.REFUTES, V.CONTRADICTED))
    assert case.severity == "LOW"
    done = override_claim_severity(db, case.id, "c2", reviewer_id="r1", severity="MEDIUM",
                                   reason="table too high for a debunk")
    assert done.severity == "LOW"
    assert len(severity_overrides(db)) == 1


def test_override_rules(db):
    from app.services.review_service import ReviewError, override_claim_severity, severity_overrides

    case, _ = _open(db, "j", HIGH_ROW)
    with pytest.raises(ReviewError, match="reason"):
        override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="LOW", reason=" ")
    with pytest.raises(ReviewError, match="reviewer_id"):
        override_claim_severity(db, case.id, "c1", reviewer_id="", severity="LOW", reason="x")
    with pytest.raises(ReviewError, match="unknown severity"):
        override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="CRITICAL", reason="x")
    with pytest.raises(ReviewError, match="not part of"):
        override_claim_severity(db, case.id, "c9", reviewer_id="r1", severity="LOW", reason="x")
    with pytest.raises(ReviewError, match="not found"):
        override_claim_severity(db, "nope", "c1", reviewer_id="r1", severity="LOW", reason="x")
    with pytest.raises(ReviewError, match="already has"):
        override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="HIGH", reason="x")
    assert severity_overrides(db) == []
    # A second override logs a second event and records from-the-last-override.
    override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="LOW", reason="a")
    override_claim_severity(db, case.id, "c1", reviewer_id="r2", severity="MEDIUM", reason="b")
    log = severity_overrides(db)
    assert [(e.details["from"], e.details["to"]) for e in log] == [("HIGH", "LOW"), ("LOW", "MEDIUM")]


def test_override_on_a_resolved_case_keeps_the_decision(db):
    from app.services.review_service import override_claim_severity, record_review_decision

    case, _ = _open(db, "j", HIGH_ROW)
    record_review_decision(db, case.id, reviewer_id="r1", action="CORRECT", reason="x",
                           corrected_label="DEBUNKING")
    done = override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="MEDIUM", reason="y")
    assert done.severity == "MEDIUM"
    assert done.action.value == "CORRECT" and done.corrected_label == "DEBUNKING"


def test_refreshing_an_open_case_keeps_overrides(db):
    from app.services.review_service import open_review_case, override_claim_severity

    case, s = _open(db, "j", LOW_ROW)
    override_claim_severity(db, case.id, "c1", reviewer_id="r1", severity="HIGH", reason="x")
    again = open_review_case(db, "j", s)  # e.g. a resumed graph re-persists
    assert again.id == case.id
    assert again.severity == "HIGH"
    assert again.claim_severities["c1"]["override"]["severity"] == "HIGH"


def test_migration_0010_upgrades_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "app" / "db" / "migrations"))
    command.upgrade(cfg, "0010")
    insp = inspect(create_engine(url))
    assert {"severity", "claim_severities", "severity_table_version"} <= {
        c["name"] for c in insp.get_columns("human_reviews")}
    assert {"actor_id", "action", "entity_type", "entity_id", "job_id", "reason", "details", "created_at"} <= {
        c["name"] for c in insp.get_columns("audit_events")}
    command.downgrade(cfg, "0009")
    insp = inspect(create_engine(url))
    assert "audit_events" not in insp.get_table_names()
    assert "severity" not in {c["name"] for c in insp.get_columns("human_reviews")}
