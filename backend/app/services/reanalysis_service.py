"""Deliberate re-analysis and versioned results (T55; target design §1, §11, §12, §17).

``reanalyse_video`` starts a new analysis of a video that already has one, on purpose,
so a pipeline change can be checked on old videos. It is separate from the reuse rules
that guard against accidental double runs, which stay as they are: a duplicate upload
reuses the video (T33), and POST /jobs/create returns the caller's PENDING / STARTED /
SUCCESS / REVIEW_REQUIRED job (T11/T28).

- **Lineage.** A video's versions are the jobs on it owned by one user (``jobs.user_id``):
  the video owner's. A re-run belongs to the video owner even when an admin starts it,
  so it shows in the owner's job list (as in ``start_reanalysis``, T28). Each new job
  links to the newest job of its lineage through ``jobs.previous_job_id``.
- **Rate limit.** Each caller may start ``REANALYSIS_MAX_PER_VIDEO`` re-runs of one
  video per rolling ``REANALYSIS_WINDOW_HOURS``, counted from the audit log (action
  ``reanalysis_requested``, entity the video). A re-run whose dispatch failed doesn't
  count: nothing was analysed.
- **Open review case.** An OPEN case on the lineage becomes SUPERSEDED, linked to the new
  job, with an audit entry; it leaves the queue (which lists OPEN cases) without a
  decision. The old job keeps its REVIEW_REQUIRED status: its result was never
  reviewed. The new job's result goes through the review rule (§11) from scratch.
- **Versions.** The video's current result is its newest finished job;
  ``result_versions`` lists the others for the result page.
"""
from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.job import Job, JobState, JobStatus
from app.db.models.result import Result
from app.db.models.review import AuditEvent, HumanReview, ReviewCaseStatus
from app.db.models.video import Video

logger = logging.getLogger(__name__)

REANALYSIS_REQUESTED_ACTION = "reanalysis_requested"
REVIEW_SUPERSEDED_ACTION = "review_superseded"
REASON_MAX = 2000
DISPATCH_FAILED = "DISPATCH_FAILED"
REVIEW_REJECTED = "REVIEW_REJECTED"


class ReanalysisRateLimited(Exception):
    def __init__(self, retry_after: int, limit: int, window_hours: int):
        super().__init__(f"at most {limit} re-analyses of this video per {window_hours} h")
        self.retry_after = retry_after
        self.limit = limit
        self.window_hours = window_hours


class ReanalysisDisabled(Exception):
    pass


@dataclass
class ReanalysisOutcome:
    job: Job
    previous_job_id: Optional[str]
    superseded_review_ids: list[str] = field(default_factory=list)
    remaining: int = 0
    audit_event_id: Optional[str] = None


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


# ------------------------------------------------------------------ lineage


def lineage_owner(db: Session, video: Video) -> Optional[str]:
    """Whose versions a re-run continues: the video's owner; for a legacy video with no
    owner, the owner of its newest job (NULL if none)."""
    if video.user_id:
        return video.user_id
    newest = (db.query(Job).filter(Job.video_id == video.id)
              .order_by(Job.created_at.desc(), Job.id.desc()).first())
    return newest.user_id if newest is not None else None


def lineage_query(db: Session, video_id: str, owner: Optional[str]):
    q = db.query(Job).filter(Job.video_id == video_id)
    return q.filter(Job.user_id.is_(None) if owner is None else Job.user_id == owner)


def is_finished(job: Job) -> bool:
    """A job whose result can be shown: done, in review, or rejected by a reviewer."""
    return job.status in (JobStatus.SUCCESS, JobStatus.REVIEW_REQUIRED) or (
        job.status == JobStatus.FAILED and job.error_code == REVIEW_REJECTED
    )


# ------------------------------------------------------------------ rate limit


def _window(now: datetime) -> tuple[timedelta, datetime]:
    span = timedelta(hours=settings.REANALYSIS_WINDOW_HOURS)
    return span, now - span


def recent_requests(db: Session, actor_id: str, video_id: str, now: datetime) -> list[datetime]:
    """When ``actor_id`` started counted re-runs of the video inside the window, oldest first."""
    _, since = _window(now)
    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == REANALYSIS_REQUESTED_ACTION, AuditEvent.actor_id == actor_id,
                AuditEvent.entity_type == "video", AuditEvent.entity_id == video_id,
                AuditEvent.created_at >= since)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    # Filtered in Python: ``details`` is JSON (portable across SQLite and Postgres).
    return [_utc(e.created_at) for e in rows if not (e.details or {}).get("dispatch_failed")]


def check_rate(db: Session, actor_id: str, video_id: str, now: datetime) -> int:
    """How many re-runs are left after this one; raises ``ReanalysisRateLimited`` with
    the seconds until a slot frees up when none is left."""
    limit = settings.REANALYSIS_MAX_PER_VIDEO
    if limit <= 0:
        raise ReanalysisDisabled("re-analysis is turned off")
    times = recent_requests(db, actor_id, video_id, now)
    if len(times) >= limit:
        span, _ = _window(now)
        # A slot frees when enough of the oldest requests leave the window to drop the
        # count below the limit.
        frees_at = times[len(times) - limit] + span
        retry_after = max(1, math.ceil((frees_at - now).total_seconds()))
        raise ReanalysisRateLimited(retry_after, limit, settings.REANALYSIS_WINDOW_HOURS)
    return limit - len(times) - 1


# ------------------------------------------------------------------ start


def reanalyse_video(
    db: Session,
    video: Video,
    *,
    actor_id: str,
    actor_role: Optional[str] = None,
    reason: Optional[str] = None,
    dispatch: Callable[[str, Optional[str]], Optional[str]],
    now: Optional[datetime] = None,
) -> ReanalysisOutcome:
    """Create and dispatch a new job for ``video`` (the caller has already been checked:
    video owner or admin). Raises ``ReanalysisRateLimited`` over the limit."""
    from app.core import progress
    from app.services.job_events import record_state, sync_state_from_status

    now = _utc(now) or datetime.now(timezone.utc)
    reason = (reason or "").strip() or None
    if reason is not None and len(reason) > REASON_MAX:
        raise ValueError(f"the reason is longer than {REASON_MAX} characters")

    # Serialise re-runs of one video (Postgres row lock; SQLite has one writer anyway),
    # so two requests at once can't both take the last slot.
    db.query(Video).filter(Video.id == video.id).with_for_update().one()
    remaining = check_rate(db, actor_id, video.id, now)

    owner = lineage_owner(db, video)
    previous = (lineage_query(db, video.id, owner)
                .order_by(Job.created_at.desc(), Job.id.desc()).first())
    new_job = Job(id=str(uuid.uuid4()), video_id=video.id, status=JobStatus.PENDING, user_id=owner,
                  previous_job_id=previous.id if previous is not None else None)
    db.add(new_job)
    db.flush()

    superseded: list[str] = []
    open_cases = (
        db.query(HumanReview)
        .join(Job, Job.id == HumanReview.job_id)
        .filter(Job.video_id == video.id, HumanReview.status == ReviewCaseStatus.OPEN,
                Job.user_id.is_(None) if owner is None else Job.user_id == owner)
        .with_for_update(of=HumanReview)
        .all()
    )
    for case in open_cases:
        case.status = ReviewCaseStatus.SUPERSEDED
        case.superseded_by_job_id = new_job.id
        superseded.append(case.id)
        db.add(AuditEvent(
            actor_id=actor_id, action=REVIEW_SUPERSEDED_ACTION, entity_type="human_review",
            entity_id=case.id, job_id=case.job_id, reason=reason,
            details={"review_id": case.id, "superseded_by_job_id": new_job.id, "video_id": video.id,
                     "severity": case.severity, "proposed_label": case.proposed_label},
            created_at=now,
        ))
    event = AuditEvent(
        actor_id=actor_id, action=REANALYSIS_REQUESTED_ACTION, entity_type="video", entity_id=video.id,
        job_id=new_job.id, reason=reason,
        details={"video_id": video.id, "new_job_id": new_job.id,
                 "previous_job_id": new_job.previous_job_id, "actor_role": actor_role,
                 "lineage_owner": owner, "superseded_review_ids": superseded},
        created_at=now,
    )
    db.add(event)
    db.commit()

    # Dispatch as POST /jobs/create does: PENDING, QUEUED just before the hand-off.
    record_state(db, new_job, JobState.PENDING, step=progress.UPLOADED,
                 detail={"reason": "reanalysis", "previous_job_id": new_job.previous_job_id})
    record_state(db, new_job, JobState.QUEUED)
    try:
        new_job.celery_task_id = dispatch(new_job.id, video.storage_key)
    except Exception as exc:  # broker down, etc.: the job is failed and the slot given back
        logger.warning("re-analysis dispatch failed for job %s: %s", new_job.id, exc)
        new_job.status = JobStatus.FAILED
        new_job.error_code = DISPATCH_FAILED
        event.details = {**(event.details or {}), "dispatch_failed": True}
        remaining += 1
    db.commit()
    if new_job.error_code:
        sync_state_from_status(db, new_job, detail={"error_code": new_job.error_code})
    db.refresh(new_job)
    return ReanalysisOutcome(job=new_job, previous_job_id=new_job.previous_job_id,
                             superseded_review_ids=superseded, remaining=remaining,
                             audit_event_id=event.id)


# ------------------------------------------------------------------ versions


@dataclass
class ResultVersions:
    previous: list[tuple[Job, Result]]
    current_job_id: Optional[str]
    latest_job: Optional[Job]


def result_versions(db: Session, job: Job, *, limit: int = 50) -> ResultVersions:
    """The other versions of ``job``'s result, from its lineage (same video, same owner):

    - ``previous``: finished jobs with a stored result created before ``job``, newest first;
    - ``current_job_id``: the lineage's newest finished job (the video's current result);
    - ``latest_job``: the lineage's newest job if it isn't ``job`` and has no result to
      show (a re-run that is running, or that failed)."""
    jobs = (lineage_query(db, job.video_id, job.user_id)
            .order_by(Job.created_at.desc(), Job.id.desc()).all())
    results = {r.job_id: r for r in db.query(Result).filter(Result.job_id.in_([j.id for j in jobs]))}
    finished = [j for j in jobs if is_finished(j) and j.id in results]
    key = (_utc(job.created_at), job.id)
    previous = [(j, results[j.id]) for j in finished if j.id != job.id and (_utc(j.created_at), j.id) < key]
    newest = jobs[0] if jobs else None
    latest = (newest if newest is not None and newest.id != job.id
              and not (is_finished(newest) and newest.id in results) else None)
    return ResultVersions(previous=previous[:limit],
                          current_job_id=finished[0].id if finished else None,
                          latest_job=latest)


def latest_finished_first(db: Session, query) -> Optional[Job]:
    """From a query over ``Job`` (newest first): the newest finished job with a result,
    or else the newest job (so the caller can answer 202 / 409 for it)."""
    jobs = query.all()
    if not jobs:
        return None
    with_result = {r for (r,) in db.query(Result.job_id).filter(Result.job_id.in_([j.id for j in jobs]))}
    for j in jobs:
        if is_finished(j) and j.id in with_result:
            return j
    return jobs[0]

