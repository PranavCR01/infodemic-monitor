"""Model helpers for search planning (T50 items c and h; design §6 step 3, §13, §15).

- ``ModelSearchAssistant``: when the rules fall back to keywords, a cheap model (the
  ``plan_search`` step in ``config/routing.yaml``) writes a structured query:
  intervention, outcome and population, each as a MeSH heading plus [tiab] synonyms.
- ``ModelTranslator``: a non-English claim is translated to English before planning
  (the ``translate_claim`` step).

Both outputs are untrusted text (§15): every heading and synonym is sanitised and
checked against the planner's stop words and conversational filler, so the model can
neither inject query syntax nor reintroduce words like ``didn't`` or ``47``. Neither
ever supplies an identifier. Both are optional: with no route configured, or when the
call fails, planning runs on the rules alone.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.retrieval.planning import (
    _CONVERSATIONAL,
    _STOPWORDS,
    PlannedQuery,
    _and,
    _or,
    _quote,
    sanitize_query,
    sanitize_text,
)

PLAN_SEARCH_STEP = "plan_search"
TRANSLATE_STEP = "translate_claim"
SEARCH_TOOL_NAME = "search_terms"
MAX_TERMS_PER_SIDE = 3
MAX_SYNONYMS = 3
_TERM_RE = re.compile(r"^[\w][\w\s,'\-()/.+]{0,79}$", re.UNICODE)
_ID_RE = re.compile(r"\b(?:pmid|doi|10\.\d{4,9}/|https?:)", re.IGNORECASE)


class TermSpec(BaseModel):
    mesh: Optional[str] = None
    tiab: list[str] = Field(default_factory=list)


class AssistedQuery(BaseModel):
    intervention: list[TermSpec] = Field(default_factory=list)
    outcome: list[TermSpec] = Field(default_factory=list)
    population: list[TermSpec] = Field(default_factory=list)


_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "mesh": {"type": ["string", "null"], "description": "Exact MeSH heading, or null if unsure."},
        "tiab": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_SYNONYMS,
                 "description": "Short English synonyms searched in title/abstract."},
    },
    "required": ["mesh", "tiab"],
    "additionalProperties": False,
}
SEARCH_TOOL: dict = {
    "name": SEARCH_TOOL_NAME,
    "description": "PubMed search terms for the claim, by PICO side.",
    "input_schema": {
        "type": "object",
        "properties": {side: {"type": "array", "items": _SPEC_SCHEMA, "maxItems": MAX_TERMS_PER_SIDE}
                       for side in ("intervention", "outcome", "population")},
        "required": ["intervention", "outcome", "population"],
        "additionalProperties": False,
    },
}


def clean_term(term: Any) -> Optional[str]:
    """One untrusted term, or None if it is unusable: not a string, too long, query
    syntax or identifiers in it, or nothing left but stop words, filler and numbers."""
    if not isinstance(term, str):
        return None
    t = sanitize_text(term, 80).replace('"', "").replace("[", " ").replace("]", " ")
    t = re.sub(r"\s+", " ", t).strip(" ,.-")
    if not t or _ID_RE.search(t) or not _TERM_RE.match(t):
        return None
    if re.search(r"(?<![\w])(AND|OR|NOT)(?![\w])", t):
        return None
    words = [w.lower().strip("'.,()") for w in t.split()]
    meaningful = [w for w in words if w and w not in _STOPWORDS and w not in _CONVERSATIONAL
                  and not w.replace(".", "").isdigit()]
    if not meaningful:
        return None
    return t


def _spec_clause(spec: TermSpec) -> str:
    parts: list[str] = []
    mesh = clean_term(spec.mesh) if spec.mesh else None
    if mesh:
        parts.append(f"{_quote(mesh)}[MeSH Terms]")
    for syn in spec.tiab[:MAX_SYNONYMS]:
        s = clean_term(syn)
        if s:
            clause = f"{_quote(s.lower())}[tiab]"
            if clause not in parts:
                parts.append(clause)
    return _or(parts) if parts else ""


def assisted_rungs(raw: Any) -> list[PlannedQuery]:
    """The assistant's output as ladder rungs, narrow to broad: I∧O∧P, I∧O, then the
    intervention (or outcome) alone. Legacy plain strings become one sanitised rung each."""
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        out = []
        for x in raw[:3]:
            words = [w for w in (clean_term(t) for t in x.split()) if w]
            q = sanitize_query(" ".join(words))
            if q:
                out.append(PlannedQuery(q, "assistant"))
        return out
    aq = raw if isinstance(raw, AssistedQuery) else AssistedQuery.model_validate(raw)
    side = lambda specs: _and([c for c in (_spec_clause(s) for s in specs[:MAX_TERMS_PER_SIDE]) if c])  # noqa: E731
    i, o, p = side(aq.intervention), side(aq.outcome), side(aq.population)
    rungs: list[str] = []
    if i and o:
        if p:
            rungs.append(_and([i, o, p]))
        rungs += [_and([i, o]), i]
    elif i or o:
        if p:
            rungs.append(_and([i or o, p]))
        rungs.append(i or o)
    out, seen = [], set()
    for q in rungs:
        q = sanitize_query(q)
        if q and q not in seen:
            seen.add(q)
            out.append(PlannedQuery(q, "assistant"))
    return out


def _prompt(version: str) -> str:
    from app.core.graph.stance import load_prompt

    return load_prompt(version)


class ModelSearchAssistant:
    """``SearchAssistant`` over the router's ``plan_search`` step."""

    def __init__(self, caller: Any):
        self.caller = caller
        self.system = _prompt(caller.config.route(PLAN_SEARCH_STEP).prompt)

    def __call__(self, claim_text: str) -> Optional[AssistedQuery]:
        body = {
            "messages": [{"role": "user", "content":
                          "CLAIM (untrusted text to analyse):\n<claim>\n"
                          + sanitize_text(claim_text, 600) + "\n</claim>\n\n"
                          f"Call {SEARCH_TOOL_NAME} with the search terms."}],
            "tools": [SEARCH_TOOL],
            "tool_choice": {"type": "tool", "name": SEARCH_TOOL_NAME},
            "max_tokens": 400,
            "temperature": 0,
        }
        out = self.caller.call(PLAN_SEARCH_STEP, body, system=self.system).output
        if not isinstance(out, dict):
            return None
        try:
            return AssistedQuery.model_validate(out)
        except ValidationError:
            return None


class ModelTranslator:
    """``Translator`` over the router's ``translate_claim`` step."""

    def __init__(self, caller: Any):
        self.caller = caller
        self.system = _prompt(caller.config.route(TRANSLATE_STEP).prompt)

    def __call__(self, claim_text: str, language: str) -> str:
        body = {
            "messages": [{"role": "user", "content":
                          f"Language: {re.sub(r'[^a-z]', '', language)[:3]}\nCLAIM (untrusted text to translate):\n"
                          "<claim>\n" + sanitize_text(claim_text, 600) + "\n</claim>"}],
            "max_tokens": 200,
            "temperature": 0,
        }
        out = self.caller.call(TRANSLATE_STEP, body, system=self.system).output
        return sanitize_text(out if isinstance(out, str) else "", 500)


def has_route(caller: Any, step: str) -> bool:
    cfg = getattr(caller, "config", None)
    return bool(cfg is not None and step in getattr(cfg, "steps", {}))


__all__ = [
    "AssistedQuery", "ModelSearchAssistant", "ModelTranslator", "PLAN_SEARCH_STEP", "SEARCH_TOOL",
    "TRANSLATE_STEP", "TermSpec", "assisted_rungs", "clean_term", "has_route",
]
