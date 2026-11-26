"""Human review cases (target design §12, §17 ``human_reviews``; issue #36).

One row per job sent to review. It records why the case was escalated (the review
rule's reasons, which rule fired), the proposed result the reviewer is asked to check,
and, once a reviewer acts, who did what, when and why. Review is a durable state of
the job (``JobStatus.REVIEW_REQUIRED``), not a flag in a checkpoint.
"""
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewCaseStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    # T55: the video was deliberately re-analysed while this case was open. The case
    # leaves the queue without a decision; ``superseded_by_job_id`` names the new job,
    # whose result goes through the review rule (§11) from scratch.
    SUPERSEDED = "SUPERSEDED"


class ReviewAction(str, enum.Enum):
    """What a reviewer can do (§12)."""

    APPROVE = "APPROVE"
    CORRECT = "CORRECT"
    MARK_INSUFFICIENT = "MARK_INSUFFICIENT"
    REQUEST_REANALYSIS = "REQUEST_REANALYSIS"
    REJECT = "REJECT"


class ReviewReasonCode(str, enum.Enum):
    """Why the reviewer decided as they did (D7, T34): stored next to the written note
    so overturn rates can be counted per kind of system error."""

    CLAIM_OVERGENERALISED = "CLAIM_OVERGENERALISED"
    EVIDENCE_MISREAD = "EVIDENCE_MISREAD"
    STANCE_MISREAD = "STANCE_MISREAD"
    MISSING_SOURCE = "MISSING_SOURCE"
    SYSTEM_CORRECT = "SYSTEM_CORRECT"
    OTHER = "OTHER"


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), unique=True, nullable=False)
    status: Mapped[ReviewCaseStatus] = mapped_column(
        SAEnum(ReviewCaseStatus, name="reviewcasestatus"), default=ReviewCaseStatus.OPEN, nullable=False
    )
    # Why the case was escalated: the review rule's reasons, and per rule which reasons
    # it gave (for the per-rule review counts and overturn rates, §12).
    reasons: Mapped[list] = mapped_column(JSON, nullable=False)
    rules_fired: Mapped[list] = mapped_column(JSON, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    proposed_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    proposed_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Filled in when a reviewer acts. Every action records who, when and why (§12).
    reviewer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[Optional[ReviewAction]] = mapped_column(
        SAEnum(ReviewAction, name="reviewaction"), nullable=True
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # T34 (migration 0016): a ``ReviewReasonCode`` value; NULL on decisions made before.
    reason_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    corrected_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    corrections: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Review priority (§12 "Severity", T22). Orders the queue; never changes a label or
    # verdict. ``severity`` is the video's effective severity (HIGH / MEDIUM / LOW, or
    # null when no claim is MISINFO-relevant); ``claim_severities`` holds each claim's
    # table severity, its basis and any reviewer override. Null on cases opened before
    # migration 0010.
    severity: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, index=True)
    claim_severities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    severity_table_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # T55 (migration 0017): set when the case is SUPERSEDED by a re-analysis.
    superseded_by_job_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("jobs.id"), nullable=True
    )


class AuditEvent(Base):
    """Who did what to which record, and when (§17 ``audit_events``). T22 writes
    reviewer severity overrides here; other actions can use it too."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    job_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("jobs.id"), nullable=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ReviewPreReveal(Base):
    """A reviewer's own judgement of a HIGH-severity case, recorded before the server
    shows them the system's stances and verdicts (D7 blind step, T34). One per reviewer
    per case; never edited. ``claims`` is ``{claim_id: {"stance", "verdict"}}``;
    ``created_at`` is the server's clock."""

    __tablename__ = "review_pre_reveals"
    __table_args__ = (UniqueConstraint("review_id", "reviewer_id", name="uq_pre_reveal_review_reviewer"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(String, ForeignKey("human_reviews.id"), nullable=False, index=True)
    reviewer_id: Mapped[str] = mapped_column(String, nullable=False)
    claims: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    case_severity: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
