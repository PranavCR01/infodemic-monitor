from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str


class OCRSegment(BaseModel):
    segment_id: str
    timestamp_seconds: float
    text: str


class FusedSegment(BaseModel):
    segment_id: str
    text: str
    source_segment_ids: list[str]


class ExtractedClaim(BaseModel):
    claim_id: str
    claim_text: str
    claim_category: str
    source_segment_ids: list[str]
    start_seconds: float
    end_seconds: float
    requires_verification: bool


class StanceResult(BaseModel):
    claim_id: str
    stance: Literal[
        "ENDORSES",
        "REFUTES",
        "NEUTRAL",
        "QUOTES",
        "UNCLEAR",
    ]
    source_segment_ids: list[str]


class EvidenceRecord(BaseModel):
    evidence_id: str
    pmid: str | None
    doi: str | None
    title: str
    abstract: str | None
    publication_year: int | None
    publication_type: list[str]
    source_url: str
    retrieved_at: str
    relevance_score: float | None


class VerificationResult(BaseModel):
    claim_id: str
    verdict: Literal[
        "SUPPORTED",
        "CONTRADICTED",
        "MIXED",
        "INSUFFICIENT_EVIDENCE",
        "NOT_VERIFIABLE",
    ]
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    explanation: str
    limitations: list[str]


class CriticResult(BaseModel):
    claim_id: str
    decision: Literal[
        "APPROVE",
        "RETRIEVE_MORE",
        "REVISE_VERIFICATION",
        "ESCALATE",
    ]
    issues: list[str]
    suggested_queries: list[str]
    requires_review: bool


class FinalClassification(BaseModel):
    video_id: str
    classification: Literal[
        "MISINFO",
        "NO_MISINFO",
        "DEBUNKING",
        "CANNOT_RECOGNIZE",
    ]
    claim_ids: list[str]
    evidence_ids: list[str]
    explanation: str
    limitations: list[str]
    requires_human_review: bool
    review_reasons: list[str]


class PipelineError(BaseModel):
    node: str
    error_type: str
    message: str


class PipelineState(TypedDict):
    job_id: str
    video_id: str
    pipeline_version: str
    media_uri: str

    transcript_segments: list[TranscriptSegment]
    ocr_segments: list[OCRSegment]
    fused_segments: list[FusedSegment]

    claims: list[ExtractedClaim]
    stance_results: dict[str, StanceResult]

    retrieval_queries: dict[str, list[str]]
    retrieved_evidence: dict[str, list[EvidenceRecord]]
    verification_results: dict[str, VerificationResult]
    critic_results: dict[str, CriticResult]
    retrieval_attempts: dict[str, int]
    verification_revision_attempts: NotRequired[dict[str, int]]

    final_result: NotRequired[FinalClassification]

    validation_errors: list[str]
    requires_human_review: bool
    review_reasons: list[str]
    errors: list[PipelineError]