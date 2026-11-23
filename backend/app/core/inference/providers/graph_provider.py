"""The LangGraph pipeline as an ``InferenceProvider`` (T11, issue #38; design §1, §4–§12).

``GraphProvider.classify(fusion)`` runs the full graph (claims → stance → retrieval →
rerank → verify ⇄ critic → judge → validate → review policy) on a ``FusionResult`` and
returns a ``ClassificationResult``, so it slots in where the single-call providers do.
``run(...)`` returns the same result plus what the caller needs to persist claim-level
output (the final graph state) and whether a fallback happened.

**When the graph runs (decision, context/MULTI_AGENT.md §7k).** On every video while
``USE_GRAPH_PIPELINE`` is on. Not only below a confidence threshold: today's confidence
is the single call's own, uncalibrated number (§11), and gating on it would make the
single call — the thing the graph exists to replace — decide which videos get evidence.

**Fallback.** The single-call provider answers instead, and the outcome records why,
when the graph:

- raises (``graph_error:<Type>``),
- runs past ``timeout_seconds`` (``timeout``; checked between graph steps, so a step
  in flight finishes first; each provider call has its own timeout),
- ends without a ``final_result`` (``no_result``),
- could not reach the claim extractor's model (``extraction_unavailable``): "no
  claims" would otherwise be published as "no checkable health claims",
- extracted claims but every later model call failed (``models_unavailable``).

A graph that ran and *abstained* (CANNOT_RECOGNIZE, insufficient evidence, review) is
not a failure and is never replaced by the single call: abstention is the designed
answer to uncertainty (§1 "Scientific uncertainty: abstain").

**Resume.** The run's thread is the job ID. If the checkpointer already holds an
unfinished run for the job (a worker died), it is resumed; a finished run is reused
without re-running anything (Celery may deliver the task twice, §1).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from app.core.graph import routing as r
from app.core.graph.builder import compile_graph, run_config
from app.core.graph.checkpoint import check_resumable, memory_checkpointer
from app.core.graph.claims import extraction_unavailable, make_extract_claims
from app.core.graph.critic import make_critique_verification
from app.core.graph.judge import make_judge_classification, to_classification_result
from app.core.graph.nodes import NodeFn
from app.core.graph.retrieval_nodes import make_retrieval_nodes
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.graph.stance import make_analyze_stance
from app.core.graph.state import OcrSegment, PipelineState, TranscriptSegment, initial_state
from app.core.graph.verifier import make_verify_claims
from app.core.inference.classifier import InferenceProvider
from app.core.schemas.pipeline import ClassificationResult, FusionResult

PROVIDER_NAME = "langgraph"

# Speech rate used to estimate timing when the fusion has no Whisper segments (the
# single-call fusion keeps only text). ~15 characters a second ≈ 150 words a minute.
_EST_CHARS_PER_SECOND = 15.0
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


class GraphTimeout(RuntimeError):
    pass


@dataclass
class GraphOutcome:
    """What one ``GraphProvider.run`` produced."""

    classification: ClassificationResult
    pipeline: str                                  # "graph" | "graph_fallback"
    state: Optional[dict] = None                   # final graph state (also on most fallbacks)
    fallback_reason: Optional[str] = None
    model_calls: list = field(default_factory=list)  # CallRecords from this run
    resumed: bool = False
    timing_estimated: bool = False

    @property
    def fallback_used(self) -> bool:
        return self.pipeline == "graph_fallback"

    @property
    def requires_human_review(self) -> bool:
        return bool(not self.fallback_used and self.state and self.state.get("requires_human_review"))


# ------------------------------------------------------------- fusion → state


def segments_from_fusion(fusion: FusionResult) -> tuple[list[TranscriptSegment], list[OcrSegment], bool]:
    """Transcript and caption pieces for the graph.

    Uses Whisper's timed segments when the fusion kept them
    (``metadata["transcript_segments"]``, the graph path's ``fuse(keep_segments=True)``).
    Otherwise the transcript is split into sentences with timing estimated from text
    length; the third value says so (recorded on the outcome as ``timing_estimated``;
    the §10 timestamp check then has no video length to compare with). Captions (``visual_text``, one per line) get the same treatment.
    """
    raw = (fusion.metadata or {}).get("transcript_segments")
    estimated = False
    transcript: list[TranscriptSegment] = []
    if raw:
        for i, s in enumerate(raw, start=1):
            text = str(s.get("text", "")).strip()
            if not text:
                continue
            start = max(0.0, float(s.get("start", 0.0)))
            end = max(start, float(s.get("end", start)))
            transcript.append(TranscriptSegment(segment_id=f"t{len(transcript) + 1}", start=start, end=end, text=text))
    elif fusion.transcript.strip():
        estimated = True
        t = 0.0
        for sentence in _SENTENCE.split(fusion.transcript.strip()):
            sentence = sentence.strip()
            if not sentence:
                continue
            dur = max(1.0, len(sentence) / _EST_CHARS_PER_SECOND)
            transcript.append(TranscriptSegment(
                segment_id=f"t{len(transcript) + 1}", start=round(t, 2), end=round(t + dur, 2), text=sentence))
            t += dur
    ocr: list[OcrSegment] = []
    lines = [l.strip() for l in (fusion.visual_text or "").splitlines() if l.strip()]
    if lines:
        estimated = True
        end = max((s.end for s in transcript), default=float(len(lines)))
        for line in dict.fromkeys(lines):
            ocr.append(OcrSegment(segment_id=f"o{len(ocr) + 1}", start=0.0, end=end, text=line, confidence=1.0))
    return transcript, ocr, estimated


def fusion_nodes(transcript: list[TranscriptSegment], ocr: list[OcrSegment]) -> dict[str, NodeFn]:
    """``transcribe_audio`` / ``extract_ocr`` that hand the graph the pieces the worker
    already extracted (the single-call path's ``MultimodalFusion``), so the media is
    transcribed once whichever path runs."""
    def transcribe_audio(state: PipelineState) -> dict:
        return {"transcript_segments": list(transcript)}

    def extract_ocr(state: PipelineState) -> dict:
        return {"ocr_segments": list(ocr)}

    return {r.TRANSCRIBE_AUDIO: transcribe_audio, r.EXTRACT_OCR: extract_ocr}


def build_nodes(caller: Any, retriever: Any, *, budgets: Budgets = DEFAULT_BUDGETS,
                library: Any = None, references: Any = None) -> dict[str, NodeFn]:
    """The real nodes for the model-calling and retrieval steps. Fusion, validation,
    the review policy and the judge's rules are deterministic and already the default
    graph's; load_artifacts / human_review / persist_result stay reference-only (the
    worker persists, see ``app.services.pipeline_result_service``)."""
    return {
        r.EXTRACT_CLAIMS: make_extract_claims(caller),
        r.ANALYZE_STANCE: make_analyze_stance(caller),
        **make_retrieval_nodes(retriever, budgets=budgets, library=library, references=references),
        r.VERIFY_CLAIMS: make_verify_claims(caller, budgets=budgets),
        r.CRITIQUE_VERIFICATION: make_critique_verification(caller, budgets=budgets),
        r.JUDGE_CLASSIFICATION: make_judge_classification(caller, budgets=budgets),
    }


# ------------------------------------------------------------------ provider


class GraphProvider:
    """``InferenceProvider`` backed by the LangGraph pipeline, with a single-call fallback."""

    def __init__(
        self,
        *,
        caller: Any,
        retriever: Any,
        fallback: InferenceProvider,
        checkpointer: Any = None,
        budgets: Budgets = DEFAULT_BUDGETS,
        library: Any = None,
        references: Any = None,
        timeout_seconds: float = 900.0,
        pipeline_version: str = "graph_v1",
        clock: Callable[[], float] = time.monotonic,
        node_overrides: Optional[Mapping[str, NodeFn]] = None,
    ):
        self.caller = caller
        self.retriever = retriever
        self.fallback = fallback
        self.checkpointer = checkpointer if checkpointer is not None else memory_checkpointer()
        self.budgets = budgets
        self.library = library
        self.references = references
        self.timeout_seconds = timeout_seconds
        self.pipeline_version = pipeline_version
        self._clock = clock
        self._overrides = dict(node_overrides or {})
        # Built once, so a bad routing config or a missing prompt file fails at start-up.
        self._nodes = build_nodes(caller, retriever, budgets=budgets, library=library, references=references)

    # InferenceProvider -------------------------------------------------------

    def classify(self, fusion: FusionResult) -> ClassificationResult:
        return self.run(fusion).classification

    # Full run ----------------------------------------------------------------

    def _records(self) -> list:
        return list(getattr(self.caller, "records", None) or [])

    def _model_label(self) -> str:
        cfg = getattr(self.caller, "config", None)
        version = getattr(cfg, "version", None)
        return f"{self.pipeline_version}/{version}" if version else self.pipeline_version

    def run(self, fusion: FusionResult, *, job_id: Optional[str] = None,
            video_id: Optional[str] = None, media_uri: Optional[str] = None,
            video_duration_seconds: Optional[float] = None) -> GraphOutcome:
        job_id = job_id or f"adhoc-{time.time_ns()}"
        start = self._clock()
        calls_before = len(self._records())
        transcript, ocr, estimated = segments_from_fusion(fusion)
        state: Optional[dict] = None
        resumed = False
        try:
            graph = compile_graph(
                {**self._nodes, **fusion_nodes(transcript, ocr), **self._overrides},
                checkpointer=self.checkpointer, budgets=self.budgets,
            )
            config = run_config(job_id, self.budgets)
            check_resumable(graph, config)
            snapshot = graph.get_state(config)
            if snapshot and snapshot.values and not snapshot.next:
                state = dict(snapshot.values)          # finished earlier: reuse, don't re-run
                resumed = True
            else:
                if snapshot and snapshot.values and snapshot.next:
                    inp, resumed = None, True          # unfinished: resume from the checkpoint
                else:
                    inp = initial_state(
                        job_id=job_id, video_id=video_id or job_id,
                        media_uri=media_uri or f"fusion://{job_id}",
                        pipeline_version=self.pipeline_version,
                        video_duration_seconds=video_duration_seconds,
                    )
                deadline = start + self.timeout_seconds
                for _chunk in graph.stream(inp, config, stream_mode="values"):
                    if self._clock() > deadline:
                        raise GraphTimeout(f"graph run exceeded {self.timeout_seconds:.0f}s")
                state = dict(graph.get_state(config).values)
        except GraphTimeout:
            return self._fall_back(fusion, "timeout", state, calls_before, resumed, estimated)
        except Exception as exc:  # noqa: BLE001 - any graph failure falls back
            return self._fall_back(fusion, f"graph_error:{type(exc).__name__}: {exc}"[:500], state,
                                   calls_before, resumed, estimated)

        reason = self._failure_reason(state, calls_before)
        if reason:
            return self._fall_back(fusion, reason, state, calls_before, resumed, estimated)
        latency = int(round((self._clock() - start) * 1000))
        classification = to_classification_result(
            state, latency_ms=latency, provider=PROVIDER_NAME, model_used=self._model_label())
        return GraphOutcome(
            classification=classification, pipeline="graph", state=state,
            model_calls=self._records()[calls_before:], resumed=resumed, timing_estimated=estimated,
        )

    def _failure_reason(self, state: Optional[dict], calls_before: int) -> Optional[str]:
        if not state or state.get("final_result") is None:
            return "no_result"
        if extraction_unavailable(state.get("errors") or []):
            return "extraction_unavailable"
        # Claims were extracted but every later model call failed (stance, verifier,
        # critic, explanation): the abstention that follows would be an outage, not a
        # finding about the evidence.
        calls = [c for c in self._records()[calls_before:] if getattr(c, "step", None) != "extract_claims"]
        if calls and all(getattr(c, "error", None) for c in calls):
            return "models_unavailable"
        return None

    def _fall_back(self, fusion: FusionResult, reason: str, state: Optional[dict], calls_before: int,
                   resumed: bool, estimated: bool) -> GraphOutcome:
        # The single call's own errors (InferenceProviderError) propagate: with both
        # paths down the job fails as it does today.
        classification = self.fallback.classify(fusion)
        return GraphOutcome(
            classification=classification, pipeline="graph_fallback", state=state,
            fallback_reason=reason, model_calls=self._records()[calls_before:], resumed=resumed,
            timing_estimated=estimated,
        )


def shared_query_cache(settings: Any) -> Any:
    """The Redis query cache the retrieval MCP server uses (T13, same ``retrieval:``
    prefix), when ``GRAPH_SHARED_RETRIEVAL`` is on and ``REDIS_URL`` is set (the worker
    already needs Redis as its Celery broker). Cache errors are swallowed by
    ``RedisQueryCache``, so a Redis outage only costs extra NCBI calls. ``None`` = the
    retriever's in-memory cache, as before.

    T13's shared NCBI token bucket is *not* wired: it lives in ``app.mcp_server.quota``
    and ``app.core`` must not import the MCP server (T13's test). Moving the bucket into
    ``app.core.retrieval`` is left for a person (context/MULTI_AGENT.md §7m).
    """
    if not (getattr(settings, "GRAPH_SHARED_RETRIEVAL", False) and getattr(settings, "REDIS_URL", "")):
        return None
    import redis

    from app.core.retrieval.cache import RedisQueryCache

    return RedisQueryCache(redis.Redis.from_url(settings.REDIS_URL))


def reference_searcher(settings: Any, cache: Any = None) -> Any:
    """Authoritative references for facts of record (§6, T17), or ``None`` while
    ``USE_REFERENCE_SOURCES`` is off (the default): claims are then still tagged with a
    ``claim_kind`` but every claim is retrieved from PubMed only, as before T17.
    Snapshots go to the ``reference_snapshots`` table (migration 0009). Pages whose
    publisher blocks scripted requests are read from the committed stored-snapshot
    archive (``data/reference_snapshots``, T19), never requested."""
    if not getattr(settings, "USE_REFERENCE_SOURCES", False):
        return None
    from app.core.retrieval.pubmed import shared_rate_limiter
    from app.core.retrieval.references import ReferenceSearcher, SqlSnapshotStore, load_reference_config
    from app.db.session import SessionLocal

    return ReferenceSearcher(
        load_reference_config(), snapshots=SqlSnapshotStore(SessionLocal), cache=cache,
        rate_limiter=shared_rate_limiter(bool(getattr(settings, "NCBI_API_KEY", ""))),
        api_key=getattr(settings, "NCBI_API_KEY", "") or "",
    )


def build_graph_provider(settings: Any = None, *, checkpointer: Any = None) -> GraphProvider:
    """The production wiring, from settings: routed models (``config/routing.yaml``)
    through real provider clients, PubMed through the guarded client, the single-call
    provider as the fallback. Only called when ``USE_GRAPH_PIPELINE`` is on."""
    if settings is None:
        from app.core.config import settings
    from app.core.inference import get_provider
    from app.core.retrieval.pubmed import PubMedClient
    from app.core.retrieval.retriever import EvidenceRetriever
    from app.core.routing.clients import default_clients
    from app.core.routing.config import load_routing
    from app.core.routing.router import ModelRouter

    router = ModelRouter(load_routing(), default_clients(
        anthropic_api_key=settings.ANTHROPIC_API_KEY, openai_api_key=settings.OPENAI_API_KEY,
        timeout=settings.GRAPH_MODEL_TIMEOUT_SECONDS,
    ))
    cache = shared_query_cache(settings)
    retriever = EvidenceRetriever(
        PubMedClient(api_key=settings.NCBI_API_KEY, email=settings.NCBI_EMAIL),
        cache,
        max_results=settings.RETRIEVAL_MAX_RESULTS_PER_QUERY,
    )
    return GraphProvider(
        caller=router, retriever=retriever, fallback=get_provider(), checkpointer=checkpointer,
        references=reference_searcher(settings, cache),
        timeout_seconds=settings.GRAPH_TIMEOUT_SECONDS, pipeline_version=settings.GRAPH_PIPELINE_VERSION,
    )
