import uuid
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.ownership import own_jobs, owned_job_or_404, owner_id, video_or_404
from app.api.result_models import JobResultResponse
from app.auth.dependencies import get_current_user
from app.core import progress
from app.db.models.job import Job, JobState, JobStatus
from app.db.models.result import Result
from app.db.session import get_db
from app.services import job_events, job_service
from app.services.result_view_service import job_result
from app.worker.tasks import process_video_task

router = APIRouter(prefix="/jobs", tags=["jobs"])
# §17 routes (T28). The unprefixed routes above stay as they are for the current frontend.
v1_router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    video_id: str


# ------------------------------------------------------------------ response models


class JobListItem(BaseModel):
    """One row of the jobs list. The first seven fields are the ones the current
    frontend reads; the rest were added by T28."""

    job_id: str
    status: str
    error_code: Optional[str] = None
    created_at: Optional[str] = None
    filename: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    video_id: Optional[str] = None
    state: str
    step: Optional[str] = None
    updated_at: Optional[str] = None
    # T33: who started the job (JWT ``sub``; NULL on legacy jobs). Reviewers and admins
    # see other users' jobs in the list; this tells them whose.
    submitted_by: Optional[str] = None
    # T30
    misinfo_basis: Optional[str] = None
    label_display: Optional[str] = None


class JobListPage(BaseModel):
    items: List[JobListItem]
    total: int
    limit: int
    offset: int


class JobOut(BaseModel):
    job_id: str
    video_id: str
    status: str
    error_code: Optional[str] = None
    celery_task_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # T28, additive.
    state: str
    step: Optional[str] = None
    step_label: Optional[str] = None
    attempts: int = 0
    submitted_by: Optional[str] = None  # T33


class StepOut(BaseModel):
    key: str
    label: str


class JobEventOut(BaseModel):
    id: str
    seq: int
    kind: str  # "state" | "step"
    state: Optional[str] = None
    status: Optional[str] = None
    step: Optional[str] = None
    step_label: Optional[str] = None
    attempt: int = 0
    detail: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None


class JobEventsOut(BaseModel):
    job_id: str
    status: str
    state: str
    step: Optional[str] = None
    attempts: int = 0
    # True once the pipeline has stopped working on the job (completed, failed,
    # rejected, or waiting for a person in REVIEW_REQUIRED): the frontend can stop polling.
    processing_finished: bool
    # The stepper's steps in order, and those this job's pipeline goes through.
    steps: List[StepOut]
    pipeline_steps: List[str]
    events: List[JobEventOut]


def _status(job: Job) -> str:
    return getattr(job.status, "value", job.status)


def _job_out(job: Job) -> JobOut:
    step = job_events.current_step(job)
    return JobOut(
        job_id=job.id, video_id=job.video_id, status=_status(job), error_code=job.error_code,
        celery_task_id=job.celery_task_id, created_at=job.created_at, updated_at=job.updated_at,
        state=job_events.effective_state(job), step=step,
        step_label=progress.STEP_LABELS.get(step) if step else None, attempts=job.attempts or 0,
        submitted_by=job.user_id,
    )


def _pipeline_steps(db: Session, job: Job) -> List[str]:
    """Which steps apply: the graph's if the job ran (or is running) the graph."""
    from app.core.config import settings

    result = db.query(Result).filter(Result.job_id == job.id).first()
    if result is not None:
        graph = result.pipeline == "graph"
    else:
        graph = bool(settings.USE_GRAPH_PIPELINE)
    return list(progress.PIPELINE_STEPS["graph" if graph else "single_call"])


def _query_page(db, user, *, limit, offset, label, q, status, mine=False):
    try:
        return job_service.query_jobs(
            db, limit=limit, offset=offset, label=label, search=q, statuses=status or (), user=user,
            mine=mine,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status: {exc}")


_STATUS_HELP = ("Filter by state: legacy statuses (PENDING, STARTED, SUCCESS, FAILED, REVIEW_REQUIRED) "
                "and/or §1 states (QUEUED, RUNNING, RETRY_PENDING, COMPLETED, REJECTED, ...). "
                "Repeat the parameter or separate values with commas.")
_MINE_HELP = ("Only the caller's own jobs. Without it the list holds every job the caller may "
              "see: their own, plus other users' for reviewers and admins (T33).")


# ------------------------------------------------------------------ legacy routes


@router.get("", response_model=List[JobListItem])
def list_jobs(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    label: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=200, description="Search filename, job id or video id"),
    status: Optional[List[str]] = Query(None, description=_STATUS_HELP),
    mine: bool = Query(False, description=_MINE_HELP),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """The jobs the caller may see, newest first. Still a bare list for the current
    frontend; the total matching the filters is in the ``X-Total-Count`` header (T28)."""
    rows, total = _query_page(db, current_user, limit=limit, offset=offset, label=label, q=q,
                              status=status, mine=mine)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.post("/create")
def create_job(
    payload: CreateJobRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # T34: remember the submitter's name and email (from the verified token) so review
    # screens can say whose video this is.
    from app.services import users_service

    users_service.remember(db, current_user)
    # T33: only a video the caller may see (their own; any for reviewers/admins);
    # someone else's looks missing.
    video = video_or_404(db, payload.video_id, current_user)

    # Only the caller's own job is reused (T28): a reviewer starting a job on another
    # user's video gets their own job, not a handle on the owner's.
    existing_job = (
        own_jobs(db.query(Job), current_user)
        .filter(
            Job.video_id == payload.video_id,
            Job.status.in_([
                JobStatus.PENDING,
                JobStatus.STARTED,
                JobStatus.SUCCESS,
                # A video already in human review is not analysed again (T11). Only
                # the graph pipeline (USE_GRAPH_PIPELINE) ever sets this state.
                JobStatus.REVIEW_REQUIRED,
            ]),
        )
        .order_by(Job.created_at.desc())
        .first()
    )

    if existing_job:
        return {
            "job_id": existing_job.id,
            "video_id": existing_job.video_id,
            "status": existing_job.status,
            "celery_task_id": existing_job.celery_task_id,
        }

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, video_id=payload.video_id, status=JobStatus.PENDING,
              user_id=owner_id(current_user))
    db.add(job)
    db.commit()
    job_events.record_state(db, job, JobState.PENDING, step=progress.UPLOADED)

    # QUEUED is logged just before the hand-off so a fast worker's RUNNING comes after it.
    job_events.record_state(db, job, JobState.QUEUED)
    try:
        task = process_video_task.delay(job_id, storage_key=video.storage_key)
    except Exception as exc:
        job_events.record_state(db, job, JobState.PENDING,
                                detail={"reason": "dispatch_failed", "error": type(exc).__name__})
        raise
    job.celery_task_id = task.id
    db.commit()

    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "celery_task_id": job.celery_task_id,
    }


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _job_out(owned_job_or_404(db, job_id, current_user))


@router.get("/{job_id}/result", response_model=JobResultResponse)
def get_result(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """The video-level result, plus (T26) everything stored for the reviewer and the
    result page: claims with stance rationale and quoted segments, modality, critic
    notes, papers with source kind / year / publisher / abstract snippet, transcript and
    OCR segments, and the review case with its status, severity and structured reasons.
    Existing fields are unchanged; ``review`` stays set once its case is resolved."""
    job = owned_job_or_404(db, job_id, current_user)
    # T34: no result for a reviewer still blind to this job's HIGH review case.
    from app.services.blind_review import require_revealed

    require_revealed(db, job, current_user)
    if job.status not in (JobStatus.SUCCESS, JobStatus.REVIEW_REQUIRED):
        raise HTTPException(status_code=202, detail=f"Job not complete — status: {job.status}")

    result = db.query(Result).filter(Result.job_id == job_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return job_result(db, job, result).model_dump()


# ------------------------------------------------------------------ /v1 routes (T28)


@v1_router.get("", response_model=JobListPage)
def list_jobs_v1(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    label: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=200, description="Search filename, job id or video id"),
    status: Optional[List[str]] = Query(None, description=_STATUS_HELP),
    mine: bool = Query(False, description=_MINE_HELP),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """The jobs the caller may see, newest first, with the total matching the filters."""
    rows, total = _query_page(db, current_user, limit=limit, offset=offset, label=label, q=q,
                              status=status, mine=mine)
    return JobListPage(items=rows, total=total, limit=limit, offset=offset)


@v1_router.get("/{job_id}", response_model=JobOut)
def get_job_v1(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _job_out(owned_job_or_404(db, job_id, current_user))


@v1_router.get("/{job_id}/events", response_model=JobEventsOut)
def get_job_events(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Processing history (§17): every state change and pipeline step, oldest first.
    Jobs created before T28 have no history; their state is derived from ``status``."""
    job = owned_job_or_404(db, job_id, current_user)
    state = job_events.effective_state(job)
    step = job_events.current_step(job)
    events = [
        JobEventOut(
            id=e.id, seq=e.seq, kind=e.kind, state=e.state, status=e.status, step=e.step,
            step_label=progress.STEP_LABELS.get(e.step) if e.step else None, attempt=e.attempt or 0,
            detail=e.detail, created_at=e.created_at,
        )
        for e in job_events.list_events(db, job.id)
    ]
    return JobEventsOut(
        job_id=job.id, status=_status(job), state=state, step=step, attempts=job.attempts or 0,
        processing_finished=state in job_events.PROCESSING_FINISHED_STATES,
        steps=[StepOut(key=k, label=v) for k, v in progress.STEP_LABELS.items()],
        pipeline_steps=_pipeline_steps(db, job), events=events,
    )
