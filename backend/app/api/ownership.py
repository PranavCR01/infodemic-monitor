"""The one place the result endpoints ask "may this caller see this job?" (§15, §17; T26).

"Every endpoint checks that the requested object belongs to the caller." Every T26
read (``GET /jobs/{id}``, ``GET /jobs/{id}/result``, ``/v1/videos/{id}/results``,
``/v1/videos/{id}/claims``, ``/v1/claims/{id}/evidence``) goes through
``can_view_job`` / ``visible_jobs`` here, and answers **404, not 403**, for an object the
caller may not see, so existence doesn't leak (context/PRODUCTION.md §6a).

**The owner column belongs to T27** (queue decision 2026-11-24: "owner_id on videos and
jobs ... T26 and T28 must not add their own"). Until it lands there is no owner to
compare, so these functions only enforce what can be enforced today: an authenticated
caller (the routers depend on ``get_current_user``) and an existing object. T27 fills in
``can_view_job`` and ``visible_jobs`` (owner, or reviewer/admin; legacy NULL rows admin
only) and every T26 endpoint follows without further change.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from app.db.models.job import Job


def can_view_job(job: Job, user: Optional[dict]) -> bool:
    """Whether ``user`` may read ``job`` and everything stored for it. T27: compare the
    job's owner with ``user['sub']`` and allow reviewer/admin roles."""
    return True


def visible_jobs(query: Query, user: Optional[dict]) -> Query:
    """Restrict a query over ``Job`` to the jobs ``user`` may see (same rule as
    ``can_view_job``). T27: filter on the owner column."""
    return query


def owned_job_or_404(db: Session, job_id: str, user: Optional[dict]) -> Job:
    job = db.get(Job, job_id)
    if job is None or not can_view_job(job, user):
        raise HTTPException(status_code=404, detail="Job not found")
    return job
