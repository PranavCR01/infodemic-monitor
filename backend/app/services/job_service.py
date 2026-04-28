from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.job import Job
from app.db.models.result import Result
from app.db.models.video import Video


def list_jobs(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    label: Optional[str] = None,
) -> list[dict]:
    query = (
        db.query(Job, Video, Result)
        .join(Video, Job.video_id == Video.id)
        .outerjoin(Result, Result.job_id == Job.id)
    )
    if label:
        query = query.filter(Result.label == label)

    rows = (
        query
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "job_id": job.id,
            "status": job.status,
            "error_code": job.error_code,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "filename": video.filename,
            "label": result.label if result else None,
            "confidence": result.confidence if result else None,
        }
        for job, video, result in rows
    ]
