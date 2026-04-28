import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.video import Video
from app.db.session import get_db
from app.services import job_service
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
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "video_id": job.video_id,
        "status": job.status,
        "error_code": job.error_code,
        "celery_task_id": job.celery_task_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("/{job_id}/result")
def get_result(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.SUCCESS:
        raise HTTPException(status_code=202, detail=f"Job not complete — status: {job.status}")

    result = db.query(Result).filter(Result.job_id == job_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    video = db.query(Video).filter(Video.id == job.video_id).first()

    return {
        "job_id": job_id,
        "filename": video.filename if video else None,
        "label": result.label,
        "confidence": result.confidence,
        "explanation": result.explanation,
        "evidence_snippets": result.evidence_snippets,
        "citations": result.citations,
        "provider": result.provider,
        "model_used": result.model_used,
        "latency_ms": result.latency_ms,
        "submitted_at": job.created_at,
        "created_at": result.created_at,
    }
