"""The one place the API asks "may this caller see this job?" (§15, §17; T26, T28).

"Every endpoint checks that the requested object belongs to the caller." Every job and
result read (``GET /jobs``, ``/jobs/{id}``, ``/jobs/{id}/result``, ``/v1/jobs...``,
``/v1/videos/{id}/results``, ``/v1/videos/{id}/claims``, ``/v1/claims/{id}/evidence``)
goes through ``can_view_job`` / ``visible_jobs`` here, and answers **404, not 403**, for an
object the caller may not see, so existence doesn't leak (context/PRODUCTION.md §6a).

T26 put the call sites in place; T28 added the owner (migration 0011, ``jobs.user_id`` =
the JWT ``sub`` of the user who started the job) and the owner check below. Jobs created
before 0011 have no owner: with ``REQUIRE_AUTH`` off (local development, where everyone
is the same dev user) they stay visible; with auth on they are hidden until a person
assigns an owner. T33 extends these two functions (reviewer/admin roles, NULL-owner rows
for admins, a video owner) and every endpoint follows without further change.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.db.models.job import Job


def owner_id(user: Optional[dict]) -> Optional[str]:
    sub = (user or {}).get("sub")
    return str(sub) if sub else None


def _legacy_visible() -> bool:
    return not settings.REQUIRE_AUTH


def can_view_job(job: Job, user: Optional[dict]) -> bool:
    """Whether ``user`` may read ``job`` and everything stored for it: the job's owner."""
    if job.user_id is None:
        return _legacy_visible()
    uid = owner_id(user)
    return uid is not None and job.user_id == uid


def visible_jobs(query: Query, user: Optional[dict]) -> Query:
    """Restrict a query over ``Job`` to the jobs ``user`` may see (same rule as
    ``can_view_job``)."""
    uid = owner_id(user)
    conds = []
    if uid is not None:
        conds.append(Job.user_id == uid)
    if _legacy_visible():
        conds.append(Job.user_id.is_(None))
    if not conds:
        return query.filter(Job.id.is_(None))  # matches nothing
    return query.filter(or_(*conds))


def owned_job_or_404(db: Session, job_id: str, user: Optional[dict]) -> Job:
    """The caller's job, or 404 (missing and not-yours look the same)."""
    job = db.get(Job, job_id)
    if job is None or not can_view_job(job, user):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# T28's names, kept as thin wrappers so a monkeypatched can_view_job / visible_jobs
# (tests, T33) applies everywhere.
def can_see(job: Job, user: Optional[dict]) -> bool:
    return can_view_job(job, user)


def owned_jobs(query: Query, user: Optional[dict]) -> Query:
    return visible_jobs(query, user)


def get_owned_job(db: Session, job_id: str, user: Optional[dict]) -> Job:
    return owned_job_or_404(db, job_id, user)
