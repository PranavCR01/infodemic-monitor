"""Review HTTP API (target design §12, §15, §17; T27).

| Method | Path | Who |
|---|---|---|
| GET  | ``/v1/me`` | anyone signed in: their id and server-decided role |
| GET  | ``/v1/reviews`` | reviewer, admin: the queue (severity, then age), filters, pages |
| GET  | ``/v1/reviews/{review_id}`` | reviewer, admin: one case with its audit trail |
| POST | ``/v1/reviews/{review_id}/decision`` | reviewer, admin: approve / correct / mark insufficient / reject / request re-analysis |
| POST | ``/v1/reviews/{review_id}/pre-reveal`` | reviewer, admin: the blind step on a HIGH case (T34) |
| GET  | ``/v1/reviews/{review_id}/blind-material`` | reviewer, admin, only while blind on that case: what to judge from (T40) |
| POST | ``/v1/reviews/{review_id}/claims/{claim_id}/severity`` | reviewer, admin: severity override |
| POST | ``/v1/jobs/{job_id}/review-request`` | the job's owner, reviewer, admin: ask for a person to check a result (T32) |

Roles come from the verified JWT (``app.auth.roles``); the reviewer recorded on every
action is the token's subject, never a field in the body (bodies forbid extra fields).
Per-object access (T33) goes through ``app.api.ownership``: reviewers see cases on every
owned job, admins also those on legacy jobs with no owner; a case the caller may not see
is a 404 like a missing one. Nobody may decide (or re-rate) a case on their own video:
that is a 403, since the caller can already see the case. ``submitted_by`` on queue
items and cases is the job's owner (``jobs.user_id``); the decider is
``decision.reviewer_id``.
Analysts get 403 on every review route, before any lookup, so a refusal reveals
nothing about which cases exist. The service functions (``review_service``, T09/T22)
do the work; this module only checks, maps errors and shapes responses.

T34 (lead's decision D7):

- **Reason codes.** A decision takes ``reason_code`` (``ReviewReasonCode``) next to the
  written ``reason``, which must be at least 10 characters once trimmed. Both go on the
  case and in the audit event. A client that sends no code (written before T34) gets
  ``OTHER``, and the audit event records ``reason_code_defaulted: true`` so those
  decisions can be told apart. ``SYSTEM_CORRECT`` goes only with APPROVE.
- **Blind step for HIGH cases** (``app.services.blind_review``): until the caller has
  posted ``/pre-reveal`` (their own stance and verdict for every claim, server-timed),
  ``GET`` of the case and the queue withhold the system's view (``system_view_withheld:
  true``): no proposed label or result, reasons, rules fired, validation errors,
  claim stances/verdicts, request note or audit details. ``claims`` lists each claim's
  text, category and times so the reviewer can judge. A decision on such a case
  without the deciding reviewer's pre-reveal is a 409 ``PRE_REVEAL_REQUIRED``; with
  one, the audit event links it and records per-claim agreement.
- **Names** (``app.services.users_service``): audit entries, decisions, queue items and
  the request carry ``*_name`` (display name, else email) and ``*_email``; queue items
  carry ``is_own`` (the caller submitted the job or owns the video). Names come from the
  ``users`` table, filled from verified tokens; another user's email is shown only to
  reviewers and admins.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api import ownership
from app.api.ownership import owned_job_or_404
from app.auth.dependencies import get_current_user
from app.auth.roles import PERMISSIONS, Role, require_role, role_of, user_id_of
from app.core.graph.state import Stance, Verdict
from app.core.schemas.pipeline import MisinfoLabel
from app.db.models.job import Job
from app.db.models.review import (
    AuditEvent,
    HumanReview,
    ReviewAction,
    ReviewCaseStatus,
    ReviewPreReveal,
    ReviewReasonCode,
)
from app.db.models.video import Video
from app.db.session import get_db
from app.services import blind_material as blind_mat
from app.services import blind_review as blind
from app.services import review_service as rs
from app.services import users_service
from app.services.review_reasons import ReasonView, parse_reasons

router = APIRouter(prefix="/v1", tags=["reviews"])

require_reviewer = require_role(Role.REVIEWER)

REASON_MIN = 10  # T34 (D7): a decision's note


# ------------------------------------------------------------------ response models


class MeView(BaseModel):
    user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None  # T34: from the token's user_metadata
    role: Role
    permissions: list[str]


class AuditEntry(BaseModel):
    id: str
    actor_id: str
    actor_name: Optional[str] = None  # T34: display name, else email
    actor_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: str
    reason: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReviewDecisionView(BaseModel):
    reviewer_id: str
    reviewer_name: Optional[str] = None  # T34
    reviewer_email: Optional[str] = None
    action: ReviewAction
    reason: Optional[str] = None
    reason_code: Optional[ReviewReasonCode] = None  # T34; None on decisions made before
    corrected_label: Optional[str] = None
    corrections: Optional[dict[str, Any]] = None
    decided_at: Optional[datetime] = None


class ReviewQueueItem(BaseModel):
    review_id: str
    job_id: str
    video_id: Optional[str] = None
    filename: Optional[str] = None
    job_status: Optional[str] = None
    # T33: who started the job under review (``jobs.user_id``); NULL on legacy jobs.
    submitted_by: Optional[str] = None
    submitted_by_name: Optional[str] = None  # T34
    submitted_by_email: Optional[str] = None
    # T34: the caller submitted this job or owns the video (so can't decide it).
    is_own: bool = False
    # T34: an open HIGH case needs each reviewer's blind judgement before a decision;
    # ``system_view_withheld`` is true while the caller hasn't given theirs (then the
    # proposed label, reasons and rules fired are withheld: empty / null).
    blind_step_required: bool = False
    system_view_withheld: bool = False
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


class ReviewRequestInfo(BaseModel):
    """Who asked for a review that no rule raised, when, and their note (T32)."""

    requested_by: str
    requested_by_name: Optional[str] = None  # T34
    requested_by_email: Optional[str] = None
    note: Optional[str] = None
    requested_at: datetime


class CaseClaimView(BaseModel):
    """One claim of the case (T34). ``stance`` and ``verdict`` are the system's and are
    null while the system's view is withheld."""

    claim_id: str
    text: Optional[str] = None
    category: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None
    severity: Optional[str] = None
    stance: Optional[str] = None
    verdict: Optional[str] = None


class PreRevealView(BaseModel):
    id: str
    reviewer_id: str
    claims: dict[str, dict[str, str]]
    note: Optional[str] = None
    case_severity: Optional[str] = None
    created_at: datetime


class ReviewCaseView(ReviewQueueItem):
    claims: list[CaseClaimView] = Field(default_factory=list)
    # The caller's own blind judgement, once given (T34).
    pre_reveal: Optional[PreRevealView] = None
    request: Optional[ReviewRequestInfo] = None
    validation_errors: list[Any] = Field(default_factory=list)
    proposed_result: Optional[dict[str, Any]] = None
    claim_severities: Optional[dict[str, Any]] = None
    policy_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)


class ReviewRequestResponse(BaseModel):
    """What the requester sees: the case for this job (new or the one already there).
    No proposed result or audit trail; those are for reviewers."""

    created: bool
    review_id: str
    job_id: str
    job_status: Optional[str] = None
    case_status: ReviewCaseStatus
    reasons: list[str]
    reason_details: list[ReasonView]
    request: Optional[ReviewRequestInfo] = None
    created_at: datetime


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
    # T34: the note; at least REASON_MIN characters once trimmed.
    reason: str = Field(min_length=1, max_length=4000)
    # T34: why, as a code. Missing (pre-T34 clients) → OTHER, flagged in the audit event.
    reason_code: Optional[ReviewReasonCode] = None
    corrected_label: Optional[MisinfoLabel] = None
    claim_corrections: list[ClaimCorrection] = Field(default_factory=list, max_length=200)

    @field_validator("reason")
    @classmethod
    def _reason_long_enough(cls, v: str) -> str:
        if len(v.strip()) < REASON_MIN:
            raise ValueError(f"the reason must be at least {REASON_MIN} characters")
        return v


class PreRevealClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=64)
    stance: Stance
    verdict: Verdict


class PreRevealRequest(BaseModel):
    # extra="forbid": the reviewer and the time come from the server.
    model_config = ConfigDict(extra="forbid")

    claims: list[PreRevealClaim] = Field(min_length=1, max_length=200)
    note: Optional[str] = Field(None, max_length=blind.NOTE_MAX)


class ReviewRequestBody(BaseModel):
    # extra="forbid": the requester comes from the token, not the body.
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=rs.REQUEST_NOTE_MAX,
                      description="why a person should check this result (required)")


class SeverityOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str = Field(min_length=1, max_length=4000)


# ------------------------------------------------------------------ helpers


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class _Ctx:
    """Per-request view context: the caller and the users table rows needed."""

    def __init__(self, db: Session, user: dict, ids: set[Optional[str]] = frozenset()):
        self.db = db
        self.user = user
        self.users = users_service.load(db, ids)

    def person(self, user_id: Optional[str]) -> users_service.Person:
        return users_service.person(self.users, user_id, viewer=self.user)


def _ids_for(db: Session, cases: list[HumanReview]) -> set[Optional[str]]:
    ids: set[Optional[str]] = set()
    for case in cases:
        job = db.get(Job, case.job_id)
        ids.add(job.user_id if job is not None else None)
        ids.add(case.reviewer_id)
    return ids


def _decision(case: HumanReview, ctx: _Ctx) -> Optional[ReviewDecisionView]:
    if case.action is None or case.reviewer_id is None:
        return None
    who = ctx.person(case.reviewer_id)
    return ReviewDecisionView(
        reviewer_id=case.reviewer_id,
        reviewer_name=who.name,
        reviewer_email=who.email,
        action=case.action,
        reason=case.decision_reason,
        reason_code=case.reason_code,
        corrected_label=case.corrected_label,
        corrections=case.corrections,
        decided_at=_utc(case.decided_at),
    )


def _item_fields(db: Session, case: HumanReview, now: datetime, ctx: _Ctx) -> dict[str, Any]:
    job = db.get(Job, case.job_id)
    video = db.get(Video, job.video_id) if job is not None else None
    created = _utc(case.created_at)
    withheld = blind.is_blind(db, case, ctx.user)
    submitter = ctx.person(job.user_id if job is not None else None)
    return dict(
        review_id=case.id,
        job_id=case.job_id,
        video_id=job.video_id if job is not None else None,
        filename=video.filename if video is not None else None,
        job_status=job.status.value if job is not None and job.status is not None else None,
        submitted_by=job.user_id if job is not None else None,
        submitted_by_name=submitter.name,
        submitted_by_email=submitter.email,
        is_own=ownership.is_own(ctx.user, job, video),
        blind_step_required=blind.requires_blind_step(case),
        system_view_withheld=withheld,
        status=case.status,
        severity=case.severity,
        severity_table_version=case.severity_table_version,
        reasons=[] if withheld else list(case.reasons or []),
        rules_fired=[] if withheld else list(case.rules_fired or []),
        proposed_label=None if withheld else case.proposed_label,
        created_at=created,
        age_seconds=max(0, int((now - created).total_seconds())),
        decision=_decision(case, ctx),
    )


def _audit(e: AuditEvent, ctx: _Ctx, *, withheld: bool = False) -> AuditEntry:
    who = ctx.person(e.actor_id)
    return AuditEntry(
        id=e.id, actor_id=e.actor_id, actor_name=who.name, actor_email=who.email,
        action=e.action, entity_type=e.entity_type, entity_id=e.entity_id,
        # Blind (T34): who did what and when, but not what they wrote or saw.
        reason=None if withheld else e.reason,
        details={} if withheld else dict(e.details or {}),
        created_at=_utc(e.created_at),
    )


def _request_info(db: Session, job_id: str, ctx: _Ctx, *, withheld: bool = False) -> Optional[ReviewRequestInfo]:
    e = rs.review_request_event(db, job_id)
    if e is None:
        return None
    if e.actor_id not in ctx.users:
        ctx.users.update(users_service.load(db, [e.actor_id]))
    who = ctx.person(e.actor_id)
    return ReviewRequestInfo(requested_by=e.actor_id, requested_by_name=who.name,
                             requested_by_email=who.email, note=None if withheld else e.reason,
                             requested_at=_utc(e.created_at))


def _case_claims(db: Session, case: HumanReview, *, withheld: bool) -> list[CaseClaimView]:
    from app.core.graph.severity import effective_claim_severity
    from app.db.models.claim import ClaimRow

    system = rs.claim_ids_of(db, case)
    rows = {r.claim_id: r for r in db.query(ClaimRow).filter(ClaimRow.job_id == case.job_id).all()}
    sev = case.claim_severities or {}
    out = []
    def order(cid: str) -> tuple[float, str]:
        row = rows.get(cid)
        return (row.start_seconds if row is not None else float("inf"), cid)

    for cid in sorted(set(system) | set(rows), key=order):
        row = rows.get(cid)
        mine = system.get(cid) or {}
        out.append(CaseClaimView(
            claim_id=cid,
            text=row.text if row is not None else None,
            category=row.category if row is not None else None,
            start=row.start_seconds if row is not None else None,
            end=row.end_seconds if row is not None else None,
            severity=effective_claim_severity(sev[cid]) if cid in sev else None,
            stance=None if withheld else mine.get("stance"),
            verdict=None if withheld else mine.get("verdict"),
        ))
    return out


def _pre_reveal_view(pre: Optional[ReviewPreReveal]) -> Optional[PreRevealView]:
    if pre is None:
        return None
    return PreRevealView(id=pre.id, reviewer_id=pre.reviewer_id, claims=dict(pre.claims or {}),
                         note=pre.note, case_severity=pre.case_severity, created_at=_utc(pre.created_at))


def _blind_claim_severities(claims: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Claim severities without what the system decided about each claim."""
    if claims is None:
        return None
    hidden = {"stance", "verdict", "misinfo_relevant"}
    return {cid: {k: v for k, v in (e or {}).items() if k not in hidden} for cid, e in claims.items()}


def _case_view(db: Session, case: HumanReview, user: dict) -> ReviewCaseView:
    now = datetime.now(timezone.utc)
    trail = rs.review_audit_trail(db, case.job_id)
    ctx = _Ctx(db, user, _ids_for(db, [case]) | {e.actor_id for e in trail})
    fields = _item_fields(db, case, now, ctx)
    withheld = fields["system_view_withheld"]
    return ReviewCaseView(
        **fields,
        claims=_case_claims(db, case, withheld=withheld),
        pre_reveal=_pre_reveal_view(blind.pre_reveal_of(db, case.id, ownership.owner_id(user))),
        request=_request_info(db, case.job_id, ctx, withheld=withheld),
        validation_errors=[] if withheld else list(case.validation_errors or []),
        proposed_result=None if withheld else case.proposed_result,
        claim_severities=_blind_claim_severities(case.claim_severities) if withheld else case.claim_severities,
        policy_version=case.policy_version,
        pipeline_version=case.pipeline_version,
        audit_trail=[_audit(e, ctx, withheld=withheld) for e in trail],
    )


def _get_case(db: Session, review_id: str, user: dict) -> HumanReview:
    """The case if the caller may see its job (T33), else 404 like a missing one."""
    case = db.get(HumanReview, review_id)
    job = db.get(Job, case.job_id) if case is not None else None
    if case is None or job is None or not ownership.can_view_job(job, user):
        raise HTTPException(status_code=404, detail="review not found")
    return case


def _forbid_own(db: Session, case: HumanReview, user: dict) -> None:
    """Nobody decides a case on their own video (T33, §12): the submitter of the job or
    the owner of the video gets 403, whatever their role."""
    job = db.get(Job, case.job_id)
    video = db.get(Video, job.video_id) if job is not None else None
    if ownership.is_own(user, job, video):
        raise HTTPException(status_code=403, detail="you can't review your own video")


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
def me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> MeView:
    """Who the server thinks the caller is, and what their role allows (a hint for the
    UI; every action is checked again on the server)."""
    role = role_of(current_user)
    users_service.remember(db, current_user)
    email, name = users_service.profile_from_token(current_user)
    return MeView(
        user_id=user_id_of(current_user),
        email=email,
        display_name=name,
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
    users_service.remember(db, current_user)
    severities = [s.strip() for raw in (severity or []) for s in raw.split(",") if s.strip()]
    try:
        cases, total = rs.review_queue_page(
            db, status=None if status == "ALL" else status, severities=severities or None,
            reason=reason, limit=limit, offset=offset,
            visible_jobs=lambda q: ownership.visible_jobs(q, current_user),
            # T34: the reason filter must not reveal reasons of cases the caller is blind to.
            hide_reasons=lambda c: blind.is_blind(db, c, current_user),
        )
    except rs.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    ctx = _Ctx(db, current_user, _ids_for(db, cases))
    return ReviewQueuePage(
        items=[ReviewQueueItem(**_item_fields(db, c, now, ctx)) for c in cases],
        total=total, limit=limit, offset=offset,
    )


@router.get("/reviews/{review_id}", response_model=ReviewCaseView)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
) -> ReviewCaseView:
    """One case with its audit trail. On an open HIGH case the system's view is withheld
    until the caller has posted their own judgement to ``/pre-reveal`` (T34)."""
    users_service.remember(db, current_user)
    return _case_view(db, _get_case(db, review_id, current_user), current_user)


@router.get("/reviews/{review_id}/blind-material", response_model=blind_mat.BlindMaterialResponse)
def blind_material(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
) -> blind_mat.BlindMaterialResponse:
    """What a blind reviewer judges from on a HIGH case (D7 Q1, T40): the claims (text,
    category, times, quoted segment ids), the transcript and on-screen text with
    timestamps, and every paper or reference retrieval put in front of the verifier, in
    retrieval order, with no relation, citation, verdict, stance, label, reasons, critic
    notes or confidence (``app.services.blind_material``). Only while the caller is blind
    on the case: anyone else gets 403 ``BLIND_STEP_NOT_ACTIVE`` and uses the case and
    result routes. Analysts 403 before lookup; a case the caller may not see is 404."""
    users_service.remember(db, current_user)
    case = _get_case(db, review_id, current_user)
    if not blind.is_blind(db, case, current_user):
        raise HTTPException(status_code=403, detail={
            "code": blind_mat.NOT_BLIND,
            "review_id": case.id,
            "message": "blind material is only for a reviewer who has not yet recorded their "
                       "own judgement on an open HIGH-severity case",
        })
    return blind_mat.blind_material(db, case)


@router.post("/reviews/{review_id}/pre-reveal", response_model=ReviewCaseView, status_code=201)
def pre_reveal(
    review_id: str,
    payload: PreRevealRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_reviewer),
) -> ReviewCaseView:
    """The blind step (D7, T34): record the caller's own stance and verdict for every
    claim of an open HIGH case, timed by the server, before they see the system's. Answers
    with the full case view. One per reviewer per case (409 on a second); 409 on a case
    that doesn't need the step or is resolved; 403 on your own video; logged to the
    audit trail."""
    users_service.remember(db, current_user)
    case = _get_case(db, review_id, current_user)
    _forbid_own(db, case, current_user)
    try:
        blind.record_pre_reveal(
            db, case, reviewer_id=user_id_of(current_user),
            claims=[c.model_dump(mode="json") for c in payload.claims], note=payload.note,
        )
    except blind.PreRevealError as exc:
        db.rollback()
        msg = str(exc)
        if msg.startswith("conflict: "):
            raise HTTPException(status_code=409, detail=msg[len("conflict: "):]) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    db.refresh(case)
    return _case_view(db, case, current_user)


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
    users_service.remember(db, current_user)
    case = _get_case(db, review_id, current_user)
    _forbid_own(db, case, current_user)
    if case.status != ReviewCaseStatus.OPEN:
        raise HTTPException(status_code=409, detail="review is already resolved")
    # T34: reason code; pre-T34 clients send none → OTHER, flagged in the audit event.
    details: dict[str, Any] = {}
    code = payload.reason_code
    if code is None:
        code = ReviewReasonCode.OTHER
        details["reason_code_defaulted"] = True
    if code == ReviewReasonCode.SYSTEM_CORRECT and payload.action != ReviewAction.APPROVE:
        raise HTTPException(status_code=422, detail="SYSTEM_CORRECT goes only with APPROVE")
    # T34: the blind step. A HIGH case needs this reviewer's own judgement first.
    if blind.requires_blind_step(case):
        pre = blind.pre_reveal_of(db, case.id, reviewer_id)
        if pre is None:
            raise HTTPException(status_code=409, detail={
                "code": blind.PRE_REVEAL_REQUIRED,
                "message": "this is a HIGH-severity case: record your own judgement with "
                           f"POST /v1/reviews/{case.id}/pre-reveal before deciding",
            })
        details.update(pre_reveal_id=pre.id, pre_reveal_at=_utc(pre.created_at).isoformat(),
                       pre_reveal_agreement=blind.agreement(db, case, pre))
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
            reason_code=code.value,
            audit_details=details,
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
    return DecisionResponse(case=_case_view(db, case, current_user), reanalysis_job=reanalysis)


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
    users_service.remember(db, current_user)
    _forbid_own(db, _get_case(db, review_id, current_user), current_user)
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
    return _case_view(db, case, current_user)


@router.post("/jobs/{job_id}/review-request", response_model=ReviewRequestResponse,
             responses={200: {"description": "the job already had a review case; that case is returned"},
                        201: {"description": "a review case was opened"}},
             status_code=201)
def request_review(
    job_id: str,
    payload: ReviewRequestBody,
    response: Response,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ReviewRequestResponse:
    """Ask for a person to check a result the review rule didn't send to review (§12;
    T32). Allowed for the job's owner and for reviewers and admins: access goes through
    ``app.api.ownership`` like every result read, so anyone else gets 404. A note is
    required. Opens a case with the reason ``user_requested`` and logs the request (who,
    when, the note) to the audit trail. If the job already has a case, opened by the
    review rule or by an earlier request, that case is returned with 200 and nothing
    changes. A job with no finished result answers 409."""
    requester_id = user_id_of(current_user)
    users_service.remember(db, current_user)
    job = owned_job_or_404(db, job_id, current_user)
    try:
        case, created = rs.request_review(
            db, job, requester_id=requester_id, note=payload.note,
            requester_role=role_of(current_user).value,
        )
    except rs.ReviewError as exc:
        db.rollback()
        msg = str(exc)
        if "no finished result" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=422, detail=msg) from exc
    if not created:
        response.status_code = 200
    db.refresh(job)
    return ReviewRequestResponse(
        created=created,
        review_id=case.id,
        job_id=case.job_id,
        job_status=job.status.value if job.status is not None else None,
        case_status=case.status,
        reasons=list(case.reasons or []),
        reason_details=parse_reasons(case.reasons),
        # Names only for an analyst requester (users_service.person): never another's email.
        request=_request_info(db, case.job_id, _Ctx(db, current_user)),
        created_at=_utc(case.created_at),
    )
