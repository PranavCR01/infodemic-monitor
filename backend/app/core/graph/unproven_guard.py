"""Unproven guard: no UNSUPPORTED from an empty or off-topic search (T49, design §7).

UNSUPPORTED means "the full search found no evidence for or against this efficacy
claim". That reading is only honest if the search actually reached the claim's topic.
In production job 5cc07f48 (vitamin K video, 2026-11-26) one claim got zero PubMed
results and another got only vitamin D / osteoporosis papers; both became UNSUPPORTED
and an accurate video was labelled MISINFO (unproven). An empty or off-topic search
says nothing about the claim, so it must not count as "nothing supports it".

**Rule.** A verdict of UNSUPPORTED stands only if the evidence the verifier was given
(the claim's reranked evidence: what retrieval kept) holds at least one record that is
*on topic* for the claim's intervention. Otherwise the verdict becomes
INSUFFICIENT_EVIDENCE with the limitation ``search_found_nothing_on_topic``. With no
other judged claim, the judge's last branch (§9, unchanged) then gives
CANNOT_RECOGNIZE with the ``nothing_judged`` review reason.

**On topic (deterministic, no model).** A record is on topic if

1. the verifier cited it (``supporting_evidence_ids`` / ``contradicting_evidence_ids``;
   §7 requires UNSUPPORTED to cite nothing, so in practice rule 2 decides), or
2. its title or abstract contains the claim's intervention terms (below), matched
   case-insensitively on whole words after the same normalisation as claims
   (``planning.normalize_claim``; hyphens read as spaces; a trailing ``s``/``es``
   plural is allowed). A match immediately followed by "antagonist(s)" does not count
   (T50: "vitamin K antagonists" are warfarin-type drugs, not vitamin K).

**Intervention terms.**

- If the §6 planner's rule-based frame (``planning.frame_claim``) recognises an
  intervention concept in the claim (``kind == "intervention"``), the terms are each
  such concept's matched text, label, MeSH heading and synonyms. Any one of them in the
  record is enough. The concept's *parent* heading is never used (``Vitamins`` would
  make every vitamin paper on topic).
- Otherwise the terms are the claim's intervention-side words: the label before a
  colon ("Burdock Root: rids kidney stones"), else the content words before the first
  claim verb (``cures``, ``prevents``, ``helps`` ...), else those of the whole claim.
  Stop words, filler words (``high``, ``natural``, ``drinking`` ...) and words the
  lexicon recognises as a condition, outcome or population are dropped; a one-letter or
  short digit token is kept glued to the word before it (``vitamin k``, ``omega 3``,
  ``type 2``), so "vitamin K" never shrinks to "vitamin". At most the first
  ``MAX_FALLBACK_TERMS`` words are used, and **all** of them must appear in the record.
  This is strict on purpose: when the system does not know what the intervention is,
  the safe error is CANNOT_RECOGNIZE + review, not MISINFO.
- No terms at all (a claim with only stop words) means nothing can be shown to be on
  topic, so UNSUPPORTED never stands.

The check runs in the ``verify_claims`` node right after each verdict, not in the judge,
so the §9 rules and the judge cross-check are unchanged. Every other verdict passes
through untouched.

**T64 (production job d2bf4179, vitamin K re-analysis, 2026-11-26).** An accurate video
was still MISINFO (unproven), decided by c12 "vitamin K is a vitamin that helps prevent a
potentially devastating condition": UNSUPPORTED on ONE kept record (a brodifacoum case
report) while its sibling c14 (the preventive injection) was SUPPORTED by two
systematic reviews. Three more deterministic checks, in this order, after the on-topic
check above (each turns UNSUPPORTED into INSUFFICIENT_EVIDENCE and appends its
limitation; the first that fires wins):

- **(c) outcome unspecified** (``outcome_unspecified``): the claim names no condition or
  outcome ("a potentially devastating condition", "many diseases"), so no study could
  test it and "nothing supports it" says nothing. The verifier prompt asks the model to
  set the ``outcome_unspecified`` flag (``verifier.py``); :func:`outcome_unspecified`
  enforces it in code even when the model ignores the flag: the words after the last
  claim verb hold no lexicon condition/outcome and are only generic nouns ("condition",
  "diseases", "problems" ...) with vague modifiers ("a", "many", "potentially",
  "devastating" ...).
- **(a) search too thin** (``search_too_thin``): UNSUPPORTED needs at least
  ``MIN_ON_TOPIC_RECORDS`` (3) on-topic kept records, or at least one on-topic
  systematic review, randomised trial or guideline (``STRONG_STUDY_TYPES``; study type
  from the record, else ``rerank.classify_study`` on its publication type). One or two
  case reports are not "the full search found nothing".
- **(b) sibling claim** (``contradicted_by_sibling_claim``) needs the other claims, so it
  runs once per verify pass over all results: :func:`apply_sibling_rule`. Narrowed from
  the queue row (T64 decision): the sibling must also not name a *different* outcome,
  since a supported claim about one outcome says nothing about another (tune v22: "eggs
  prevent fatty liver" SUPPORTED vs "eggs prevent macular degeneration" UNSUPPORTED).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from app.core.graph.state import EvidenceRecord, GraphClaim, Verdict, VerificationResult
from app.core.retrieval.mesh import find_concepts
from app.core.retrieval.planning import _STOPWORDS, _VERB_RE, frame_claim, normalize_claim

OFF_TOPIC_LIMITATION = "search_found_nothing_on_topic"
THIN_SEARCH_LIMITATION = "search_too_thin"  # T64 (a)
OUTCOME_UNSPECIFIED_LIMITATION = "outcome_unspecified"  # T64 (c)
SIBLING_LIMITATION = "contradicted_by_sibling_claim"  # T64 (b)
MIN_ON_TOPIC_RECORDS = 3
STRONG_STUDY_TYPES = frozenset({"systematic_review", "rct", "guideline"})
EFFICACY_CATEGORIES = frozenset({"treatment_efficacy", "prevention"})
THIN_SEARCH_EXPLANATION = (
    "Not determined: the search kept too few records on this claim's intervention (and no "
    "systematic review, randomised trial or guideline) to say that no study supports it."
)
OUTCOME_UNSPECIFIED_EXPLANATION = (
    "Not determined: the claim does not name the condition or outcome, so no study can be "
    "said to test it."
)
SIBLING_EXPLANATION = (
    "Not determined: another claim in this video about the same intervention is supported "
    "by the evidence, so the lack of evidence for this wording does not decide the label."
)
OFF_TOPIC_EXPLANATION = (
    "Not determined: the search kept no record about this claim's intervention, so it "
    "is unknown whether any study tests the claim."
)
MAX_FALLBACK_TERMS = 4
_MIN_TERM_CHARS = 2
# Words that never name an intervention, on top of the planner's stop words: filler
# adjectives and the verbs of taking something ("drinking seawater" → "seawater").
_FILLER = frozenset(
    """high low rich full natural pure healthy powerful certain something called which
    using use uses taking take takes eating eat eats drinking drink drinks consuming
    consume rubbing rub applying apply new simple lot lots""".split()
)
_GLUE_HEADS = frozenset({"vitamin", "vitamins"})  # "vitamin a" glues although "a" is a stop word

__all__ = [
    "OFF_TOPIC_LIMITATION", "OFF_TOPIC_EXPLANATION", "MAX_FALLBACK_TERMS",
    "InterventionTerms", "intervention_terms", "on_topic", "on_topic_ids", "apply_unproven_guard",
    "THIN_SEARCH_LIMITATION", "OUTCOME_UNSPECIFIED_LIMITATION", "SIBLING_LIMITATION",
    "MIN_ON_TOPIC_RECORDS", "STRONG_STUDY_TYPES", "outcome_unspecified", "thin_search",
    "same_intervention", "apply_sibling_rule",
]


@dataclass(frozen=True)
class InterventionTerms:
    """``terms`` and how to combine them: ``require_all`` False means any one is enough
    (a recognised concept's alternative names); True means every word must appear
    (the fallback words of an unrecognised intervention)."""

    terms: tuple[str, ...]
    require_all: bool
    source: str  # "concept" | "fallback" | "none"


def _norm(text: str) -> str:
    return " ".join(normalize_claim(text).replace("-", " ").split())


def _glued_tokens(text: str) -> list[str]:
    """Tokens with a one-letter / short digit token glued to the word before it."""
    out: list[str] = []
    for tok in text.split():
        tok = tok.strip("'.%+")
        if not tok:
            continue
        short = len(tok) == 1 or (len(tok) <= 3 and any(ch.isdigit() for ch in tok))
        prev = out[-1] if out else ""
        glue = short and prev and prev not in _STOPWORDS and not prev.isdigit() and " " not in prev and (
            tok not in _STOPWORDS or prev in _GLUE_HEADS)
        if glue:
            out[-1] = f"{out[-1]} {tok}"
            continue
        out.append(tok)
    return out


def intervention_terms(claim_text: str) -> InterventionTerms:
    """The claim's intervention terms (see the module docstring)."""
    frame = frame_claim(claim_text)
    concepts = [c for c in frame.intervention if c.kind == "intervention"]
    if concepts:
        terms: list[str] = []
        for c in concepts:
            for t in (c.matched_text, c.label, c.mesh or "", *c.synonyms):
                t = _norm(t)
                if len(t) >= _MIN_TERM_CHARS and t not in terms:
                    terms.append(t)
        return InterventionTerms(tuple(terms), require_all=False, source="concept")

    text = _norm(claim_text)
    # Words the lexicon knows as a condition / outcome / population are not the
    # intervention ("cancer" in "a soap that treats skin cancer").
    for m in sorted(find_concepts(text), key=lambda m: -m.start):
        if m.concept.kind != "intervention":
            text = f"{text[:m.start]} {text[m.end:]}"
    keep = lambda w: w not in _STOPWORDS and w not in _FILLER and len(w) >= _MIN_TERM_CHARS  # noqa: E731
    # "Burdock Root: rids kidney stones" (an on-screen list): the label before the
    # colon is the intervention.
    head = claim_text.split(":", 1)[0] if ":" in claim_text else ""
    side_words = [w for w in _glued_tokens(_norm(head)) if keep(w)] if head.strip() else []
    if not side_words:
        verb = _VERB_RE.search(text)
        side = text[: verb.start()] if verb else text
        side_words = [w for w in _glued_tokens(side) if keep(w)]
        if not side_words and verb:
            side_words = [w for w in _glued_tokens(text) if keep(w)]
    words = side_words
    words = [w for w in dict.fromkeys(words) if not w.isdigit()][:MAX_FALLBACK_TERMS]
    if not words:
        return InterventionTerms((), require_all=True, source="none")
    return InterventionTerms(tuple(words), require_all=True, source="fallback")


# A drug class named after what it blocks is not about that thing: "vitamin K
# antagonists" are warfarin-type anticoagulants (T50 review), so a mention immediately
# followed by one of these words does not count.
_NOT_ABOUT_SUFFIX = r"(?!\s+(?:antagonists?|antagonism|antagonistic)\b)"


def _term_re(term: str) -> re.Pattern[str]:
    stem = term[:-1] if term.endswith("s") and len(term) > 3 else term
    return re.compile(r"(?<!\w)" + re.escape(stem) + r"(?:s|es)?(?!\w)" + _NOT_ABOUT_SUFFIX)


def on_topic(record: EvidenceRecord, terms: InterventionTerms) -> bool:
    """Whether the record's title or abstract carries the intervention terms."""
    if not terms.terms:
        return False
    text = _norm(f"{record.title} {record.abstract}")
    hits = [bool(_term_re(t).search(text)) for t in terms.terms]
    return all(hits) if terms.require_all else any(hits)


def on_topic_ids(
    claim: GraphClaim, evidence: Sequence[EvidenceRecord], cited: Iterable[str] = ()
) -> list[str]:
    """IDs of the records that are on topic for the claim's intervention."""
    cited = set(cited)
    terms = intervention_terms(claim.claim_text)
    return [e.evidence_id for e in evidence if e.evidence_id in cited or on_topic(e, terms)]


def _study_type(record: EvidenceRecord) -> str:
    """The record's study type as a ``rerank.StudyType`` value: the stored one when it is
    a known, informative value, else the publication-type lookup."""
    from app.core.retrieval.rerank import StudyType, classify_study

    st = str(record.study_type or "").strip().lower()
    if st in {t.value for t in StudyType} and st != StudyType.UNKNOWN.value:
        return st
    return classify_study(record).value


def thin_search(on_topic_records: Sequence[EvidenceRecord]) -> bool:
    """T64 (a): fewer than ``MIN_ON_TOPIC_RECORDS`` on-topic records and none of them a
    systematic review, randomised trial or guideline."""
    if len(on_topic_records) >= MIN_ON_TOPIC_RECORDS:
        return False
    return not any(_study_type(e) in STRONG_STUDY_TYPES for e in on_topic_records)


# T64 (c): nouns that name no condition or outcome on their own, and the words that may
# stand around them without naming one ("a potentially devastating condition").
_GENERIC_OUTCOME_NOUNS = frozenset(
    """condition conditions disease diseases illness illnesses ailment ailments disorder
    disorders problem problems issue issues sickness sicknesses malady maladies thing
    things complication complications""".split()
)
_VAGUE_MODIFIERS = frozenset(
    """potentially possibly devastating deadly dangerous serious severe terrible horrible
    awful nasty fatal lethal life threatening threatening many lot lots number numerous
    countless several various variety range host all any certain other others common
    chronic major minor rare kinds kind types type sorts sort whole bunch different
    health medical related against help helps helping prevent prevents preventing avoid
    avoids stop stops ward protect protects protecting fight fights fighting treat treats
    cure cures heal heals reduce reduces lower lowers keep keeps away off""".split()
)


def outcome_words(claim_text: str) -> frozenset[str]:
    """The outcome the claim names: lexicon condition/outcome concepts (by key) and the
    content words after its last claim verb, without stop words, vague modifiers and
    generic nouns. Empty: the claim names no outcome."""
    text = _norm(claim_text)
    verbs = list(_VERB_RE.finditer(text))
    if not verbs:
        return frozenset()
    tail = text[verbs[-1].end():]
    out = {m.concept.key for m in find_concepts(tail) if m.concept.kind != "intervention"}
    for m in sorted(find_concepts(tail), key=lambda m: -m.start):
        tail = f"{tail[:m.start]} {tail[m.end:]}"
    for w in tail.split():
        w = w.strip("'.,;:!?()[]")
        if (len(w) > 2 and w not in _STOPWORDS and w not in _VAGUE_MODIFIERS
                and w not in _GENERIC_OUTCOME_NOUNS and w not in _FILLER):
            out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return frozenset(out)


def outcome_unspecified(claim_text: str) -> bool:
    """T64 (c): the claim names no condition or outcome: after its last claim verb there is
    no lexicon condition/outcome, and the words left are only generic nouns ("condition",
    "diseases") with vague modifiers. Deliberately narrow: a word the rule does not know
    ("heart disease", "kidney stones") means the outcome *is* named."""
    text = _norm(claim_text)
    verbs = list(_VERB_RE.finditer(text))
    if not verbs:
        return False
    tail = text[verbs[-1].end():]
    if any(m.concept.kind != "intervention" for m in find_concepts(tail)):
        return False
    words = [w.strip("'.,;:!?") for w in tail.split()]
    words = [w for w in words if w and w not in _STOPWORDS and w not in _VAGUE_MODIFIERS]
    return bool(words) and all(w in _GENERIC_OUTCOME_NOUNS for w in words)


def _insufficient(result: VerificationResult, explanation: str, limitation: str) -> VerificationResult:
    return result.model_copy(update={
        "verdict": Verdict.INSUFFICIENT_EVIDENCE,
        "explanation": explanation,
        "limitations": [*result.limitations, limitation],
    })


def apply_unproven_guard(
    claim: GraphClaim, evidence: Sequence[EvidenceRecord], result: VerificationResult
) -> VerificationResult:
    """UNSUPPORTED stands only with at least one on-topic record (T49), a named outcome
    (T64 c) and a search that is not too thin (T64 a); otherwise INSUFFICIENT_EVIDENCE
    with ``search_found_nothing_on_topic`` / ``outcome_unspecified`` /
    ``search_too_thin``. Other verdicts pass through unchanged."""
    if result.verdict != Verdict.UNSUPPORTED:
        return result
    cited = [*result.supporting_evidence_ids, *result.contradicting_evidence_ids]
    ids = set(on_topic_ids(claim, evidence, cited))
    if not ids:
        return _insufficient(result, OFF_TOPIC_EXPLANATION, OFF_TOPIC_LIMITATION)
    if outcome_unspecified(claim.claim_text):
        return _insufficient(result, OUTCOME_UNSPECIFIED_EXPLANATION, OUTCOME_UNSPECIFIED_LIMITATION)
    if thin_search([e for e in evidence if e.evidence_id in ids]):
        return _insufficient(result, THIN_SEARCH_EXPLANATION, THIN_SEARCH_LIMITATION)
    return result


# ------------------------------------------------------------------ T64 (b) siblings


def same_intervention(a: GraphClaim, b: GraphClaim) -> bool:
    """Two claims are about the same intervention when their intervention terms share a
    term (a recognised concept's names; for unrecognised ones, the same word list)."""
    ta, tb = intervention_terms(a.claim_text), intervention_terms(b.claim_text)
    if not ta.terms or not tb.terms:
        return False
    if ta.require_all or tb.require_all:
        if ta.require_all and tb.require_all:
            return set(ta.terms) == set(tb.terms)
        # one recognised concept, one fallback word list: the fallback words must name it
        concept, words = (tb, ta) if ta.require_all else (ta, tb)
        return " ".join(words.terms) in concept.terms
    return bool(set(ta.terms) & set(tb.terms))


def same_outcome(unsupported: GraphClaim, sibling: GraphClaim) -> bool:
    """T64 (b), narrowed: the SUPPORTED sibling speaks to the UNSUPPORTED claim's outcome
    only if the UNSUPPORTED claim names none ("a potentially devastating condition") or
    the two name a common one. "Eggs prevent fatty liver" (SUPPORTED) says nothing about
    "eggs prevent macular degeneration" (tune v22)."""
    mine = outcome_words(unsupported.claim_text)
    return not mine or outcome_unspecified(unsupported.claim_text) or bool(mine & outcome_words(sibling.claim_text))


def apply_sibling_rule(
    claims: Sequence[GraphClaim], results: dict[str, VerificationResult]
) -> dict[str, VerificationResult]:
    """T64 (b): an UNSUPPORTED claim cannot decide the label when another claim in the
    same video about the same intervention, in a prevention / efficacy category, is
    SUPPORTED, and the two don't name different outcomes (:func:`same_outcome`): it
    becomes INSUFFICIENT_EVIDENCE with ``contradicted_by_sibling_claim``.
    The judge keeps its ``unproven_claim`` review reason (``judge.decide``), so a person
    still sees it. Returns a new dict; only changed entries differ."""
    by_id = {c.claim_id: c for c in claims}
    supported = [
        by_id[cid] for cid, v in results.items()
        if v.verdict == Verdict.SUPPORTED and cid in by_id
        and by_id[cid].claim_category in EFFICACY_CATEGORIES
    ]
    if not supported:
        return dict(results)
    out = dict(results)
    for cid, v in results.items():
        if v.verdict != Verdict.UNSUPPORTED or cid not in by_id:
            continue
        claim = by_id[cid]
        if any(s.claim_id != cid and same_intervention(claim, s) and same_outcome(claim, s) for s in supported):
            out[cid] = _insufficient(v, SIBLING_EXPLANATION, SIBLING_LIMITATION)
    return out
