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

from app.core.retrieval.schemas import ClaimKind, EvidenceRecord
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
    # T30 (decision D1 = B): an *efficacy* claim (treatment_efficacy /
    # prevention) for which the full retrieval budget found no evidence for or against.
    # Not CONTRADICTED: "no evidence supports this", never "this is false". Code
    # gates it (``routing.unproven_allowed``); every other no-evidence claim stays
    # INSUFFICIENT_EVIDENCE.
    UNSUPPORTED = "UNSUPPORTED"
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


class ScreenDocument(_Record):
    """A document or chart shown on screen (T68): a one-line note written by the vision
    model, never its text. Not claim-extraction input; offered to find_study as a
    search hint. Untrusted video content (§15)."""

    start: float
    end: float
    note: str


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
    # §4: a research question (does X work / cause Y) or a fact of record (a schedule,
    # a legal limit, a statistic, a basic physiological fact). Retrieval uses it to
    # choose between studies and authoritative references (§6, T17). Defaults to a
    # research question, so checkpoints written before T17 load and keep PubMed-only
    # retrieval.
    claim_kind: ClaimKind = "research_question"


CONTEXT_FIELDS = ("subject", "exposure", "amount", "population", "outcome")


class ContextItem(_Record):
    """One piece of a claim's context (T70), as the video states it elsewhere: its words
    and the transcript / OCR pieces (``t*`` / ``o*``) they come from. Kept only when
    grounded in the pieces it cites. Untrusted video content (§15)."""

    text: str
    segment_ids: list[str]


class ClaimContext(_Record):
    """What a claim means in its video (T70, prompt ``extract_v5``): the subject or
    product, exposure route or setting, amount or dose, population and outcome the video
    attaches to it elsewhere, each grounded in cited segments. ``claim_text`` stays the
    verbatim claim. ``scope`` is ``specific`` only when the model said so and at least one
    item survived grounding; a ``universal`` claim is judged as stated. ``dropped`` names
    items removed as ungrounded."""

    claim_id: str
    subject: Optional[ContextItem] = None
    exposure: Optional[ContextItem] = None
    amount: Optional[ContextItem] = None
    population: Optional[ContextItem] = None
    outcome: Optional[ContextItem] = None
    scope: Literal["specific", "universal"] = "universal"
    dropped: list[str] = Field(default_factory=list)

    def items(self) -> list[tuple[str, ContextItem]]:
        return [(f, getattr(self, f)) for f in CONTEXT_FIELDS if getattr(self, f) is not None]


class VideoTopic(_Record):
    """The video's topic in one line (T70), produced once by extraction and grounded in
    the segments it cites. Claim context is read against it. Untrusted video content."""

    text: str
    segment_ids: list[str]


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
    # Added by T07, optional and additive so earlier checkpoints still load.
    # ``reviewed_attempt`` / ``reviewed_revision``: the claim's retrieval-attempt and
    # verification-revision counts when this review was made. Routing uses them to
    # tell "new evidence or a new verdict since the review" from "nothing changed"
    # (an exhausted claim is not re-verified or re-reviewed while other claims loop).
    # ``None`` (scripted critics, pre-T07 checkpoints) keeps the T02 behaviour.
    reviewed_attempt: Optional[int] = None
    reviewed_revision: Optional[int] = None
    # Which checks raised the issues (e.g. ``code:strength``, ``model``), and which
    # model and prompt produced the review (§13). ``None`` for stub / code-only reviews.
    checks: list[str] = Field(default_factory=list)
    model: Optional[str] = None
    prompt_version: Optional[str] = None


class FinalClassification(_Record):
    """The judge's video label and the claims that decided it (§9)."""

    video_id: str
    classification: MisinfoLabel
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    # Added by T08 (judge). Optional and additive, so earlier checkpoints still load.
    # ``decision_rule`` names the §9 rule that fired; ``review_flags`` are the patterns
    # the rules can't settle (mixed video, unclear stance on a false claim, ...), which
    # the review policy turns into review reasons. ``model``/``prompt_version`` describe
    # the explanation writer (``None`` when the deterministic template was used).
    decision_rule: Optional[str] = None
    review_flags: list[str] = Field(default_factory=list)
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    # Added by T30, optional and additive. Set only when the label is MISINFO:
    # ``contradicted``, ``denies_supported`` or ``unproven`` (§9). The interface shows
    # "MISINFO (unproven)" for the last; the label itself stays one of the four.
    misinfo_basis: Optional[str] = None


class ReferenceConsulted(_Record):
    """One allow-listed reference page or Bookshelf search tried for a claim (T31, §6
    "Trusted sources beyond PubMed"). Names and hosts come from the allow-list in
    config, never from a model; ``url`` is the allow-listed page, never an API request
    URL. ``outcome``: passage / no_passage / no_results / skipped / error."""

    source_id: str
    source_name: str
    publisher: str = ""
    site: Optional[str] = None
    item: str
    mode: str
    outcome: str
    url: Optional[str] = None


class SearchRound(_Record):
    """What one ``retrieve_evidence`` round did for one claim (T31, "How we searched").

    ``pubmed_hits``: PMIDs ESearch returned for the query; ``pubmed_records``: those
    left after the publication-type and year filters; ``new_records``: what the round
    added to the claim's set after PMID/DOI dedup (references included). Counts are
    ``None`` when the search failed. ``pubmed_error`` holds the exception type only,
    never its message (an HTTP error message can carry the request URL and API key).
    Recording this never changes what is retrieved.
    """

    round: int
    pubmed_query: Optional[str] = None
    pubmed_hits: Optional[int] = None
    pubmed_records: Optional[int] = None
    from_cache: Optional[bool] = None
    pubmed_error: Optional[str] = None
    references: list[ReferenceConsulted] = Field(default_factory=list)
    reference_passages: Optional[int] = None
    reference_error: Optional[str] = None
    new_records: int = 0
    # T50 (§6 planning). ``query_kind``: which rung of the plan the query was
    # (citation, pico, intervention_outcome, broader_outcome, intervention_only,
    # assistant, keywords, critic ...). ``ladder_exhausted``: the plan had no query left
    # that hadn't run, so the claim's search stopped here instead of repeating one.
    # ``plan``: on the claim's first round, what planning decided (language, translation,
    # carried-over context concept, citation cue, assistant use, the rungs). Optional and
    # additive, so older checkpoints still load.
    query_kind: Optional[str] = None
    ladder_exhausted: bool = False
    plan: Optional[dict] = None


class FindStudyCandidate(_Record):
    """One id the find-the-study model proposed and what verification made of it (T50 i)."""

    pmid: Optional[str] = None
    doi: Optional[str] = None
    outcome: str  # verified_pubmed | verified_journal_doi | invalid_format | not_found | mismatch | error | duplicate
    reason: str = ""
    evidence_id: Optional[str] = None
    via: Optional[str] = None  # efetch | esearch_doi | crossref


class FindStudyTrail(_Record):
    """What the find-the-study step did for one claim (T50 i). Web text never appears
    here: only the searches the model ran, the ids it proposed and our verification."""

    reason: str  # cites_study | nothing_on_topic
    round: int = 0
    web_queries: list[str] = Field(default_factory=list)
    web_searches: int = 0
    candidates: list[FindStudyCandidate] = Field(default_factory=list)
    verified: int = 0
    model: Optional[str] = None
    cost_usd: Optional[float] = None
    latency_ms: int = 0
    error: Optional[str] = None


class SharedStudy(_Record):
    """A cited-study record another claim of the video holds, offered to this claim
    (T57, ``app.core.graph.shared_study``). ``shared_from``: the claim it came from.
    ``outcome``: kept | not_kept_by_reranker | off_topic | citation_mismatch."""

    evidence_id: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    shared_from: str
    outcome: str
    reason: str = ""
    relevance_score: Optional[float] = None


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
    ScreenDocument,
    FusedSegment,
    GraphClaim,
    ContextItem,
    ClaimContext,
    VideoTopic,
    StanceResult,
    EvidenceRecord,
    VerificationResult,
    CriticResult,
    FinalClassification,
    FindStudyCandidate,
    FindStudyTrail,
    SharedStudy,
    ReferenceConsulted,
    SearchRound,
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
    # Optional input (T09): the video's length, for the §10 timestamp check. When
    # absent, timestamps are still checked for order and sign but not against a length.
    video_duration_seconds: float

    # Ingestion and extraction (§1–§3).
    artifacts: list[ArtifactRef]
    transcript_segments: list[TranscriptSegment]
    ocr_segments: list[OcrSegment]
    # Documents and charts shown on screen (T68), as notes. Optional and additive:
    # written only when vision OCR is on and saw one.
    screen_documents: list[ScreenDocument]
    fused_segments: list[FusedSegment]

    # Claims and stance (§4–§5).
    claims: list[GraphClaim]
    # Claim context (T70, switch ``routing.CLAIM_CONTEXT``): per claim, what it means in the
    # video, and the video's one-line topic. Optional and additive: written by
    # extract_claims only when the switch is on and there is something to write.
    claim_contexts: dict[str, ClaimContext]
    video_topic: VideoTopic
    stance_results: dict[str, StanceResult]

    # Retrieval loop (§6–§8).
    retrieval_queries: dict[str, list[str]]
    retrieved_evidence: dict[str, list[EvidenceRecord]]
    retrieval_attempts: dict[str, int]
    reranked_evidence: dict[str, list[EvidenceRecord]]
    # "How we searched" (T31): one entry per retrieve_evidence round per claim, written
    # by retrieve_evidence alongside retrieved_evidence. Optional and additive: a
    # checkpoint without it still loads, and persistence falls back to the queries.
    search_trail: dict[str, list[SearchRound]]
    # Offline-library passages (§6 "Fallback"), per claim, for claims where the
    # fallback fired (an empty list: it fired and found nothing). Written by
    # rerank_evidence, which decides when it fires. Kept across rounds, like
    # retrieved_evidence, so every cited library ID stays checkable.
    library_evidence: dict[str, list[EvidenceRecord]]
    # Find-the-study (T50 i): verified records per claim (PubMed or journal_doi) and
    # what the step did. Written by rerank_evidence, which decides when it runs; the
    # records are kept through reranking. Optional and additive.
    found_study_evidence: dict[str, list[EvidenceRecord]]
    find_study_trail: dict[str, FindStudyTrail]
    # A study the video cites, shared across its claims (T57): per claim, the
    # cited-study records other claims hold that were offered to it, where each came
    # from (``shared_from``) and whether the reranker and the on-topic check kept it.
    # Rebuilt by rerank_evidence every round. Optional and additive.
    shared_study_trail: dict[str, list[SharedStudy]]
    verification_results: dict[str, VerificationResult]
    verification_revisions: dict[str, int]
    critic_results: dict[str, CriticResult]

    # Decision, validation and review (§9–§12).
    final_result: FinalClassification
    validation_errors: list[str]
    # How many times validation has run (T09): 1 after the first check, 2 after the
    # one repair attempt (§10). Routing uses it to bound the repair loop.
    validation_attempts: int
    requires_human_review: bool
    review_reasons: list[str]
    review_status: ReviewStatus
    persisted_result_ref: str

    # Shared, append-only: any node may add errors (reducer concatenates).
    errors: Annotated[list[NodeError], operator.add]


INPUT_FIELDS: frozenset[str] = frozenset(
    {"state_schema_version", "job_id", "video_id", "pipeline_version", "media_uri",
     "video_duration_seconds"}
)
SHARED_FIELDS: frozenset[str] = frozenset({"errors"})


def initial_state(
    *,
    job_id: str,
    video_id: str,
    media_uri: str,
    pipeline_version: str,
    video_duration_seconds: Optional[float] = None,
) -> PipelineState:
    """The input a run starts from. Every other field is filled in by nodes."""
    state = PipelineState(
        state_schema_version=STATE_SCHEMA_VERSION,
        job_id=job_id,
        video_id=video_id,
        pipeline_version=pipeline_version,
        media_uri=media_uri,
        errors=[],
    )
    if video_duration_seconds is not None:
        state["video_duration_seconds"] = float(video_duration_seconds)
    return state


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
