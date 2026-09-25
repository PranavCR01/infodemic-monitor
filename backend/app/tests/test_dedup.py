from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models.video import Video
from app.services.video_service import save_video


def test_duplicate_video_reuses_existing_video(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Video.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    content = b"same video bytes"

    first_video = save_video(db, content, "first.mp4")
    second_video = save_video(db, content, "second.mp4")

    assert first_video.id == second_video.id
    assert first_video.file_hash == second_video.file_hash
    assert db.query(Video).count() == 1

    db.close()

from app.api.routers.jobs import CreateJobRequest, create_job
from app.db.models.job import Job, JobStatus


def test_existing_job_is_reused(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Video.__table__.create(bind=engine)
    Job.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    video = Video(
        filename="video.mp4",
        file_path="/tmp/video.mp4",
        file_size=100,
        file_hash="a" * 64,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    existing_job = Job(
        video_id=video.id,
        status=JobStatus.SUCCESS,
    )
    db.add(existing_job)
    db.commit()
    db.refresh(existing_job)

    payload = CreateJobRequest(video_id=video.id)

    result = create_job(
        payload=payload,
        db=db,
        current_user={},
    )

    assert result["job_id"] == existing_job.id
    assert db.query(Job).count() == 1

    db.close()


def test_failed_job_can_be_retried(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Video.__table__.create(bind=engine)
    Job.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    video = Video(
        filename="video.mp4",
        file_path="/tmp/video.mp4",
        file_size=100,
        file_hash="b" * 64,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    failed_job = Job(
        video_id=video.id,
        status=JobStatus.FAILED,
    )
    db.add(failed_job)
    db.commit()

    class FakeTask:
        id = "fake-celery-task-id"

    monkeypatch.setattr(
        "app.api.routers.jobs.process_video_task.delay",
        lambda *args, **kwargs: FakeTask(),
    )

    payload = CreateJobRequest(video_id=video.id)

    result = create_job(
        payload=payload,
        db=db,
        current_user={},
    )

    assert result["job_id"] != failed_job.id
    assert db.query(Job).count() == 2

    db.close()
