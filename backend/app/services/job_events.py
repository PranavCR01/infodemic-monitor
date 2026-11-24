"""Job state and progress history (T28; design §1, §16, §17 ``job_events``).

Two vocabularies live side by side:

- ``jobs.status``: the five legacy values the current frontend reads (PENDING, STARTED,
  SUCCESS, FAILED, REVIEW_REQUIRED). Unchanged.
- ``jobs.state``: the §1 state (PENDING, QUEUED, RUNNING, RETRY_PENDING,
  REVIEW_REQUIRED, COMPLETED, FAILED, REJECTED), written here together with a
  ``job_events`` row.

``effective_state`` reconciles them: the stored §1 state is used only while it agrees
with ``status`` (another writer may change ``status`` without going through this module),
otherwise the state is derived from ``status``.

Recording is best effort: a failed write is rolled back and logged, and never fails the
job. Callers commit their own work before recording.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import String, and_, case, cast, func
from sqlalchemy.orm import Session

from app.core import progress
from app.db.models.job import Job, JobEvent, JobState, JobStatus

logger = logging.getLogger(__name__)

# §1 state -> the legacy status it is compatible with.
LEGACY_STATUS_OF: dict[str, str] = {
    JobState.PENDING.value: JobStatus.PENDING.value,
    JobState.QUEUED.value: JobStatus.PENDING.value,
    JobState.RETRY_PENDING.value: JobStatus.PENDING.value,
    JobState.RUNNING.value: JobStatus.STARTED.value,
    JobState.COMPLETED.value: JobStatus.SUCCESS.value,
    JobState.REVIEW_REQUIRED.value: JobStatus.REVIEW_REQUIRED.value,
    JobState.FAILED.value: JobStatus.FAILED.value,
    # A reviewer's rejection is stored as FAILED + error_code REVIEW_REJECTED
    # (review_service.decide), so the legacy frontend shows it as failed.
    JobState.REJECTED.value: JobStatus.FAILED.value,
}

REVIEW_REJECTED = "REVIEW_REJECTED"

# Legacy status -> §1 state when nothing finer is known.
STATE_OF_STATUS: dict[str, str] = {
    JobStatus.PENDING.value: JobState.PENDING.value,
    JobStatus.STARTED.value: JobState.RUNNING.value,
    JobStatus.SUCCESS.value: JobState.COMPLETED.value,
    JobStatus.FAILED.value: JobState.FAILED.value,
    JobStatus.REVIEW_REQUIRED.value: JobState.REVIEW_REQUIRED.value,
}

LEGACY_STATUSES = frozenset(s.value for s in JobStatus)
STATES = frozenset(s.value for s in JobState)

TERMINAL_STATES = frozenset({JobState.COMPLETED.value, JobState.FAILED.value, JobState.REJECTED.value})
PROCESSING_FINISHED_STATES = TERMINAL_STATES | {JobState.REVIEW_REQUIRED.value}


def _value(x: Any) -> Optional[str]:
    return None if x is None else getattr(x, "value", x)


def _compatible(state: Optional[str], status: Optional[str]) -> bool:
    if state is None or status is None:
        return False
    legacy = LEGACY_STATUS_OF.get(state)
    # A state with no legacy twin is only trusted if status says the same.
    return legacy == status if legacy is not None else state == status


def _derived_state(job: Job) -> str:
    status = _value(job.status)
    if status == JobStatus.FAILED.value and job.error_code == REVIEW_REJECTED:
        return JobState.REJECTED.value
    return STATE_OF_STATUS.get(status, status or JobState.PENDING.value)


def effective_state(job: Job) -> str:
    """The §1 state of ``job``."""
    if _compatible(job.state, _value(job.status)):
        return job.state  # type: ignore[return-value]
    return _derived_state(job)


def effective_state_sql():
    """``effective_state`` as a SQL expression, for filtering the jobs list."""
    status = cast(Job.status, String)
    trusted = [(and_(Job.state == state, status == legacy), Job.state)
               for state, legacy in LEGACY_STATUS_OF.items()]
    rejected = (and_(status == JobStatus.FAILED.value, Job.error_code == REVIEW_REJECTED),
                JobState.REJECTED.value)
    derived = case(rejected, *[(status == s, st) for s, st in STATE_OF_STATUS.items()], else_=status)
    return case(*trusted, else_=derived)


def current_step(job: Job) -> Optional[str]:
    """The step shown on the stepper, or None when nothing is running."""
    state = effective_state(job)
    if state in (JobState.RUNNING.value, JobState.RETRY_PENDING.value):
        return job.current_step
    if state in (JobState.PENDING.value, JobState.QUEUED.value):
        return job.current_step or progress.UPLOADED
    return job.current_step


def _next_seq(db: Session, job_id: str) -> int:
    last = db.query(func.max(JobEvent.seq)).filter(JobEvent.job_id == job_id).scalar()
    return (last or 0) + 1


def _write(db: Session, job: Job, *, kind: str, state: Optional[str], step: Optional[str],
           detail: Optional[dict]) -> Optional[JobEvent]:
    try:
        event = JobEvent(
            job_id=job.id, seq=_next_seq(db, job.id), kind=kind, state=state,
            status=_value(job.status), step=step, attempt=job.attempts or 0, detail=detail,
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()
        return event
    except Exception:  # noqa: BLE001 - history is best effort, never fails the job
        logger.warning("could not record job event for %s", getattr(job, "id", "?"), exc_info=True)
        db.rollback()
        return None


def record_state(db: Session, job: Job, state: str | JobState, *, step: Optional[str] = None,
                 detail: Optional[dict] = None) -> Optional[JobEvent]:
    """Set ``job.state`` (and optionally the step) and log the change. Does not touch
    ``job.status``: callers set the legacy status themselves. A repeat of the current
    state with the same step is not logged again (Celery may deliver a task twice)."""
    state = _value(state)
    if state not in STATES:
        raise ValueError(f"unknown job state {state!r}")
    if job.state == state and (step is None or step == job.current_step) and not detail:
        return None
    job.state = state
    if step is not None:
        job.current_step = step
    return _write(db, job, kind="state", state=state, step=step or job.current_step, detail=detail)


def record_step(db: Session, job: Job, step: str, *, detail: Optional[dict] = None) -> Optional[JobEvent]:
    """Log a pipeline step starting. Consecutive repeats of the same step are dropped."""
    if step not in progress.STEP_LABELS:
        raise ValueError(f"unknown step {step!r}")
    if job.current_step == step:
        return None
    job.current_step = step
    return _write(db, job, kind="step", state=effective_state(job), step=step, detail=detail)


def sync_state_from_status(db: Session, job: Job, *, detail: Optional[dict] = None) -> Optional[JobEvent]:
    """After code that only sets the legacy ``status`` (the result writers, the failure
    path), log the matching §1 state."""
    if _compatible(job.state, _value(job.status)):
        return None
    return record_state(db, job, _derived_state(job), detail=detail)


def step_reporter(db: Session, job: Job) -> Callable[[str], None]:
    """A ``progress.reporting`` reporter that logs steps for ``job``. Call it from the
    thread that owns ``db`` only (the pipeline reports from the worker's thread)."""
    def report(step: str) -> None:
        record_step(db, job, step)
    return report


def list_events(db: Session, job_id: str) -> list[JobEvent]:
    return (
        db.query(JobEvent)
        .filter(JobEvent.job_id == job_id)
        .order_by(JobEvent.seq.asc(), JobEvent.created_at.asc())
        .all()
    )


def split_status_filter(values: Iterable[str]) -> tuple[set[str], set[str]]:
    """Split ``?status=`` values into legacy statuses and §1 states. Comma-separated
    and repeated values both work; matching ignores case. Unknown values raise
    ValueError. A value in both vocabularies (PENDING, FAILED, REVIEW_REQUIRED) is
    matched as the §1 state, which is the finer one."""
    legacy: set[str] = set()
    states: set[str] = set()
    for raw in values:
        for v in str(raw).split(","):
            v = v.strip().upper()
            if not v:
                continue
            if v in STATES:
                states.add(v)
            elif v in LEGACY_STATUSES:
                legacy.add(v)
            else:
                raise ValueError(v)
    return legacy, states
