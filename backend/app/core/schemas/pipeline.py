"""Pipeline data contracts.

All extraction and inference modules import from this file.
Do not split into multiple files — a single import source eliminates circular import risk.
"""
import enum
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class MisinfoLabel(str, enum.Enum):
    """Canonical misinformation classification labels.

    Uses (str, enum.Enum) NOT enum.StrEnum — avoids SQLAlchemy mapped_column
    compatibility issues. Members serialize as plain string values in FastAPI
    JSON responses (e.g., "MISINFO" not 0).
    """
    MISINFO = "MISINFO"
    NO_MISINFO = "NO_MISINFO"
    DEBUNKING = "DEBUNKING"
    CANNOT_RECOGNIZE = "CANNOT_RECOGNIZE"


def display_label(label: "MisinfoLabel | str | None", misinfo_basis: Optional[str] = None) -> Optional[str]:
    """The label as the interface shows it (target design §9, T30): "MISINFO (unproven)"
    when a MISINFO label's basis is ``unproven``, otherwise the label with spaces
    ("CANNOT RECOGNIZE", "NO MISINFO"). The stored label is always one of the four."""
    if label is None:
        return None
    value = label.value if isinstance(label, MisinfoLabel) else str(label)
    if value == MisinfoLabel.MISINFO.value and misinfo_basis == "unproven":
        return "MISINFO (unproven)"
    return value.replace("_", " ")


class PubMedCitation(BaseModel):
    """A single PubMed citation linked to a specific health claim in the transcript."""
    claim_id: Optional[str] = None
    claim: str
    title: str
    pmid: str
    url: str


class Claim(BaseModel):
    """One health claim in a video, with its own verdict and citations."""
    claim_id: str
    text: str
    label: MisinfoLabel
    confidence: float
    evidence: list[str] = []
    citations: list[PubMedCitation] = []

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class FusionResult(BaseModel):
    """Output of MultimodalFusion.fuse() — combined transcript + OCR signals.

    Passed directly to InferenceProvider.classify().
    """
    transcript: str
    visual_text: str
    combined_content: str
    metadata: dict[str, Any]


class ClassificationResult(BaseModel):
    """Output of InferenceProvider.classify() — structured misinformation verdict.

    Persisted to the Result ORM model in Phase 4.
    label is stored as String in DB (not SAEnum) — validated here at application layer.
    """
    label: MisinfoLabel
    confidence: float
    explanation: str
    evidence_snippets: list[str]
    provider: str
    model_used: str
    latency_ms: int
    citations: Optional[list[PubMedCitation]] = None
    claims: Optional[list[Claim]] = None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Clamp confidence to [0.0, 1.0]. LLM outputs are not always in range."""
        return max(0.0, min(1.0, v))
