"""Deliberate re-analysis with versioned results (T55; design §1, §11, §12, §17).

Uses T33's fixtures: real HS256 tokens through the real ``get_current_user``, fake
storage and a fake queue, on SQLite and (with ``LIBRARY_TEST_PG_DSN``) Postgres. The
seed gives each of alice, bob and a legacy (NULL) owner a video with one job in review
(created at T0), a result and an OPEN HIGH review case.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.review import AuditEvent, HumanReview, ReviewAction, ReviewCaseStatus
from app.db.models.video import Video
from app.services import reanalysis_service as rsvc
from app.tests import test_ownership_t33 as t33
from app.tests.test_ownership_t33 import CALLERS, PG_DSN, T0, env, pg_engine  # noqa: F401 (fixtures)

URL = "/v1/videos/vid-{}/reanalyse"


def _post(env, caller, tag="alice", body=None):
    kw = {"headers": CALLERS[caller]}
    if body is not None:
        kw["json"] = body
    return env["client"].post(URL.format(tag), **kw)


def _events(env, action):
    s = env["Session"]()
    try:
        return s.query(AuditEvent).filter(AuditEvent.action == action).order_by(AuditEvent.created_at).all()
    finally:
        s.close()


def _add_job(Session, jid, *, tag="alice", status=JobStatus.SUCCESS, at, label="NO_MISINFO",
             version="graph_v1", error_code=None, result=True, previous=None):
    s = Session()
    owner = None if tag == "legacy" else tag
    s.add(Job(id=jid, video_id=f"vid-{tag}", status=status, user_id=owner, created_at=at,
              error_code=error_code, previous_job_id=previous))
    s.flush()
    if result:
        s.add(Result(job_id=jid, label=label, confidence=0.9, explanation="x", evidence_snippets=[],
                     combined_content="", provider="langgraph", model_used="graph", latency_ms=1,
                     pipeline="graph", pipeline_version=version, created_at=at + timedelta(minutes=5)))
    s.commit()
    s.close()


# ------------------------------------------------------------------ route table


def test_route_is_classified_in_the_t33_table():
    assert t33.ROUTES.get(("POST", "/v1/videos/{video_id}/reanalyse")) == t33.OWNER_OR_ADMIN


# ------------------------------------------------------------------ who may call it


@pytest.mark.parametrize("caller,tag,expected", [
    ("owner", "alice", 202),
    ("admin", "alice", 202),
    ("reviewer", "alice", 403),  # sees the video, but the reviewer role isn't enough
    ("other", "alice", 404),     # can't see it: looks missing (§15)
    ("owner", "legacy", 404),
    ("reviewer", "legacy", 404),
    ("admin", "legacy", 202),
    ("owner", "missing", 404),
    ("admin", "missing", 404),
])
def test_owner_or_admin_only(env, caller, tag, expected):
    r = _post(env, caller, tag)
    assert r.status_code == expected, r.text
    if expected == 403:
        assert r.json()["detail"]["code"] == "REANALYSIS_FORBIDDEN"
    s = env["Session"]()
    n_jobs = s.query(Job).filter(Job.video_id == f"vid-{tag}").count()
    s.close()
    assert n_jobs == (2 if expected == 202 else (0 if tag == "missing" else 1))


def test_unauthenticated_is_401(env):
    assert env["client"].post(URL.format("alice")).status_code == 401


def test_admin_rerun_belongs_to_the_video_owner(env):
    r = _post(env, "admin", body={"reason": "check the T50 search changes"})
    assert r.status_code == 202
    s = env["Session"]()
    job = s.get(Job, r.json()["job_id"])
    assert job.user_id == "alice" and job.previous_job_id == "job-alice"
    s.close()
    ev = _events(env, rsvc.REANALYSIS_REQUESTED_ACTION)[0]
    assert ev.actor_id == "adam" and ev.details["actor_role"] == "admin"
    # The owner sees the new job in their own list.
    ids = [j["job_id"] for j in env["client"].get("/v1/jobs", headers=CALLERS["owner"]).json()["items"]]
    assert r.json()["job_id"] in ids


# ------------------------------------------------------------------ new job, dispatch


def test_creates_a_new_linked_job_and_dispatches_it(env):
    r = _post(env, "owner", body={"reason": "pipeline v2 shipped"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["previous_job_id"] == "job-alice"
    assert body["status"] == "PENDING" and body["state"] == "QUEUED"
    assert body["celery_task_id"] == "celery-task-t33"  # the same queue as /jobs/create
    assert body["reanalyses_remaining"] == settings.REANALYSIS_MAX_PER_VIDEO - 1
    assert r.headers["X-Reanalyses-Remaining"] == str(body["reanalyses_remaining"])
    s = env["Session"]()
    old = s.get(Job, "job-alice")
    assert old.status == JobStatus.REVIEW_REQUIRED  # the old job is not changed
    s.close()
    events = env["client"].get(f"/v1/jobs/{body['job_id']}/events", headers=CALLERS["owner"]).json()
    assert [e["state"] for e in events["events"]] == ["PENDING", "QUEUED"]
    assert events["events"][0]["detail"] == {"reason": "reanalysis", "previous_job_id": "job-alice"}
    ev = _events(env, rsvc.REANALYSIS_REQUESTED_ACTION)
    assert len(ev) == 1 and ev[0].reason == "pipeline v2 shipped" and ev[0].job_id == body["job_id"]
    assert ev[0].entity_type == "video" and ev[0].entity_id == "vid-alice"


def test_each_rerun_links_to_the_one_before(env):
    first = _post(env, "owner").json()["job_id"]
    second = _post(env, "owner").json()
    assert second["previous_job_id"] == first


def test_reason_is_optional_and_bounded(env):
    assert _post(env, "owner").status_code == 202
    assert _post(env, "owner", body={}).status_code == 202
    assert _post(env, "owner", body={"reason": "x" * 2001}).status_code == 422


def test_dispatch_failure_fails_the_job_and_gives_the_slot_back(env, monkeypatch):
    from app.api.routers import videos as videos_router

    def broken(job_id, key):
        raise ConnectionError("broker down")

    env["app"].dependency_overrides[videos_router.get_reanalysis_dispatcher] = lambda: broken
    monkeypatch.setattr(settings, "REANALYSIS_MAX_PER_VIDEO", 1)
    r = _post(env, "owner")
    assert r.status_code == 202
    assert r.json()["status"] == "FAILED" and r.json()["error_code"] == "DISPATCH_FAILED"
    assert r.json()["state"] == "FAILED" and r.json()["reanalyses_remaining"] == 1
    del env["app"].dependency_overrides[videos_router.get_reanalysis_dispatcher]
    assert _post(env, "owner").status_code == 202  # the failed one didn't count
    assert _post(env, "owner").status_code == 429


# ------------------------------------------------------------------ rate limit


def test_rate_limit_three_per_day_then_429_with_retry_after(env):
    assert settings.REANALYSIS_MAX_PER_VIDEO == 3 and settings.REANALYSIS_WINDOW_HOURS == 24
    remaining = [_post(env, "owner").json()["reanalyses_remaining"] for _ in range(3)]
    assert remaining == [2, 1, 0]
    r = _post(env, "owner")
    assert r.status_code == 429
    retry = int(r.headers["Retry-After"])
    assert 24 * 3600 - 60 <= retry <= 24 * 3600
    d = r.json()["detail"]
    assert d["code"] == "REANALYSIS_RATE_LIMITED" and d["retry_after_seconds"] == retry
    assert d["limit"] == 3 and d["window_hours"] == 24
    s = env["Session"]()
    assert s.query(Job).filter(Job.video_id == "vid-alice").count() == 4  # seed + 3
    s.close()


def test_rate_limit_is_per_user_and_per_video(env):
    for _ in range(3):
        assert _post(env, "owner").status_code == 202
    assert _post(env, "owner").status_code == 429
    assert _post(env, "admin").status_code == 202           # another user, same video
    assert _post(env, "admin", "bob").status_code == 202    # another video


def test_rate_limit_is_configurable(env, monkeypatch):
    monkeypatch.setattr(settings, "REANALYSIS_MAX_PER_VIDEO", 1)
    monkeypatch.setattr(settings, "REANALYSIS_WINDOW_HOURS", 2)
    assert _post(env, "owner").status_code == 202
    r = _post(env, "owner")
    assert r.status_code == 429 and 7140 <= int(r.headers["Retry-After"]) <= 7200


def test_zero_turns_the_route_off(env, monkeypatch):
    monkeypatch.setattr(settings, "REANALYSIS_MAX_PER_VIDEO", 0)
    r = _post(env, "owner")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "REANALYSIS_DISABLED"


def test_retry_after_counts_from_the_request_that_frees_a_slot(env):
    """Rolling window: requests 23 h, 2 h and 1 h ago fill the limit; a slot frees when
    the 23 h one turns 24 h old, in one hour."""
    now = datetime.now(timezone.utc)
    s = env["Session"]()
    for hours in (30, 23, 2, 1):  # the 30 h one is outside the window
        s.add(AuditEvent(actor_id="alice", action=rsvc.REANALYSIS_REQUESTED_ACTION, entity_type="video",
                         entity_id="vid-alice", details={}, created_at=now - timedelta(hours=hours)))
    s.commit()
    assert rsvc.recent_requests(s, "alice", "vid-alice", now)[0] == now - timedelta(hours=23)
    with pytest.raises(rsvc.ReanalysisRateLimited) as exc:
        rsvc.check_rate(s, "alice", "vid-alice", now)
    assert exc.value.retry_after == 3600
    assert rsvc.check_rate(s, "alice", "vid-alice", now + timedelta(hours=1, seconds=1)) == 0
    s.close()


# ------------------------------------------------------------------ open review case


def test_open_case_is_superseded_leaves_the_queue_and_is_audited(env):
    c = env["client"]
    queue = c.get("/v1/reviews", headers=CALLERS["admin"]).json()
    assert "rev-alice" in [i["review_id"] for i in queue["items"]]

    r = _post(env, "owner", body={"reason": "retrieval fixed"})
    new_id = r.json()["job_id"]
    assert r.json()["superseded_review_ids"] == ["rev-alice"]

    s = env["Session"]()
    case = s.get(HumanReview, "rev-alice")
    assert case.status == ReviewCaseStatus.SUPERSEDED and case.superseded_by_job_id == new_id
    assert case.action is None and case.reviewer_id is None  # no decision was made
    assert s.query(HumanReview).filter(HumanReview.job_id == new_id).count() == 0  # starts afresh
    assert s.get(HumanReview, "rev-bob").status == ReviewCaseStatus.OPEN  # other videos untouched
    s.close()

    ev = _events(env, rsvc.REVIEW_SUPERSEDED_ACTION)
    assert len(ev) == 1
    assert (ev[0].actor_id, ev[0].entity_id, ev[0].job_id, ev[0].reason) == (
        "alice", "rev-alice", "job-alice", "retrieval fixed")
    assert ev[0].details["superseded_by_job_id"] == new_id

    for caller in ("admin", "reviewer"):
        ids = [i["review_id"] for i in c.get("/v1/reviews", headers=CALLERS[caller]).json()["items"]]
        assert "rev-alice" not in ids
    sup = c.get("/v1/reviews?status=SUPERSEDED", headers=CALLERS["admin"]).json()["items"]
    assert [i["review_id"] for i in sup] == ["rev-alice"] and sup[0]["status"] == "SUPERSEDED"
    assert "rev-alice" in [i["review_id"] for i in
                           c.get("/v1/reviews?status=ALL", headers=CALLERS["admin"]).json()["items"]]
    # The case's audit trail shows it, and it can no longer be decided.
    view = c.get("/v1/reviews/rev-alice", headers=CALLERS["admin"]).json()
    assert rsvc.REVIEW_SUPERSEDED_ACTION in [e["action"] for e in view["audit_trail"]]
    d = c.post("/v1/reviews/rev-alice/decision", headers=CALLERS["admin"], json=t33.DECISION)
    assert d.status_code == 409


def test_old_result_shows_its_case_as_superseded(env):
    new_id = _post(env, "owner").json()["job_id"]
    r = env["client"].get("/jobs/job-alice/result", headers=CALLERS["owner"]).json()
    assert r["review"]["status"] == "SUPERSEDED" and r["review"]["case_status"] == "SUPERSEDED"
    assert r["review"]["resolved"] is False and r["review"]["superseded_by_job_id"] == new_id
    assert r["is_current"] is True  # the re-run hasn't finished: the old result is still current
    assert r["latest_job"]["job_id"] == new_id and r["latest_job"]["status"] == "PENDING"


def test_no_open_case_nothing_superseded(env):
    s = env["Session"]()
    s.get(HumanReview, "rev-alice").status = ReviewCaseStatus.RESOLVED
    s.get(HumanReview, "rev-alice").action = ReviewAction.APPROVE
    s.commit()
    s.close()
    assert _post(env, "owner").json()["superseded_review_ids"] == []
    assert _events(env, rsvc.REVIEW_SUPERSEDED_ACTION) == []


# ------------------------------------------------------------------ reuse paths unchanged


def test_jobs_create_still_reuses_and_reanalyse_does_not(env):
    c = env["client"]
    r = c.post("/jobs/create", headers=CALLERS["owner"], json={"video_id": "vid-alice"})
    assert r.json()["job_id"] == "job-alice"  # REVIEW_REQUIRED job reused (T11)
    new_id = _post(env, "owner").json()["job_id"]
    assert new_id != "job-alice"
    r = c.post("/jobs/create", headers=CALLERS["owner"], json={"video_id": "vid-alice"})
    assert r.json()["job_id"] == new_id  # the newest reusable job, no third one
    s = env["Session"]()
    assert s.query(Job).filter(Job.video_id == "vid-alice").count() == 2
    assert s.get(Job, new_id).previous_job_id == "job-alice"
    s.close()


@pytest.mark.parametrize("status", [JobStatus.PENDING, JobStatus.STARTED, JobStatus.SUCCESS])
def test_jobs_create_reuse_statuses_unchanged(env, status):
    s = env["Session"]()
    s.get(Job, "job-alice").status = status
    s.commit()
    s.close()
    r = env["client"].post("/jobs/create", headers=CALLERS["owner"], json={"video_id": "vid-alice"})
    assert r.json()["job_id"] == "job-alice"
    s = env["Session"]()
    assert s.get(Job, "job-alice").previous_job_id is None
    s.close()


def test_duplicate_upload_still_reuses_the_video(env):
    from app.services.video_service import register_uploaded_video

    _post(env, "owner")
    s = env["Session"]()
    video, duplicate = register_uploaded_video(s, "uploads/alice/again.mp4", "again.mp4", 1,
                                               "alice".ljust(64, "0")[:64], user_id="alice")
    assert duplicate is True and video.id == "vid-alice"
    s.close()


def test_reviewer_request_reanalysis_links_previous_job(env):
    from app.services import review_service

    s = env["Session"]()
    case = review_service.record_review_decision(s, "rev-bob", reviewer_id="rita",
                                                 action="REQUEST_REANALYSIS", reason="terms fixed")
    job = review_service.start_reanalysis(s, case, reviewer_id="rita", dispatch=lambda j, k: "t")
    assert job.previous_job_id == "job-bob" and job.user_id == "bob"
    s.close()


# ------------------------------------------------------------------ versions


def test_previous_jobs_newest_first_and_current_is_newest_finished(env):
    S = env["Session"]
    s = S()
    s.get(HumanReview, "rev-alice").status = ReviewCaseStatus.RESOLVED
    s.get(Job, "job-alice").status = JobStatus.SUCCESS
    s.query(Result).filter(Result.job_id == "job-alice").one().created_at = T0 + timedelta(minutes=5)
    s.commit()
    s.close()
    _add_job(S, "a2", at=T0 + timedelta(days=1), label="MISINFO", version="graph_v1+aaa", previous="job-alice")
    _add_job(S, "a3", at=T0 + timedelta(days=2), status=JobStatus.FAILED, error_code="REVIEW_REJECTED",
             label="DEBUNKING", version="graph_v1+bbb", previous="a2")
    _add_job(S, "a4", at=T0 + timedelta(days=3), version="graph_v1+ccc", previous="a3")
    _add_job(S, "a5", at=T0 + timedelta(days=4), status=JobStatus.FAILED, error_code="PIPELINE_ERROR",
             result=False, previous="a4")  # failed re-run: no result
    _add_job(S, "a6", at=T0 + timedelta(days=5), status=JobStatus.STARTED, result=False, previous="a5")
    _add_job(S, "b2", tag="bob", at=T0 + timedelta(days=6))  # another video

    c = env["client"]
    for caller in ("owner", "admin", "reviewer"):
        r = c.get("/v1/videos/vid-alice/results", headers=CALLERS[caller])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["job_id"] == "a4" and body["is_current"] is True and body["current_job_id"] == "a4"
        assert body["previous_job_id"] == "a3"
        assert [p["job_id"] for p in body["previous_jobs"]] == ["a3", "a2", "job-alice"]
        assert body["latest_job"]["job_id"] == "a6" and body["latest_job"]["status"] == "STARTED"
    p = body["previous_jobs"]
    assert (p[0]["label"], p[0]["pipeline_version"], p[0]["status"]) == ("DEBUNKING", "graph_v1+bbb", "FAILED")
    assert p[1]["label_display"] and p[1]["finished_at"].startswith("2026-11-21T12:05")
    finished = [x["finished_at"] for x in p]
    assert finished == sorted(finished, reverse=True)
    # The claims route follows the same current job.
    assert c.get("/v1/videos/vid-alice/claims", headers=CALLERS["owner"]).json()["job_id"] == "a4"

    # An older version, by job id: only what came before it, and it isn't current.
    old = c.get("/jobs/a2/result", headers=CALLERS["owner"]).json()
    assert old["is_current"] is False and old["current_job_id"] == "a4"
    assert [x["job_id"] for x in old["previous_jobs"]] == ["job-alice"]
    assert old["latest_job"]["job_id"] == "a6"

    # Once the running job finishes it becomes current.
    _add_job(S, "a7", at=T0 + timedelta(days=7), version="graph_v1+ddd", previous="a6")
    body = c.get("/v1/videos/vid-alice/results", headers=CALLERS["owner"]).json()
    assert body["job_id"] == "a7" and body["latest_job"] is None
    assert [x["job_id"] for x in body["previous_jobs"]] == ["a4", "a3", "a2", "job-alice"]


def test_only_a_running_job_still_answers_202(env):
    s = env["Session"]()
    s.add(Video(id="vid-new", filename="n.mp4", file_path="/x/n.mp4", file_size=1, file_hash="n" * 64,
                storage_key="uploads/alice/n.mp4", user_id="alice"))
    s.flush()
    s.add(Job(id="job-new", video_id="vid-new", status=JobStatus.STARTED, user_id="alice"))
    s.commit()
    s.close()
    assert env["client"].get("/v1/videos/vid-new/results", headers=CALLERS["owner"]).status_code == 202


def test_first_run_has_no_versions(env):
    body = env["client"].get("/v1/videos/vid-alice/results", headers=CALLERS["owner"]).json()
    assert body["previous_jobs"] == [] and body["previous_job_id"] is None
    assert body["is_current"] is True and body["current_job_id"] == "job-alice" and body["latest_job"] is None


# ------------------------------------------------------------------ migration


def test_alembic_has_one_head(monkeypatch, tmp_path):
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(t33._alembic(f"sqlite:///{tmp_path / 'x.db'}", monkeypatch))
    assert script.get_heads() == ["0017"]


def _check_migration(url, monkeypatch, *, postgres=False):
    from alembic import command

    cfg = t33._alembic(url, monkeypatch)
    command.upgrade(cfg, "0016")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO videos (id, filename, file_path, file_size, file_hash, created_at) "
                          "VALUES ('v', 'f', 'p', 1, :h, CURRENT_TIMESTAMP)"), {"h": "a" * 64})
        for jid in ("j1", "j2"):
            conn.execute(text("INSERT INTO jobs (id, video_id, status, user_id, attempts, created_at, updated_at) "
                              "VALUES (:j, 'v', 'REVIEW_REQUIRED', 'alice', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                         {"j": jid})
        conn.execute(text("INSERT INTO human_reviews (id, job_id, status, reasons, rules_fired, validation_errors, "
                          "policy_version, created_at) VALUES ('r1', 'j1', 'OPEN', '[]', '[]', '[]', 'p', "
                          "CURRENT_TIMESTAMP)"))
    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert "previous_job_id" in {c["name"] for c in insp.get_columns("jobs")}
    assert any(ix["name"] == "ix_jobs_previous_job_id" for ix in insp.get_indexes("jobs"))
    assert any(fk["referred_table"] == "jobs" and fk["constrained_columns"] == ["previous_job_id"]
               for fk in insp.get_foreign_keys("jobs"))
    assert "superseded_by_job_id" in {c["name"] for c in insp.get_columns("human_reviews")}
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET previous_job_id = 'j1' WHERE id = 'j2'"))
        conn.execute(text("UPDATE human_reviews SET status = 'SUPERSEDED', superseded_by_job_id = 'j2'"))
    if postgres:
        with pytest.raises(Exception):  # the FK holds
            with engine.begin() as conn:
                conn.execute(text("UPDATE jobs SET previous_job_id = 'nope' WHERE id = 'j2'"))
    engine.dispose()

    command.downgrade(cfg, "0016")
    engine = create_engine(url)
    insp = inspect(engine)
    assert "previous_job_id" not in {c["name"] for c in insp.get_columns("jobs")}
    assert "superseded_by_job_id" not in {c["name"] for c in insp.get_columns("human_reviews")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM human_reviews")).scalar() == "RESOLVED"
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar() == 2
        if postgres:
            values = conn.execute(text("SELECT unnest(enum_range(NULL::reviewcasestatus))::text")).scalars().all()
            assert values == ["OPEN", "RESOLVED"]
    engine.dispose()
    command.upgrade(cfg, "head")


def test_migration_0017_sqlite(monkeypatch, tmp_path):
    _check_migration(f"sqlite:///{tmp_path / 'm.db'}", monkeypatch)


def test_migration_0017_postgres(monkeypatch):
    if not PG_DSN:
        pytest.skip("set LIBRARY_TEST_PG_DSN to a throwaway Postgres database with pgvector")
    from sqlalchemy.engine import make_url

    name = f"t55m_{uuid.uuid4().hex[:12]}"
    admin = create_engine(PG_DSN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    try:
        url = make_url(PG_DSN).set(database=name).render_as_string(hide_password=False)
        _check_migration(url, monkeypatch, postgres=True)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        admin.dispose()
