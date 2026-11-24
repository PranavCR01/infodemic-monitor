"""Review HTTP API and roles (T27; design §12, §15, §17).

Tokens are real HS256 JWTs signed with a test secret and verified by the real
``get_current_user``, so the role check runs end to end. No network: the database is
in-memory SQLite and the re-analysis dispatcher is a fake.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import reviews
from app.auth.roles import Role, role_of
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db

SECRET = "test-secret-not-real-0123456789abcdef"
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def token(sub: str, *, app_role=None, user_role=None, top_role="authenticated", **extra) -> str:
    claims = {"sub": sub, "aud": "authenticated", "role": top_role,
              "exp": datetime.now(timezone.utc) + timedelta(hours=1), **extra}
    if app_role is not None:
        claims["app_metadata"] = {"provider": "email", "role": app_role}
    if user_role is not None:
        claims["user_metadata"] = {"role": user_role}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


ANALYST = auth(token("analyst-1"))
REVIEWER = auth(token("reviewer-1", app_role="reviewer"))
REVIEWER2 = auth(token("reviewer-2", app_role="reviewer"))
ADMIN = auth(token("admin-1", app_role="admin"))


def _claims(**over):
    base = {
        "c1": {"severity": "HIGH", "basis": ["topic:cancer"], "stance": "ENDORSES",
               "verdict": "CONTRADICTED", "misinfo_relevant": True},
        "c2": {"severity": "LOW", "basis": [], "stance": "QUOTES",
               "verdict": "INSUFFICIENT_EVIDENCE", "misinfo_relevant": False},
    }
    base.update(over)
    return base


PG_DSN = os.environ.get("LIBRARY_TEST_PG_DSN")


_TABLES = ("videos", "jobs", "results", "human_reviews", "audit_events",
           "claims", "claim_stances", "verification_results", "review_pre_reveals", "users")


@pytest.fixture(scope="module")
def pg_engine():
    """One throwaway Postgres database for this module (CI sets LIBRARY_TEST_PG_DSN), so
    the row lock and the queue's SQL run on the real database too."""
    if not PG_DSN:
        pytest.skip("set LIBRARY_TEST_PG_DSN to a throwaway Postgres database with pgvector")
    from sqlalchemy.engine import make_url

    import app.db.models  # noqa: F401

    name = f"t27_{uuid.uuid4().hex[:12]}"
    admin = create_engine(PG_DSN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(make_url(PG_DSN).set(database=name))
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in _TABLES])
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(params=["sqlite", "postgres"])
def env(request, monkeypatch):
    import app.db.models  # noqa: F401

    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    if request.param == "sqlite":
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in _TABLES])
    else:
        engine = request.getfixturevalue("pg_engine")
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE " + ", ".join(_TABLES) + " CASCADE"))
    Session = sessionmaker(bind=engine)

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    dispatched: list[tuple] = []
    state = {"fail_dispatch": False}

    def dispatcher():
        def _d(job_id, storage_key):
            if state["fail_dispatch"]:
                raise ConnectionError("broker down")
            dispatched.append((job_id, storage_key))
            return f"task-{job_id}"
        return _d

    app = FastAPI()
    app.include_router(reviews.router)
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[reviews.get_reanalysis_dispatcher] = dispatcher
    yield {"client": TestClient(app), "Session": Session, "dispatched": dispatched, "state": state}


def add_case(env, job_id, *, severity="HIGH", reasons=("judge:mixed_video",), created=T0,
             claims=None, status="OPEN", label="MISINFO", owner="submitter-1",
             revealed=("reviewer-1", "reviewer-2", "admin-1")):
    """A review case. ``revealed``: reviewers whose blind judgement (T34) is already
    recorded, so tests of other rules can decide HIGH cases; the blind step itself is
    tested in test_review_blind_t34."""
    from app.core.graph.review_policy import rule_of
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.db.models.review import HumanReview, ReviewCaseStatus
    from app.db.models.video import Video

    s = env["Session"]()
    s.add(Video(id=f"vid-{job_id}", filename=f"{job_id}.mp4", file_path="/x", file_size=1,
                storage_key=f"uploads/u/{job_id}.mp4", user_id=owner))
    s.flush()
    # T33: jobs have an owner (NULL-owner cases are admin only; see test_ownership_t33).
    s.add(Job(id=job_id, video_id=f"vid-{job_id}", status=JobStatus.REVIEW_REQUIRED, user_id=owner))
    s.flush()
    s.add(Result(job_id=job_id, label=label, confidence=0.0, explanation="x", evidence_snippets=[],
                 combined_content="", provider="graph", model_used="none", latency_ms=1))
    case = HumanReview(
        id=f"rev-{job_id}", job_id=job_id, status=ReviewCaseStatus(status), reasons=list(reasons),
        rules_fired=[{"rule": rule_of(r), "reasons": [r]} for r in reasons], validation_errors=[],
        proposed_label=label, proposed_result={"classification": label, "claim_ids": ["c1"]},
        policy_version="p1", pipeline_version="t", created_at=created, severity=severity,
        claim_severities=_claims() if claims is None else claims, severity_table_version="sev-1",
    )
    s.add(case)
    s.flush()
    from app.db.models.review import ReviewPreReveal

    for sub in revealed if status == "OPEN" else ():
        s.add(ReviewPreReveal(review_id=case.id, reviewer_id=sub, claims={}))
    s.commit()
    s.close()
    return f"rev-{job_id}"


# ------------------------------------------------------------------ roles


@pytest.mark.parametrize("user,expected", [
    ({"sub": "a"}, Role.ANALYST),
    ({"sub": "a", "app_metadata": {"role": "reviewer"}}, Role.REVIEWER),
    ({"sub": "a", "app_metadata": {"role": "ADMIN"}}, Role.ADMIN),
    ({"sub": "a", "app_metadata": {"roles": ["reviewer", "admin"]}}, Role.ADMIN),
    ({"sub": "a", "app_metadata": {"role": "superuser"}}, Role.ANALYST),
    ({"sub": "a", "app_metadata": {"role": 7}}, Role.ANALYST),
    ({"sub": "a", "app_metadata": "admin"}, Role.ANALYST),
    # User-editable metadata and the Postgres role claim are never trusted.
    ({"sub": "a", "user_metadata": {"role": "admin"}}, Role.ANALYST),
    ({"sub": "a", "role": "admin"}, Role.ANALYST),
    ({"sub": "a", "role": "service_role"}, Role.ANALYST),
])
def test_role_of(user, expected):
    assert role_of(user) == expected


def test_me_reports_server_side_role(env):
    c = env["client"]
    assert c.get("/v1/me", headers=ANALYST).json()["role"] == "analyst"
    me = c.get("/v1/me", headers=REVIEWER).json()
    assert me["user_id"] == "reviewer-1" and me["role"] == "reviewer"
    assert "reviews:decide" in me["permissions"]
    assert c.get("/v1/me", headers=ADMIN).json()["role"] == "admin"
    forged = auth(token("u", user_role="admin", top_role="admin"))
    assert c.get("/v1/me", headers=forged).json()["role"] == "analyst"


def test_dev_user_role_comes_from_config(env, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_AUTH", False)
    c = env["client"]
    assert c.get("/v1/me").json()["role"] == "analyst"
    monkeypatch.setattr(settings, "DEV_USER_ROLE", "reviewer")
    assert c.get("/v1/me").json()["role"] == "reviewer"


def test_missing_bad_or_forged_tokens_are_refused(env):
    c = env["client"]
    rid = add_case(env, "j1")
    assert c.get("/v1/reviews").status_code == 401
    assert c.get("/v1/reviews", headers={"Authorization": "Bearer nope"}).status_code == 401
    other_key = jwt.encode({"sub": "x", "app_metadata": {"role": "admin"}}, "wrong-secret-0123456789abcdef-0123456789", algorithm="HS256")
    assert c.get("/v1/reviews", headers=auth(other_key)).status_code == 401
    expired = jwt.encode({"sub": "x", "app_metadata": {"role": "admin"},
                          "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, SECRET, algorithm="HS256")
    assert c.get(f"/v1/reviews/{rid}", headers=auth(expired)).status_code == 401
    no_sub = jwt.encode({"app_metadata": {"role": "admin"}}, SECRET, algorithm="HS256")
    assert c.get("/v1/reviews", headers=auth(no_sub)).status_code == 401


def test_analyst_cannot_see_or_act_on_reviews(env):
    c = env["client"]
    rid = add_case(env, "j1")
    assert c.get("/v1/reviews", headers=ANALYST).status_code == 403
    assert c.get(f"/v1/reviews/{rid}", headers=ANALYST).status_code == 403
    # Same answer for a case that doesn't exist: nothing is revealed.
    assert c.get("/v1/reviews/missing", headers=ANALYST).status_code == 403
    r = c.post(f"/v1/reviews/{rid}/decision", headers=ANALYST, json={"action": "APPROVE", "reason": "checked the papers"})
    assert r.status_code == 403
    r = c.post(f"/v1/reviews/{rid}/claims/c1/severity", headers=ANALYST,
               json={"severity": "LOW", "reason": "x"})
    assert r.status_code == 403
    # User-editable metadata claiming reviewer changes nothing.
    forged = auth(token("analyst-2", user_role="reviewer"))
    assert c.post(f"/v1/reviews/{rid}/decision", headers=forged,
                  json={"action": "APPROVE", "reason": "checked the papers"}).status_code == 403
    case = c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()
    assert case["status"] == "OPEN" and case["audit_trail"] == []


# ------------------------------------------------------------------ queue


def test_queue_sorts_by_severity_then_age_and_paginates(env):
    c = env["client"]
    add_case(env, "low-old", severity="LOW", created=T0)
    add_case(env, "high-new", severity="HIGH", created=T0 + timedelta(hours=2))
    add_case(env, "high-old", severity="HIGH", created=T0)
    add_case(env, "none", severity=None, created=T0 - timedelta(days=1))
    add_case(env, "med", severity="MEDIUM", created=T0 + timedelta(hours=5))
    r = c.get("/v1/reviews", headers=REVIEWER)
    assert r.status_code == 200
    body = r.json()
    assert [i["job_id"] for i in body["items"]] == ["high-old", "high-new", "med", "low-old", "none"]
    assert body["total"] == 5 and body["limit"] == 20 and body["offset"] == 0
    first = body["items"][0]
    assert first["review_id"] == "rev-high-old" and first["video_id"] == "vid-high-old"
    assert first["filename"] == "high-old.mp4" and first["job_status"] == "REVIEW_REQUIRED"
    assert first["age_seconds"] > 0 and first["decision"] is None
    assert first["rules_fired"] == [{"rule": "judge_flags", "reasons": ["judge:mixed_video"]}]

    page = c.get("/v1/reviews?limit=2&offset=2", headers=ADMIN).json()
    assert [i["job_id"] for i in page["items"]] == ["med", "low-old"] and page["total"] == 5
    assert c.get("/v1/reviews?limit=0", headers=REVIEWER).status_code == 422
    assert c.get("/v1/reviews?limit=101", headers=REVIEWER).status_code == 422
    assert c.get("/v1/reviews?offset=-1", headers=REVIEWER).status_code == 422


def test_queue_filters_by_severity_reason_and_status(env):
    c = env["client"]
    add_case(env, "a", severity="HIGH", reasons=["weak_evidence:c1", "judge:mixed_video"])
    add_case(env, "b", severity="MEDIUM", reasons=["unclear_stance:c2"])
    add_case(env, "c", severity=None, reasons=["weak_evidence:c3"])
    add_case(env, "d", severity="HIGH", reasons=["weak_evidence:c1"], status="RESOLVED")

    def ids(q):
        r = c.get(f"/v1/reviews{q}", headers=REVIEWER)
        assert r.status_code == 200, r.text
        return [i["job_id"] for i in r.json()["items"]], r.json()["total"]

    assert ids("?severity=HIGH") == (["a"], 1)
    assert ids("?severity=HIGH,NONE") == (["a", "c"], 2)
    assert ids("?severity=medium&severity=none") == (["b", "c"], 2)
    assert ids("?reason=weak_evidence") == (["a", "c"], 2)        # by rule / prefix
    assert ids("?reason=weak_evidence:c3") == (["c"], 1)          # exact reason
    assert ids("?reason=judge_flags") == (["a"], 1)               # rule name of judge:*
    assert ids("?reason=weak_evidence&severity=HIGH") == (["a"], 1)
    assert ids("?reason=weak_evidence&limit=1&offset=1") == (["c"], 2)
    assert ids("?status=RESOLVED") == (["d"], 1)
    assert ids("?status=ALL&reason=weak_evidence") == (["a", "d", "c"], 3)
    assert c.get("/v1/reviews?severity=URGENT", headers=REVIEWER).status_code == 422
    assert c.get("/v1/reviews?status=CLOSED", headers=REVIEWER).status_code == 422


def test_queue_from_a_real_review_case(env):
    """A case opened by the graph's own open_review_case (T09/T22) shows up correctly."""
    from app.db.models.job import Job, JobStatus
    from app.db.models.video import Video
    from app.services.review_service import open_review_case
    from app.tests.test_severity import HIGH_ROW, LOW_ROW, state

    s = env["Session"]()
    s.add(Video(id="vid-g", filename="g.mp4", file_path="/x", file_size=1, user_id="submitter-1"))
    s.flush()
    s.add(Job(id="job-g", video_id="vid-g", status=JobStatus.STARTED, user_id="submitter-1"))
    s.commit()
    st = state(HIGH_ROW, LOW_ROW, job_id="job-g")
    st.update(requires_human_review=True, review_reasons=["judge:mixed_video"])
    case = open_review_case(s, "job-g", st)
    rid = case.id
    s.close()
    item = env["client"].get("/v1/reviews", headers=REVIEWER).json()["items"][0]
    assert item["review_id"] == rid and item["severity"] == "HIGH"
    full = env["client"].get(f"/v1/reviews/{rid}", headers=REVIEWER).json()
    assert set(full["claim_severities"]) == {"c1", "c2"}


# ------------------------------------------------------------------ case


def test_get_case_has_full_detail(env):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.get(f"/v1/reviews/{rid}", headers=REVIEWER)
    assert r.status_code == 200
    body = r.json()
    assert body["proposed_result"]["classification"] == "MISINFO"
    assert body["claim_severities"]["c1"]["verdict"] == "CONTRADICTED"
    assert body["policy_version"] == "p1" and body["severity_table_version"] == "sev-1"
    assert body["audit_trail"] == [] and body["decision"] is None
    assert c.get("/v1/reviews/nope", headers=REVIEWER).status_code == 404


# ------------------------------------------------------------------ decisions


def _job(env, job_id):
    from app.db.models.job import Job
    from app.db.models.result import Result

    s = env["Session"]()
    job = s.get(Job, job_id)
    result = s.query(Result).filter(Result.job_id == job_id).one()
    out = (job.status.value, job.error_code, result.label)
    s.close()
    return out


def test_approve_records_who_when_why_and_audits(env):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
               json={"action": "APPROVE", "reason": "  papers check out  "})
    assert r.status_code == 200, r.text
    body = r.json()
    case = body["case"]
    assert case["status"] == "RESOLVED" and body["reanalysis_job"] is None
    d = case["decision"]
    assert d["reviewer_id"] == "reviewer-1" and d["action"] == "APPROVE"
    assert d["reason"] == "papers check out" and d["decided_at"]
    [ev] = case["audit_trail"]
    assert ev["actor_id"] == "reviewer-1" and ev["action"] == "review_decision"
    assert ev["reason"] == "papers check out" and ev["details"]["decision"] == "APPROVE"
    assert _job(env, "j1") == ("SUCCESS", None, "MISINFO")
    # Resolved cases leave the default (OPEN) queue.
    assert c.get("/v1/reviews", headers=REVIEWER).json()["total"] == 0
    # A second decision is a conflict.
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER2, json={"action": "REJECT", "reason": "not a health video"})
    assert r.status_code == 409


def test_reason_is_required(env):
    c = env["client"]
    rid = add_case(env, "j1")
    for body in ({"action": "APPROVE"}, {"action": "APPROVE", "reason": ""},
                 {"action": "APPROVE", "reason": "   "}):
        assert c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=body).status_code == 422
    assert c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()["status"] == "OPEN"


def test_client_cannot_name_the_reviewer_or_role(env):
    c = env["client"]
    rid = add_case(env, "j1")
    for extra in ({"reviewer_id": "someone-else"}, {"role": "admin"}):
        r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
                   json={"action": "APPROVE", "reason": "checked the papers", **extra})
        assert r.status_code == 422
    r = c.post(f"/v1/reviews/{rid}/decision", headers=ADMIN, json={"action": "APPROVE", "reason": "checked the papers"})
    assert r.json()["case"]["decision"]["reviewer_id"] == "admin-1"


def test_correct_label_and_claim_verdicts_and_stances(env):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json={
        "action": "CORRECT", "reason": "speaker is debunking",
        "corrected_label": "DEBUNKING",
        "claim_corrections": [
            {"claim_id": "c1", "stance": "REFUTES"},
            {"claim_id": "c2", "verdict": "CONTRADICTED", "stance": "ENDORSES"},
        ],
    })
    assert r.status_code == 200, r.text
    d = r.json()["case"]["decision"]
    assert d["action"] == "CORRECT" and d["corrected_label"] == "DEBUNKING"
    assert d["corrections"] == {"claims": {
        "c1": {"stance": {"from": "ENDORSES", "to": "REFUTES"}},
        "c2": {"verdict": {"from": "INSUFFICIENT_EVIDENCE", "to": "CONTRADICTED"},
               "stance": {"from": "QUOTES", "to": "ENDORSES"}},
    }}
    assert r.json()["case"]["audit_trail"][0]["details"]["corrections"] == d["corrections"]
    assert _job(env, "j1") == ("SUCCESS", None, "DEBUNKING")
    # The model's original claim view is kept alongside the correction.
    assert r.json()["case"]["claim_severities"]["c1"]["stance"] == "ENDORSES"


def test_correct_with_only_claim_corrections_keeps_label(env):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json={
        "action": "CORRECT", "reason": "verdict wrong",
        "claim_corrections": [{"claim_id": "c1", "verdict": "SUPPORTED"}]})
    assert r.status_code == 200, r.text
    assert _job(env, "j1") == ("SUCCESS", None, "MISINFO")


@pytest.mark.parametrize("body,status", [
    ({"action": "CORRECT", "reason": "reviewer note x"}, 422),                                   # nothing to correct
    ({"action": "CORRECT", "reason": "reviewer note x", "corrected_label": "FAKE"}, 422),        # unknown label
    ({"action": "CORRECT", "reason": "reviewer note x", "claim_corrections": [{"claim_id": "c9", "verdict": "SUPPORTED"}]}, 422),
    ({"action": "CORRECT", "reason": "reviewer note x", "claim_corrections": [{"claim_id": "c1", "verdict": "MAYBE"}]}, 422),
    ({"action": "CORRECT", "reason": "reviewer note x", "claim_corrections": [{"claim_id": "c1"}]}, 422),
    ({"action": "CORRECT", "reason": "reviewer note x", "claim_corrections": [{"claim_id": "c1", "verdict": "CONTRADICTED"}]}, 422),
    ({"action": "CORRECT", "reason": "reviewer note x", "claim_corrections": [
        {"claim_id": "c1", "verdict": "SUPPORTED"}, {"claim_id": "c1", "stance": "REFUTES"}]}, 422),
    ({"action": "APPROVE", "reason": "reviewer note x", "corrected_label": "MISINFO"}, 422),     # approve takes no corrections
    ({"action": "REJECT", "reason": "reviewer note x", "claim_corrections": [{"claim_id": "c1", "verdict": "SUPPORTED"}]}, 422),
    ({"action": "DELETE", "reason": "reviewer note x"}, 422),
])
def test_invalid_decisions_change_nothing(env, body, status):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=body)
    assert r.status_code == status, r.text
    case = c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()
    assert case["status"] == "OPEN" and case["audit_trail"] == []
    assert _job(env, "j1") == ("REVIEW_REQUIRED", None, "MISINFO")


def test_reject_and_mark_insufficient(env):
    c = env["client"]
    a, b = add_case(env, "ja"), add_case(env, "jb")
    assert c.post(f"/v1/reviews/{a}/decision", headers=REVIEWER,
                  json={"action": "REJECT", "reason": "off-topic video"}).status_code == 200
    assert _job(env, "ja") == ("FAILED", "REVIEW_REJECTED", "MISINFO")
    assert c.post(f"/v1/reviews/{b}/decision", headers=REVIEWER,
                  json={"action": "MARK_INSUFFICIENT", "reason": "too confident"}).status_code == 200
    assert _job(env, "jb") == ("SUCCESS", None, "CANNOT_RECOGNIZE")


def test_decision_on_missing_case_is_404(env):
    r = env["client"].post("/v1/reviews/nope/decision", headers=REVIEWER, json={"action": "APPROVE", "reason": "reviewer note x"})
    assert r.status_code == 404


def test_request_reanalysis_starts_a_new_job(env):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
               json={"action": "REQUEST_REANALYSIS", "reason": "retrieval terms fixed"})
    assert r.status_code == 200, r.text
    body = r.json()
    new = body["reanalysis_job"]
    assert new["video_id"] == "vid-j1" and new["status"] == "PENDING" and new["job_id"] != "j1"
    assert env["dispatched"] == [(new["job_id"], "uploads/u/j1.mp4")]
    actions = [e["action"] for e in body["case"]["audit_trail"]]
    assert actions == ["review_decision", "reanalysis_started"]
    assert body["case"]["audit_trail"][1]["details"]["new_job_id"] == new["job_id"]
    assert body["case"]["status"] == "RESOLVED"
    assert _job(env, "j1")[0] == "REVIEW_REQUIRED"  # old job unchanged (T09)


def test_reanalysis_dispatch_failure_keeps_the_decision(env):
    c = env["client"]
    env["state"]["fail_dispatch"] = True
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
               json={"action": "REQUEST_REANALYSIS", "reason": "try again with new terms"})
    assert r.status_code == 200
    assert r.json()["reanalysis_job"]["status"] == "FAILED"
    assert r.json()["reanalysis_job"]["error_code"] == "DISPATCH_FAILED"
    assert r.json()["case"]["status"] == "RESOLVED"


# ------------------------------------------------------------------ severity override


def test_severity_override_reorders_and_is_audited(env):
    c = env["client"]
    a = add_case(env, "a", severity="HIGH", created=T0 + timedelta(hours=1))
    add_case(env, "b", severity="MEDIUM", created=T0)
    r = c.post(f"/v1/reviews/{a}/claims/c1/severity", headers=REVIEWER,
               json={"severity": "LOW", "reason": "satire account, low reach"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["severity"] == "LOW"
    assert body["claim_severities"]["c1"]["override"]["reviewer_id"] == "reviewer-1"
    [ev] = body["audit_trail"]
    assert ev["action"] == "severity_override" and ev["details"]["from"] == "HIGH" and ev["details"]["to"] == "LOW"
    # Labels never change; queue order does.
    assert body["proposed_label"] == "MISINFO" and _job(env, "a") == ("REVIEW_REQUIRED", None, "MISINFO")
    assert [i["job_id"] for i in c.get("/v1/reviews", headers=REVIEWER).json()["items"]] == ["b", "a"]


@pytest.mark.parametrize("path,body,status", [
    ("c1", {"severity": "LOW"}, 422),                          # no reason
    ("c1", {"severity": "LOW", "reason": "  "}, 422),          # blank reason
    ("c1", {"severity": "URGENT", "reason": "x"}, 422),        # unknown level
    ("c1", {"severity": "HIGH", "reason": "x"}, 409),          # unchanged
    ("c9", {"severity": "LOW", "reason": "x"}, 404),           # not this case's claim
    ("c1", {"severity": "LOW", "reason": "x", "reviewer_id": "z"}, 422),
])
def test_severity_override_rules(env, path, body, status):
    c = env["client"]
    rid = add_case(env, "j1")
    r = c.post(f"/v1/reviews/{rid}/claims/{path}/severity", headers=REVIEWER, json=body)
    assert r.status_code == status, r.text
    assert c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()["audit_trail"] == []


def test_severity_override_missing_case_is_404(env):
    r = env["client"].post("/v1/reviews/nope/claims/c1/severity", headers=ADMIN,
                           json={"severity": "LOW", "reason": "x"})
    assert r.status_code == 404


def test_full_audit_trail_in_order(env):
    c = env["client"]
    rid = add_case(env, "j1")
    c.post(f"/v1/reviews/{rid}/claims/c1/severity", headers=REVIEWER2, json={"severity": "MEDIUM", "reason": "a"})
    c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json={"action": "APPROVE", "reason": "approved after checking"})
    trail = c.get(f"/v1/reviews/{rid}", headers=ADMIN).json()["audit_trail"]
    assert [(e["actor_id"], e["action"], e["reason"]) for e in trail] == [
        ("reviewer-2", "severity_override", "a"), ("reviewer-1", "review_decision", "approved after checking")]


def test_app_mounts_review_routes():
    """The router serves the five routes and app.main includes it. (Importing app.main
    needs greenlet for the async health check, which isn't a test dependency.)"""
    from pathlib import Path

    paths = {r.path for r in reviews.router.routes}
    assert paths == {"/v1/me", "/v1/reviews", "/v1/reviews/{review_id}",
                     "/v1/reviews/{review_id}/decision", "/v1/reviews/{review_id}/claims/{claim_id}/severity",
                     "/v1/jobs/{job_id}/review-request",  # T32
                     "/v1/reviews/{review_id}/pre-reveal",  # T34
                     "/v1/reviews/{review_id}/blind-material"}  # T40
    main_src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "app.include_router(reviews.router)" in main_src


def test_claim_corrections_on_a_case_opened_before_severity(env):
    """Cases opened before migration 0010 have no claim_severities: the claims, with
    their stance and verdict, come from the stored claim rows (T11)."""
    from app.db.models.claim import ClaimRow, ClaimStanceRow, VerificationResultRow

    rid = add_case(env, "old", severity=None, claims={})
    s = env["Session"]()
    row = ClaimRow(job_id="old", claim_id="c1", text="t", category="other", start_seconds=0.0,
                   end_seconds=1.0, source_segment_ids=["t1"])
    s.add(row)
    s.flush()
    s.add(ClaimStanceRow(claim_pk=row.id, stance="ENDORSES", segment_ids=["t1"]))
    s.add(VerificationResultRow(claim_pk=row.id, verdict="CONTRADICTED", limitations=[]))
    s.commit()
    s.close()
    r = env["client"].post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json={
        "action": "CORRECT", "reason": "reviewer note x", "claim_corrections": [{"claim_id": "c1", "verdict": "SUPPORTED"}]})
    assert r.status_code == 200, r.text
    assert r.json()["case"]["decision"]["corrections"] == {
        "claims": {"c1": {"verdict": {"from": "CONTRADICTED", "to": "SUPPORTED"}}}}
