"""Research-dashboard aggregates (T62; design §12, §16, §17).

``GET /v1/stats`` shows totals across **all** users for a window (7, 30 or 90 days, or
all time). It never names a video, job, claim, review or user: every figure is a count,
a share or a median, and every count passes through small-cell suppression first.

Unit of counting
----------------
A **video** is counted once per window, with its newest result created in the window
(a re-analysis therefore replaces, not adds). The per-week buckets assign the video to
the ISO week (Monday, UTC) of that result, so the weeks partition the window total, and
the label cells partition the same population. Only the four canonical labels are
counted; a legacy row with any other label is left out of the whole population (not
shown as an "other" cell), so no published total includes it.

Claim categories count **videos** with at least one claim in the category, not claims:
one upload with six claims in one category must not reach the threshold on its own.

Jobs pending/running and the review backlog are snapshots of now (a job stuck since
before the window still matters); failed jobs and review decisions fall in the window by
``jobs.created_at`` / ``human_reviews.decided_at``.

Small-cell suppression
----------------------
Every count below ``MIN_CELL`` (5), zero included, is published as ``"<5"``.

Suppressed cells could be recovered by subtraction wherever a group of cells adds up to
a published total. Groups with a total here:

- the per-week buckets (total: ``videos.total``);
- the four labels (total: ``videos.total``);
- the MISINFO basis split (total: the MISINFO cell);
- review decisions changed / kept (total: ``reviews.decisions``).

In each group, after the primary suppression, more cells are suppressed (secondary
suppression, smallest first) until either nothing is suppressed, or at least two cells
are suppressed *and* the suppressed cells add up to ``MIN_CELL`` or more, so neither
one hidden cell nor a small hidden sum can be worked out from the total. A suppressed
total suppresses its whole group; a suppressed MISINFO cell suppresses its whole basis
split. A share is published only when both of its parts are; the median time to
decision only when the decision count is.

Groups without a total (job counts, the backlog, top categories) need only primary
suppression. Categories under the threshold are left out of the list entirely: their
names are free text from the model and a rare one could describe a single video.

Not covered (documented in context/MULTI_AGENT.md §7ah): differencing **across**
windows (30-day minus 7-day figures) or across time (the figures before and after one
video finishes). Each response is safe on its own; comparing responses can still narrow
a small change down. The 60-second shared cache limits the time resolution only.
"""
from __future__ import annotations

import statistics
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional, Union

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.schemas.pipeline import MisinfoLabel
from app.db.models.claim import ClaimRow
from app.db.models.job import Job, JobState, JobStatus
from app.db.models.result import Result
from app.db.models.review import HumanReview, ReviewCaseStatus

MIN_CELL = 5
SUPPRESSED = "<5"
TOP_CATEGORIES = 10
WINDOWS: dict[str, Optional[int]] = {"7d": 7, "30d": 30, "90d": 90, "all": None}
LABELS = [l.value for l in (MisinfoLabel.MISINFO, MisinfoLabel.NO_MISINFO,
                            MisinfoLabel.DEBUNKING, MisinfoLabel.CANNOT_RECOGNIZE)]
BASES = ["contradicted", "unproven", "denies_supported", "unspecified"]
NOTE = "These figures describe videos uploaded to this tool, not how common misinformation is online."
REVIEW_REJECTED = "REVIEW_REJECTED"

_PENDING_STATES = {JobState.PENDING.value, JobState.QUEUED.value, JobState.RETRY_PENDING.value}

Cell = Union[int, str]


# ------------------------------------------------------------------ suppression


def suppress_group(cells: dict[str, int], total: int) -> dict[str, Cell]:
    """Primary plus secondary suppression for cells that add up to a published
    ``total``. Returns the cells as published (an int, or ``"<5"``)."""
    if total < MIN_CELL:
        return {k: SUPPRESSED for k in cells}
    hidden = {k for k, v in cells.items() if v < MIN_CELL}
    if hidden:
        # Smallest first; ties broken by name so the result is deterministic.
        rest = sorted((k for k in cells if k not in hidden), key=lambda k: (cells[k], k))
        while rest and (len(hidden) < 2 or sum(cells[k] for k in hidden) < MIN_CELL):
            hidden.add(rest.pop(0))
    return {k: (SUPPRESSED if k in hidden else v) for k, v in cells.items()}


def cell(n: int) -> Cell:
    """Primary suppression only, for a count that belongs to no group with a total."""
    return SUPPRESSED if n < MIN_CELL else n


# ------------------------------------------------------------------ helpers


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _week_start(dt: datetime) -> date:
    d = dt.date()
    return d - timedelta(days=d.weekday())


def _chunks(items: list[str], n: int = 500) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _norm_category(c: Optional[str]) -> Optional[str]:
    if not c:
        return None
    c = c.strip().lower()[:64]
    return c or None


# ------------------------------------------------------------------ compute


def compute_stats(db: Session, window: str, now: Optional[datetime] = None) -> dict:
    if window not in WINDOWS:
        raise ValueError(f"unknown window {window!r}")
    now = _utc(now) or datetime.now(timezone.utc)
    days = WINDOWS[window]
    start = now - timedelta(days=days) if days is not None else None

    # --- the population: each video's newest result in the window
    q = (db.query(Result.job_id, Job.video_id, Result.label, Result.misinfo_basis, Result.created_at)
         .join(Job, Job.id == Result.job_id)
         .filter(Result.label.in_(LABELS)))
    if start is not None:
        q = q.filter(Result.created_at >= start)
    latest: dict[str, tuple] = {}
    for job_id, video_id, label, basis, created in q:
        created = _utc(created)
        if created is None or created > now:
            continue
        cur = latest.get(video_id)
        if cur is None or (created, job_id) > (cur[3], cur[0]):
            latest[video_id] = (job_id, label, basis, created)

    total = len(latest)
    total_cell = cell(total)

    # Per-week buckets: every week from the window start (or the first result) to now.
    weeks = Counter(_week_start(v[3]) for v in latest.values())
    first = _week_start(start) if start is not None else (min(weeks) if weeks else _week_start(now))
    week_keys: list[date] = []
    w = first
    while w <= _week_start(now):
        week_keys.append(w)
        w += timedelta(days=7)
    week_cells = suppress_group({w.isoformat(): weeks.get(w, 0) for w in week_keys}, total)

    # Labels and the MISINFO basis split.
    label_counts = Counter(v[1] for v in latest.values())
    labels = suppress_group({l: label_counts.get(l, 0) for l in LABELS}, total)
    basis_counts = Counter((v[2] if v[2] in BASES[:3] else "unspecified")
                           for v in latest.values() if v[1] == MisinfoLabel.MISINFO.value)
    basis_raw = {b: basis_counts.get(b, 0) for b in BASES}
    if labels[MisinfoLabel.MISINFO.value] == SUPPRESSED:
        basis = {b: SUPPRESSED for b in BASES}
    else:
        basis = suppress_group(basis_raw, label_counts.get(MisinfoLabel.MISINFO.value, 0))

    # --- jobs
    jobs = db.query(Job.state, Job.status, Job.error_code, Job.created_at).filter(
        or_(Job.state.in_(list(_PENDING_STATES) + [JobState.RUNNING.value]),
            Job.status.in_([JobStatus.PENDING, JobStatus.STARTED, JobStatus.FAILED])))
    pending = running = failed = 0
    for state, status, error_code, created in jobs:
        status_v = status.value if isinstance(status, JobStatus) else status
        if state is not None:
            if state in _PENDING_STATES:
                pending += 1
            elif state == JobState.RUNNING.value:
                running += 1
        elif status_v == JobStatus.PENDING.value:
            pending += 1
        elif status_v == JobStatus.STARTED.value:
            running += 1
        if status_v == JobStatus.FAILED.value and error_code != REVIEW_REJECTED:
            created = _utc(created)
            if start is None or (created is not None and created >= start):
                failed += 1

    # --- reviews
    backlog = db.query(HumanReview).filter(HumanReview.status == ReviewCaseStatus.OPEN).count()
    rq = db.query(HumanReview.created_at, HumanReview.decided_at, HumanReview.proposed_label,
                  HumanReview.corrected_label).filter(
        HumanReview.status == ReviewCaseStatus.RESOLVED, HumanReview.decided_at.isnot(None))
    if start is not None:
        rq = rq.filter(HumanReview.decided_at >= start)
    hours: list[float] = []
    changed = 0
    for created, decided, proposed, corrected in rq:
        created, decided = _utc(created), _utc(decided)
        if decided is None or decided > now:
            continue
        if created is not None:
            hours.append(max(0.0, (decided - created).total_seconds() / 3600))
        else:
            hours.append(float("nan"))
        if corrected is not None and corrected != proposed:
            changed += 1
    decisions = len(hours)
    decision_cells = suppress_group({"changed": changed, "kept": decisions - changed}, decisions)
    share = None
    if decisions >= MIN_CELL and SUPPRESSED not in decision_cells.values():
        share = round(changed / decisions, 3)
    median = None
    valid_hours = [h for h in hours if h == h]
    if decisions >= MIN_CELL and len(valid_hours) >= MIN_CELL:
        median = round(statistics.median(valid_hours), 1)

    # --- top claim categories (videos per category)
    cat_videos: dict[str, set[str]] = {}
    job_to_video = {v[0]: vid for vid, v in latest.items()}
    for chunk in _chunks(list(job_to_video)):
        for job_id, category in db.query(ClaimRow.job_id, ClaimRow.category).filter(ClaimRow.job_id.in_(chunk)):
            c = _norm_category(category)
            if c:
                cat_videos.setdefault(c, set()).add(job_to_video[job_id])
    cats = sorted(((c, len(v)) for c, v in cat_videos.items() if len(v) >= MIN_CELL),
                  key=lambda x: (-x[1], x[0]))[:TOP_CATEGORIES]

    return {
        "window": window,
        "window_start": start.isoformat() if start is not None else None,
        "window_end": now.isoformat(),
        "generated_at": now.isoformat(),
        "cache_seconds": settings.STATS_CACHE_SECONDS,
        "min_cell": MIN_CELL,
        "note": NOTE,
        "videos": {
            "total": total_cell,
            "per_week": [{"week_start": k, "videos": v} for k, v in week_cells.items()],
        },
        "jobs": {"pending_now": cell(pending), "running_now": cell(running), "failed": cell(failed)},
        "labels": {**labels, "misinfo_basis": basis},
        "reviews": {
            "backlog_now": cell(backlog),
            "decisions": cell(decisions),
            "changed_label": decision_cells["changed"],
            "kept_label": decision_cells["kept"],
            "changed_label_share": share,
            "median_hours_to_decision": median,
        },
        "top_categories": [{"category": c, "videos": n} for c, n in cats],
    }


# ------------------------------------------------------------------ cache


_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def get_stats(db: Session, window: str) -> dict:
    """The stats for ``window``, from a process-wide cache of ``STATS_CACHE_SECONDS``.
    The figures are the same for every caller (aggregates only), so one cache serves all."""
    ttl = settings.STATS_CACHE_SECONDS
    if ttl <= 0:
        return compute_stats(db, window)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(window)
        if hit is not None and hit[0] > now:
            return hit[1]
    payload = compute_stats(db, window)
    with _lock:
        _cache[window] = (now + ttl, payload)
    return payload
