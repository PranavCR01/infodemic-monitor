"""Claim context: judge each claim as meant in its video (T70; design §4, §6, §7, §9).

Switch: ``routing.CLAIM_CONTEXT`` (default OFF). With it off nothing here is called and
every request, state field and output is byte-identical to before T70.

Trigger: tune v135 (labmuffin benzene, golden NO_MISINFO) came out MISINFO in production
jobs cf2ea579, f85f2daa and 008c97a3, each decided by "Benzene doesn't get through skin
easily". The video means a thin layer of benzoyl-peroxide cream with 2-20 ppm benzene; the
verifier judged the bare sentence against occupational solvent-on-hands reviews. What was
missing is context stated elsewhere in the video (the on-screen "1 application = 0.5-1.0 g"
card, "acne products"), which a same-sentence qualifier (extract_v4 rule 3) cannot carry.

What this module holds (code; the model only proposes):

- **The extract_v5 output schema.** Each claim may carry ``context``: ``subject`` (the
  product or thing), ``exposure`` (route or setting), ``amount`` (dose), ``population``,
  ``outcome`` (the condition a vague claim refers to; supersedes T64(d)) and ``scope``
  (``specific`` / ``universal``). Each item cites block IDs. The first window also returns
  a one-line ``video_topic`` with its block IDs.
- **Grounding.** An item is kept only if every block it cites is in the SEGMENT INDEX and
  at least half of its content words appear in those blocks (the claim grounding rule,
  ``MIN_GROUNDING``). Anything else is dropped and named in ``ClaimContext.dropped``. The
  topic is grounded the same way, else not stored.
- **Scope guardrail.** ``scope`` is ``specific`` only when the model said so AND at least
  one item survived grounding. Everything else is ``universal``, and a universal claim is
  judged as stated: the verifier sees no context, the planner adds none, and no
  context-derived code (setting mismatch, softening) is kept for it. "Vaccines cause
  autism" is universal however much the video talks about one child.
- **Rendering.** The verifier's fenced context block, the planner's search hint and the
  report's "In context: ..." line all come from the grounded items only.
"""
from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping, Optional

from pydantic import Field

from app.core.graph import routing as r
from app.core.graph.state import CONTEXT_FIELDS, ClaimContext, ContextItem, VideoTopic
from app.core.guardrails.outputs import _Out, grounding_overlap

MIN_GROUNDING = 0.5  # same threshold as a claim's own grounding (claims.MIN_GROUNDING)
MAX_ITEM_CHARS = 200
MAX_TOPIC_CHARS = 200
CONTEXT_PROMPTS = frozenset({"extract_v5"})  # extraction prompts that ask for context
VERIFY_CONTEXT_PROMPTS = frozenset({"verify_v4"})  # verifier prompts that read it

FIELD_LABELS = {
    "subject": "subject or product",
    "exposure": "exposure route or setting",
    "amount": "amount or dose",
    "population": "population",
    "outcome": "condition or outcome",
}


# ------------------------------------------------------------------ model output (strict)


class ExtractedContextItem(_Out):
    text: str = Field(min_length=1, max_length=MAX_ITEM_CHARS)
    source_segment_ids: list[str] = Field(default_factory=list, max_length=20)


class ExtractedContext(_Out):
    subject: Optional[ExtractedContextItem] = None
    exposure: Optional[ExtractedContextItem] = None
    amount: Optional[ExtractedContextItem] = None
    population: Optional[ExtractedContextItem] = None
    outcome: Optional[ExtractedContextItem] = None
    scope: Literal["specific", "universal"] = "universal"


class ExtractedClaimV5(_Out):
    """``ExtractedClaim`` (T10) plus ``context``. Same fields and limits otherwise."""

    claim_text: str = Field(min_length=3, max_length=500)
    claim_category: str = Field(default="other", max_length=64)
    source_segment_ids: list[str] = Field(min_length=1, max_length=50)
    requires_verification: bool = True
    claim_kind: Optional[str] = Field(default=None, max_length=32)
    context: Optional[ExtractedContext] = None


class ExtractionOutputV5(_Out):
    claims: list[ExtractedClaimV5] = Field(default_factory=list, max_length=200)
    video_topic: Optional[ExtractedContextItem] = None


# ------------------------------------------------------------------ tool schema

_ITEM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "The video's own words for this item."},
        "source_segment_ids": {
            "type": "array", "items": {"type": "string"},
            "description": "Block IDs from the SEGMENT INDEX where the video states this item.",
        },
    },
    "required": ["text", "source_segment_ids"],
    "additionalProperties": False,
}
CONTEXT_SCHEMA: dict = {
    "type": "object",
    "description": "What the claim means in this video, from anywhere in the video. Leave out any "
                   "item the video does not state.",
    "properties": {
        "subject": {**_ITEM_SCHEMA, "description": "The product or thing the claim is about."},
        "exposure": {**_ITEM_SCHEMA, "description": "Exposure route or setting (on skin, inhaled, "
                                                    "eaten, at work ...)."},
        "amount": {**_ITEM_SCHEMA, "description": "Amount, dose or concentration."},
        "population": {**_ITEM_SCHEMA, "description": "Who the claim is about."},
        "outcome": {**_ITEM_SCHEMA, "description": "The condition or outcome a vague claim refers to."},
        "scope": {"type": "string", "enum": ["specific", "universal"],
                  "description": "specific: the video means the claim only in this context; "
                                 "universal: it is asserted generally."},
    },
    "required": ["scope"],
    "additionalProperties": False,
}
TOPIC_SCHEMA: dict = {**_ITEM_SCHEMA, "description": "The video's topic in one line, with the blocks it "
                                                     "comes from."}


def extract_tool_v5(base: dict, *, ask_topic: bool) -> dict:
    """``base`` (the record_claims tool for the prompt's categories) with ``context`` per
    claim and, in the first window only, ``video_topic``."""
    schema = base["input_schema"]
    item = schema["properties"]["claims"]["items"]
    props = {**schema["properties"],
             "claims": {**schema["properties"]["claims"],
                        "items": {**item, "properties": {**item["properties"], "context": CONTEXT_SCHEMA}}}}
    if ask_topic:
        props["video_topic"] = TOPIC_SCHEMA
    return {**base, "input_schema": {**schema, "properties": props}}


def topic_instruction(topic: Optional[VideoTopic], *, ask_topic: bool) -> str:
    if ask_topic:
        return ("\nAlso give video_topic: the video's topic in one line, in the video's words, citing "
                "the blocks it comes from. Read each claim's context against that topic.\n")
    if topic is not None:
        # The topic itself is in a fenced block (it is video words a model picked).
        return ("\nThe video's topic, found at the start of the video, is in the fenced block with id "
                "\"video_topic\". Read each claim's context against it.\n")
    return ""


def _plain(text: str) -> str:
    return " ".join(str(text).replace('"', "'").split())[:MAX_TOPIC_CHARS]


# ------------------------------------------------------------------ grounding


def _ground_item(item: Optional[ExtractedContextItem], blocks: Mapping[str, dict]) -> Optional[ContextItem]:
    if item is None:
        return None
    cited = list(dict.fromkeys(item.source_segment_ids))
    if not cited or any(b not in blocks for b in cited):
        return None
    source = " ".join(blocks[b]["text"] for b in cited)
    if grounding_overlap(item.text, source) < MIN_GROUNDING:
        return None
    pieces = list(dict.fromkeys(p for b in cited for p in blocks[b]["pieces"]))
    return ContextItem(text=item.text, segment_ids=pieces)


def ground_context(claim_id: str, raw: Optional[ExtractedContext], blocks: Mapping[str, dict]) -> ClaimContext:
    """The grounded context of one claim. Ungrounded items are dropped and named; the
    scope is ``specific`` only with at least one grounded item."""
    if raw is None:
        return ClaimContext(claim_id=claim_id)
    kept: dict[str, ContextItem] = {}
    dropped: list[str] = []
    for f in CONTEXT_FIELDS:
        given = getattr(raw, f)
        if given is None:
            continue
        grounded = _ground_item(given, blocks)
        if grounded is None:
            dropped.append(f)
        else:
            kept[f] = grounded
    scope = "specific" if raw.scope == "specific" and kept else "universal"
    return ClaimContext(claim_id=claim_id, scope=scope, dropped=dropped, **kept)


def ground_topic(raw: Optional[ExtractedContextItem], blocks: Mapping[str, dict]) -> Optional[VideoTopic]:
    item = _ground_item(raw, blocks)
    return VideoTopic(text=item.text, segment_ids=item.segment_ids) if item else None


# ------------------------------------------------------------------ reading it back


def is_specific(ctx: Optional[ClaimContext]) -> bool:
    return bool(ctx is not None and ctx.scope == "specific" and ctx.items())


def context_of(state: Mapping[str, Any], claim_id: str) -> Optional[ClaimContext]:
    """The claim's context when the switch is on and the claim is specific; else None
    (a universal claim is judged as stated)."""
    if not r.CLAIM_CONTEXT:
        return None
    ctx = (state.get("claim_contexts") or {}).get(claim_id)
    return ctx if is_specific(ctx) else None


def context_line(ctx: Optional[ClaimContext]) -> Optional[str]:
    """``In context: ...`` for the report, from grounded items only; None when the claim
    is universal or has none."""
    if not is_specific(ctx):
        return None
    parts = [f"{FIELD_LABELS[f]}: {_plain(i.text)}" for f, i in ctx.items()]
    return "In context: " + "; ".join(parts) + "."


def verifier_block(ctx: ClaimContext, topic: Optional[VideoTopic]) -> str:
    """The text of the verifier's fenced context block (untrusted video words)."""
    lines = []
    if topic is not None:
        lines.append(f"Video topic: {_plain(topic.text)}")
    lines += [f"{FIELD_LABELS[f].capitalize()}: {_plain(i.text)}" for f, i in ctx.items()]
    return "\n".join(lines)


def planner_hint(ctx: Optional[ClaimContext]) -> tuple[tuple[str, str], ...]:
    """``(field, text)`` pairs the query planner may use; empty for universal claims."""
    if not is_specific(ctx):
        return ()
    return tuple((f, i.text) for f, i in ctx.items())


def setting_match_of(limitations: Iterable[str]) -> Optional[str]:
    """The verifier's setting_match, from its limitation code (T70), or None."""
    prefix = r.SETTING_MATCH_LIMITATION + ":"
    for x in limitations or ():
        if isinstance(x, str) and x.startswith(prefix) and x[len(prefix):] in ("same", "partial", "different"):
            return x[len(prefix):]
    return None


def is_context_code(text: str) -> bool:
    """Structured codes T69 / T70 store in ``limitations``: for code, not for readers."""
    if not isinstance(text, str):
        return False
    if text == r.SOFTENED_LIMITATION:
        return True
    head, sep, tail = text.partition(":")
    if not sep:
        return False
    if head == r.SETTING_MATCH_LIMITATION:
        return tail in ("same", "partial", "different")
    return head == r.CONTEXT_MISMATCH_LIMITATION and tail in r.CONTEXT_MISMATCH_KINDS


def context_payload(ctx: Optional[ClaimContext], topic: Optional[VideoTopic]) -> Optional[dict]:
    """What persistence stores with the claim (inside its search-trail JSON, as T65 (f)
    stores source_meta: no migration). None when there is nothing to store."""
    if ctx is None and topic is None:
        return None
    out: dict = {}
    if ctx is not None:
        out.update(ctx.model_dump(exclude={"claim_id"}, exclude_none=True))
    if topic is not None:
        out["video_topic"] = topic.model_dump()
    return out


def payload_context(raw: Optional[Mapping[str, Any]]) -> tuple[Optional[ClaimContext], Optional[VideoTopic]]:
    """Read :func:`context_payload` back; anything that no longer parses is ignored."""
    if not isinstance(raw, Mapping):
        return None, None
    try:
        topic = VideoTopic.model_validate(raw["video_topic"]) if raw.get("video_topic") else None
    except ValueError:
        topic = None
    try:
        body = {k: v for k, v in raw.items() if k != "video_topic"}
        ctx = ClaimContext.model_validate({"claim_id": "", **body}) if body else None
    except ValueError:
        ctx = None
    return ctx, topic


def check_prompts(extract_version: Optional[str] = None, verify_version: Optional[str] = None) -> None:
    """With the switch on, a prompt that can't carry context is a configuration error,
    caught when the node is built (as a missing prompt file is)."""
    if not r.CLAIM_CONTEXT:
        return
    if extract_version is not None and extract_version not in CONTEXT_PROMPTS:
        raise ValueError(f"routing.CLAIM_CONTEXT is on but extract_claims routes to {extract_version!r}; "
                         f"route it to one of {sorted(CONTEXT_PROMPTS)} in config/routing.yaml")
    if verify_version is not None and verify_version not in VERIFY_CONTEXT_PROMPTS:
        raise ValueError(f"routing.CLAIM_CONTEXT is on but verify_claims routes to {verify_version!r}; "
                         f"route it to one of {sorted(VERIFY_CONTEXT_PROMPTS)} in config/routing.yaml")


__all__ = [
    "CONTEXT_PROMPTS", "VERIFY_CONTEXT_PROMPTS", "ExtractionOutputV5", "extract_tool_v5",
    "topic_instruction", "ground_context", "ground_topic", "context_of", "context_line",
    "verifier_block", "planner_hint", "setting_match_of", "is_context_code", "context_payload",
    "payload_context", "check_prompts", "is_specific",
]
