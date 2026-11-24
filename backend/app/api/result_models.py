"""Typed response models for the result API (target design §12, §17; T26).

Every field the existing ``GET /jobs/{job_id}/result`` returned is kept with the same
name and meaning; T26's fields are additions. The current frontend reads ``review`` as
``{status, reasons: string[]} | null`` and ``claims[].evidence[]`` with
``evidence_id/title/pmid/url/study_type/relation``; those keep their shape.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.core.schemas.search_trail import SearchTrailView
from app.services.review_reasons import ReasonView

Modality = Literal["speech", "screen", "both"]
SourceKind = Literal["pubmed", "reference", "library", "other"]
# OPEN case → REVIEW_REQUIRED (what the current frontend checks). Resolved cases:
# APPROVE → VERIFIED; CORRECT / MARK_INSUFFICIENT → CORRECTED; REJECT → REJECTED;
# REQUEST_REANALYSIS → REANALYSIS_REQUESTED.
ReviewStatus = Literal["REVIEW_REQUIRED", "VERIFIED", "CORRECTED", "REJECTED", "REANALYSIS_REQUESTED"]


class SegmentView(BaseModel):
    """A transcript (speech) or OCR (screen) segment with its timestamps."""

    segment_id: str
    source: Literal["speech", "screen"]
    start_seconds: float
    end_seconds: float
    text: str
    confidence: Optional[float] = None  # OCR only


class EvidenceView(BaseModel):
    # unchanged fields (T11)
    evidence_id: str
    title: str
    pmid: Optional[str] = None
    url: Optional[str] = None
    study_type: Optional[str] = None
    relation: str  # SUPPORTS | CONTRADICTS | CONSIDERED
    # T26
    source_kind: SourceKind
    doi: Optional[str] = None
    year: Optional[int] = None
    publisher: Optional[str] = None
    publication_type: list[str] = Field(default_factory=list)
    abstract_snippet: str = ""
    relevance_score: Optional[float] = None
    rank: Optional[int] = None
    retrieved_at: Optional[str] = None
    snapshot_sha256: Optional[str] = None


class CriticView(BaseModel):
    decision: str
    issues: list[str] = Field(default_factory=list)
    requires_review: bool = False


class ClaimSeverityView(BaseModel):
    claim_id: str
    severity: Optional[str] = None          # effective: the override if any, else the table's
    table_severity: Optional[str] = None
    basis: list[str] = Field(default_factory=list)
    misinfo_relevant: bool = False
    override: Optional[dict[str, Any]] = None


class ClaimView(BaseModel):
    # unchanged fields (T11)
    claim_id: str
    text: str
    category: str
    start_seconds: float
    end_seconds: float
    label: Optional[str] = None
    deciding: bool = False
    stance: Optional[str] = None
    verdict: Optional[str] = None
    verdict_explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    evidence: list[EvidenceView] = Field(default_factory=list)  # cited papers only
    # T26
    id: str  # stable row id, for GET /v1/claims/{id}/evidence
    claim_kind: Optional[str] = None
    requires_verification: bool = True
    source_segment_ids: list[str] = Field(default_factory=list)
    modality: Optional[Modality] = None
    stance_rationale: str = ""
    stance_segment_ids: list[str] = Field(default_factory=list)
    stance_quotes: list[SegmentView] = Field(default_factory=list)
    retrieval_attempts: Optional[int] = None
    critic: Optional[CriticView] = None
    severity: Optional[ClaimSeverityView] = None
    # T31: "How we searched". Null when the claim was never searched, for
    # single-call results, and for rows stored before T31.
    search_trail: Optional[SearchTrailView] = None


class ReviewView(BaseModel):
    """The review case. Not null once a case exists, also after it is resolved."""

    # unchanged fields (T09/T11)
    status: ReviewStatus
    reasons: list[str] = Field(default_factory=list)
    # T26
    review_id: str
    case_status: Literal["OPEN", "RESOLVED"]
    resolved: bool
    action: Optional[str] = None
    reason_details: list[ReasonView] = Field(default_factory=list)
    rules_fired: list[dict[str, Any]] = Field(default_factory=list)
    severity: Optional[str] = None
    claim_severities: list[ClaimSeverityView] = Field(default_factory=list)
    severity_table_version: Optional[str] = None
    proposed_label: Optional[str] = None
    corrected_label: Optional[str] = None
    decision_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None


class JobResultResponse(BaseModel):
    """``GET /jobs/{job_id}/result``: the existing response plus T26's fields."""

    job_id: str
    filename: Optional[str] = None
    label: str
    confidence: float
    explanation: str
    evidence_snippets: list[Any] = Field(default_factory=list)
    citations: Optional[list[Any]] = None
    provider: str
    model_used: str
    latency_ms: int
    submitted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    pipeline: Optional[str] = None
    fallback_reason: Optional[str] = None
    review: Optional[ReviewView] = None
    claims: list[ClaimView] = Field(default_factory=list)
    # T26
    video_id: Optional[str] = None
    status: Optional[str] = None  # job state
    pipeline_version: Optional[str] = None
    decision_rule: Optional[str] = None
    deciding_claim_ids: list[str] = Field(default_factory=list)
    # T30 (§9): why a MISINFO label was given ("contradicted", "denies_supported",
    # "unproven"; null otherwise) and the label as the interface shows it
    # ("MISINFO (unproven)", "CANNOT RECOGNIZE"). ``label`` itself is unchanged.
    misinfo_basis: Optional[str] = None
    label_display: Optional[str] = None
    transcript_segments: list[SegmentView] = Field(default_factory=list)
    ocr_segments: list[SegmentView] = Field(default_factory=list)


class ClaimsResponse(BaseModel):
    job_id: str
    video_id: str
    claims: list[ClaimView]


class ClaimEvidenceResponse(BaseModel):
    claim_id: str
    id: str
    job_id: str
    evidence: list[EvidenceView]  # every paper the verifier saw, CONSIDERED included
