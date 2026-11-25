from typing import Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.schemas.pipeline import display_label
from app.db.models.job import Job
from app.db.models.result import Result
from app.db.models.video import Video
from app.services import job_events


def _row(job: Job, video: Video, result: Optional[Result]) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "error_code": job.error_code,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "filename": video.filename,
        "label": result.label if result else None,
        "confidence": result.confidence if result else None,
        # T28, additive: the §1 state, the stepper step and a few fields for search results.
        "video_id": job.video_id,
        "state": job_events.effective_state(job),
        "step": job_events.current_step(job),
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "submitted_by": job.user_id,  # T33
        # T30: why a MISINFO label was given, and the label as shown.
        "misinfo_basis": result.misinfo_basis if result else None,
        "label_display": display_label(result.label, result.misinfo_basis) if result else None,
    }


def query_jobs(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    label: Optional[str] = None,
    search: Optional[str] = None,
    statuses: Iterable[str] = (),
    user: Optional[dict] = None,
    restrict_to_owner: bool = True,
    mine: bool = False,
) -> tuple[list[dict], int]:
    """One page of jobs (newest first) and the total matching the filters (T28).

    ``search`` matches the filename (case-insensitive substring) or an exact job or
    video id. ``statuses`` takes legacy statuses and/or §1 states (see
    ``job_events.split_status_filter``; raises ValueError on an unknown value).
    ``restrict_to_owner`` limits the page to the jobs ``user`` may see (T33: their own,
    others' for reviewers/admins); ``mine`` to the caller's own.
    """
    from app.api.ownership import own_jobs, owned_jobs

    query = (
        db.query(Job, Video, Result)
        .join(Video, Job.video_id == Video.id)
        .outerjoin(Result, Result.job_id == Job.id)
    )
    if restrict_to_owner:
        query = owned_jobs(query, user)
    if mine:
        query = own_jobs(query, user)
    if label:
        query = query.filter(Result.label == label)
    if search and search.strip():
        term = search.strip()
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(or_(
            Video.filename.ilike(f"%{escaped}%", escape="\\"),
            Job.id == term,
            Job.video_id == term,
        ))
    legacy, states = job_events.split_status_filter(statuses)
    if legacy or states:
        conds = []
        if legacy:
            conds.append(Job.status.in_(sorted(legacy)))
        if states:
            conds.append(job_events.effective_state_sql().in_(sorted(states)))
        query = query.filter(or_(*conds))

    # T34: a reviewer who hasn't given their blind judgement on a job's open HIGH case
    # doesn't see its label here, and label filters leave it out (no probing).
    from app.services.blind_review import blind_job_ids

    blind = blind_job_ids(db, user) if user is not None else set()
    if label and blind:
        query = query.filter(Job.id.notin_(sorted(blind)))

    total = query.with_entities(func.count(Job.id)).order_by(None).scalar() or 0
    rows = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
    out = [_row(job, video, result) for job, video, result in rows]
    for row in out:
        if row["job_id"] in blind:
            row.update(label=None, confidence=None, misinfo_basis=None, label_display=None)
    return out, int(total)


def list_jobs(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    label: Optional[str] = None,
    *,
    search: Optional[str] = None,
    statuses: Iterable[str] = (),
    user: Optional[dict] = None,
    restrict_to_owner: bool = True,
) -> list[dict]:
    rows, _ = query_jobs(db, limit=limit, offset=offset, label=label, search=search,
                         statuses=statuses, user=user, restrict_to_owner=restrict_to_owner)
    return rows
