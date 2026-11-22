"""Typed state for the LangGraph pipeline (target design §1 checkpointing, §2–§12).

``PipelineState`` is the graph's shared state. It is a ``TypedDict`` (LangGraph's
native state type) whose nested values are Pydantic models, so every node gets
validated, typed records while the checkpointer still stores plain channels.

Rules this module encodes:

- **Versioned.** ``STATE_SCHEMA_VERSION`` is stored in every run's state. Bump it on any
  breaking change to a field or a nested model, so an old checkpoint is never resumed
  against an incompatible graph (see ``checkpoint.check_resumable``).
- **References, not payloads.** Media lives in object storage; state holds
  ``ArtifactRef`` URIs only. Evidence records keep the title and abstract that the
  verifier needs, never the raw PubMed response. ``assert_checkpoint_safe`` enforces
  this in tests.
- **One owner per field.** ``NODE_OUTPUTS`` in ``nodes.py`` maps every node to the fields
  it may write; the builder rejects any other write at run time.
"""
from __future__ import annotations

import enum
import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.core.retrieval.schemas import EvidenceRecord
from app.core.schemas.pipeline import MisinfoLabel

STATE_SCHEMA_VERSION = "1.0.0"


class _Record(BaseModel):
    """Base for state records: immutable, and unknown fields are an error."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- enums


class Stance(str, enum.Enum):
    """What the speaker does with a claim (§5)."""

    ENDORSES = "ENDORSES"
    REFUTES = "REFUTES"
    QUOTES = "QUOTES"
    NEUTRAL = "NEUTRAL"
    UNCLEAR = "UNCLEAR"


class Verdict(str, enum.Enum):
    """What the evidence says about a claim (§7)."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    MIXED = "MIXED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


class CriticDecision(str, enum.Enum):
    """The critic's decision on one verdict (§8)."""

    APPROVE = "APPROVE"
    RETRIEVE_MORE = "RETRIEVE_MORE"
    REVISE_VERIFICATION = "REVISE_VERIFICATION"
    ESCALATE = "ESCALATE"


class ReviewStatus(str, enum.Enum):
    """Review state of the run (§1 job states, §12)."""

    NOT_REQUIRED = "NOT_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


# ------------------------------------------------------------------ nested models


class ArtifactRef(_Record):
    """A pointer to a large artefact in object storage (§1, §17). Never the bytes."""

    kind: Literal["video", "audio", "frames", "transcript_json", "ocr_json", "other"]
    uri: str
    sha256: Optional[str] = None


class TranscriptSegment(_Record):
    """One Whisper segment (§2)."""

    segment_id: str
    start: float
    end: float
    text: str


class OcrSegment(_Record):
    """One collapsed on-screen caption (§2, §3 step 1)."""

    segment_id: str
    start: float
    end: float
    text: str
    confidence: float


class FusedSegment(_Record):
    """One fused timeline segment (§3)."""

    segment_id: str
    start: float
    end: float
    spoken: str = ""
    on_screen: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


class GraphClaim(_Record):
    """One extracted claim (§4). Distinct from ``schemas.pipeline.Claim``, which is the
    claim as it appears in the final ``ClassificationResult``."""

    claim_id: str
    claim_text: str
    claim_category: str
    source_segment_ids: list[str]
    start_seconds: float
    end_seconds: float
    requires_verification: bool = True


class StanceResult(_Record):
    """The speaker's stance on one claim (§5). ``confidence`` stays empty until
    calibrated (§5, §11)."""

    claim_id: str
    stance: Stance
    stance_segment_ids: list[str]
    rationale: str = ""
    confidence: Optional[float] = None
    # Which model and prompt produced this stance (§13). Optional and additive, so
    # checkpoints written before T04 still load; ``None`` for stub or fallback results.
    model: Optional[str] = None
    prompt_version: Optional[str] = None


# ``EvidenceRecord`` (§6) is defined in the retrieval package, which has no LangGraph
# dependency, so the graph and the MCP server share it. Re-exported here.


class VerificationResult(_Record):
    """The verifier's verdict on one claim (§7)."""

    claim_id: str
    verdict: Verdict
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    raw_confidence: Optional[float] = None
    # Which model and prompt produced this verdict (§13). Optional and additive (T06),
    # so earlier checkpoints still load; ``None`` for stub results.
    model: Optional[str] = None
    prompt_version: Optional[str] = None


class CriticResult(_Record):
    """The critic's review of one verdict (§8)."""

    claim_id: str
    decision: CriticDecision
    issues: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    requires_review: bool = False


class FinalClassification(_Record):
    """The judge's video label and the claims that decided it (§9)."""

    video_id: str
    classification: MisinfoLabel
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None


class NodeError(_Record):
    """A recoverable error a node recorded instead of raising."""

    node: str
    message: str
    claim_id: Optional[str] = None
    retryable: bool = False


# All nested types stored in checkpoints. Registered with the msgpack serializer so
# checkpoints read back under LANGGRAPH_STRICT_MSGPACK=true (see checkpoint.py).
CHECKPOINT_TYPES: tuple[type, ...] = (
    Stance,
    Verdict,
    CriticDecision,
    ReviewStatus,
    MisinfoLabel,
    ArtifactRef,
    TranscriptSegment,
    OcrSegment,
    FusedSegment,
    GraphClaim,
    StanceResult,
    EvidenceRecord,
    VerificationResult,
    CriticResult,
    FinalClassification,
    NodeError,
)


# -------------------------------------------------------------------------- state


class PipelineState(TypedDict, total=False):
    """Graph state. Per-claim maps are keyed by ``claim_id``.

    Fields beyond the architecture §5 list (``artifacts``, ``reranked_evidence``,
    ``verification_revisions``, ``review_status``, ``persisted_result_ref``) exist so that
    every node owns its own output; see context/MULTI_AGENT.md for the decision.
    """

    # Inputs (set by the caller, never written by a node).
    state_schema_version: str
    job_id: str
    video_id: str
    pipeline_version: str
    media_uri: str

    # Ingestion and extraction (§1–§3).
    artifacts: list[ArtifactRef]
    transcript_segments: list[TranscriptSegment]
    ocr_segments: list[OcrSegment]
    fused_segments: list[FusedSegment]

    # Claims and stance (§4–§5).
    claims: list[GraphClaim]
    stance_results: dict[str, StanceResult]

    # Retrieval loop (§6–§8).
    retrieval_queries: dict[str, list[str]]
    retrieved_evidence: dict[str, list[EvidenceRecord]]
    retrieval_attempts: dict[str, int]
    reranked_evidence: dict[str, list[EvidenceRecord]]
    verification_results: dict[str, VerificationResult]
    verification_revisions: dict[str, int]
    critic_results: dict[str, CriticResult]

    # Decision, validation and review (§9–§12).
    final_result: FinalClassification
    validation_errors: list[str]
    requires_human_review: bool
    review_reasons: list[str]
    review_status: ReviewStatus
    persisted_result_ref: str

    # Shared, append-only: any node may add errors (reducer concatenates).
    errors: Annotated[list[NodeError], operator.add]


INPUT_FIELDS: frozenset[str] = frozenset(
    {"state_schema_version", "job_id", "video_id", "pipeline_version", "media_uri"}
)
SHARED_FIELDS: frozenset[str] = frozenset({"errors"})


def initial_state(
    *, job_id: str, video_id: str, media_uri: str, pipeline_version: str
) -> PipelineState:
    """The input a run starts from. Every other field is filled in by nodes."""
    return PipelineState(
        state_schema_version=STATE_SCHEMA_VERSION,
        job_id=job_id,
        video_id=video_id,
        pipeline_version=pipeline_version,
        media_uri=media_uri,
        errors=[],
    )


# ---------------------------------------------------------- checkpoint size guard

# A checkpoint holds references and short texts. Anything bigger than this in a single
# string is almost certainly a raw artefact or API response that belongs in storage.
MAX_CHECKPOINT_STRING = 20_000


def assert_checkpoint_safe(value: Any, path: str = "state") -> None:
    """Raise ``ValueError`` if ``value`` holds bytes or an oversized string."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{path}: binary data must live in object storage, not state")
    if isinstance(value, str):
        if len(value) > MAX_CHECKPOINT_STRING:
            raise ValueError(
                f"{path}: string of {len(value)} chars exceeds {MAX_CHECKPOINT_STRING}; "
                "store it as an artefact and keep a reference"
            )
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            assert_checkpoint_safe(getattr(value, name), f"{path}.{name}")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            assert_checkpoint_safe(v, f"{path}[{k!r}]")
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for i, v in enumerate(value):
            assert_checkpoint_safe(v, f"{path}[{i}]")
