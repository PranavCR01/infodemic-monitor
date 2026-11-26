"""Retrieval planning: claim → PICO frame → PubMed queries (§6 "Planning the search").

Rules do the work by default:

1. ``normalize_claim`` lower-cases and strips punctuation and emoji.
2. ``frame_claim`` splits the claim at its claim verb ("cures", "causes", "prevents"…):
   concepts before the verb are the intervention, after it the outcome. Population
   ("in children") and comparator ("better than X") phrases are pulled out first.
   Concepts come from the MeSH lexicon (``mesh.py``).
3. ``QueryPlanner.plan`` builds a ``SearchPlan``: a ladder of queries, each different from
   and broader than the one before (T50 d); round *n* runs the *n*-th rung and the search
   stops when they run out (no query is repeated):

   - a citation lookup first when the claim cites a study (journal [ta], year [dp],
     topic; ``citation.py``, T50 e);
   - intervention AND outcome AND population, MeSH plus [tiab] synonyms;
   - the population dropped; the outcome broadened to its parent heading; the
     intervention alone (an intervention is never broadened to its parent heading);
   - with no concept recognised: the search assistant's structured query (if one is
     configured), then at most three of the claim's own terms (T50 c, f).

   Terms keep their one-letter or digit part (``vitamin k``, ``type 2 diabetes``; T50 a).
   A claim that refers to the video's main intervention without naming it gets that
   concept (``context``). A non-English claim is translated first when a translator is
   configured, else planned with its language's stop words (``language.py``, T50 h).

The ``assistant`` and ``translator`` are small LLMs injected by the caller, which picks
the model from the routing config (§13); nothing here names a model. Whatever they
return is untrusted text and sanitised; neither ever supplies an identifier.
"""
from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol, Sequence

from app.core.retrieval.citation import CitationCue, citation_cue
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


# Words that carry no search meaning in a spoken claim (T50 f): conversational
# intensifiers, hedges and quantity words. "Babies who didn't get the shot are 81 times
# more likely ..." must not become ``didn't 81 times higher likely`` in a keyword query.
_CONVERSATIONAL = frozenset(
    """didnt didn't doesnt doesn't isnt isn't arent aren't wasnt wasn't havent haven't hasnt
    hasn't wouldnt wouldn't shouldnt shouldn't couldnt couldn't get gets got getting go goes
    going gone gonna wanna gotta know knows think thinks thought want wants need needs needed
    see seen look looks looking find finds found make makes made called call thing things stuff
    way ways lot lots kind sort super pretty basically higher lower high low times likely
    unlikely less much many overwhelming huge massive tiny small big little dangerous fine
    okay ok yes number numbers percent amount evidence study studies research researchers show
    shows showed shown proven proof claim claims tell tells told believe believes person guy
    girl man woman everything nothing anything something someone anyone take takes taking""".split()
)
# Words a one-letter or short digit token belongs to ("vitamin k", "hepatitis b",
# "type 2 diabetes", "covid 19", "omega 3"). Glued even when the short token is itself a
# stop word ("vitamin a").
_GLUE_HEADS = frozenset({"vitamin", "vitamins", "vitamina", "vitamine", "hepatitis", "type", "tipo",
                         "stage", "grade", "phase", "covid", "omega", "group", "class", "factor",
                         "complex", "coenzyme", "coenzima", "b", "q"})
# A glued term that ends with a digit after one of these takes the next word too:
# "type 2 diabetes", "stage 4 cancer".
_GLUE_NEXT = frozenset({"type", "tipo", "stage", "grade", "phase"})


def _is_short(tok: str) -> bool:
    return len(tok) == 1 or (len(tok) <= 3 and any(ch.isdigit() for ch in tok))


def term_tokens(normalized_text: str, stopwords: frozenset[str] = _STOPWORDS) -> list[str]:
    """The text's tokens with a one-letter or short digit token glued to the word it
    belongs to (§6, T50 a): ``vitamin k``, ``hepatitis b``, ``type 2 diabetes``,
    ``covid 19``. Plain numbers ("81 times", "15 ans") stay separate tokens."""
    out: list[str] = []
    take_next = False
    for raw in normalized_text.split():
        tok = raw.strip("'.%+,")
        if not tok:
            continue
        if take_next and out and tok not in stopwords:
            out[-1] = f"{out[-1]} {tok}"
            take_next = False
            continue
        take_next = False
        prev = out[-1] if out else ""
        head = prev.split(" ")[0] if prev else ""
        glue = bool(prev) and _is_short(tok) and (
            head in _GLUE_HEADS
            or (" " not in prev and prev not in stopwords and not prev.isdigit() and tok not in stopwords
                and not tok.isdigit()))
        if glue:
            out[-1] = f"{prev} {tok}"
            take_next = head in _GLUE_NEXT and tok[-1:].isdigit()
            continue
        out.append(tok)
    return out


def content_words(normalized_text: str, lang: str = "en") -> list[str]:
    """The claim's searchable words and terms, in order, without stop words, claim
    verbs, qualifiers, plain numbers or conversational filler (T50 a, f). Terms keep
    their one-letter or digit part (``vitamin k``, never ``vitamin``). For a claim in
    another language, that language's stop words apply too (T50 h)."""
    from app.core.retrieval.language import STOPWORDS

    stop = _STOPWORDS | STOPWORDS.get(lang, frozenset())
    stripped = _QUALIFIER_RE.sub(" ", normalized_text)
    stripped = _VERB_RE.sub(" ", stripped)
    out: list[str] = []
    for w in term_tokens(stripped, stop):
        w = w.strip("'-.")
        if (len(w) < 2 or w in stop or w in _CONVERSATIONAL or w.replace(",", "").replace(".", "").isdigit()
                or w in out):
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
    """Small-LLM helper used only when the rules fall back to keywords (§6 step 3,
    T50 c). Returns either plain search-term strings (legacy) or an ``AssistedQuery``
    (``app.core.retrieval.assist``): intervention / outcome / population as MeSH
    headings plus [tiab] synonyms. Whatever it returns is untrusted text and is
    sanitised; it never supplies identifiers."""

    def __call__(self, claim_text: str) -> Any: ...


class Translator(Protocol):
    """Translates a non-English claim to English before planning (T50 h). Returns the
    English text; the output is untrusted and sanitised."""

    def __call__(self, claim_text: str, language: str) -> str: ...


# Delivery routes that say how something is given, not what is given: a claim whose
# only intervention is one of these ("babies who don't get the shot") is about the
# video's main substance (T50, context carry-over).
GENERIC_INTERVENTIONS = frozenset({"injection", "oral_drops"})
_ANAPHORA_RE = re.compile(r"(?<![\w-])(?:this|these|that|those|the shot|the injection|the drops|the jab)(?![\w-])")
_NON_LATIN_LANGS = frozenset({"hi", "ru", "ar", "zh", "ja", "ko", "el", "he", "th", "bn", "ta"})
MAX_KEYWORD_TERMS = 3  # the keyword fallback never ANDs more than this many terms (T50 f)
_PLAN_CACHE_SIZE = 512


@dataclass(frozen=True)
class PlannedQuery:
    query: str
    # citation | pico | intervention_outcome | broader_outcome | intervention_only |
    # intervention_population | outcome_population | outcome_only | broader_condition |
    # assistant | keywords | critic
    kind: str


@dataclass(frozen=True)
class SearchPlan:
    """Everything planning decided for one claim, recorded in the search trail.

    ``rungs`` run in order, one per round, each different from and broader than the one
    before (§6 "When nothing comes back", T50 d). When they run out the claim's search
    stops; nothing is re-run from the cache."""

    claim_text: str
    language: str
    search_text: str  # what the rules framed: the English translation when there is one
    translated: bool = False
    translation_error: Optional[str] = None
    context_concept: Optional[str] = None  # the video's main intervention, carried over
    citation: Optional[dict] = None
    cites_study: bool = False
    assistant_used: bool = False
    assistant_error: Optional[str] = None
    rungs: tuple[PlannedQuery, ...] = ()

    def kind_of(self, query: str) -> Optional[str]:
        return next((r.kind for r in self.rungs if r.query == query), None)

    def describe(self) -> dict:
        return {"language": self.language, "translated": self.translated,
                "search_text": self.search_text if self.translated else None,
                "translation_error": self.translation_error, "context_concept": self.context_concept,
                "citation": self.citation, "assistant_used": self.assistant_used,
                "assistant_error": self.assistant_error,
                "rungs": [{"kind": r.kind, "query": r.query} for r in self.rungs]}


def dominant_intervention(context: Sequence[str]) -> Optional[Concept]:
    """The intervention concept named by the most claims of the video (at least two),
    or None. Ties go to the one named first."""
    counts: dict[str, int] = {}
    first: dict[str, Concept] = {}
    for text in context:
        seen: set[str] = set()
        for c in frame_claim(text).intervention:
            if c.kind != "intervention" or c.key in GENERIC_INTERVENTIONS or c.key in seen:
                continue
            seen.add(c.key)
            counts[c.key] = counts.get(c.key, 0) + 1
            first.setdefault(c.key, c)
    if not counts:
        return None
    best = max(counts, key=lambda k: (counts[k], -list(first).index(k)))
    return first[best] if counts[best] >= 2 else None


def _with_context(frame: ClaimFrame, context: Sequence[str]) -> tuple[ClaimFrame, Optional[str]]:
    """Carry the video's main intervention over to a claim that refers to it without
    naming it: "babies who don't get *the shot*", "*these studies* on newborns"."""
    if not context:
        return frame, None
    own = [c for c in frame.intervention if c.kind == "intervention"]
    generic_only = bool(own) and all(c.key in GENERIC_INTERVENTIONS for c in own)
    if own and not generic_only:
        return frame, None
    if not own and not _ANAPHORA_RE.search(frame.normalized_text):
        return frame, None
    concept = dominant_intervention(context)
    if concept is None:
        return frame, None
    outcome = tuple(c for c in frame.outcome if c.key != concept.key)
    return frame.model_copy(update={"intervention": (concept,), "outcome": outcome}), concept.key


def _or(clauses: list[str]) -> str:
    clauses = [c for c in clauses if c]
    return clauses[0] if len(clauses) == 1 else "(" + " OR ".join(clauses) + ")"


def _rule_rungs(frame: ClaimFrame) -> list[PlannedQuery]:
    """Narrow to broad, each rung dropping something the one before had. An
    intervention is never broadened to its parent heading: ``Vitamins`` would make every
    vitamin paper a hit (the vitamin K → vitamin D failure in job 5cc07f48)."""
    I = [c for c in frame.intervention]
    O = [c for c in frame.outcome]
    P = [c for c in frame.population]
    i_clause = _and([concept_clause(c) for c in I])
    o_clause = _and([concept_clause(c) for c in O])
    p_clause = _and([concept_clause(c) for c in P])
    out: list[PlannedQuery] = []
    if I and O:
        if P:
            out.append(PlannedQuery(_and([i_clause, o_clause, p_clause]), "pico"))
        out.append(PlannedQuery(_and([i_clause, o_clause]), "intervention_outcome"))
        if any(c.parent_mesh for c in O):
            broader = _and([concept_clause(c, use_parent=bool(c.parent_mesh)) for c in O])
            out.append(PlannedQuery(_and([i_clause, broader]), "broader_outcome"))
        out.append(PlannedQuery(i_clause, "intervention_only"))
    elif I:
        if P:
            out.append(PlannedQuery(_and([i_clause, p_clause]), "intervention_population"))
        out.append(PlannedQuery(i_clause, "intervention_only"))
        if len(I) > 1:
            out.append(PlannedQuery(_or([concept_clause(c) for c in I]), "intervention_any"))
    elif O:
        if P:
            out.append(PlannedQuery(_and([o_clause, p_clause]), "outcome_population"))
        out.append(PlannedQuery(o_clause, "outcome_only"))
        if any(c.parent_mesh for c in O):
            out.append(PlannedQuery(
                _and([concept_clause(c, use_parent=bool(c.parent_mesh)) for c in O]), "broader_condition"))
    return out


def keyword_rungs(keywords: Sequence[str]) -> list[PlannedQuery]:
    """The keyword fallback (T50 f): at most ``MAX_KEYWORD_TERMS`` terms, the longer
    (more specific) ones first, then one fewer. Never eight conversational words ANDed."""
    terms = list(dict.fromkeys(keywords))
    if not terms:
        return []
    ranked = sorted(terms, key=lambda w: (-(" " in w), -len(w)))
    chosen = [w for w in terms if w in ranked[:MAX_KEYWORD_TERMS]]
    out = [PlannedQuery(" ".join(_quote(w) for w in chosen), "keywords")]
    if len(chosen) > 1:
        fewer = [w for w in chosen if w in ranked[: len(chosen) - 1]]
        out.append(PlannedQuery(" ".join(_quote(w) for w in fewer), "keywords"))
    return out


def citation_query(cue: CitationCue, frame: ClaimFrame, keywords: Sequence[str]) -> Optional[str]:
    """``"JAMA"[ta] AND 2026[dp] AND (topic)``: the cited journal and year plus the
    claim's topic terms. None without a journal or a year (a sample size alone can't be
    searched)."""
    if not (cue.journal or cue.year):
        return None
    if frame.intervention:
        topic = _and([concept_clause(c) for c in frame.intervention])
    elif frame.outcome:
        topic = _and([concept_clause(c) for c in frame.outcome])
    else:
        topic = " ".join(_quote(w) for w in list(keywords)[:2])
    if not topic:
        return None
    parts = []
    if cue.journal:
        parts.append(f'"{cue.journal}"[ta]')
    if cue.year:
        parts.append(f"{cue.year}[dp]")
    parts.append(topic)
    return _and(parts)


class QueryPlanner:
    """Query ladder for one claim (§6 "Planning", "When nothing comes back"; T50).

    Rules-only unless a ``translator`` (non-English claims, T50 h) or an ``assistant``
    (keyword fallback, T50 c) is injected; both degrade to the rules when they fail.
    Plans are cached per claim, so a model is consulted at most once per claim per
    process, whichever round asks."""

    def __init__(self, assistant: Optional[SearchAssistant] = None,
                 translator: Optional[Translator] = None) -> None:
        self.assistant = assistant
        self.translator = translator
        self._plans: "OrderedDict[tuple, SearchPlan]" = OrderedDict()

    # -- planning --

    def plan(self, claim_text: str, *, claim_kind: str = "research_question",
             context: Sequence[str] = ()) -> SearchPlan:
        key = (claim_text, claim_kind, tuple(context))
        cached = self._plans.get(key)
        if cached is not None:
            self._plans.move_to_end(key)
            return cached
        plan = self._build(claim_text, claim_kind, tuple(context))
        self._plans[key] = plan
        if len(self._plans) > _PLAN_CACHE_SIZE:
            self._plans.popitem(last=False)
        return plan

    def _build(self, claim_text: str, claim_kind: str, context: tuple[str, ...]) -> SearchPlan:
        from app.core.retrieval.language import detect_language, is_english

        lang = detect_language(claim_text)
        search_text, translated, translation_error = claim_text, False, None
        if not is_english(lang) and self.translator is not None:
            try:
                english = sanitize_text(self.translator(claim_text, lang) or "")
            except Exception as exc:  # noqa: BLE001 - rules still run on the original
                translation_error = type(exc).__name__
            else:
                if english:
                    search_text, translated = english, True
                else:
                    translation_error = "empty"
        rules_lang = "en" if translated else lang
        frame = frame_claim(search_text)
        frame, context_concept = _with_context(frame, [c for c in context if c != claim_text])
        keywords = content_words(frame.normalized_text, rules_lang)
        if not translated and lang in _NON_LATIN_LANGS:
            # The rules can't read this script (normalisation even splits Devanagari
            # words at their vowel signs): no keyword query rather than a junk one.
            keywords = []
        cue = citation_cue(frame.normalized_text)
        rungs: list[PlannedQuery] = []
        cq = citation_query(cue, frame, keywords) if cue.cites_study else None
        if cq:
            rungs.append(PlannedQuery(cq, "citation"))
        rule = _rule_rungs(frame)
        assistant_used, assistant_error = False, None
        if rule:
            rungs += rule
        else:
            # The rules found nothing to frame and would fall back to keywords: the
            # assistant (if configured) writes a structured query first.
            assisted, assistant_error = self._assist(search_text)
            assistant_used = bool(assisted)
            rungs += assisted
            rungs += keyword_rungs(keywords)
        out: list[PlannedQuery] = []
        seen: set[str] = set()
        for r in rungs:
            q = sanitize_query(r.query)
            if q and q not in seen:
                seen.add(q)
                out.append(PlannedQuery(q, r.kind))
        return SearchPlan(
            claim_text=claim_text, language=lang, search_text=search_text, translated=translated,
            translation_error=translation_error, context_concept=context_concept,
            citation=cue.describe() if cue.cites_study else None, cites_study=cue.cites_study,
            assistant_used=assistant_used, assistant_error=assistant_error, rungs=tuple(out))

    def _assist(self, text: str) -> tuple[list[PlannedQuery], Optional[str]]:
        if self.assistant is None:
            return [], None
        from app.core.retrieval.assist import assisted_rungs

        try:
            raw = self.assistant(text)
        except Exception as exc:  # noqa: BLE001 - the helper is optional; rules still run
            return [], type(exc).__name__
        try:
            return assisted_rungs(raw), None
        except Exception as exc:  # noqa: BLE001 - malformed output is dropped
            return [], type(exc).__name__

    # -- the ladder --

    def ladder(self, claim_text: str, *, claim_kind: str = "research_question",
               context: Sequence[str] = ()) -> list[str]:
        return [r.query for r in self.plan(claim_text, claim_kind=claim_kind, context=context).rungs]

    def next_query(
        self,
        claim_text: str,
        already_run: list[str],
        suggestions: Iterable[str] = (),
        *,
        plan: Optional[SearchPlan] = None,
        claim_kind: str = "research_question",
        context: Sequence[str] = (),
    ) -> Optional[str]:
        """The query for the next search round of a claim.

        Critic suggestions (§8) come first, sanitised; otherwise the next rung of the
        ladder that hasn't been run. ``None`` when every candidate has been tried: the
        caller stops the claim's search and records that, it never repeats a query.
        """
        for s in suggestions:
            q = sanitize_query(s)
            if q and q not in already_run:
                return q
        plan = plan or self.plan(claim_text, claim_kind=claim_kind, context=context)
        for r in plan.rungs:
            if r.query not in already_run:
                return r.query
        return None


def sanitize_text(text: str, max_chars: int = 500) -> str:
    """Untrusted model text used as a claim (a translation): printable characters only,
    no URLs, bounded length."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"https?://\S+", " ", t)
    t = "".join(ch if ch.isprintable() else " " for ch in t)
    t = re.sub(r"[<>{}`$\\|]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:max_chars].strip()


__all__ = [
    "GENERIC_INTERVENTIONS",
    "MAX_KEYWORD_TERMS",
    "PlannedQuery",
    "QueryPlanner",
    "SearchAssistant",
    "SearchPlan",
    "Translator",
    "citation_query",
    "concept_clause",
    "content_words",
    "dominant_intervention",
    "frame_claim",
    "keyword_rungs",
    "normalize_claim",
    "sanitize_query",
    "sanitize_text",
    "term_tokens",
]
