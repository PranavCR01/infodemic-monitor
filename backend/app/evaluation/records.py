"""What a system under evaluation returns, and what a run records."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.routing.router import CallRecord
from app.core.schemas.pipeline import MisinfoLabel


class EvidenceRef(BaseModel):
    evidence_id: str
    pmid: Optional[str] = None


class PredictedClaim(BaseModel):
    claim_id: str
    claim_text: str
    source: Optional[str] = None            # speech / screen / both
    source_segment_ids: list[str] = Field(default_factory=list)
    stance: Optional[str] = None
    verdict: Optional[str] = None           # final, after the critic
    initial_verdict: Optional[str] = None   # the verifier's first verdict, before critique
    confidence: Optional[float] = None
    retrieved: list[EvidenceRef] = Field(default_factory=list)  # ranked, best first
    cited_evidence_ids: list[str] = Field(default_factory=list)
    critic_decisions: list[str] = Field(default_factory=list)   # APPROVE / RETRIEVE_MORE / ...


class VideoPrediction(BaseModel):
    video_id: str
    label: MisinfoLabel
    confidence: Optional[float] = None
    explanation: str = ""
    # None: the system does not produce claims (e.g. the single-call baseline).
    # []: the system looked and found none.
    claims: Optional[list[PredictedClaim]] = None
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    review_overturned: Optional[bool] = None  # filled in from reviewer outcomes, if any
    latency_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    model_calls: list[CallRecord] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class RunRecord(BaseModel):
    """Everything needed to reproduce a number (section 14)."""

    run_id: str
    benchmark: str
    system: str
    split: str
    started_at: str
    finished_at: str
    config_hash: str
    code_revision: Optional[str]
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    routing_version: Optional[str] = None
    routing_hash: Optional[str] = None
    model_versions: dict[str, Any] = Field(default_factory=dict)
    n_videos: int
    n_errors: int
    metrics: dict[str, Any]
    tracked_failures: dict[str, Any]
    output_dir: Optional[str] = None
