"""The one place the API asks "may this caller see this job / video?" (§15, §17; T26,
T28, T33).

"Every endpoint checks that the requested object belongs to the caller." Every job,
video, result and review read goes through ``can_view_job`` / ``visible_jobs`` /
``can_view_video`` here, and answers **404, not 403**, for an object the caller may not
see, so existence doesn't leak (context/PRODUCTION.md §6a).

The rule (T33, design §15 "a user sees only their own videos, jobs and results ...
separate roles for reviewers and admins"):

| Row's owner            | analyst | reviewer | admin |
|------------------------|---------|----------|-------|
| the caller             | yes     | yes      | yes   |
| another user           | no      | yes      | yes   |
| NULL (legacy, pre-0011/0014) | no | no     | yes   |

Owners are the verified JWT ``sub`` (``jobs.user_id``, migration 0011; ``videos.user_id``,
migration 0014); roles come from ``app.auth.roles`` (the token's ``app_metadata`` only).
Nothing here reads an id or a role from a request body.

With ``REQUIRE_AUTH`` off (local development, one dev user) NULL-owner rows stay visible
to that user, as before. A video is also visible to anyone who may see a job on it, so
users who shared a video row before per-user duplicate detection (T33) keep reaching
their own results.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import false, or_
from sqlalchemy.orm import Query, Session

from app.auth.roles import Role, has_role
from app.core.config import settings
from app.db.models.job import Job
from app.db.models.video import Video


def owner_id(user: Optional[dict]) -> Optional[str]:
    sub = (user or {}).get("sub")
    return str(sub) if sub else None


def _legacy_visible() -> bool:
    return not settings.REQUIRE_AUTH


def _role_at_least(user: Optional[dict], role: Role) -> bool:
    # A role without a subject counts for nothing: every read needs a known caller.
    return owner_id(user) is not None and has_role(user or {}, role)


def is_admin(user: Optional[dict]) -> bool:
    return _role_at_least(user, Role.ADMIN)


def is_reviewer(user: Optional[dict]) -> bool:
    """Reviewer or admin."""
    return _role_at_least(user, Role.REVIEWER)


def _row_visible(row_owner: Optional[str], user: Optional[dict]) -> bool:
    uid = owner_id(user)
    if uid is None:
        return False
    if row_owner is None:
        return is_admin(user) or _legacy_visible()
    return row_owner == uid or is_reviewer(user)


def _visible_filter(column, user: Optional[dict]):
    """The same rule as ``_row_visible`` as a SQL condition on an owner column."""
    uid = owner_id(user)
    if uid is None:
        return false()
    if is_admin(user):
        return None  # no restriction
    conds = [column.isnot(None)] if is_reviewer(user) else [column == uid]
    if _legacy_visible():
        conds.append(column.is_(None))
    return or_(*conds)


# ------------------------------------------------------------------ jobs


def can_view_job(job: Job, user: Optional[dict]) -> bool:
    """Whether ``user`` may read ``job`` and everything stored for it."""
    return _row_visible(job.user_id, user)


def visible_jobs(query: Query, user: Optional[dict]) -> Query:
    """Restrict a query over ``Job`` to the jobs ``user`` may see (same rule as
    ``can_view_job``)."""
    cond = _visible_filter(Job.user_id, user)
    return query if cond is None else query.filter(cond)


def own_jobs(query: Query, user: Optional[dict]) -> Query:
    """Only the caller's own jobs, whatever their role (plus NULL-owner jobs in local
    development). Used where "visible" is too wide, e.g. reusing an existing job."""
    uid = owner_id(user)
    if uid is None:
        return query.filter(false())
    cond = Job.user_id == uid
    if _legacy_visible():
        cond = or_(cond, Job.user_id.is_(None))
    return query.filter(cond)


def owned_job_or_404(db: Session, job_id: str, user: Optional[dict]) -> Job:
    """The job if the caller may see it, or 404 (missing and not-yours look the same)."""
    job = db.get(Job, job_id)
    if job is None or not can_view_job(job, user):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ------------------------------------------------------------------ videos


def can_view_video(db: Session, video: Video, user: Optional[dict]) -> bool:
    """Whether ``user`` may read ``video``: by its own owner, or because they may see a
    job on it (videos uploaded before migration 0014 have no owner of their own)."""
    if _row_visible(video.user_id, user):
        return True
    return visible_jobs(db.query(Job.id), user).filter(Job.video_id == video.id).first() is not None


def video_or_404(db: Session, video_id: str, user: Optional[dict]) -> Video:
    video = db.get(Video, video_id)
    if video is None or not can_view_video(db, video, user):
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def is_own(user: Optional[dict], job: Optional[Job] = None, video: Optional[Video] = None) -> bool:
    """Whether the caller submitted ``job`` or owns ``video`` (for "reviewers may not
    decide a case on their own video")."""
    uid = owner_id(user)
    if uid is None:
        return False
    return (job is not None and job.user_id == uid) or (video is not None and video.user_id == uid)


# T28's names, kept as thin wrappers so a monkeypatched can_view_job / visible_jobs
# (tests) applies everywhere.
def can_see(job: Job, user: Optional[dict]) -> bool:
    return can_view_job(job, user)


def owned_jobs(query: Query, user: Optional[dict]) -> Query:
    return visible_jobs(query, user)


def get_owned_job(db: Session, job_id: str, user: Optional[dict]) -> Job:
    return owned_job_or_404(db, job_id, user)
