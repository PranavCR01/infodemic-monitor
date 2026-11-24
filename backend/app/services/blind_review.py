"""The blind "your judgement first" step for HIGH-severity cases (lead's decision D7;
target design §12; T34).

A reviewer of a HIGH case records their own stance and verdict for every claim
(``record_pre_reveal``) before the server shows them what the system proposed. The
server enforces it; the UI's own gating is not a control.

**Which cases.** A case needs the step while it is OPEN and either its severity is
HIGH or the severity table (ignoring reviewer overrides) makes it HIGH. The second
condition means overriding a claim's severity down cannot be used to skip the step.

**Who is blind.** A reviewer or admin with no pre-reveal on that case, who did not
submit the job and does not own the video. (People can't decide their own video, and
they already see their own results.)

**What a blind caller gets.** The case view is split (``app.api.routers.reviews``):
the claims (text, category, times, table severity) and the case metadata, but not the
proposed label or result, the reasons and rules that fired (they name stances and
verdicts, e.g. ``judge:denies_supported:c1``), validation errors, the claims' stances,
verdicts or MISINFO relevance, or audit details. The same caller also gets 403
``PRE_REVEAL_REQUIRED`` from the result, claims and evidence routes of that job, and
the job list hides that job's label and leaves it out of label-filtered pages. The
video's severity (HIGH) stays visible: it is what puts the case at the top of the queue.
What the blind caller judges from instead is ``GET /v1/reviews/{id}/blind-material``
(``app.services.blind_material``, T40), open only while they are blind.

A decision on a case that needs the step is rejected (409 ``PRE_REVEAL_REQUIRED``)
unless the deciding reviewer has a pre-reveal on it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.job import Job
from app.db.models.review import AuditEvent, HumanReview, ReviewCaseStatus, ReviewPreReveal
from app.db.models.video import Video

PRE_REVEAL_ACTION = "review_pre_reveal"
PRE_REVEAL_REQUIRED = "PRE_REVEAL_REQUIRED"
NOTE_MAX = 4000


def _table_severity(case: HumanReview) -> Optional[str]:
    from app.core.graph.severity import video_severity

    claims = {cid: {k: v for k, v in (e or {}).items() if k != "override"}
              for cid, e in (case.claim_severities or {}).items()}
    sev = video_severity(claims)
    return sev.value if sev else None


def requires_blind_step(case: HumanReview) -> bool:
    if case.status != ReviewCaseStatus.OPEN:
        return False
    return case.severity == "HIGH" or _table_severity(case) == "HIGH"


def pre_reveal_of(db: Session, review_id: str, reviewer_id: Optional[str]) -> Optional[ReviewPreReveal]:
    if not reviewer_id:
        return None
    return (
        db.query(ReviewPreReveal)
        .filter(ReviewPreReveal.review_id == review_id, ReviewPreReveal.reviewer_id == reviewer_id)
        .one_or_none()
    )


def _is_own(db: Session, case: HumanReview, user: Optional[Mapping[str, Any]]) -> bool:
    from app.api.ownership import is_own

    job = db.get(Job, case.job_id)
    video = db.get(Video, job.video_id) if job is not None else None
    return is_own(user, job, video)


def is_blind(db: Session, case: HumanReview, user: Optional[Mapping[str, Any]]) -> bool:
    """Whether ``user`` must not yet see the system's view of ``case``."""
    from app.api.ownership import owner_id

    if not requires_blind_step(case):
        return False
    if _is_own(db, case, user):
        return False
    return pre_reveal_of(db, case.id, owner_id(user)) is None


def blind_job_ids(db: Session, user: Optional[Mapping[str, Any]]) -> set[str]:
    """Jobs whose open HIGH case ``user`` is blind to (for the job list)."""
    from app.api.ownership import is_reviewer, owner_id

    uid = owner_id(user)
    if uid is None or not is_reviewer(user):
        return set()  # analysts only see their own jobs, which are never blind to them
    revealed = {r for (r,) in db.query(ReviewPreReveal.review_id)
                .filter(ReviewPreReveal.reviewer_id == uid).all()}
    out: set[str] = set()
    cases = db.query(HumanReview).filter(HumanReview.status == ReviewCaseStatus.OPEN).all()
    for case in cases:
        if case.id in revealed or not requires_blind_step(case):
            continue
        if not _is_own(db, case, user):
            out.add(case.job_id)
    return out


def blind_case_for_job(db: Session, job: Job, user: Optional[Mapping[str, Any]]) -> Optional[HumanReview]:
    case = db.query(HumanReview).filter(HumanReview.job_id == job.id).one_or_none()
    if case is not None and is_blind(db, case, user):
        return case
    return None


def require_revealed(db: Session, job: Job, user: Optional[Mapping[str, Any]]) -> None:
    """403 ``PRE_REVEAL_REQUIRED`` if ``user`` is blind to ``job``'s review case. Call
    after the ownership check, so a job the caller may not see is still a 404."""
    case = blind_case_for_job(db, job, user)
    if case is not None:
        raise HTTPException(status_code=403, detail={
            "code": PRE_REVEAL_REQUIRED,
            "review_id": case.id,
            "message": "this result is in HIGH-severity review: record your own judgement "
                       f"(POST /v1/reviews/{case.id}/pre-reveal) before seeing the system's",
        })


class PreRevealError(ValueError):
    pass


def record_pre_reveal(
    db: Session,
    case: HumanReview,
    *,
    reviewer_id: str,
    claims: list[Mapping[str, Any]],
    note: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ReviewPreReveal:
    """Record a reviewer's blind judgement: a stance and a verdict for **every** claim
    of the case, from the fixed sets. One per reviewer per case; the server's clock
    sets the time; logged to ``audit_events``. Raises ``PreRevealError`` (message starts
    with "conflict:" for 409s)."""
    from app.core.graph.state import Stance, Verdict
    from app.services.review_service import claim_ids_of

    if case.status != ReviewCaseStatus.OPEN:
        raise PreRevealError("conflict: review is already resolved")
    if not requires_blind_step(case):
        raise PreRevealError("conflict: the blind step applies to HIGH-severity cases only")
    if pre_reveal_of(db, case.id, reviewer_id) is not None:
        raise PreRevealError("conflict: you already recorded your judgement on this case")
    known = claim_ids_of(db, case)
    out: dict[str, dict[str, str]] = {}
    for item in claims:
        cid = str(item.get("claim_id") or "")
        if cid not in known:
            raise PreRevealError(f"claim {cid!r} is not part of review {case.id!r}")
        if cid in out:
            raise PreRevealError(f"claim {cid!r} is given twice")
        entry = {}
        for field, enum_cls in (("stance", Stance), ("verdict", Verdict)):
            try:
                entry[field] = enum_cls(str(item.get(field) or "").upper()).value
            except ValueError:
                allowed = ", ".join(e.value for e in enum_cls)
                raise PreRevealError(f"claim {cid!r}: {field} must be one of {allowed}") from None
        out[cid] = entry
    missing = sorted(set(known) - set(out))
    if missing:
        raise PreRevealError(f"give a stance and verdict for every claim; missing {missing}")
    note = (note or "").strip() or None
    at = now or datetime.now(timezone.utc)
    row = ReviewPreReveal(review_id=case.id, reviewer_id=reviewer_id, claims=out, note=note,
                          case_severity=case.severity, created_at=at)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise PreRevealError("conflict: you already recorded your judgement on this case") from None
    db.add(AuditEvent(
        actor_id=reviewer_id,
        action=PRE_REVEAL_ACTION,
        entity_type="human_review",
        entity_id=case.id,
        job_id=case.job_id,
        reason=note,
        details={"review_id": case.id, "pre_reveal_id": row.id, "claims": out,
                 "case_severity": case.severity},
        created_at=at,
    ))
    db.commit()
    db.refresh(row)
    return row


def agreement(db: Session, case: HumanReview, pre: ReviewPreReveal) -> dict[str, dict[str, bool]]:
    """Per claim, whether the reviewer's blind stance / verdict matched the system's."""
    from app.services.review_service import claim_ids_of

    system = claim_ids_of(db, case)
    return {
        cid: {"stance": mine.get("stance") == (system.get(cid) or {}).get("stance"),
              "verdict": mine.get("verdict") == (system.get(cid) or {}).get("verdict")}
        for cid, mine in (pre.claims or {}).items()
    }
