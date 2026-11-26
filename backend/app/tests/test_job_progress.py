"""T28: job progress events for the stepper, §1 states, ownership, and the jobs list's
total / search / status filter (design §1, §16, §17). Everything is mocked: no model,
queue or storage call leaves the process."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401 - registers every table
from app.api.routers import jobs as jobs_router
from app.core import progress
from app.core.config import settings
from app.db.base import Base
from app.db.models.job import Job, JobEvent, JobState, JobStatus
from app.db.models.result import Result
from app.db.models.video import Video
from app.db.session import get_db
from app.services import job_events

BACKEND = Path(__file__).resolve().parents[2]
SECRET = "test-secret-for-t28-only-0123456789abcdef"


# ------------------------------------------------------------------ helpers


def _session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _video(db, vid="vid-1", filename="clip.mp4", owner="user-a"):
    db.add(Video(id=vid, filename=filename, file_path=f"/tmp/{vid}.mp4", file_size=1, user_id=owner))
    db.commit()


def _job(db, jid, *, user="user-a", status=JobStatus.PENDING, state=None, vid="vid-1",
         created=None, label=None):
    job = Job(id=jid, video_id=vid, status=status, user_id=user, state=state,
              created_at=created or datetime.now(timezone.utc))
    db.add(job)
    db.commit()
    if label:
        db.add(Result(job_id=jid, label=label, confidence=0.5, explanation="x", evidence_snippets=[],
                      combined_content="", provider="p", model_used="m", latency_ms=1))
        db.commit()
    return job


def _token(sub: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": sub, "aud": "authenticated", "iat": now, "exp": now + 600}, SECRET, algorithm="HS256")


def _auth(sub: str) -> dict:
    return {"Authorization": f"Bearer {_token(sub)}"}


@pytest.fixture
def api(monkeypatch):
    """The jobs routers on their own app, with real JWT checking (REQUIRE_AUTH on)."""
    Session = _session_factory()
    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    app = FastAPI()
    app.include_router(jobs_router.router)
    app.include_router(jobs_router.v1_router)

    def db_dep():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = db_dep
    return TestClient(app), Session


class FakeTask:
    id = "celery-task-1"


# ------------------------------------------------------------------ progress module


def test_step_vocabulary_matches_the_stepper():
    assert progress.STEPS == ("uploaded", "transcribing", "reading_on_screen_text", "finding_claims",
                              "checking_stance", "searching_evidence", "verifying", "final_checks")
    from app.core.graph.nodes import make_stub_nodes

    nodes = set(make_stub_nodes())
    # Every graph node either moves the stepper or is a known no-op, and nothing else is mapped.
    assert nodes == set(progress.NODE_STEPS) | {"load_artifacts", "fuse_modalities"}
    assert set(progress.NODE_STEPS.values()) <= set(progress.STEPS)


def test_report_step_is_a_noop_without_reporter_and_never_raises():
    progress.report_step(progress.TRANSCRIBING)  # nothing installed: no error

    def boom(step):
        raise RuntimeError("db down")

    with progress.reporting(boom):
        progress.report_step(progress.VERIFYING)  # swallowed
    seen = []
    with progress.reporting(seen.append):
        progress.report_node("extract_claims")
        progress.report_node("load_artifacts")  # no step
    assert seen == ["finding_claims"]
    assert progress.current_reporter() is None


# ------------------------------------------------------------------ state recording


def test_record_state_and_step_write_ordered_events_and_dedupe():
    db = _session_factory()()
    _video(db)
    job = _job(db, "j1")
    job_events.record_state(db, job, JobState.PENDING, step=progress.UPLOADED)
    job_events.record_state(db, job, JobState.QUEUED)
    job_events.record_state(db, job, JobState.QUEUED)            # repeat: dropped
    job.status = JobStatus.STARTED
    db.commit()
    job_events.record_state(db, job, JobState.RUNNING)
    job_events.record_step(db, job, progress.TRANSCRIBING)
    job_events.record_step(db, job, progress.TRANSCRIBING)       # repeat: dropped
    job_events.record_step(db, job, progress.VERIFYING)
    events = job_events.list_events(db, "j1")
    assert [(e.seq, e.kind, e.state, e.step) for e in events] == [
        (1, "state", "PENDING", "uploaded"),
        (2, "state", "QUEUED", "uploaded"),
        (3, "state", "RUNNING", "uploaded"),
        (4, "step", "RUNNING", "transcribing"),
        (5, "step", "RUNNING", "verifying"),
    ]
    assert events[2].status == "STARTED"
    assert job.state == "RUNNING" and job.current_step == "verifying"
    with pytest.raises(ValueError):
        job_events.record_state(db, job, "SOMETHING")
    with pytest.raises(ValueError):
        job_events.record_step(db, job, "dancing")


def test_recording_failure_never_breaks_the_caller():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Video.__table__.create(engine)
    Job.__table__.create(engine)  # no job_events table (migration not run)
    db = sessionmaker(bind=engine)()
    _video(db)
    job = _job(db, "j1")
    assert job_events.record_state(db, job, JobState.QUEUED) is None
    assert db.get(Job, "j1").status == JobStatus.PENDING  # session still usable


@pytest.mark.parametrize("status,state,expected,error_code", [
    (JobStatus.PENDING, None, "PENDING", None),
    (JobStatus.PENDING, "QUEUED", "QUEUED", None),
    (JobStatus.PENDING, "RETRY_PENDING", "RETRY_PENDING", None),
    (JobStatus.STARTED, None, "RUNNING", None),
    (JobStatus.STARTED, "QUEUED", "RUNNING", None),          # status moved on without an event
    (JobStatus.SUCCESS, "RUNNING", "COMPLETED", None),
    (JobStatus.SUCCESS, None, "COMPLETED", None),
    (JobStatus.FAILED, "RUNNING", "FAILED", None),
    (JobStatus.REVIEW_REQUIRED, "RUNNING", "REVIEW_REQUIRED", None),
    (JobStatus.REVIEW_REQUIRED, "REJECTED", "REVIEW_REQUIRED", None),
    (JobStatus.FAILED, "REVIEW_REQUIRED", "REJECTED", "REVIEW_REJECTED"),   # reviewer rejected
    (JobStatus.FAILED, "REJECTED", "REJECTED", None),
    (JobStatus.FAILED, None, "FAILED", "TRANSCRIPTION_ERROR"),
])
def test_effective_state_python_and_sql_agree(status, state, expected, error_code):
    db = _session_factory()()
    _video(db)
    job = _job(db, "j1", status=status, state=state)
    job.error_code = error_code
    db.commit()
    assert job_events.effective_state(job) == expected
    sql = db.query(job_events.effective_state_sql()).filter(Job.id == "j1").scalar()
    assert sql == expected


def test_split_status_filter():
    legacy, states = job_events.split_status_filter(["started,queued", "SUCCESS", " "])
    assert legacy == {"STARTED", "SUCCESS"} and states == {"QUEUED"}
    with pytest.raises(ValueError):
        job_events.split_status_filter(["nope"])


# ------------------------------------------------------------------ job creation


def test_create_job_sets_owner_and_logs_pending_then_queued(monkeypatch):
    from app.api.routers.jobs import CreateJobRequest, create_job

    db = _session_factory()()
    _video(db)
    monkeypatch.setattr(jobs_router.process_video_task, "delay", lambda *a, **k: FakeTask())
    out = create_job(payload=CreateJobRequest(video_id="vid-1"), db=db, current_user={"sub": "user-a"})
    assert out["status"] == JobStatus.PENDING          # legacy response unchanged
    job = db.get(Job, out["job_id"])
    assert job.user_id == "user-a" and job.celery_task_id == "celery-task-1"
    events = job_events.list_events(db, job.id)
    assert [(e.state, e.step) for e in events] == [("PENDING", "uploaded"), ("QUEUED", "uploaded")]
    assert job_events.effective_state(job) == "QUEUED"


def test_create_job_dispatch_failure_is_logged(monkeypatch):
    from app.api.routers.jobs import CreateJobRequest, create_job

    db = _session_factory()()
    _video(db)

    def down(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(jobs_router.process_video_task, "delay", down)
    with pytest.raises(ConnectionError):
        create_job(payload=CreateJobRequest(video_id="vid-1"), db=db, current_user={"sub": "user-a"})
    job = db.query(Job).one()
    last = job_events.list_events(db, job.id)[-1]
    assert last.state == "PENDING" and last.detail["reason"] == "dispatch_failed"
    assert job_events.effective_state(job) == "PENDING"


# ------------------------------------------------------------------ worker


@pytest.fixture
def worker_db(monkeypatch):
    import app.db.session as sess

    Session = _session_factory()
    db = Session()
    monkeypatch.setattr(sess, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    _video(db)
    return db


def _single_call_stubs(monkeypatch, label="MISINFO"):
    """Single-call path with fake transcription, provider and grounding."""
    import app.core.pipeline as pl
    from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel

    class Fusion:
        def fuse(self, path, keep_segments=False):
            return FusionResult(transcript="t", visual_text="", combined_content="[AUDIO TRANSCRIPT]\nt", metadata={})

    class Provider:
        def classify(self, fusion):
            return ClassificationResult(label=MisinfoLabel(label), confidence=0.8, explanation="e",
                                        evidence_snippets=["s"], provider="fake", model_used="m", latency_ms=3)

    async def ground(transcript):
        return []

    import app.core.grounding.pubmed as pubmed
    monkeypatch.setattr(pl, "MultimodalFusion", Fusion)
    monkeypatch.setattr(pl, "get_provider", lambda: Provider())
    monkeypatch.setattr(pubmed, "ground_transcript", ground)


def _history(db, jid):
    return [(e.kind, e.state, e.step) for e in job_events.list_events(db, jid)]


def test_single_call_job_logs_states_and_steps(worker_db, monkeypatch):
    import app.worker.tasks as tasks

    _single_call_stubs(monkeypatch)
    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", False)
    job = _job(worker_db, "j1")
    job_events.record_state(worker_db, job, JobState.PENDING, step=progress.UPLOADED)
    job_events.record_state(worker_db, job, JobState.QUEUED)

    out = tasks.process_video_task.run("j1")
    assert out["status"] == "SUCCESS"
    job = worker_db.get(Job, "j1")
    assert job.status == JobStatus.SUCCESS and job.attempts == 1
    assert _history(worker_db, "j1") == [
        ("state", "PENDING", "uploaded"),
        ("state", "QUEUED", "uploaded"),
        ("state", "RUNNING", "uploaded"),
        ("step", "RUNNING", "transcribing"),
        ("step", "RUNNING", "verifying"),
        ("step", "RUNNING", "searching_evidence"),   # MISINFO: post-hoc PubMed grounding
        ("state", "COMPLETED", "searching_evidence"),
    ]


def test_single_call_result_is_unchanged_by_recording(worker_db, monkeypatch):
    """Recording steps must not alter the pipeline's output (T28 rule)."""
    import app.core.pipeline as pl

    _single_call_stubs(monkeypatch, label="NO_MISINFO")
    plain = asyncio.run(pl.run_pipeline("v.mp4"))
    seen = []
    with progress.reporting(seen.append):
        reported = asyncio.run(pl.run_pipeline("v.mp4"))
    assert plain[0] == reported[0]
    assert plain[1].model_dump() == reported[1].model_dump()
    assert seen == ["transcribing", "verifying"]   # no grounding for NO_MISINFO


def test_failed_job_logs_failed_with_error_code(worker_db, monkeypatch):
    import app.core.pipeline as pl
    import app.worker.tasks as tasks
    from app.core.exceptions import TranscriptionError

    async def failing(path):
        progress.report_step(progress.TRANSCRIBING)
        raise TranscriptionError(provider="openai")

    monkeypatch.setattr(pl, "run_pipeline", failing)
    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", False)
    _job(worker_db, "j1")
    with pytest.raises(TranscriptionError):
        tasks.process_video_task.run("j1")
    job = worker_db.get(Job, "j1")
    assert job.status == JobStatus.FAILED and job.error_code == "TRANSCRIPTION_ERROR"
    last = job_events.list_events(worker_db, "j1")[-1]
    assert (last.state, last.step, last.detail) == ("FAILED", "transcribing", {"error_code": "TRANSCRIPTION_ERROR"})


def test_redelivered_job_logs_retry_pending_then_running(worker_db, monkeypatch):
    """A job found STARTED was picked up before and its worker died (§1): the history
    shows RETRY_PENDING, then RUNNING on the next attempt."""
    import app.worker.tasks as tasks

    _single_call_stubs(monkeypatch, label="NO_MISINFO")
    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", False)
    job = _job(worker_db, "j1", status=JobStatus.STARTED, state="RUNNING")
    job.attempts = 1
    worker_db.commit()
    tasks.process_video_task.run("j1")
    job = worker_db.get(Job, "j1")
    assert job.attempts == 2
    states = [e for e in job_events.list_events(worker_db, "j1") if e.kind == "state"]
    assert [e.state for e in states] == ["RETRY_PENDING", "RUNNING", "COMPLETED"]
    assert states[0].detail == {"reason": "redelivered", "previous_status": "STARTED"}
    assert states[1].attempt == 2


def test_graph_job_logs_every_stepper_step_and_result_is_unchanged(worker_db, monkeypatch):
    import app.core.inference.providers.graph_provider as gpm
    import app.core.pipeline as pl
    import app.worker.tasks as tasks
    from app.tests.test_graph_integration import fusion, make_provider

    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", True)

    class Fusion:
        def fuse(self, path, keep_segments=False):
            return fusion()

    monkeypatch.setattr(pl, "MultimodalFusion", Fusion)
    monkeypatch.setattr(gpm, "build_graph_provider", lambda checkpointer=None: make_provider(checkpointer=checkpointer))
    _job(worker_db, "j1")
    out = tasks.process_video_task.run("j1")
    assert out["pipeline"] == "graph"

    steps = [s for k, _, s in _history(worker_db, "j1") if k == "step"]
    # Every stepper step after "uploaded" shows up, in pipeline order (the critic's loop
    # may revisit searching/verifying, so only first occurrences are compared).
    first = list(dict.fromkeys(steps))
    assert first == list(progress.STEPS[1:])
    final = job_events.list_events(worker_db, "j1")[-1]
    assert final.kind == "state" and final.state == job_events.effective_state(worker_db.get(Job, "j1"))
    assert final.state in ("COMPLETED", "REVIEW_REQUIRED")

    # Same run without a reporter gives the same classification.
    plain = make_provider().run(fusion(), job_id="plain-run")
    seen = []
    with progress.reporting(seen.append):
        reported = make_provider().run(fusion(), job_id="reported-run")
    a, b = plain.classification.model_dump(), reported.classification.model_dump()
    a.pop("latency_ms"); b.pop("latency_ms")
    assert a == b and plain.pipeline == reported.pipeline == "graph"
    assert seen and set(seen) <= set(progress.STEPS)


# ------------------------------------------------------------------ API: events + ownership


def _seed_events(Session):
    db = Session()
    _video(db)
    job = _job(db, "j-a", user="user-a")
    job_events.record_state(db, job, JobState.PENDING, step=progress.UPLOADED)
    job_events.record_state(db, job, JobState.QUEUED)
    job.status = JobStatus.STARTED
    db.commit()
    job_events.record_state(db, job, JobState.RUNNING)
    job_events.record_step(db, job, progress.TRANSCRIBING)
    _job(db, "j-b", user="user-b")
    db.close()


def test_events_endpoint_returns_history_to_the_owner(api):
    client, Session = api
    _seed_events(Session)
    r = client.get("/v1/jobs/j-a/events", headers=_auth("user-a"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "STARTED" and body["state"] == "RUNNING" and body["step"] == "transcribing"
    assert body["processing_finished"] is False
    assert [s["key"] for s in body["steps"]] == list(progress.STEPS)
    assert body["steps"][2]["label"] == "Reading on-screen text"
    assert body["pipeline_steps"] == list(progress.PIPELINE_STEPS["single_call"])
    assert [(e["seq"], e["kind"], e["state"], e["step"]) for e in body["events"]] == [
        (1, "state", "PENDING", "uploaded"), (2, "state", "QUEUED", "uploaded"),
        (3, "state", "RUNNING", "uploaded"), (4, "step", "RUNNING", "transcribing"),
    ]
    assert body["events"][3]["step_label"] == "Transcribing"


def test_events_and_job_are_hidden_from_other_users(api):
    client, Session = api
    _seed_events(Session)
    for path in ("/v1/jobs/j-a/events", "/v1/jobs/j-a", "/jobs/j-a", "/jobs/j-a/result"):
        assert client.get(path, headers=_auth("user-b")).status_code == 404, path
        assert client.get(path).status_code == 401, path
    assert client.get("/v1/jobs/missing/events", headers=_auth("user-a")).status_code == 404


def test_legacy_job_endpoint_keeps_its_fields_and_adds_state(api):
    client, Session = api
    _seed_events(Session)
    body = client.get("/jobs/j-a", headers=_auth("user-a")).json()
    for key in ("job_id", "video_id", "status", "error_code", "celery_task_id", "created_at", "updated_at"):
        assert key in body
    assert body["status"] == "STARTED"            # one of the 5 legacy values
    assert body["state"] == "RUNNING" and body["step"] == "transcribing" and body["step_label"] == "Transcribing"
    assert client.get("/v1/jobs/j-a", headers=_auth("user-a")).json() == body


def test_unowned_legacy_jobs_hidden_with_auth_visible_in_local_dev(api, monkeypatch):
    client, Session = api
    db = Session()
    _video(db)
    _job(db, "old", user=None, status=JobStatus.SUCCESS)
    db.close()
    assert client.get("/jobs/old", headers=_auth("user-a")).status_code == 404
    assert client.get("/v1/jobs", headers=_auth("user-a")).json()["total"] == 0

    monkeypatch.setattr(settings, "REQUIRE_AUTH", False)   # dev user, no token
    body = client.get("/jobs/old").json()
    assert body["status"] == "SUCCESS" and body["state"] == "COMPLETED"
    events = client.get("/v1/jobs/old/events").json()
    assert events["events"] == [] and events["processing_finished"] is True
    assert client.get("/v1/jobs").json()["total"] == 1


# ------------------------------------------------------------------ API: jobs list


def _seed_list(Session):
    db = Session()
    _video(db, "v1", "Garlic cures COVID.mp4")
    _video(db, "v2", "vaccine_talk.mov")
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)
    _job(db, "a1", vid="v1", status=JobStatus.SUCCESS, created=base, label="MISINFO")
    _job(db, "a2", vid="v2", status=JobStatus.PENDING, state="QUEUED", created=base + timedelta(hours=1))
    _job(db, "a3", vid="v2", status=JobStatus.STARTED, state="RUNNING", created=base + timedelta(hours=2))
    _job(db, "a4", vid="v1", status=JobStatus.PENDING, state="RETRY_PENDING", created=base + timedelta(hours=3))
    _job(db, "a5", vid="v2", status=JobStatus.REVIEW_REQUIRED, created=base + timedelta(hours=4))
    _job(db, "b1", vid="v1", user="user-b", status=JobStatus.SUCCESS, created=base + timedelta(hours=5))
    db.close()


def _ids(body):
    return [row["job_id"] for row in (body["items"] if isinstance(body, dict) else body)]


def test_v1_jobs_list_has_total_and_pagination(api):
    client, Session = api
    _seed_list(Session)
    body = client.get("/v1/jobs?limit=2&offset=1", headers=_auth("user-a")).json()
    assert body["total"] == 5 and body["limit"] == 2 and body["offset"] == 1
    assert _ids(body) == ["a4", "a3"]                 # newest first, only user-a's
    first = client.get("/v1/jobs", headers=_auth("user-a")).json()["items"][0]
    assert first["status"] == "REVIEW_REQUIRED" and first["state"] == "REVIEW_REQUIRED"


def test_jobs_list_search(api):
    client, Session = api
    _seed_list(Session)
    h = _auth("user-a")
    assert _ids(client.get("/v1/jobs?q=garlic", headers=h).json()) == ["a4", "a1"]
    assert _ids(client.get("/v1/jobs?q=a3", headers=h).json()) == ["a3"]
    assert _ids(client.get("/v1/jobs?q=v2", headers=h).json()) == ["a5", "a3", "a2"]   # by video id
    assert client.get("/v1/jobs?q=%25", headers=h).json()["total"] == 0                # % is literal
    assert client.get("/v1/jobs?q=b1", headers=h).json()["total"] == 0                 # not mine


@pytest.mark.parametrize("query,expected", [
    ("status=QUEUED", ["a2"]),
    ("status=RETRY_PENDING", ["a4"]),
    ("status=RUNNING", ["a3"]),
    ("status=COMPLETED", ["a1"]),
    ("status=PENDING", []),                         # §1 PENDING: created but not queued
    ("status=queued,running", ["a3", "a2"]),
    ("status=STARTED&status=SUCCESS", ["a3", "a1"]),  # legacy values still work
    ("status=REVIEW_REQUIRED", ["a5"]),
    ("status=COMPLETED&label=MISINFO", ["a1"]),
])
def test_jobs_list_status_filter(api, query, expected):
    client, Session = api
    _seed_list(Session)
    body = client.get(f"/v1/jobs?{query}", headers=_auth("user-a")).json()
    assert _ids(body) == expected and body["total"] == len(expected)


def test_jobs_list_unknown_status_is_422(api):
    client, Session = api
    _seed_list(Session)
    r = client.get("/v1/jobs?status=DANCING", headers=_auth("user-a"))
    assert r.status_code == 422


def test_legacy_jobs_list_is_still_a_list_with_total_header(api):
    client, Session = api
    _seed_list(Session)
    r = client.get("/jobs?limit=2", headers=_auth("user-a"))
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert r.headers["X-Total-Count"] == "5"
    row = r.json()[0]
    for key in ("job_id", "status", "error_code", "created_at", "filename", "label", "confidence"):
        assert key in row
    assert row["status"] in {"PENDING", "STARTED", "SUCCESS", "FAILED", "REVIEW_REQUIRED"}
    r = client.get("/jobs?q=garlic&status=RETRY_PENDING", headers=_auth("user-a"))
    assert _ids(r.json()) == ["a4"] and r.headers["X-Total-Count"] == "1"
    assert client.get("/jobs", headers=_auth("user-b")).headers["X-Total-Count"] == "1"


# ------------------------------------------------------------------ migration


def test_migration_0011_upgrades_and_downgrades(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    command.upgrade(cfg, "0011")
    insp = inspect(create_engine(url))
    assert {c.name for c in JobEvent.__table__.columns} <= {c["name"] for c in insp.get_columns("job_events")}
    later = {"previous_job_id"}  # added by 0017 (T55)
    assert {c.name for c in Job.__table__.columns} - later <= {c["name"] for c in insp.get_columns("jobs")}
    command.downgrade(cfg, "0010")
    insp = inspect(create_engine(url))
    assert "job_events" not in insp.get_table_names()
    assert "user_id" not in {c["name"] for c in insp.get_columns("jobs")}


# ------------------------------------------------------------------ review decisions


@pytest.mark.parametrize("action,state", [("APPROVE", "COMPLETED"), ("REJECT", "REJECTED")])
def test_review_decision_is_logged_as_a_state_change(action, state):
    from app.services.review_service import open_review_case, record_review_decision
    from app.tests.test_validation_review import Harness

    db = _session_factory()()
    _video(db)
    job = _job(db, "j1", status=JobStatus.STARTED, state="RUNNING")
    run = Harness().run()
    case = open_review_case(db, "j1", run)
    job_events.sync_state_from_status(db, job)            # what the worker does after persisting
    record_review_decision(db, case.id, reviewer_id="rev-1", action=action, reason="checked the sources")
    job = db.get(Job, "j1")
    assert job.status in (JobStatus.SUCCESS, JobStatus.FAILED)  # legacy values unchanged
    assert job_events.effective_state(job) == state
    last = job_events.list_events(db, "j1")[-1]
    assert (last.state, last.detail) == (state, {"review_id": case.id, "action": action})
    assert [e.state for e in job_events.list_events(db, "j1")] == ["REVIEW_REQUIRED", state]


@pytest.mark.parametrize("dispatch_ok", [True, False])
def test_reanalysis_job_keeps_the_original_owner_and_has_a_history(dispatch_ok):
    from app.services.review_service import open_review_case, record_review_decision, start_reanalysis
    from app.tests.test_validation_review import Harness

    db = _session_factory()()
    _video(db)
    _job(db, "j1", user="user-a", status=JobStatus.STARTED)
    case = open_review_case(db, "j1", Harness().run())
    case = record_review_decision(db, case.id, reviewer_id="rev-1", action="REQUEST_REANALYSIS",
                                  reason="transcript looks truncated")

    def dispatch(job_id, key):
        if not dispatch_ok:
            raise ConnectionError("redis down")
        return "task-2"

    new = start_reanalysis(db, case, reviewer_id="rev-1", dispatch=dispatch)
    assert new.user_id == "user-a"                       # the owner, not the reviewer
    states = [e.state for e in job_events.list_events(db, new.id)]
    first = job_events.list_events(db, new.id)[0]
    assert first.detail["previous_job_id"] == "j1" and first.step == "uploaded"
    if dispatch_ok:
        assert states == ["PENDING", "QUEUED"] and job_events.effective_state(new) == "QUEUED"
    else:
        assert states == ["PENDING", "QUEUED", "FAILED"]
        assert job_events.list_events(db, new.id)[-1].detail == {"error_code": "DISPATCH_FAILED"}
