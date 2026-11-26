"""Persisting human-review cases (target design §12; issue #36).

``open_review_case`` is what the graph's ``persist_result`` step calls (T11) when the
review rule sent a run to a person: the job moves to ``REVIEW_REQUIRED`` and a
``human_reviews`` row records the reasons, which rules fired, any validation failures
and the proposed result. ``record_review_decision`` records what a reviewer did (who,
when, why). A reviewer UI and API endpoint are out of scope for T09.

Severity (§12, T22): ``open_review_case`` also stores each claim's severity and the
video's severity; ``review_queue`` lists cases by severity, then age;
``override_claim_severity`` lets a reviewer change one claim's severity with a reason,
logged to ``audit_events``. None of these touch the label, the verdicts, the proposed
result or the job's state.

Nothing on the single-call path calls these functions.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from sqlalchemy import case as sql_case
from sqlalchemy.orm import Session

from app.core.schemas.pipeline import MisinfoLabel
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.review import AuditEvent, HumanReview, ReviewAction, ReviewCaseStatus


REVIEW_DECISION_ACTION = "review_decision"
REANALYSIS_ACTION = "reanalysis_started"


class ReviewError(ValueError):
    """A review action that isn't allowed (missing reason, case already resolved, ...)."""


def _rules_fired(reasons: list[str]) -> list[dict[str, Any]]:
    from app.core.graph.review_policy import rule_of

    by_rule: dict[str, list[str]] = defaultdict(list)
    for reason in reasons:
        by_rule[rule_of(reason)].append(reason)
    return [{"rule": k, "reasons": v} for k, v in by_rule.items()]


def review_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    """The fields of a review case, taken from a finished graph state."""
    from app.core.graph.review_policy import default_review_policy
    from app.core.graph.severity import assess

    final = state.get("final_result")
    reasons = list(state.get("review_reasons") or [])
    sev = assess(state)
    return {
        "severity": sev.severity.value if sev.severity else None,
        "claim_severities": sev.claims,
        "severity_table_version": sev.table_version,
        "reasons": reasons,
        "rules_fired": _rules_fired(reasons),
        "validation_errors": list(state.get("validation_errors") or []),
        "proposed_label": final.classification.value if final is not None else None,
        "proposed_result": final.model_dump(mode="json") if final is not None else None,
        "policy_version": default_review_policy().version,
        "pipeline_version": state.get("pipeline_version"),
    }


def open_review_case(db: Session, job_id: str, state: Mapping[str, Any]) -> HumanReview:
    """Move the job to ``REVIEW_REQUIRED`` and record why. Idempotent per job: a
    re-run (e.g. a resumed graph) refreshes the open case instead of adding one."""
    if not state.get("requires_human_review"):
        raise ReviewError("the review rule did not send this run to review")
    job = db.get(Job, job_id)
    if job is None:
        raise ReviewError(f"job {job_id!r} not found")
    payload = review_payload(state)
    case = db.query(HumanReview).filter(HumanReview.job_id == job_id).one_or_none()
    if case is None:
        case = HumanReview(job_id=job_id, status=ReviewCaseStatus.OPEN, **payload)
        db.add(case)
    elif case.status == ReviewCaseStatus.OPEN:
        _keep_overrides(case.claim_severities, payload)
        for k, v in payload.items():
            setattr(case, k, v)
    else:
        raise ReviewError(f"review for job {job_id!r} is already resolved")
    job.status = JobStatus.REVIEW_REQUIRED
    db.commit()
    db.refresh(case)
    return case


def record_review_decision(
    db: Session,
    review_id: str,
    *,
    reviewer_id: str,
    action: ReviewAction | str,
    reason: str,
    corrected_label: Optional[str] = None,
    corrections: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
    reason_code: Optional[str] = None,
    audit_details: Optional[Mapping[str, Any]] = None,
) -> HumanReview:
    """Record a reviewer's action (§12). Every action needs a reviewer and a written
    reason. ``reason_code`` (T34, a ``ReviewReasonCode``) is stored on the case and in
    the audit event; ``audit_details`` are added to the audit event (e.g. the blind
    pre-reveal it followed). Job state afterwards:

    - APPROVE → SUCCESS (the proposed result stands);
    - CORRECT → SUCCESS with ``corrected_label`` and/or per-claim ``corrections``
      recorded; a stored ``Result`` row takes the corrected label;
    - MARK_INSUFFICIENT → SUCCESS with the label CANNOT_RECOGNIZE;
    - REJECT → FAILED, ``error_code = REVIEW_REJECTED``;
    - REQUEST_REANALYSIS → stays REVIEW_REQUIRED; the caller starts a new job.

    Corrections are not fed back into prompts or models (§12 "feedback loop"); they are
    candidate evaluation examples only.
    """
    action = ReviewAction(action)
    if reason_code is not None:
        from app.db.models.review import ReviewReasonCode

        try:
            reason_code = ReviewReasonCode(reason_code).value
        except ValueError:
            raise ReviewError(f"unknown reason_code {reason_code!r}") from None
    if not reviewer_id:
        raise ReviewError("reviewer_id is required")
    if not (reason or "").strip():
        raise ReviewError("a written reason is required for every review action")
    # Lock the row (Postgres) so two reviewers deciding at once can't both resolve it.
    case = (
        db.query(HumanReview).filter(HumanReview.id == review_id).with_for_update().one_or_none()
    )
    if case is None:
        raise ReviewError(f"review {review_id!r} not found")
    if case.status != ReviewCaseStatus.OPEN:
        raise ReviewError("review is already resolved")

    if corrected_label is not None:
        corrected_label = MisinfoLabel(corrected_label).value  # raises on an unknown label
    if action == ReviewAction.CORRECT and corrected_label is None and not corrections:
        raise ReviewError("CORRECT needs a corrected label or claim corrections")
    if action == ReviewAction.MARK_INSUFFICIENT:
        corrected_label = MisinfoLabel.CANNOT_RECOGNIZE.value
    if action not in (ReviewAction.CORRECT, ReviewAction.MARK_INSUFFICIENT) and (corrected_label or corrections):
        raise ReviewError(f"{action.value} does not take corrections")

    case.reviewer_id = reviewer_id
    case.action = action
    case.decision_reason = reason.strip()
    case.reason_code = reason_code
    case.corrected_label = corrected_label
    case.corrections = corrections
    case.decided_at = now or datetime.now(timezone.utc)
    case.status = ReviewCaseStatus.RESOLVED

    job = db.get(Job, case.job_id)
    if job is not None:
        if action in (ReviewAction.APPROVE, ReviewAction.CORRECT, ReviewAction.MARK_INSUFFICIENT):
            job.status = JobStatus.SUCCESS
            if corrected_label:
                result = db.query(Result).filter(Result.job_id == job.id).one_or_none()
                if result is not None:
                    result.label = corrected_label
        elif action == ReviewAction.REJECT:
            job.status = JobStatus.FAILED
            job.error_code = "REVIEW_REJECTED"
    # Every action records who, when and why (§12), in the shared audit log too (T27).
    db.add(AuditEvent(
        actor_id=reviewer_id,
        action=REVIEW_DECISION_ACTION,
        entity_type="human_review",
        entity_id=case.id,
        job_id=case.job_id,
        reason=case.decision_reason,
        details={
            "review_id": case.id,
            "decision": action.value,
            "reason_code": reason_code,
            "proposed_label": case.proposed_label,
            "corrected_label": corrected_label,
            "corrections": corrections,
            **dict(audit_details or {}),
        },
        created_at=case.decided_at,
    ))
    db.commit()
    if job is not None:
        # T28: log the job's new §1 state (COMPLETED or REJECTED) in its history.
        from app.services.job_events import sync_state_from_status

        sync_state_from_status(db, job, detail={"review_id": case.id, "action": action.value})
    db.refresh(case)
    return case


# ------------------------------------------------------------------ severity (T22)

SEVERITY_OVERRIDE_ACTION = "severity_override"


def _keep_overrides(old: Optional[dict], payload: dict[str, Any]) -> None:
    """A refreshed case keeps reviewers' overrides for claims that are still there."""
    from app.core.graph.severity import video_severity

    new = payload.get("claim_severities") or {}
    for cid, entry in (old or {}).items():
        if entry.get("override") and cid in new:
            new[cid]["override"] = entry["override"]
    sev = video_severity(new)
    payload["severity"] = sev.value if sev else None


def _severity_order():
    """HIGH, MEDIUM, LOW, then cases with no severity."""
    return sql_case(
        (HumanReview.severity == "HIGH", 0),
        (HumanReview.severity == "MEDIUM", 1),
        (HumanReview.severity == "LOW", 2),
        else_=3,
    )


def review_queue(
    db: Session,
    *,
    status: Optional[ReviewCaseStatus | str] = ReviewCaseStatus.OPEN,
    limit: Optional[int] = None,
) -> list[HumanReview]:
    """Review cases by severity first (HIGH first), then age (oldest first) (§12).
    ``status=None`` lists every case."""
    q = db.query(HumanReview)
    if status is not None:
        q = q.filter(HumanReview.status == ReviewCaseStatus(status))
    q = q.order_by(_severity_order(), HumanReview.created_at.asc(), HumanReview.id.asc())
    if limit is not None:
        q = q.limit(limit)
    return q.all()


def override_claim_severity(
    db: Session,
    review_id: str,
    claim_id: str,
    *,
    reviewer_id: str,
    severity: str,
    reason: str,
    now: Optional[datetime] = None,
) -> HumanReview:
    """A reviewer changes one claim's severity, with a written reason (§12). The case's
    video severity is recomputed from the effective claim severities, and the change is
    logged to ``audit_events`` (who, when, why, from what to what) so the table can be
    corrected from real cases. Labels, verdicts, the proposed result, the reviewer
    decision and the job's state are not touched. Allowed on resolved cases too: the
    log is for correcting the table, not only for ordering the queue."""
    from app.core.graph.severity import Severity, effective_claim_severity, video_severity

    if not reviewer_id:
        raise ReviewError("reviewer_id is required")
    if not (reason or "").strip():
        raise ReviewError("a written reason is required for a severity override")
    try:
        new_level = Severity(str(severity).upper()).value
    except ValueError:
        raise ReviewError(f"unknown severity {severity!r}; use HIGH, MEDIUM or LOW") from None
    case = db.get(HumanReview, review_id)
    if case is None:
        raise ReviewError(f"review {review_id!r} not found")
    claims = copy.deepcopy(case.claim_severities or {})
    if claim_id not in claims:
        raise ReviewError(f"claim {claim_id!r} is not part of review {review_id!r}")

    entry = claims[claim_id]
    previous = effective_claim_severity(entry)
    if previous == new_level:
        raise ReviewError(f"claim {claim_id!r} already has severity {new_level}")
    at = now or datetime.now(timezone.utc)
    entry["override"] = {
        "severity": new_level, "reason": reason.strip(), "reviewer_id": reviewer_id, "at": at.isoformat(),
    }
    video_before = case.severity
    video_after = video_severity(claims)
    case.claim_severities = claims  # reassign so the JSON change is saved
    case.severity = video_after.value if video_after else None
    db.add(AuditEvent(
        actor_id=reviewer_id,
        action=SEVERITY_OVERRIDE_ACTION,
        entity_type="claim",
        entity_id=f"{case.job_id}:{claim_id}",
        job_id=case.job_id,
        reason=reason.strip(),
        details={
            "review_id": case.id,
            "claim_id": claim_id,
            "table_severity": entry.get("severity"),
            "basis": entry.get("basis"),
            "from": previous,
            "to": new_level,
            "video_severity_before": video_before,
            "video_severity_after": case.severity,
            "severity_table_version": case.severity_table_version,
        },
        created_at=at,
    ))
    db.commit()
    db.refresh(case)
    return case


def severity_overrides(db: Session, *, job_id: Optional[str] = None) -> list[AuditEvent]:
    """The severity-override log, oldest first (for correcting the table)."""
    q = db.query(AuditEvent).filter(AuditEvent.action == SEVERITY_OVERRIDE_ACTION)
    if job_id is not None:
        q = q.filter(AuditEvent.job_id == job_id)
    return q.order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc()).all()


# ------------------------------------------------------------------ review API (T27)

SEVERITY_FILTERS = ("HIGH", "MEDIUM", "LOW", "NONE")


def _matches_reason(case: HumanReview, wanted: str) -> bool:
    """A case matches a reason filter if any stored reason is that exact reason, starts
    with ``<wanted>:`` (e.g. ``weak_evidence`` matches ``weak_evidence:c1``), or came from
    the rule called ``wanted`` (e.g. ``judge_flags`` matches ``judge:mixed_video``)."""
    from app.core.graph.review_policy import rule_of

    for reason in case.reasons or []:
        if reason == wanted or reason.startswith(wanted + ":") or rule_of(reason) == wanted:
            return True
    return False


def review_queue_page(
    db: Session,
    *,
    status: Optional[ReviewCaseStatus | str] = ReviewCaseStatus.OPEN,
    severities: Optional[list[str]] = None,
    reason: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    visible_jobs: Optional[Callable] = None,
    hide_reasons: Optional[Callable[[HumanReview], bool]] = None,
) -> tuple[list[HumanReview], int]:
    """One page of the queue, in queue order (severity, then age), and the total that
    match. ``severities`` takes HIGH / MEDIUM / LOW and NONE (no MISINFO-relevant claim).
    The reason filter runs in Python because reasons are a JSON list (portable across
    SQLite and Postgres); the severity and status filters run in SQL.
    ``visible_jobs`` (T33) restricts a query over ``Job`` to the jobs the caller may see
    (``app.api.ownership.visible_jobs`` bound to the caller); cases on other jobs are
    left out of the page and the total.
    ``hide_reasons`` (T34) marks cases whose reasons the caller may not see yet (the blind
    step); a reason filter never matches them, so it can't be used to probe them."""
    q = db.query(HumanReview)
    if visible_jobs is not None:
        q = visible_jobs(q.join(Job, Job.id == HumanReview.job_id))
    if status is not None:
        q = q.filter(HumanReview.status == ReviewCaseStatus(status))
    if severities:
        wanted = {s.upper() for s in severities}
        unknown = wanted - set(SEVERITY_FILTERS)
        if unknown:
            raise ReviewError(f"unknown severity filter {sorted(unknown)}; use HIGH, MEDIUM, LOW or NONE")
        levels = [s for s in wanted if s != "NONE"]
        conds = []
        if levels:
            conds.append(HumanReview.severity.in_(levels))
        if "NONE" in wanted:
            conds.append(HumanReview.severity.is_(None))
        from sqlalchemy import or_

        q = q.filter(or_(*conds))
    q = q.order_by(_severity_order(), HumanReview.created_at.asc(), HumanReview.id.asc())
    if reason:
        matching = [c for c in q.all()
                    if not (hide_reasons is not None and hide_reasons(c)) and _matches_reason(c, reason)]
        return matching[offset: offset + limit], len(matching)
    total = q.order_by(None).count()
    return q.offset(offset).limit(limit).all(), total


def claim_ids_of(db: Session, case: HumanReview) -> dict[str, dict[str, Optional[str]]]:
    """The claims a reviewer can correct, with the stance and verdict the run gave them.
    Taken from the case's severity entries (T22); for cases opened before migration
    0010, from the stored claim rows (T11)."""
    if case.claim_severities:
        return {
            cid: {"stance": e.get("stance"), "verdict": e.get("verdict")}
            for cid, e in case.claim_severities.items()
        }
    from app.db.models.claim import ClaimRow

    rows = db.query(ClaimRow).filter(ClaimRow.job_id == case.job_id).all()
    out: dict[str, dict[str, Optional[str]]] = {}
    for row in rows:
        out[row.claim_id] = {
            "stance": row.stance.stance if row.stance is not None else None,
            "verdict": row.verification.verdict if row.verification is not None else None,
        }
    return out


def build_claim_corrections(
    db: Session, case: HumanReview, items: list[Mapping[str, Any]]
) -> Optional[dict[str, Any]]:
    """Check and normalise a reviewer's per-claim corrections (§12: "correct a claim's
    verdict, its stance"). Each item names a claim of this case and a new verdict and/or
    stance from the fixed sets. Stored as ``{"claims": {cid: {"verdict": {"from", "to"},
    "stance": {"from", "to"}}}}`` so the change can become a candidate evaluation example.
    The model's original outputs are not overwritten."""
    from app.core.graph.state import Stance, Verdict

    if not items:
        return None
    known = claim_ids_of(db, case)
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        cid = str(item.get("claim_id") or "")
        if cid not in known:
            raise ReviewError(f"claim {cid!r} is not part of review {case.id!r}")
        if cid in out:
            raise ReviewError(f"claim {cid!r} is corrected twice")
        entry: dict[str, Any] = {}
        for field_name, enum_cls in (("verdict", Verdict), ("stance", Stance)):
            value = item.get(field_name)
            if value is None:
                continue
            try:
                new = enum_cls(str(value).upper()).value
            except ValueError:
                allowed = ", ".join(e.value for e in enum_cls)
                raise ReviewError(f"unknown {field_name} {value!r}; use one of {allowed}") from None
            old = known[cid].get(field_name)
            if new == old:
                raise ReviewError(f"claim {cid!r} already has {field_name} {new}")
            entry[field_name] = {"from": old, "to": new}
        if not entry:
            raise ReviewError(f"correction for claim {cid!r} changes neither verdict nor stance")
        out[cid] = entry
    return {"claims": out}


def review_audit_trail(db: Session, job_id: str) -> list[AuditEvent]:
    """Every audit event for a job's review, oldest first: decisions, severity
    overrides and re-analysis requests."""
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.job_id == job_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )


def start_reanalysis(
    db: Session,
    case: HumanReview,
    *,
    reviewer_id: str,
    dispatch: Any,
    now: Optional[datetime] = None,
) -> Job:
    """After REQUEST_REANALYSIS: start a new job for the same video (the old job keeps
    its REVIEW_REQUIRED state and resolved case, T09) and log it. ``dispatch(job_id,
    storage_key)`` queues the work and returns a task id; if it fails, the new job is
    marked FAILED with ``DISPATCH_FAILED`` (the decision still stands) and returned."""
    import uuid

    from app.db.models.video import Video

    if case.action != ReviewAction.REQUEST_REANALYSIS:
        raise ReviewError("re-analysis follows a REQUEST_REANALYSIS decision")
    old = db.get(Job, case.job_id)
    if old is None:
        raise ReviewError(f"job {case.job_id!r} not found")
    video = db.get(Video, old.video_id)
    # T28: the re-run belongs to whoever owned the original job, not the reviewer, so it
    # shows up in that user's job list.
    new_job = Job(id=str(uuid.uuid4()), video_id=old.video_id, status=JobStatus.PENDING,
                  user_id=old.user_id, previous_job_id=old.id)  # T55: linked to the reviewed job
    db.add(new_job)
    db.add(AuditEvent(
        actor_id=reviewer_id,
        action=REANALYSIS_ACTION,
        entity_type="job",
        entity_id=new_job.id,
        job_id=case.job_id,
        reason=case.decision_reason,
        details={"review_id": case.id, "previous_job_id": case.job_id, "new_job_id": new_job.id},
        created_at=now or datetime.now(timezone.utc),
    ))
    db.commit()
    from app.core.progress import UPLOADED
    from app.db.models.job import JobState
    from app.services.job_events import record_state, sync_state_from_status

    record_state(db, new_job, JobState.PENDING, step=UPLOADED,
                 detail={"reason": "reanalysis", "previous_job_id": case.job_id, "review_id": case.id})
    record_state(db, new_job, JobState.QUEUED)
    try:
        new_job.celery_task_id = dispatch(new_job.id, video.storage_key if video else None)
    except Exception as exc:  # broker down, etc.
        import logging

        logging.getLogger(__name__).warning("re-analysis dispatch failed for job %s: %s", new_job.id, exc)
        new_job.status = JobStatus.FAILED
        new_job.error_code = "DISPATCH_FAILED"
    db.commit()
    sync_state_from_status(db, new_job, detail={"error_code": new_job.error_code} if new_job.error_code else None)
    db.refresh(new_job)
    return new_job


# ------------------------------------------------------------------ request review (T32)

REVIEW_REQUESTED_ACTION = "review_requested"
REQUEST_NOTE_MAX = 2000


def _stored_claim_severities(db: Session, job_id: str) -> tuple[Optional[dict[str, Any]], Optional[str], str]:
    """Severity of a finished job's claims from its stored rows (the same table and
    shape ``assess`` gives a graph case), so a requested case sorts in the queue like
    any other and its claims can be overridden. ``(None, None, version)`` when the job
    has no claim rows (the single-call path)."""
    from types import SimpleNamespace

    from app.core.graph.severity import claim_severity, default_severity_config, misinfo_relevant, video_severity
    from app.db.models.claim import ClaimRow

    cfg = default_severity_config()
    rows = db.query(ClaimRow).filter(ClaimRow.job_id == job_id).all()
    if not rows:
        return None, None, cfg.version
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        cs = claim_severity(SimpleNamespace(claim_id=row.claim_id, claim_text=row.text,
                                            claim_category=row.category), cfg)
        stance = row.stance.stance if row.stance is not None else None
        verdict = row.verification.verdict if row.verification is not None else None
        try:
            relevant = misinfo_relevant(stance, verdict)
        except ValueError:  # a stance or verdict this code doesn't know: don't guess
            relevant = False
        out[row.claim_id] = {
            "severity": cs.severity.value, "basis": list(cs.basis),
            "stance": stance, "verdict": verdict, "misinfo_relevant": relevant,
        }
    sev = video_severity(out)
    return out, (sev.value if sev else None), cfg.version


def _proposed_from_result(result: Result) -> dict[str, Any]:
    return {
        "classification": result.label,
        "confidence": result.confidence,
        "explanation": result.explanation,
        "decision_rule": result.decision_rule,
        "deciding_claim_ids": list(result.deciding_claim_ids or []),
        "pipeline": result.pipeline,
        "source": "stored_result",
    }


def review_request_event(db: Session, job_id: str) -> Optional[AuditEvent]:
    """The audit event of the request that opened a job's case, if a person asked."""
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.job_id == job_id, AuditEvent.action == REVIEW_REQUESTED_ACTION)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .first()
    )


def request_review(
    db: Session,
    job: Job,
    *,
    requester_id: str,
    note: str,
    requester_role: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[HumanReview, bool]:
    """Open a review case for a finished result the review rule didn't send to a
    person (§12; T32). Returns ``(case, created)``.

    - Idempotent per job: if the job already has a case (opened by the review rule or
      by an earlier request, open or resolved) that case is returned unchanged and
      nothing is logged.
    - Otherwise the job needs a stored result and status SUCCESS; the case records the
      reason ``user_requested``, the stored result as the proposed result, and each
      claim's severity from the stored rows; the job moves to ``REVIEW_REQUIRED`` (§12:
      review is a state); and the request (who, when, the note) goes to the audit
      trail. The label and verdicts are not touched.
    - The caller checks access (owner, or reviewer/admin) before calling this.
    """
    from sqlalchemy.exc import IntegrityError

    from app.core.graph.review_policy import USER_REQUESTED_REASON, default_review_policy

    if not requester_id:
        raise ReviewError("requester_id is required")
    note = (note or "").strip()
    if not note:
        raise ReviewError("a note is required to request a review")
    if len(note) > REQUEST_NOTE_MAX:
        raise ReviewError(f"the note is longer than {REQUEST_NOTE_MAX} characters")

    existing = db.query(HumanReview).filter(HumanReview.job_id == job.id).one_or_none()
    if existing is not None:
        return existing, False
    result = db.query(Result).filter(Result.job_id == job.id).one_or_none()
    if job.status != JobStatus.SUCCESS or result is None:
        raise ReviewError("this job has no finished result to review")

    claims, severity, table_version = _stored_claim_severities(db, job.id)
    reasons = [USER_REQUESTED_REASON]
    at = now or datetime.now(timezone.utc)
    status_before = job.status.value
    case = HumanReview(
        job_id=job.id,
        status=ReviewCaseStatus.OPEN,
        reasons=reasons,
        rules_fired=_rules_fired(reasons),
        validation_errors=[],
        proposed_label=result.label,
        proposed_result=_proposed_from_result(result),
        policy_version=default_review_policy().version,
        pipeline_version=result.pipeline_version,
        severity=severity,
        claim_severities=claims,
        severity_table_version=table_version,
        created_at=at,
    )
    db.add(case)
    try:
        db.flush()
    except IntegrityError:
        # Another request (or the pipeline) opened the case first: return that one.
        db.rollback()
        existing = db.query(HumanReview).filter(HumanReview.job_id == job.id).one_or_none()
        if existing is None:
            raise
        return existing, False
    job.status = JobStatus.REVIEW_REQUIRED
    db.add(AuditEvent(
        actor_id=requester_id,
        action=REVIEW_REQUESTED_ACTION,
        entity_type="human_review",
        entity_id=case.id,
        job_id=job.id,
        reason=note,
        details={
            "review_id": case.id,
            "requester_role": requester_role,
            "job_status_before": status_before,
            "proposed_label": result.label,
        },
        created_at=at,
    ))
    db.commit()
    db.refresh(case)
    return case, True
