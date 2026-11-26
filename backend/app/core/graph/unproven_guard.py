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
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from app.core.graph.state import EvidenceRecord, GraphClaim, Verdict, VerificationResult
from app.core.retrieval.mesh import find_concepts
from app.core.retrieval.planning import _STOPWORDS, _VERB_RE, frame_claim, normalize_claim

OFF_TOPIC_LIMITATION = "search_found_nothing_on_topic"
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


def apply_unproven_guard(
    claim: GraphClaim, evidence: Sequence[EvidenceRecord], result: VerificationResult
) -> VerificationResult:
    """UNSUPPORTED stands only with at least one on-topic record; otherwise
    INSUFFICIENT_EVIDENCE with ``search_found_nothing_on_topic``. Other verdicts pass
    through unchanged."""
    if result.verdict != Verdict.UNSUPPORTED:
        return result
    cited = [*result.supporting_evidence_ids, *result.contradicting_evidence_ids]
    if on_topic_ids(claim, evidence, cited):
        return result
    return result.model_copy(update={
        "verdict": Verdict.INSUFFICIENT_EVIDENCE,
        "explanation": OFF_TOPIC_EXPLANATION,
        "limitations": [*result.limitations, OFF_TOPIC_LIMITATION],
    })
