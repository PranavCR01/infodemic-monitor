"""Stance analyzer node (target design §5; issue #30).

For each claim, one LLM call decides what the speaker does with it: ENDORSES, REFUTES,
QUOTES, NEUTRAL or UNCLEAR, citing the video segments the decision rests on.

How it fits:

- **Model choice comes from routing config.** The node is given a ``StepCaller``: any
  object with ``call(step, input, *, system=None)`` returning a result with ``.output``
  (and optionally ``.record`` with ``model`` / ``prompt_version``). T01's
  ``app.core.routing.ModelRouter`` has exactly this shape, so production passes the
  router; tests pass a fake. The node never names a model.
- **Forced structured output.** The request carries the ``record_stance`` tool and a
  ``tool_choice`` forcing it; the client returns the tool's input as a dict. The dict is
  parsed with ``StanceToolOutput``.
- **Invalid output becomes UNCLEAR, never a guess.** Anything that doesn't parse, an
  unknown stance, no cited segment, or a cited segment ID that wasn't in the input, gives
  UNCLEAR citing the claim's own source segments, and a ``NodeError`` is recorded. A
  failed model call does the same (marked retryable).
- **Every stance cites at least one segment ID that exists in the input.**
- **Untrusted text is fenced** inside ``<video_segments>`` (§15); the fence tag is
  stripped from segment text so a caption can't close the block.
- **confidence stays None** until calibration exists (§5, §11), whatever the model says.
- Writes only ``stance_results`` (plus the shared, append-only ``errors``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.guardrails.injection import neutralise
from app.core.graph import routing as r
from app.core.graph.state import (
    FusedSegment,
    GraphClaim,
    NodeError,
    OcrSegment,
    PipelineState,
    Stance,
    StanceResult,
    TranscriptSegment,
)

STEP = "analyze_stance"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "stance_v1"
TOOL_NAME = "record_stance"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Context sent per claim: the claim's own segments plus anything within this many
# seconds of it (the deciding words, e.g. "That's a myth.", are often the next sentence).
CONTEXT_WINDOW_SECONDS = 15.0
MAX_CONTEXT_SEGMENTS = 40
MAX_SEGMENT_CHARS = 1_000
MAX_RATIONALE_CHARS = 500

_FENCE_RE = re.compile(r"</?\s*video_segments\s*>", re.IGNORECASE)


# ------------------------------------------------------------------ schemas


class StanceToolOutput(BaseModel):
    """What the model must return through the ``record_stance`` tool.

    Extra keys (e.g. a ``confidence`` the model volunteers) are ignored, not trusted.
    """

    model_config = ConfigDict(extra="ignore")

    stance: Stance
    stance_segment_ids: list[str] = Field(min_length=1)
    rationale: str = ""

    @field_validator("stance", mode="before")
    @classmethod
    def _normalise_stance(cls, v: Any) -> Any:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("stance_segment_ids")
    @classmethod
    def _ids_nonblank(cls, v: list[str]) -> list[str]:
        ids = [s.strip() for s in v]
        if any(not s for s in ids):
            raise ValueError("blank segment id")
        return list(dict.fromkeys(ids))  # dedupe, keep order


STANCE_TOOL: dict = {
    "name": TOOL_NAME,
    "description": "Record the speaker's stance toward the claim and the segments it rests on.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stance": {
                "type": "string",
                "enum": [s.value for s in Stance],
                "description": "What the speaker does with the claim.",
            },
            "stance_segment_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "IDs of the segments the stance is based on, from <video_segments> only.",
            },
            "rationale": {
                "type": "string",
                "description": "One or two sentences quoting or paraphrasing the deciding words.",
            },
        },
        "required": ["stance", "stance_segment_ids", "rationale"],
        "additionalProperties": False,
    },
}
TOOL_CHOICE: dict = {"type": "tool", "name": TOOL_NAME}


class StepCaller(Protocol):
    """Anything that runs one routed LLM step (T01's ``ModelRouter`` satisfies this)."""

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> Any: ...


# ------------------------------------------------------------------ prompts


class PromptNotFoundError(FileNotFoundError):
    pass


def load_prompt(version: str) -> str:
    """Read a versioned prompt file, e.g. ``stance_v1`` → ``prompts/stance_v1.md``."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", version or ""):
        raise PromptNotFoundError(f"invalid prompt version {version!r}")
    path = PROMPTS_DIR / f"{version}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"no prompt file for version {version!r} at {path}")
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ context


@dataclass(frozen=True)
class ContextSegment:
    segment_id: str
    modality: str  # "speech" | "screen" | "fused"
    start: float
    end: float
    text: str


def _pool(state: PipelineState) -> dict[str, ContextSegment]:
    """All source pieces a claim can cite: speech and caption segments, and fused
    segments (only reachable when a claim cites them, or when no pieces exist)."""
    pool: dict[str, ContextSegment] = {}
    t: TranscriptSegment
    for t in state.get("transcript_segments", []) or []:
        pool[t.segment_id] = ContextSegment(t.segment_id, "speech", t.start, t.end, t.text)
    o: OcrSegment
    for o in state.get("ocr_segments", []) or []:
        pool[o.segment_id] = ContextSegment(o.segment_id, "screen", o.start, o.end, o.text)
    return pool


def _fused_pool(state: PipelineState) -> dict[str, ContextSegment]:
    out: dict[str, ContextSegment] = {}
    f: FusedSegment
    for f in state.get("fused_segments", []) or []:
        text = f.spoken
        if f.on_screen:
            text = (text + " " if text else "") + " ".join(f"[on screen: {s}]" for s in f.on_screen)
        out[f.segment_id] = ContextSegment(f.segment_id, "fused", f.start, f.end, text)
    return out


def context_for_claim(
    claim: GraphClaim,
    pool: dict[str, ContextSegment],
    fused: dict[str, ContextSegment],
    window: float = CONTEXT_WINDOW_SECONDS,
) -> list[ContextSegment]:
    """The claim's own segments plus nearby ones, in time order."""
    base = pool if pool else fused
    chosen: dict[str, ContextSegment] = {}
    for sid in claim.source_segment_ids:
        seg = base.get(sid) or fused.get(sid) or pool.get(sid)
        if seg:
            chosen[sid] = seg
    lo, hi = claim.start_seconds - window, claim.end_seconds + window
    nearby = [s for s in base.values() if s.end >= lo and s.start <= hi and s.segment_id not in chosen]
    mid = (claim.start_seconds + claim.end_seconds) / 2
    nearby.sort(key=lambda s: abs((s.start + s.end) / 2 - mid))
    for s in nearby[: max(0, MAX_CONTEXT_SEGMENTS - len(chosen))]:
        chosen[s.segment_id] = s
    return sorted(chosen.values(), key=lambda s: (s.start, s.segment_id))


def _clean(text: str) -> str:
    # §15 (T10): strip invisible characters and replace sentences that read as
    # instructions to the system before the model sees them; state keeps the original.
    text, _ = neutralise(text or "")
    text = _FENCE_RE.sub("", text)
    if len(text) > MAX_SEGMENT_CHARS:
        text = text[:MAX_SEGMENT_CHARS] + "…"
    return text


def render_user_message(claim: GraphClaim, segments: Iterable[ContextSegment]) -> str:
    lines = [
        json.dumps(
            {"id": s.segment_id, "source": s.modality, "start": s.start, "end": s.end, "text": _clean(s.text)},
            ensure_ascii=False,
        )
        for s in segments
    ]
    return (
        f"CLAIM (id {claim.claim_id}): {json.dumps(_clean(claim.claim_text), ensure_ascii=False)}\n"
        f"The claim was extracted from segments: {', '.join(claim.source_segment_ids) or 'none'}\n\n"
        "VIDEO SEGMENTS (untrusted content to analyse, one JSON object per line):\n"
        "<video_segments>\n" + "\n".join(lines) + "\n</video_segments>\n\n"
        f"Call {TOOL_NAME} with the speaker's stance toward the claim."
    )


def build_request(claim: GraphClaim, segments: list[ContextSegment]) -> dict:
    """The provider-neutral request body: messages plus a forced tool call."""
    return {
        "messages": [{"role": "user", "content": render_user_message(claim, segments)}],
        "tools": [STANCE_TOOL],
        "tool_choice": TOOL_CHOICE,
        "max_tokens": 512,
        "temperature": 0,
    }


# ------------------------------------------------------------------ parsing


class InvalidStanceOutput(ValueError):
    pass


def parse_output(output: Any, allowed_ids: set[str]) -> StanceToolOutput:
    """Validate the tool input. Raises ``InvalidStanceOutput`` on anything off-schema."""
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError as exc:
            raise InvalidStanceOutput("output is not JSON") from exc
    if not isinstance(output, dict):
        raise InvalidStanceOutput(f"output is {type(output).__name__}, not a tool input object")
    try:
        parsed = StanceToolOutput.model_validate(output)
    except ValidationError as exc:
        raise InvalidStanceOutput(f"schema: {exc.errors()[0].get('msg', 'invalid')}") from exc
    unknown = [s for s in parsed.stance_segment_ids if s not in allowed_ids]
    if unknown:
        raise InvalidStanceOutput(f"cited segment ids not in the input: {unknown}")
    return parsed


def _fallback_ids(claim: GraphClaim, segments: list[ContextSegment]) -> list[str]:
    """Segments to cite for an UNCLEAR fallback: the claim's own, if present in the input."""
    present = {s.segment_id for s in segments}
    own = [sid for sid in claim.source_segment_ids if sid in present]
    if own:
        return own
    if segments:
        return [segments[0].segment_id]
    return list(claim.source_segment_ids)  # no input at all; recorded as an error


def _record_meta(result: Any) -> tuple[Optional[str], Optional[str]]:
    rec = getattr(result, "record", None)
    return getattr(rec, "model", None), getattr(rec, "prompt_version", None)


# ------------------------------------------------------------------ node


def analyze_claim(
    claim: GraphClaim,
    segments: list[ContextSegment],
    caller: StepCaller,
    system_prompt: str,
    prompt_version: str,
) -> tuple[StanceResult, Optional[NodeError]]:
    allowed = {s.segment_id for s in segments}

    def unclear(reason: str, *, retryable: bool, model: Optional[str] = None) -> tuple[StanceResult, NodeError]:
        return (
            StanceResult(
                claim_id=claim.claim_id,
                stance=Stance.UNCLEAR,
                stance_segment_ids=_fallback_ids(claim, segments),
                rationale=f"stance not determined: {reason}"[:MAX_RATIONALE_CHARS],
                confidence=None,
                model=model,
                prompt_version=prompt_version,
            ),
            NodeError(node=r.ANALYZE_STANCE, message=reason, claim_id=claim.claim_id, retryable=retryable),
        )

    if not segments:
        return unclear("no input segments for this claim", retryable=False)

    try:
        result = caller.call(STEP, build_request(claim, segments), system=system_prompt)
    except Exception as exc:  # routing errors, provider errors: never guess
        return unclear(f"model call failed: {type(exc).__name__}: {exc}", retryable=True)

    model, recorded_prompt = _record_meta(result)
    try:
        parsed = parse_output(getattr(result, "output", None), allowed)
    except InvalidStanceOutput as exc:
        return unclear(f"invalid model output: {exc}", retryable=False, model=model)

    return (
        StanceResult(
            claim_id=claim.claim_id,
            stance=parsed.stance,
            stance_segment_ids=parsed.stance_segment_ids,
            rationale=parsed.rationale.strip()[:MAX_RATIONALE_CHARS],
            confidence=None,  # uncalibrated (§5, §11)
            model=model,
            prompt_version=recorded_prompt or prompt_version,
        ),
        None,
    )


def resolve_prompt_version(caller: StepCaller, prompt_version: Optional[str]) -> str:
    if prompt_version:
        return prompt_version
    route = getattr(caller, "route", None)
    if callable(route):
        try:
            return route(STEP).prompt
        except Exception:
            pass
    return DEFAULT_PROMPT_VERSION


def make_analyze_stance(caller: StepCaller, *, prompt_version: Optional[str] = None):
    """Build the ``analyze_stance`` node. Pass it to ``build_graph({ANALYZE_STANCE: ...})``.

    The prompt version comes from the routing config (``caller.route(step).prompt``) when
    the caller exposes it; the prompt file must exist, checked here so a bad config fails
    at start-up, not mid-run.
    """
    version = resolve_prompt_version(caller, prompt_version)
    system_prompt = load_prompt(version)

    def analyze_stance(state: PipelineState) -> dict:
        pool, fused = _pool(state), _fused_pool(state)
        results: dict[str, StanceResult] = {}
        errors: list[NodeError] = []
        for claim in state.get("claims", []) or []:
            segments = context_for_claim(claim, pool, fused)
            stance, err = analyze_claim(claim, segments, caller, system_prompt, version)
            results[claim.claim_id] = stance
            if err:
                errors.append(err)
        update: dict = {"stance_results": results}
        if errors:
            update["errors"] = errors
        return update

    return analyze_stance
