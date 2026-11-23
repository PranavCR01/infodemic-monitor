import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.ownership import owned_job_or_404
from app.api.result_models import JobResultResponse
from app.auth.dependencies import get_current_user
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.video import Video
from app.db.session import get_db
from app.services import job_service
from app.services.result_view_service import job_result
from app.worker.tasks import process_video_task

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    video_id: str


@router.get("")
def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    label: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return job_service.list_jobs(db, limit=limit, offset=offset, label=label)


@router.post("/create")
def create_job(
    payload: CreateJobRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    video = db.query(Video).filter(Video.id == payload.video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    existing_job = (
        db.query(Job)
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
    job = Job(id=job_id, video_id=payload.video_id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()

    task = process_video_task.delay(job_id, storage_key=video.storage_key)
    job.celery_task_id = task.id
    db.commit()

    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "celery_task_id": job.celery_task_id,
    }


@router.get("/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = owned_job_or_404(db, job_id, current_user)
    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "error_code": job.error_code,
        "celery_task_id": job.celery_task_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


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
    if job.status not in (JobStatus.SUCCESS, JobStatus.REVIEW_REQUIRED):
        raise HTTPException(status_code=202, detail=f"Job not complete — status: {job.status}")

    result = db.query(Result).filter(Result.job_id == job_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return job_result(db, job, result).model_dump()
