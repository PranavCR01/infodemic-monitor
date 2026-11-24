"""Review HTTP API (target design §12, §15, §17; T27).

| Method | Path | Who |
|---|---|---|
| GET  | ``/v1/me`` | anyone signed in: their id and server-decided role |
| GET  | ``/v1/reviews`` | reviewer, admin: the queue (severity, then age), filters, pages |
| GET  | ``/v1/reviews/{review_id}`` | reviewer, admin: one case with its audit trail |
| POST | ``/v1/reviews/{review_id}/decision`` | reviewer, admin: approve / correct / mark insufficient / reject / request re-analysis |
| POST | ``/v1/reviews/{review_id}/claims/{claim_id}/severity`` | reviewer, admin: severity override |

Roles come from the verified JWT (``app.auth.roles``); the reviewer recorded on every
action is the token's subject, never a field in the body (bodies forbid extra fields).
Analysts get 403 on every review route, before any lookup, so a refusal reveals
nothing about which cases exist. The service functions (``review_service``, T09/T22)
do the work; this module only checks, maps errors and shapes responses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.roles import PERMISSIONS, Role, require_role, role_of, user_id_of
from app.core.graph.state import Stance, Verdict
from app.core.schemas.pipeline import MisinfoLabel
from app.db.models.job import Job
from app.db.models.review import AuditEvent, HumanReview, ReviewAction, ReviewCaseStatus
from app.db.models.video import Video
from app.db.session import get_db
from app.services import review_service as rs

router = APIRouter(prefix="/v1", tags=["reviews"])

require_reviewer = require_role(Role.REVIEWER)


# ------------------------------------------------------------------ response models


class MeView(BaseModel):
    user_id: str
    email: Optional[str] = None
    role: Role
    permissions: list[str]


class AuditEntry(BaseModel):
    id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    reason: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReviewDecisionView(BaseModel):
    reviewer_id: str
    action: ReviewAction
    reason: Optional[str] = None
    corrected_label: Optional[str] = None
    corrections: Optional[dict[str, Any]] = None
    decided_at: Optional[datetime] = None


class ReviewQueueItem(BaseModel):
    review_id: str
    job_id: str
    video_id: Optional[str] = None
    filename: Optional[str] = None
    job_status: Optional[str] = None
    status: ReviewCaseStatus
    severity: Optional[str] = None
    severity_table_version: Optional[str] = None
    reasons: list[str]
    rules_fired: list[dict[str, Any]]
    proposed_label: Optional[str] = None
    created_at: datetime
    age_seconds: int
    decision: Optional[ReviewDecisionView] = None


class ReviewQueuePage(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    limit: int
    offset: int


class ReviewCaseView(ReviewQueueItem):
    validation_errors: list[Any] = Field(default_factory=list)
    proposed_result: Optional[dict[str, Any]] = None
    claim_severities: Optional[dict[str, Any]] = None
    policy_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)


class ReanalysisJobView(BaseModel):
    job_id: str
    video_id: str
    status: str
    error_code: Optional[str] = None


class DecisionResponse(BaseModel):
    case: ReviewCaseView
    reanalysis_job: Optional[ReanalysisJobView] = None


# ------------------------------------------------------------------ request models


class ClaimCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=64)
    verdict: Optional[Verdict] = None
    stance: Optional[Stance] = None


class DecisionRequest(BaseModel):
    # extra="forbid": a client can't name the reviewer or a role in the body.
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    reason: str = Field(min_length=1, max_length=4000)
    corrected_label: Optional[MisinfoLabel] = None
    claim_corrections: list[ClaimCorrection] = Field(default_factory=list, max_length=200)


class SeverityOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str = Field(min_length=1, max_length=4000)


# ------------------------------------------------------------------ helpers


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _decision(case: HumanReview) -> Optional[ReviewDecisionView]:
    if case.action is None or case.reviewer_id is None:
        return None
    return ReviewDecisionView(
        reviewer_id=case.reviewer_id,
        action=case.action,
        reason=case.decision_reason,
        corrected_label=case.corrected_label,
        corrections=case.corrections,
        decided_at=_utc(case.decided_at),
    )


def _item_fields(db: Session, case: HumanReview, now: datetime) -> dict[str, Any]:
    job = db.get(Job, case.job_id)
    video = db.get(Video, job.video_id) if job is not None else None
    created = _utc(case.created_at)
    return dict(
        review_id=case.id,
        job_id=case.job_id,
        video_id=job.video_id if job is not None else None,
        filename=video.filename if video is not None else None,
        job_status=job.status.value if job is not None and job.status is not None else None,
        status=case.status,
        severity=case.severity,
        severity_table_version=case.severity_table_version,
        reasons=list(case.reasons or []),
        rules_fired=list(case.rules_fired or []),
        proposed_label=case.proposed_label,
        created_at=created,
        age_seconds=max(0, int((now - created).total_seconds())),
        decision=_decision(case),
    )


def _audit(e: AuditEvent) -> AuditEntry:
    return AuditEntry(
        id=e.id, actor_id=e.actor_id, action=e.action, entity_type=e.entity_type,
        entity_id=e.entity_id, reason=e.reason, details=dict(e.details or {}),
        created_at=_utc(e.created_at),
    )


def _case_view(db: Session, case: HumanReview) -> ReviewCaseView:
    now = datetime.now(timezone.utc)
    return ReviewCaseView(
        **_item_fields(db, case, now),
        validation_errors=list(case.validation_errors or []),
        proposed_result=case.proposed_result,
        claim_severities=case.claim_severities,
        policy_version=case.policy_version,
        pipeline_version=case.pipeline_version,
        audit_trail=[_audit(e) for e in rs.review_audit_trail(db, case.job_id)],
    )


def _get_case(db: Session, review_id: str) -> HumanReview:
    case = db.get(HumanReview, review_id)
    if case is None:
        raise HTTPException(status_code=404, detail="review not found")
    return case


def _http(exc: rs.ReviewError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=404, detail="review not found")
    if "already resolved" in msg:
        return HTTPException(status_code=409, detail=msg)
    return HTTPException(status_code=422, detail=msg)


def get_reanalysis_dispatcher() -> Callable[[str, Optional[str]], Optional[str]]:
    """Queues a re-analysis job; returns the task id. Overridden in tests."""

    def _dispatch(job_id: str, storage_key: Optional[str]) -> Optional[str]:
        from app.worker.tasks import process_video_task

        return process_video_task.delay(job_id, storage_key=storage_key).id

    return _dispatch


# ------------------------------------------------------------------ routes


@router.get("/me", response_model=MeView)
def me(current_user: dict = Depends(get_current_user)) -> MeView:
    """Who the server thinks the caller is, and what their role allows (a hint for the
    UI; every action is checked again on the server)."""
    role = role_of(current_user)
    return MeView(
        user_id=user_id_of(current_user),
        email=current_user.get("email"),
        role=role,
        permissions=PERMISSIONS[role],
    )


@router.get("/reviews", response_model=ReviewQueuePage)
def review_queue(
    status: Literal["OPEN", "RESOLVED", "ALL"] = Query("OPEN"),
    severity: Optional[list[str]] = Query(
        None, description="HIGH, MEDIUM, LOW or NONE; repeat or comma-separate for several"),
    reason: Optional[str] = Query(
        None, max_length=128, description="a rule name (weak_evidence), or a reason (weak_evidence:c1)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
) -> ReviewQueuePage:
    """The review queue, by severity (HIGH first), then age (oldest first) (§12)."""
    severities = [s.strip() for raw in (severity or []) for s in raw.split(",") if s.strip()]
    try:
        cases, total = rs.review_queue_page(
            db, status=None if status == "ALL" else status, severities=severities or None,
            reason=reason, limit=limit, offset=offset,
        )
    except rs.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    return ReviewQueuePage(
        items=[ReviewQueueItem(**_item_fields(db, c, now)) for c in cases],
        total=total, limit=limit, offset=offset,
    )


@router.get("/reviews/{review_id}", response_model=ReviewCaseView)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
) -> ReviewCaseView:
    return _case_view(db, _get_case(db, review_id))


@router.post("/reviews/{review_id}/decision", response_model=DecisionResponse)
def decide(
    review_id: str,
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
    dispatch: Callable = Depends(get_reanalysis_dispatcher),
) -> DecisionResponse:
    """Record a reviewer's decision (§12). The reviewer is the caller; a reason is
    required. CORRECT takes a corrected label and/or per-claim verdict or stance
    corrections; REQUEST_REANALYSIS also starts a new job for the same video."""
    reviewer_id = user_id_of(current_user)
    case = _get_case(db, review_id)
    if case.status != ReviewCaseStatus.OPEN:
        raise HTTPException(status_code=409, detail="review is already resolved")
    try:
        corrections = rs.build_claim_corrections(
            db, case, [c.model_dump(mode="json", exclude_none=True) for c in payload.claim_corrections]
        )
        case = rs.record_review_decision(
            db, review_id,
            reviewer_id=reviewer_id,
            action=payload.action,
            reason=payload.reason,
            corrected_label=payload.corrected_label.value if payload.corrected_label else None,
            corrections=corrections,
        )
    except rs.ReviewError as exc:
        db.rollback()
        raise _http(exc) from exc

    reanalysis = None
    if case.action == ReviewAction.REQUEST_REANALYSIS:
        try:
            job = rs.start_reanalysis(db, case, reviewer_id=reviewer_id, dispatch=dispatch)
        except rs.ReviewError as exc:
            raise _http(exc) from exc
        # A failed dispatch comes back as a FAILED job (DISPATCH_FAILED); the decision stands.
        reanalysis = ReanalysisJobView(
            job_id=job.id, video_id=job.video_id, status=job.status.value, error_code=job.error_code,
        )
    return DecisionResponse(case=_case_view(db, case), reanalysis_job=reanalysis)


@router.post("/reviews/{review_id}/claims/{claim_id}/severity", response_model=ReviewCaseView)
def override_severity(
    review_id: str,
    claim_id: str,
    payload: SeverityOverrideRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
) -> ReviewCaseView:
    """Change one claim's severity with a reason (§12). Reorders the queue; never
    changes a label or verdict. Logged to the audit trail."""
    _get_case(db, review_id)
    try:
        case = rs.override_claim_severity(
            db, review_id, claim_id,
            reviewer_id=user_id_of(current_user), severity=payload.severity, reason=payload.reason,
        )
    except rs.ReviewError as exc:
        db.rollback()
        msg = str(exc)
        if "is not part of review" in msg:
            raise HTTPException(status_code=404, detail="claim not found in this review") from exc
        if "already has severity" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise _http(exc) from exc
    return _case_view(db, case)
