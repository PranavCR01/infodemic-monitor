import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.id"), unique=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snippets: Mapped[list] = mapped_column(JSON, nullable=False)
    citations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    combined_content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # Added by 0008 (T11). NULL on rows written before it, and on the single-call path:
    # "graph" (the graph produced the result) or "graph_fallback" (the graph failed and
    # the single-call classifier answered; ``fallback_reason`` says why).
    pipeline: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_rule: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    deciding_claim_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Added by 0011 (T30): for MISINFO, why: "contradicted", "denies_supported" or
    # "unproven" (§9). NULL otherwise, on older rows and on the single-call path.
    misinfo_basis: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
