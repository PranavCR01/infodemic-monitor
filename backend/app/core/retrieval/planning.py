"""Retrieval planning: claim → PICO frame → PubMed queries (§6 "Planning the search").

Rules do all of the work by default:

1. ``normalize_claim`` lower-cases and strips punctuation and emoji.
2. ``frame_claim`` splits the claim at its claim verb ("cures", "causes", "prevents"…):
   concepts before the verb are the intervention, after it the outcome. Population
   ("in children") and comparator ("better than X") phrases are pulled out first.
   Concepts come from the MeSH lexicon (``mesh.py``).
3. ``QueryPlanner.ladder`` builds a list of queries from narrow to broad; round *n* of a
   claim's search uses the *n*-th distinct one (§6 "When nothing comes back"):

   - round 1: intervention AND outcome AND population, MeSH plus free-text synonyms;
   - round 2: the qualifiers and population dropped;
   - round 3: parent MeSH headings;
   - last resort: the claim's content words as free text, left to PubMed's Automatic
     Term Mapping.

An optional ``assistant`` (a small LLM, per §6 step 3 and §13 "Search planning") is
consulted only when the rules find no concept at all. Whatever it returns is treated as
plain search terms and sanitised like any other untrusted query text; it never supplies
identifiers. The assistant is injected by the caller, which picks the model from the
routing config; nothing here names a model.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional, Protocol

from app.core.retrieval.mesh import Match, find_concepts
from app.core.retrieval.schemas import ClaimFrame, Concept

MAX_QUERY_CHARS = 400

# Claim verbs, longest first. The text before the verb is the intervention side.
_CLAIM_VERBS = sorted(
    [
        "cures", "cure", "cured", "treats", "treat", "heals", "heal", "reverses", "reverse",
        "prevents", "prevent", "stops", "stop", "protects against", "protect against",
        "protects from", "fights", "fight", "kills", "kill", "eliminates", "eliminate",
        "blocks", "block", "causes", "cause", "caused", "leads to", "lead to", "gives you",
        "give you", "triggers", "trigger", "is linked to", "are linked to", "linked to",
        "increases", "increase", "raises", "raise", "boosts", "boost", "reduces", "reduce",
        "lowers", "lower", "improves", "improve", "helps with", "help with", "helps",
        "help", "detoxes", "detoxifies", "burns", "burn", "works for", "work for",
        "is good for", "are good for", "is bad for", "are bad for", "damages", "damage",
        "weakens", "weaken", "destroys", "destroy", "spreads", "spread", "transmits",
        "no",
    ],
    key=len,
    reverse=True,
)
_VERB_RE = re.compile(r"(?<![\w-])(" + "|".join(re.escape(v) for v in _CLAIM_VERBS) + r")(?![\w-])")

_POPULATION_RE = re.compile(
    r"(?<![\w-])(?:in|for|among|of)\s+((?:young\s+|small\s+|older\s+|pregnant\s+)?"
    r"(?:children|kids|child|babies|baby|infants|newborns|adults|older adults|elderly|"
    r"the elderly|seniors|teenagers|teens|adolescents|pregnant women|women|men|pregnancy))"
    r"(?![\w-])"
)
_COMPARATOR_RE = re.compile(
    r"(?<![\w-])(?:better than|more effective than|worse than|instead of|rather than|"
    r"compared (?:to|with)|as well as|just like|than)\s+(.+?)(?=$|,|;|\.|\bfor\b|\bin\b)"
)
_QUALIFIER_RE = re.compile(
    r"(?<![\w-])(?:\d+(?:\.\d+)?\s?(?:mg|mcg|µg|iu|ml)\b(?:\s+a\s+day|\s+daily)?|"
    r"\d+(?:\.\d+)?\s(?:g|l|cups?|glasses|times)\b(?:\s+a\s+day|\s+daily)?|"
    r"every\s+(?:morning|day|night|evening)|daily|twice a day|once a day|on an empty stomach|"
    r"in (?:\d+|a few|few|three|two|seven) (?:days|hours|weeks))"
)
_STOPWORDS = frozenset(
    """a an and are as at be been but by can could did do does doing for from had has have
    how i if in into is it its just like may me might more most my no not of on one or our
    out really so some such than that the their them then there these they this those to
    too us very was we were what when which who will with would you your yours always never
    every everyone people say says said said actually literally totally completely truly
    myth fact true false real secret doctors dont don't won't cant can't im it's that's
    morning day daily night better worse best worst amazing great good bad
    awesome miracle""".split()
)


def normalize_claim(text: str) -> str:
    """Lower case, NFKC, ``=`` and arrows read as a claim verb, punctuation and emoji
    dropped, whitespace collapsed. Keeps hyphens and apostrophes inside words."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("’", "'")
    t = re.sub(r"\s*(=|->|→|⇒)\s*", " = ", t)
    t = t.replace(" = no ", " prevents ").replace(" = ", " gives you ")
    t = re.sub(r"[^\w\s'\-+.%]", " ", t)
    t = re.sub(r"(?<!\d)\.(?!\d)", " ", t)  # sentence dots, not decimals
    t = re.sub(r"(?<![\w])'|'(?![\w])", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _concepts_in(matches: Iterable[Match], start: int, end: int) -> list[Concept]:
    return [m.concept for m in matches if m.start >= start and m.end <= end]


def frame_claim(claim_text: str) -> ClaimFrame:
    """Rule-based PICO breakdown of one claim (§6 step 1)."""
    text = normalize_claim(claim_text)
    matches = find_concepts(text)

    population: list[Concept] = []
    comparator: list[Concept] = []
    used: set[int] = set()

    for pm in _POPULATION_RE.finditer(text):
        s, e = pm.span(1)
        for m in matches:
            if m.start >= s and m.end <= e and m.concept.kind == "population":
                population.append(m.concept)
                used.add(id(m))
    for cm in _COMPARATOR_RE.finditer(text):
        s, e = cm.span(1)
        for m in matches:
            if m.start >= s and m.end <= e and id(m) not in used:
                comparator.append(m.concept)
                used.add(id(m))
    # A population word anywhere ("babies shouldn't…") still counts as population.
    for m in matches:
        if m.concept.kind == "population" and id(m) not in used:
            population.append(m.concept)
            used.add(id(m))

    rest = [m for m in matches if id(m) not in used]
    verb = _VERB_RE.search(text)
    intervention: list[Concept] = []
    outcome: list[Concept] = []
    if verb:
        before = _concepts_in(rest, 0, verb.start())
        after = _concepts_in(rest, verb.end(), len(text))
        intervention, outcome = before, after
        if not intervention and after:
            # "Causes autism: vaccines" or verb-first phrasing: split by kind instead.
            intervention = [c for c in after if c.kind == "intervention"]
            outcome = [c for c in after if c.kind != "intervention"]
        elif not outcome and before:
            outcome = [c for c in before if c.kind in ("condition", "outcome")]
            intervention = [c for c in before if c.kind == "intervention"] or before[:1]
            if intervention == outcome:
                outcome = []
    else:
        intervention = [m.concept for m in rest if m.concept.kind == "intervention"]
        outcome = [m.concept for m in rest if m.concept.kind in ("condition", "outcome")]
    qualifiers = tuple(q.group(0) for q in _QUALIFIER_RE.finditer(text))
    return ClaimFrame(
        normalized_text=text,
        population=tuple(population),
        intervention=tuple(intervention),
        comparator=tuple(comparator),
        outcome=tuple(outcome),
        qualifiers=qualifiers,
        keywords=tuple(content_words(text)),
    )


def content_words(normalized_text: str) -> list[str]:
    stripped = _QUALIFIER_RE.sub(" ", normalized_text)
    stripped = _VERB_RE.sub(" ", stripped)
    words = [w.strip("'-.") for w in stripped.split()]
    out: list[str] = []
    for w in words:
        if len(w) < 2 or w in _STOPWORDS or w.isdigit() or w in out:
            continue
        out.append(w)
    return out[:8]


# ----------------------------------------------------------------- query syntax

_SAFE_CHARS_RE = re.compile(r"[^\w\s\"'()\[\]/,:+\-.]")


def _quote(term: str) -> str:
    term = term.replace('"', "")
    return f'"{term}"' if re.search(r"[\s,\-]", term) else term


def concept_clause(c: Concept, *, use_parent: bool = False) -> str:
    """One concept as a PubMed clause: MeSH heading OR free-text synonyms."""
    parts: list[str] = []
    if use_parent and c.parent_mesh:
        return f"{_quote(c.parent_mesh)}[MeSH Terms]"
    if c.mesh:
        parts.append(f"{_quote(c.mesh)}[MeSH Terms]")
    for s in c.synonyms:
        clause = f"{_quote(s)}[tiab]"
        if clause not in parts:
            parts.append(clause)
    return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"


def _and(clauses: list[str]) -> str:
    return " AND ".join(c for c in clauses if c)


def sanitize_query(text: str) -> str:
    """Make untrusted query text (critic or assistant output) safe to send: no control
    characters, URLs or odd symbols, bounded length. Returns "" if nothing usable
    is left."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"https?://\S+", " ", t)
    t = "".join(ch if ch.isprintable() else " " for ch in t)
    t = _SAFE_CHARS_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t.count("(") != t.count(")"):
        t = t.replace("(", " ").replace(")", " ")
        t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_QUERY_CHARS].strip()


class SearchAssistant(Protocol):
    """Small-LLM helper used only when rules find nothing (§6 step 3). Returns search
    terms, e.g. ``["hot drinks influenza"]``."""

    def __call__(self, claim_text: str) -> list[str]: ...


class QueryPlanner:
    """Deterministic query ladder for one claim (§6 "Planning", "When nothing comes back")."""

    def __init__(self, assistant: Optional[SearchAssistant] = None) -> None:
        self.assistant = assistant

    def ladder(self, claim_text: str) -> list[str]:
        frame = frame_claim(claim_text)
        candidates: list[str] = []
        core = [*frame.intervention, *frame.outcome]
        if core:
            i_clause = _and([concept_clause(c) for c in frame.intervention])
            o_clause = _and([concept_clause(c) for c in frame.outcome])
            p_clause = _and([concept_clause(c) for c in frame.population])
            candidates.append(_and([i_clause, o_clause, p_clause]))
            candidates.append(_and([i_clause, o_clause]))
            parents = [concept_clause(c, use_parent=True) for c in core]
            candidates.append(_and(parents))
        else:
            for terms in self._assist(claim_text):
                candidates.append(terms)
        if core:
            # Last resort: the claim's own words for each concept, as free text.
            candidates.append(" ".join(_quote(c.matched_text) for c in core))
        elif frame.keywords:
            candidates.append(" ".join(frame.keywords))
        out: list[str] = []
        for q in candidates:
            q = sanitize_query(q)
            if q and q not in out:
                out.append(q)
        return out

    def _assist(self, claim_text: str) -> list[str]:
        if self.assistant is None:
            return []
        try:
            return [t for t in (self.assistant(claim_text) or []) if isinstance(t, str)][:3]
        except Exception:  # the helper is optional; rules still produce a keyword query
            return []

    def next_query(
        self,
        claim_text: str,
        already_run: list[str],
        suggestions: Iterable[str] = (),
    ) -> Optional[str]:
        """The query for the next search round of a claim.

        Critic suggestions (§8) come first, sanitised; otherwise the next rung of the
        ladder that hasn't been run. ``None`` when every candidate has been tried.
        """
        for s in suggestions:
            q = sanitize_query(s)
            if q and q not in already_run:
                return q
        for q in self.ladder(claim_text):
            if q not in already_run:
                return q
        return None


__all__ = [
    "QueryPlanner",
    "SearchAssistant",
    "concept_clause",
    "content_words",
    "frame_claim",
    "normalize_claim",
    "sanitize_query",
]
