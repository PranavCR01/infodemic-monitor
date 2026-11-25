import hashlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routers.jobs import CreateJobRequest, create_job
from app.core.config import settings
from app.db.models.job import Job, JobEvent, JobStatus
from app.db.models.video import Video
from app.services.video_service import save_video


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Video.__table__.create(bind=engine)
    Job.__table__.create(bind=engine)
    JobEvent.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    return Session()


def test_duplicate_video_reuses_existing_video(tmp_path, monkeypatch):
    db = make_db()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    content = b"same video bytes"

    first_video = save_video(db, content, "first.mp4")
    second_video = save_video(db, content, "second.mp4")

    assert first_video.id == second_video.id
    assert db.query(Video).count() == 1

    db.close()


def test_new_file_creates_new_video(tmp_path, monkeypatch):
    db = make_db()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    first_video = save_video(db, b"first video bytes", "first.mp4")
    second_video = save_video(db, b"different video bytes", "second.mp4")

    assert first_video.id != second_video.id
    assert db.query(Video).count() == 2

    db.close()


def test_file_hash_is_computed_correctly(tmp_path, monkeypatch):
    db = make_db()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    content = b"video bytes to hash"
    expected_hash = hashlib.sha256(content).hexdigest()

    video = save_video(db, content, "video.mp4")
    assert video.file_hash == expected_hash

    db.close()


def test_existing_job_is_reused():
    db = make_db()

    video = Video(
        filename="video.mp4",
        file_path="/tmp/video.mp4",
        file_size=100,
        file_hash="a" * 64,
        user_id="user-a",
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    # T28: jobs have owners; only the caller's own finished job is reused.
    existing_job = Job(video_id=video.id, status=JobStatus.SUCCESS, user_id="user-a")
    db.add(existing_job)
    db.commit()
    db.refresh(existing_job)

    result = create_job(
        payload=CreateJobRequest(video_id=video.id),
        db=db,
        current_user={"sub": "user-a"},
    )

    assert result["job_id"] == existing_job.id
    assert db.query(Job).count() == 1

    db.close()


def test_another_users_job_is_not_reused(monkeypatch):
    """T28 (§17 ownership): the same video started by someone else gets its own job,
    so one user never receives another user's job id. Since T33 only a reviewer/admin
    (or the owner) can start a job on a video; an analyst gets 404 (tests in
    test_ownership_t33.py)."""
    db = make_db()
    video = Video(filename="video.mp4", file_path="/tmp/video.mp4", file_size=100, file_hash="c" * 64,
                  user_id="user-a")
    db.add(video)
    db.commit()
    theirs = Job(video_id=video.id, status=JobStatus.SUCCESS, user_id="user-a")
    db.add(theirs)
    db.commit()

    class FakeTask:
        id = "fake-celery-task-id"

    monkeypatch.setattr("app.api.routers.jobs.process_video_task.delay", lambda *a, **k: FakeTask())
    result = create_job(payload=CreateJobRequest(video_id=video.id), db=db,
                        current_user={"sub": "user-b", "app_metadata": {"role": "reviewer"}})

    assert result["job_id"] != theirs.id
    mine = db.get(Job, result["job_id"])
    assert mine.user_id == "user-b"

    db.close()


def test_failed_job_can_be_retried(monkeypatch):
    db = make_db()

    video = Video(
        filename="video.mp4",
        file_path="/tmp/video.mp4",
        file_size=100,
        file_hash="b" * 64,
        user_id="user-c",
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    failed_job = Job(video_id=video.id, status=JobStatus.FAILED, user_id="user-c")
    db.add(failed_job)
    db.commit()

    class FakeTask:
        id = "fake-celery-task-id"

    monkeypatch.setattr(
        "app.api.routers.jobs.process_video_task.delay",
        lambda *args, **kwargs: FakeTask(),
    )

    result = create_job(
        payload=CreateJobRequest(video_id=video.id),
        db=db,
        current_user={"sub": "user-c"},
    )

    assert result["job_id"] != failed_job.id
    assert db.query(Job).count() == 2

    db.close()
