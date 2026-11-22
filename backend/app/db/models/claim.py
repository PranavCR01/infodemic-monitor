"""Claim-level results of the graph pipeline (target design §17; T11, issue #38).

One set of rows per job, written in the same transaction as the video-level ``results``
row. All rows are keyed by ``job_id`` (and the graph's own ``claim_id`` /
``evidence_id``), so a re-run of the same job replaces them instead of adding a second
copy (Celery delivers at least once, §1).

Tables follow §17: ``transcript_segments``, ``ocr_segments``, ``claims``,
``claim_stances``, ``evidence_records``, ``claim_evidence``, ``verification_results``,
``critic_reviews``, ``model_runs``. Deviations, recorded in context/MULTI_AGENT.md §7k:
evidence records are per job (not shared across jobs), and the video-level
classification stays in the existing ``results`` table rather than a new
``classifications`` table.

Enums (stance, verdict, decision) are stored as short strings, like ``results.label``,
and validated by the graph's Pydantic records before they get here.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptSegmentRow(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("job_id", "segment_id", name="uq_transcript_segments_job_segment"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True, nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class OcrSegmentRow(Base):
    __tablename__ = "ocr_segments"
    __table_args__ = (UniqueConstraint("job_id", "segment_id", name="uq_ocr_segments_job_segment"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True, nullable=False)
    segment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class ClaimRow(Base):
    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("job_id", "claim_id", name="uq_claims_job_claim"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True, nullable=False)
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    source_segment_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    requires_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # §4 (T17, migration 0009): research_question / fact_of_record. Null on rows
    # written before 0009.
    claim_kind: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # The §9 rules applied to this one claim (judge.claim_label); None = no verdict.
    label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    deciding: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    stance: Mapped[Optional["ClaimStanceRow"]] = relationship(
        back_populates="claim", uselist=False, cascade="all, delete-orphan")
    verification: Mapped[Optional["VerificationResultRow"]] = relationship(
        back_populates="claim", uselist=False, cascade="all, delete-orphan")
    critic: Mapped[Optional["CriticReviewRow"]] = relationship(
        back_populates="claim", uselist=False, cascade="all, delete-orphan")
    evidence_links: Mapped[list["ClaimEvidenceRow"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan")


class ClaimStanceRow(Base):
    __tablename__ = "claim_stances"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    claim_pk: Mapped[str] = mapped_column(String, ForeignKey("claims.id", ondelete="CASCADE"),
                                          unique=True, nullable=False)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    segment_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    claim: Mapped[ClaimRow] = relationship(back_populates="stance")


class EvidenceRecordRow(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (UniqueConstraint("job_id", "evidence_id", name="uq_evidence_records_job_evidence"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True, nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    pmid: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    publication_type: Mapped[list] = mapped_column(JSON, nullable=False)
    publication_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    study_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Authoritative references (T17, migration 0009). The full fetched text is in
    # ``reference_snapshots`` under ``snapshot_sha256``.
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    retrieved_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    snapshot_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ReferenceSnapshotRow(Base):
    """The text of an authoritative reference page as fetched (§6: "Pages change, so a
    snapshot of the fetched text is stored with its hash"). One row per distinct text,
    shared across jobs: the SHA-256 of the text is the key, so identical text is
    stored once and a changed page gets a new row. T17, migration 0009."""

    __tablename__ = "reference_snapshots"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClaimEvidenceRow(Base):
    """Which paper relates to which claim, and how (§17 ``claim_evidence``).
    ``relation``: SUPPORTS / CONTRADICTS (cited by the verifier) or CONSIDERED (shown
    to the verifier, not cited)."""

    __tablename__ = "claim_evidence"
    __table_args__ = (UniqueConstraint("claim_pk", "evidence_pk", name="uq_claim_evidence_pair"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    claim_pk: Mapped[str] = mapped_column(String, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    evidence_pk: Mapped[str] = mapped_column(String, ForeignKey("evidence_records.id", ondelete="CASCADE"),
                                             nullable=False)
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    claim: Mapped[ClaimRow] = relationship(back_populates="evidence_links")
    evidence: Mapped[EvidenceRecordRow] = relationship()


class VerificationResultRow(Base):
    __tablename__ = "verification_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    claim_pk: Mapped[str] = mapped_column(String, ForeignKey("claims.id", ondelete="CASCADE"),
                                          unique=True, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    raw_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieval_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    claim: Mapped[ClaimRow] = relationship(back_populates="verification")


class CriticReviewRow(Base):
    __tablename__ = "critic_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    claim_pk: Mapped[str] = mapped_column(String, ForeignKey("claims.id", ondelete="CASCADE"),
                                          unique=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    issues: Mapped[list] = mapped_column(JSON, nullable=False)
    checks: Mapped[list] = mapped_column(JSON, nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    claim: Mapped[ClaimRow] = relationship(back_populates="critic")


class ModelRunRow(Base):
    """One routed model call (§13 ``CallRecord``; §17 ``model_runs``)."""

    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


CLAIM_LEVEL_MODELS = (
    TranscriptSegmentRow, OcrSegmentRow, ClaimRow, ClaimStanceRow, EvidenceRecordRow,
    ClaimEvidenceRow, VerificationResultRow, CriticReviewRow, ModelRunRow,
)
