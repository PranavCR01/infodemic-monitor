import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.pipeline as pipeline
import app.db.session as session_module
from app.core.config import settings
from app.core.exceptions import (
    GroundingError,
    InferenceProviderError,
    StorageError,
    TranscriptionError,
)
from app.db.base import Base
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.video import Video
from app.worker.tasks import process_video_task


@pytest.fixture
def Session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(session_module, "SessionLocal", Session)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    return Session


def make_job(Session):
    db = Session()
    video = Video(filename="video.mp4", file_path="/tmp/video.mp4", file_size=100)
    db.add(video)
    db.commit()
    job = Job(video_id=video.id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    return job_id


@pytest.mark.parametrize(
    "error, expected_code",
    [
        (StorageError(storage_key="videos/x.mp4"), "STORAGE_ERROR"),
        (TranscriptionError(provider="openai"), "TRANSCRIPTION_ERROR"),
        (InferenceProviderError(provider="anthropic"), "INFERENCE_ERROR"),
        (GroundingError("pubmed down"), "GROUNDING_ERROR"),
        (RuntimeError("something else"), "UNKNOWN_ERROR"),
    ],
)
def test_pipeline_error_sets_failed_job_with_error_code(Session, monkeypatch, error, expected_code):
    job_id = make_job(Session)

    async def failing_pipeline(video_path):
        raise error

    monkeypatch.setattr(pipeline, "run_pipeline", failing_pipeline)

    with pytest.raises(type(error)):
        process_video_task(job_id)

    db = Session()
    job = db.query(Job).filter(Job.id == job_id).first()
    assert job.status == JobStatus.FAILED
    assert job.error_code == expected_code
    assert db.query(Result).count() == 0
    db.close()
