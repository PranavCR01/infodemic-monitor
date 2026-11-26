"""Claim extractor node (target design §4; integration task T11, issue #38).

One LLM pass reads the fused timeline and returns each distinct, checkable health claim
exactly once, with pointers to the speech and caption pieces it came from.

How it fits:

- **Model choice comes from routing config.** Same ``StepCaller`` contract as the stance
  analyzer (T04) and the verifier (T06): step ``extract_claims``, prompt version from
  ``caller.route("extract_claims").prompt`` (default ``extract_v1``). No model id here.
- **Forced structured output.** The request carries the ``record_claims`` tool with a
  forced ``tool_choice``; the answer is parsed with T10's strict ``ExtractionOutput``.
- **Untrusted text is fenced** (§15) by T10's ``extraction_prompt`` builder: speech and
  each caption are separate blocks with timing in the header, not in the text.
- **Citations and grounding are checked in code.** A claim may cite only blocks it was
  shown; cited blocks map back to the transcript (``t*``) and OCR (``o*``) pieces, so
  ``source_segment_ids`` looks like the §4 example. A claim whose content words are
  mostly absent from its cited blocks ("quote, don't invent") is dropped with a
  ``guardrail:`` error, which sends the run to review.
- **Timestamps are computed, not asked for:** min start / max end of the cited pieces.
- **Malformed output gets one repair attempt** (§1 retries table), then the node keeps no
  claims and records a ``guardrail:`` error (review). A model that can't be reached is
  recorded with ``EXTRACTION_UNAVAILABLE`` in the message, ``retryable=True``; the
  graph provider treats that as a failed run and falls back to the single call (T11),
  because "no claims" would otherwise read as "no checkable health claims".
- **Long videos** (§4 probe) are passed in windows of ``window_seconds`` with
  ``overlap_seconds`` overlap; the dedup step merges claims found twice at the edges.
- **Dedup safety net (code).** §4 compares claims by embedding similarity. No embedding
  model is wired into the worker yet, so the default similarity is lexical (content
  words, negation-aware) with a high threshold; an embedding similarity can be injected
  as ``similarity``. When unsure, claims stay separate: a wrong merge hides a claim.
- **Claim cap.** T10's ``cap_claims`` (50 by default); dropped claims are recorded as a
  ``guardrail:`` error so the run goes to review.
- **claim_kind** (§4, T17): ``research_question`` or ``fact_of_record``, asked of the
  model (prompt ``extract_v2``); a missing or unknown value is decided by the fixed
  rules in ``app.core.retrieval.claim_kind``. Retrieval uses it to add authoritative
  references for facts of record (§6).
- **Evidence-strength statements** (T51): "the evidence for X is overwhelming", "these
  studies are observational" get ``claim_category = evidence_meta`` (prompt
  ``extract_v4``; and, for every prompt version, the fixed rules in
  ``app.core.claim_category``, which override the model). ``evidence_meta`` is not an
  efficacy category, so §7's UNSUPPORTED can never apply to them. The tool's category
  enum lists ``evidence_meta`` only from ``extract_v4`` on, so older prompts send the
  same request as before.
- Writes only ``claims`` (plus the shared, append-only ``errors``).
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Protocol, Sequence

from app.core.claim_category import EVIDENCE_META, resolve_claim_category
from app.core.graph import routing as r
from app.core.graph.stance import load_prompt
from app.core.graph.state import FusedSegment, GraphClaim, NodeError, PipelineState
from app.core.guardrails.config import GuardrailConfig, load_guardrails
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX
from app.core.guardrails.limits import cap_claims
from app.core.guardrails.outputs import ExtractionOutput, OutputViolation, grounding_overlap, parse_output
from app.core.guardrails.untrusted import (
    DEFAULT_MAX_BLOCK_CHARS,
    GuardedPrompt,
    extraction_prompt,
    guarded_system_prompt,
)
from app.core.retrieval.claim_kind import resolve_claim_kind
from app.core.retrieval.schemas import CLAIM_KINDS
from app.core.text_tokens import word_tokens

STEP = "extract_claims"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "extract_v2"  # v2 adds claim_kind (T17)
TOOL_NAME = "record_claims"
EXTRACTION_UNAVAILABLE = "EXTRACTION_UNAVAILABLE"

MIN_GROUNDING = 0.5  # same threshold as T10's adversarial harness
DEFAULT_WINDOW_SECONDS = 240.0
DEFAULT_OVERLAP_SECONDS = 20.0
DEDUP_THRESHOLD = 0.85
MAX_REPAIRS = 1

LEGACY_CATEGORIES = (
    "treatment_efficacy", "prevention", "causation", "safety", "diagnosis",
    "nutrition", "statistic", "other",
)
# T51: evidence_meta (statements about the state or strength of evidence). Every
# claim may carry it (the rules assign it whatever the prompt); the tool offers it to
# the model only from extract_v4 on.
CATEGORIES = (*LEGACY_CATEGORIES[:-1], EVIDENCE_META, "other")
# Prompt versions that describe evidence_meta and so get it in the tool's enum.
EVIDENCE_META_PROMPTS = frozenset({"extract_v4"})


def extract_tool(categories: Sequence[str] = LEGACY_CATEGORIES) -> dict:
    """The ``record_claims`` tool with the given category enum."""
    tool = {**EXTRACT_TOOL_BASE}
    schema = tool["input_schema"]
    item = schema["properties"]["claims"]["items"]
    props = {**item["properties"], "claim_category": {"type": "string", "enum": list(categories)}}
    tool["input_schema"] = {
        **schema,
        "properties": {"claims": {**schema["properties"]["claims"], "items": {**item, "properties": props}}},
    }
    return tool


def categories_for(prompt_version: Optional[str]) -> tuple[str, ...]:
    return CATEGORIES if prompt_version in EVIDENCE_META_PROMPTS else LEGACY_CATEGORIES


EXTRACT_TOOL_BASE: dict = {
    "name": TOOL_NAME,
    "description": "Record every distinct, checkable health claim in the video, citing block IDs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_text": {"type": "string", "description": "The claim, close to the original words."},
                        "claim_category": {"type": "string", "enum": list(LEGACY_CATEGORIES)},
                        "source_segment_ids": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Block IDs from the SEGMENT INDEX the claim comes from.",
                        },
                        "requires_verification": {"type": "boolean"},
                        "claim_kind": {
                            "type": "string", "enum": list(CLAIM_KINDS),
                            "description": "research_question (does X work / cause Y) or fact_of_record "
                                           "(a schedule, a legal limit, a statistic, a basic physiological fact).",
                        },
                    },
                    "required": ["claim_text", "claim_category", "source_segment_ids"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["claims"],
        "additionalProperties": False,
    },
}
EXTRACT_TOOL: dict = extract_tool(LEGACY_CATEGORIES)  # extract_v1..v3 (unchanged)
TOOL_CHOICE: dict = {"type": "tool", "name": TOOL_NAME}


class StepCaller(Protocol):
    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> Any: ...


Similarity = Callable[[str, str], float]


# ------------------------------------------------------------------ blocks


def block_sources(segments: Sequence[FusedSegment], piece_ids: set[str]) -> dict[str, dict]:
    """Map each fenced block ID (as ``extraction_prompt`` names them: ``f1`` for speech,
    ``f1.screen1`` for the first caption) to the transcript/OCR pieces it came from and
    its time range. ``piece_ids`` are the known ``t*``/``o*`` IDs; without them a block
    maps to its fused segment ID."""
    out: dict[str, dict] = {}
    for s in segments:
        speech = [x for x in s.sources if x in piece_ids and x.startswith("t")]
        captions = [x for x in s.sources if x in piece_ids and not x.startswith("t")]
        span = (s.start, s.end)
        if s.spoken:
            out[s.segment_id] = {"pieces": speech or [s.segment_id], "span": span, "kind": "speech",
                                 "text": s.spoken}
        for n, caption in enumerate(s.on_screen, start=1):
            piece = captions[n - 1] if n - 1 < len(captions) else s.segment_id
            out[f"{s.segment_id}.screen{n}"] = {"pieces": [piece], "span": span, "kind": "caption",
                                                "text": caption}
    return out


def segment_index(blocks: dict[str, dict]) -> str:
    lines = [f"- {bid}: {b['kind']}, {b['span'][0]:.1f}-{b['span'][1]:.1f}s" for bid, b in blocks.items()]
    return "\n".join(lines) or "(no segments)"


def _instructions(blocks: dict[str, dict], repair_note: Optional[str]) -> str:
    text = (
        "List the health claims in the fenced material.\n\n"
        f"SEGMENT INDEX (cite only these IDs):\n{segment_index(blocks)}\n"
    )
    if repair_note:
        text += (
            "\nYOUR PREVIOUS ANSWER WAS REJECTED by an automatic check: "
            f"{repair_note}\nAnswer again, following the output rules exactly.\n"
        )
    return text + f"\nCall {TOOL_NAME} with the list (empty if there are none)."


def build_prompt(
    segments: Sequence[FusedSegment], blocks: dict[str, dict], system_prompt: str,
    *, repair_note: Optional[str] = None, max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> GuardedPrompt:
    prompt = extraction_prompt(segments, task=_instructions(blocks, repair_note), max_chars=max_chars)
    return prompt.model_copy(update={
        "system": guarded_system_prompt(system_prompt),
        "citable_ids": frozenset(blocks),
    })


def build_request(prompt: GuardedPrompt, tool: Optional[dict] = None) -> dict:
    return {
        "messages": [{"role": "user", "content": prompt.render()}],
        "tools": [tool or EXTRACT_TOOL],
        "tool_choice": TOOL_CHOICE,
        "max_tokens": 2048,
        "temperature": 0,
    }


def windows(
    segments: Sequence[FusedSegment],
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
) -> list[list[FusedSegment]]:
    """Split the timeline into windows of ``window_seconds`` that overlap by
    ``overlap_seconds`` (§4 "long videos"). A short video is one window."""
    segs = sorted(segments, key=lambda s: (s.start, s.segment_id))
    if not segs:
        return []
    start, end = segs[0].start, max(s.end for s in segs)
    if end - start <= window_seconds:
        return [segs]
    step = max(1.0, window_seconds - overlap_seconds)
    out: list[list[FusedSegment]] = []
    w = start
    while w < end:
        chunk = [s for s in segs if s.end > w and s.start < w + window_seconds]
        if chunk and (not out or chunk != out[-1]):
            out.append(chunk)
        w += step
    return out


# ------------------------------------------------------------------ dedup

_NEGATIONS = frozenset({"no", "not", "never", "dont", "doesnt", "isnt", "cannot", "cant", "without", "nor"})
_STOP = frozenset(
    "a an the and or of to in on for with is are be was were it this that these those "
    "your you my our i we they he she its as at by from do does".split()
)


def _words(text: str) -> list[str]:
    # Unicode-aware since T45 (same tokens as the grounding guardrail); before, a
    # Devanagari claim had no words, so overlapping windows' copies never merged.
    return [w for w in word_tokens(text.replace("'", "")) if w not in _STOP]


def lexical_similarity(a: str, b: str) -> float:
    """Jaccard similarity of content words; 0 when one claim is negated and the other
    isn't ("X cures Y" vs "X does not cure Y" must never merge)."""
    wa, wb = _words(a), _words(b)
    if bool(_NEGATIONS & set(wa)) != bool(_NEGATIONS & set(wb)):
        return 0.0
    sa, sb = set(wa), set(wb)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def dedup_claims(
    claims: Sequence[GraphClaim], similarity: Similarity = lexical_similarity,
    threshold: float = DEDUP_THRESHOLD,
) -> tuple[list[GraphClaim], int]:
    """Merge claims that say the same thing (§4 safety net). The first one's text wins;
    sources are unioned and the span widened. Returns ``(claims, merged_count)``."""
    kept: list[GraphClaim] = []
    merged = 0
    for c in claims:
        for i, k in enumerate(kept):
            if similarity(c.claim_text, k.claim_text) >= threshold:
                kept[i] = k.model_copy(update={
                    "source_segment_ids": list(dict.fromkeys([*k.source_segment_ids, *c.source_segment_ids])),
                    "start_seconds": min(k.start_seconds, c.start_seconds),
                    "end_seconds": max(k.end_seconds, c.end_seconds),
                    "requires_verification": k.requires_verification or c.requires_verification,
                })
                merged += 1
                break
        else:
            kept.append(c)
    return kept, merged


# ------------------------------------------------------------------ node


def _gerr(kind: str, detail: str = "") -> NodeError:
    return NodeError(node=r.EXTRACT_CLAIMS, message=f"{GUARDRAIL_ERROR_PREFIX}{kind} {detail}".strip()[:500])


class _Rejected(ValueError):
    pass


def _parse(raw: Any, blocks: dict[str, dict]) -> ExtractionOutput:
    try:
        out = parse_output(STEP, raw, ExtractionOutput)
    except OutputViolation as exc:
        raise _Rejected(exc.reason) from None
    unknown = sorted({s for c in out.claims for s in c.source_segment_ids if s not in blocks})
    if unknown:
        raise _Rejected(f"cited block IDs that are not in the SEGMENT INDEX: {unknown[:10]}")
    return out  # type: ignore[return-value]


def extract_window(
    segments: Sequence[FusedSegment], piece_ids: set[str], caller: StepCaller,
    system_prompt: str, *, max_chars: int = DEFAULT_MAX_BLOCK_CHARS, max_repairs: int = MAX_REPAIRS,
    tool: Optional[dict] = None,
) -> tuple[list[GraphClaim], list[NodeError], bool]:
    """Claims from one window. Returns ``(claims, errors, unavailable)``; claim IDs are
    provisional and renumbered by the node."""
    blocks = block_sources(segments, piece_ids)
    errors: list[NodeError] = []
    repair_note: Optional[str] = None
    out: Optional[ExtractionOutput] = None
    for attempt in range(max_repairs + 1):
        prompt = build_prompt(segments, blocks, system_prompt, repair_note=repair_note, max_chars=max_chars)
        try:
            result = caller.call(STEP, build_request(prompt, tool), system=prompt.system)
        except Exception as exc:  # routing / provider errors
            errors.append(NodeError(
                node=r.EXTRACT_CLAIMS, retryable=True,
                message=f"{EXTRACTION_UNAVAILABLE}: model call failed: {type(exc).__name__}: {exc}"[:500],
            ))
            return [], errors, True
        try:
            out = _parse(getattr(result, "output", None), blocks)
            break
        except _Rejected as exc:
            if attempt < max_repairs:
                repair_note = str(exc)
                errors.append(NodeError(node=r.EXTRACT_CLAIMS, message=f"repair requested: {exc}"[:500]))
                continue
            errors.append(_gerr("output_rejected", str(exc)))
            return [], errors, False
    assert out is not None

    claims: list[GraphClaim] = []
    for item in out.claims:
        cited = list(dict.fromkeys(item.source_segment_ids))
        source_text = " ".join(blocks[b]["text"] for b in cited)
        if grounding_overlap(item.claim_text, source_text) < MIN_GROUNDING:
            errors.append(_gerr("claim_ungrounded", item.claim_text[:80]))
            continue
        pieces = list(dict.fromkeys(p for b in cited for p in blocks[b]["pieces"]))
        # T51: an evidence-strength statement is evidence_meta whatever the model said.
        category = resolve_claim_category(item.claim_category, item.claim_text, CATEGORIES)
        claims.append(GraphClaim(
            claim_id=f"w{len(claims) + 1}",
            claim_text=item.claim_text,
            claim_category=category,
            source_segment_ids=pieces,
            start_seconds=min(blocks[b]["span"][0] for b in cited),
            end_seconds=max(blocks[b]["span"][1] for b in cited),
            requires_verification=item.requires_verification,
            claim_kind=resolve_claim_kind(item.claim_kind, item.claim_text, category),
        ))
    return claims, errors, False


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


def _piece_ids(state: PipelineState) -> set[str]:
    ids = {t.segment_id for t in state.get("transcript_segments") or []}
    ids |= {o.segment_id for o in state.get("ocr_segments") or []}
    return ids


def make_extract_claims(
    caller: StepCaller,
    *,
    prompt_version: Optional[str] = None,
    guardrails: Optional[GuardrailConfig] = None,
    similarity: Similarity = lexical_similarity,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
) -> Callable[[PipelineState], dict]:
    """Build the ``extract_claims`` node. The prompt file is loaded here, so a bad
    routing config fails at start-up, not mid-run."""
    version = resolve_prompt_version(caller, prompt_version)
    system_prompt = load_prompt(version)
    tool = extract_tool(categories_for(version))
    g = guardrails or load_guardrails()

    def extract_claims(state: PipelineState) -> dict:
        segments = list(state.get("fused_segments") or [])
        if not segments:
            return {"claims": []}
        piece_ids = _piece_ids(state)
        found: list[GraphClaim] = []
        errors: list[NodeError] = []
        for window in windows(segments, window_seconds, overlap_seconds):
            claims, errs, unavailable = extract_window(
                window, piece_ids, caller, system_prompt, max_chars=g.input.max_segment_chars, tool=tool,
            )
            errors += errs
            if unavailable:
                # Partial claims would under-report the video; the provider falls back.
                return {"claims": [], "errors": errors}
            found += claims
        found.sort(key=lambda c: (c.start_seconds, c.end_seconds))
        found, _merged = dedup_claims(found, similarity)
        found = [c.model_copy(update={"claim_id": f"c{i}"}) for i, c in enumerate(found, start=1)]
        found, dropped = cap_claims(found, g.input)
        if dropped:
            errors.append(_gerr("claims_capped", f"{dropped} claims over the limit"))
        update: dict = {"claims": found}
        if errors:
            update["errors"] = errors
        return update

    return extract_claims


def extraction_unavailable(errors: Iterable[NodeError]) -> bool:
    """True when the extractor could not reach a model (the provider's fallback signal)."""
    return any(e.node == r.EXTRACT_CLAIMS and e.message.startswith(EXTRACTION_UNAVAILABLE) for e in errors)
