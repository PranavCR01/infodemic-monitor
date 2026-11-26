import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    # The analysis finished but a person must review it before the result is shown
    # (target design §11–§12, T09). Set only by the graph pipeline (behind T11's flag);
    # the single-call path never uses it. The reasons live in ``human_reviews``.
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class JobState(str, enum.Enum):
    """The §1 job states (T28). ``jobs.status`` keeps the five values the current
    frontend reads; ``jobs.state`` carries the finer §1 state next to it."""

    PENDING = "PENDING"              # created, not yet queued
    QUEUED = "QUEUED"                # on the queue
    RUNNING = "RUNNING"              # a worker is processing it
    RETRY_PENDING = "RETRY_PENDING"  # a temporary failure; it will run again
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"            # a reviewer rejected the result


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String, ForeignKey("videos.id"))
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.PENDING)
    celery_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # T28 (migration 0011). Owner = the JWT ``sub`` of the user who started the job;
    # NULL on jobs created before 0011 (visible only with REQUIRE_AUTH off).
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    # §1 state (JobState value) and the stepper step (app.core.progress), kept by
    # app.services.job_events; NULL on older jobs (derived from ``status`` instead).
    state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # T55 (migration 0017): the job this one re-analyses (a deliberate re-run from
    # POST /v1/videos/{id}/reanalyse, or a reviewer's REQUEST_REANALYSIS). NULL on first
    # runs and on jobs created before 0017.
    previous_job_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("jobs.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )



class JobEvent(Base):
    """One entry in a job's processing history (§17 ``job_events``, T28): a state change
    (``kind="state"``) or a pipeline step starting (``kind="step"``)."""

    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    step: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
