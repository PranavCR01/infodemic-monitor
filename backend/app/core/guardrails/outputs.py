"""Structured-output checks for LLM steps (§15 "Structure limits damage").

A model's answer is data. It is parsed into a strict schema (fixed label sets,
unknown fields rejected, no free text), and every ID it cites is checked against
the IDs the step was shown. Nothing a model returns is ever executed or fetched.

``OutputViolation`` means the answer is unusable; the node records a guardrail
error and takes the safe default (stance UNCLEAR, verdict INSUFFICIENT_EVIDENCE,
critic ESCALATE), which also routes the run to review.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.graph.state import CriticDecision, Stance, Verdict
from app.core.text_tokens import word_tokens

MAX_TEXT_FIELD = 2000
MAX_LIST = 50
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


class OutputViolation(ValueError):
    """The model's answer broke the output contract."""

    def __init__(self, step: str, reason: str):
        super().__init__(f"{step}: {reason}")
        self.step = step
        self.reason = reason


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _no_urls(v: str) -> str:
    # Citations come from the retrieval tool; a URL in free text is either a
    # fabricated source or an attempt to make something downstream fetch it.
    if _URL.search(v or ""):
        raise ValueError("free-text fields may not contain URLs")
    return v


class ExtractedClaim(_Out):
    claim_text: str = Field(min_length=3, max_length=500)
    claim_category: str = Field(default="other", max_length=64)
    source_segment_ids: list[str] = Field(min_length=1, max_length=MAX_LIST)
    requires_verification: bool = True
    # §4 (T17). Free string here; the extractor keeps it only when it is a known kind
    # and otherwise decides with fixed rules, so a bad value costs no repair round.
    claim_kind: Optional[str] = Field(default=None, max_length=32)


class ExtractionOutput(_Out):
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=200)


class StanceOutput(_Out):
    stance: Stance
    stance_segment_ids: list[str] = Field(default_factory=list, max_length=MAX_LIST)
    rationale: str = Field(default="", max_length=MAX_TEXT_FIELD)

    _r = field_validator("rationale")(_no_urls)


class VerificationOutput(_Out):
    verdict: Verdict
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_LIST)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_LIST)
    explanation: str = Field(default="", max_length=MAX_TEXT_FIELD)
    limitations: list[str] = Field(default_factory=list, max_length=20)

    _e = field_validator("explanation")(_no_urls)


class CriticOutput(_Out):
    decision: CriticDecision
    issues: list[str] = Field(default_factory=list, max_length=20)
    suggested_queries: list[str] = Field(default_factory=list, max_length=5)
    requires_review: bool = False


class ExplanationOutput(_Out):
    explanation: str = Field(max_length=MAX_TEXT_FIELD)

    _e = field_validator("explanation")(_no_urls)


OUTPUT_SCHEMAS: dict[str, type[_Out]] = {
    "extract_claims": ExtractionOutput,
    "analyze_stance": StanceOutput,
    "verify_claims": VerificationOutput,
    "critique": CriticOutput,
    "judge_explanation": ExplanationOutput,
}


def parse_output(step: str, raw: Any, schema: Optional[type[_Out]] = None) -> _Out:
    """Parse a model answer into ``schema`` (default: the step's schema).

    Accepts the dict a forced tool call returns, or a JSON object string. Free text,
    arrays, unknown fields and out-of-set labels are violations; nothing is coerced
    into a label.
    """
    schema = schema or OUTPUT_SCHEMAS.get(step)
    if schema is None:
        raise OutputViolation(step, "no output schema registered for this step")
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raise OutputViolation(step, "answer is free text, not a JSON object") from None
    if not isinstance(raw, dict):
        raise OutputViolation(step, f"answer is {type(raw).__name__}, not an object")
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ())) or "<root>"
        raise OutputViolation(step, f"schema violation at {loc}: {first.get('msg')}") from None


# --------------------------------------------------------- citation checks


def split_citations(cited: list[str], allowed: set[str] | frozenset[str]) -> tuple[list[str], list[str]]:
    """``(valid, fabricated)``, keeping order and dropping duplicates."""
    valid, fabricated = [], []
    for c in dict.fromkeys(cited):
        (valid if c in allowed else fabricated).append(c)
    return valid, fabricated


def check_verification(
    out: VerificationOutput, allowed_ids: set[str] | frozenset[str]
) -> tuple[VerificationOutput, list[str]]:
    """Drop cited IDs that weren't retrieved. A SUPPORTED, CONTRADICTED or MIXED
    verdict left without the citations it needs becomes INSUFFICIENT_EVIDENCE: a
    verdict the evidence can't be shown to back isn't kept.

    Returns the cleaned output and the fabricated IDs.
    """
    sup, fab_s = split_citations(out.supporting_evidence_ids, allowed_ids)
    con, fab_c = split_citations(out.contradicting_evidence_ids, allowed_ids)
    fabricated = fab_s + [f for f in fab_c if f not in fab_s]
    verdict = out.verdict
    needs = {
        Verdict.SUPPORTED: bool(sup),
        Verdict.CONTRADICTED: bool(con),
        Verdict.MIXED: bool(sup) and bool(con),
    }
    limitations = list(out.limitations)
    if verdict in needs and not needs[verdict]:
        verdict = Verdict.INSUFFICIENT_EVIDENCE
        limitations.append("verdict downgraded: its citations did not match retrieved evidence")
    elif fabricated:
        limitations.append("citations to evidence that was not retrieved were removed")
    cleaned = out.model_copy(update={
        "verdict": verdict, "supporting_evidence_ids": sup,
        "contradicting_evidence_ids": con, "limitations": limitations,
    })
    return cleaned, fabricated


def check_segment_citations(
    cited: list[str], allowed_ids: set[str] | frozenset[str]
) -> tuple[list[str], list[str]]:
    return split_citations(cited, allowed_ids)


_STOP = frozenset(
    "a an the and or of to in on for with is are be was were it this that these those "
    "your you my our i we they he she its as at by from".split()
)


def grounding_overlap(claim_text: str, source_text: str) -> float:
    """Share of the claim's content words that appear in its cited source text.

    Extraction must "quote, don't invent" (§4). A claim with little overlap with the
    segments it cites was not taken from them.

    Words are Unicode-aware (``app.core.text_tokens``, T45): before T45 only ASCII
    letters counted, so a Hindi claim scored 0.0 even against itself and was dropped.
    """
    words = [w for w in word_tokens(claim_text) if w not in _STOP]
    if not words:
        return 0.0
    source = set(word_tokens(source_text))
    return sum(1 for w in words if w in source) / len(words)
