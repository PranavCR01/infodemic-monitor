"""Rule-based ``claim_kind`` (§4), the fallback when the extractor gives none.

Claim extraction asks the model for ``claim_kind``: ``research_question`` (does X work,
does X cause Y) or ``fact_of_record`` (a schedule, a legal limit, a statistic, a basic
physiological fact). When the model leaves it out or returns something else, these
fixed rules decide, and when they can't tell, the claim stays a research question, which
keeps today's PubMed-only retrieval for it.
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.retrieval.planning import normalize_claim
from app.core.retrieval.schemas import CLAIM_KINDS, ClaimKind

RESEARCH_QUESTION: ClaimKind = "research_question"
FACT_OF_RECORD: ClaimKind = "fact_of_record"


def _cue(*patterns: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])(?:" + "|".join(patterns) + r")(?![\w-])")


# Efficacy and causation: "does X work / cause Y".
_RESEARCH = _cue(
    r"cure[sd]?", r"curing", r"treats?", r"heals?", r"prevents?", r"protects? against", r"boosts?",
    r"causes?", r"caused", r"leads? to", r"gives? you", r"kills?", r"fights?", r"works?", r"helps?",
    r"reduces? (?:the )?risk", r"increases? (?:the )?risk", r"detox\w*", r"reverses?", r"improves?",
    r"lowers?", r"raises?", r"linked to", r"cuts?", r"reduces?", r"increases?", r"decreases?",
    r"slash(?:es)?", r"stops?", r"blocks?", r"strengthens?", r"weakens?", r"damages?", r"destroys?", r"is good for", r"is bad for", r"makes? you",
)
_SCHEDULE = _cue(
    r"schedule", r"(?:first|second|third|booster) dose", r"\d+ doses?", r"doses? (?:at|by|before)",
    r"at \d+ (?:months?|weeks?|years?)(?: old| of age)?", r"recommended age", r"given at",
)
_LIMIT = _cue(
    r"legal limit", r"(?:upper|safe|daily|tolerable) (?:upper )?(?:limit|intake level)", r"limit (?:is|of)",
    r"maximum (?:daily|safe|recommended)", r"recommended (?:daily )?(?:intake|amount|allowance|dose)",
    r"rda", r"(?:fda|ema|efsa|who|cdc|nhs)[- ](?:approved|recommends?|says|limit|guidance)",
    r"(?:is|are|was|were) (?:approved|banned|licensed|authori[sz]ed)",
    r"no more than \d", r"up to \d+ ?(?:mg|g|mcg|µg|iu|milligrams?|grams?)",
)
# Counts of people, deaths or cases are statistics even with a verb ("measles kills
# 100,000 people every year"); a bare percentage is not ("cuts your risk by 50%").
_POPULATION_STATISTIC = _cue(
    r"(?:deaths|cases|people|children|adults|infections|births) (?:a|per|each|every) year",
    r"per (?:100,?000|1,?000|capita)", r"(?:leading|number one|top|second|third) (?:leading )?cause of death",
    r"(?:incidence|prevalence|mortality rate|death rate|life expectancy)",
)
_STATISTIC = _cue(
    r"\d+(?:\.\d+)? ?(?:%|percent|per cent)", r"\d+(?:[.,]\d+)? (?:million|billion|thousand)",
)
_COMPOSITION = _cue(
    r"contains? \d", r"per 100 ?(?:g|grams|ml)", r"\d+ ?(?:calories|kcal)",
    r"(?:grams?|mg|milligrams?) of (?:protein|sugar|fat|fiber|fibre|sodium|caffeine|vitamin \w+)",
    r"(?:is|are) (?:high|rich|low) in",
)
_PHYSIOLOGY = _cue(
    r"normal (?:body )?temperature", r"blood types?", r"(?:human )?body (?:is|has|contains|produces)",
    r"(?:the )?(?:heart|liver|kidneys?|brain|lungs?|pancreas|skin) (?:is|has|produces|pumps|filters|makes)",
    r"incubation period", r"half-life",
)
_FACT_CUES = (_SCHEDULE, _LIMIT, _STATISTIC, _COMPOSITION, _PHYSIOLOGY)


def infer_claim_kind(claim_text: str, claim_category: Optional[str] = None) -> ClaimKind:
    """``fact_of_record`` for statistics (by category or a population-count cue) and for
    claims with another fact-of-record cue and no efficacy or causation verb; otherwise
    ``research_question``."""
    if (claim_category or "").lower() == "statistic":
        return FACT_OF_RECORD
    text = normalize_claim(claim_text)
    if _POPULATION_STATISTIC.search(text):
        return FACT_OF_RECORD
    if _RESEARCH.search(text):
        return RESEARCH_QUESTION
    if any(c.search(text) for c in _FACT_CUES):
        return FACT_OF_RECORD
    return RESEARCH_QUESTION


def resolve_claim_kind(given: Optional[str], claim_text: str, claim_category: Optional[str] = None) -> ClaimKind:
    """The model's ``claim_kind`` when it is a valid value, else the rules'."""
    g = (given or "").strip().lower()
    if g in CLAIM_KINDS:
        return g  # type: ignore[return-value]
    return infer_claim_kind(claim_text, claim_category)
