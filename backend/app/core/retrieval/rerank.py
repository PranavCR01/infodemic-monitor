"""Reranking: keep the papers that test the claim (target design §6 "Reranking", issue #32).

Search returns papers that *mention* the topic; this module keeps the ones that *test the
claim*, scores them, and caps them at 10 per claim. Two scores, kept apart on purpose:

- **Relevance** (``relevance_score``, 0–1): does the paper address this intervention, this
  outcome and a similar population? Computed by a lightweight, deterministic lexical
  scorer over the claim's PICO frame (``planning.frame_claim``) and the MeSH lexicon:

  - intervention and outcome coverage: each claim concept scores 1.0 when one of its
    terms is in the title, 0.7 when only in the abstract, 0.4 when only its broader
    MeSH heading appears, 0 when absent. The two sides
    are combined by a geometric mean, so a paper about only the intervention or only
    the outcome scores 0, however often it says the word;
  - when the lexicon found no concept on one side ("honey cures *cough*"), that side is
    the claim's leftover content words, so a missing outcome can't turn the check into
    "mentions the intervention";
  - population: humans unless the paper reads as an animal or lab study (×0.5), and the
    claim's own population ("in children") if it names one (×0.8 when absent). A paper
    *about* the claim as a social phenomenon (misinformation, conspiracy belief,
    social-media content) is studying people's beliefs, not the claim: ×0.5;
  - claims the lexicon can't frame fall back to the share of the claim's content words
    found in the paper.

  An injected ``RelevanceModel`` (for example a biomedical cross-encoder) can replace the
  lexical scorer; §6 says to start lightweight and escalate only if measured relevance is
  poor. Nothing here names a model.

- **Study type** (``study_type``) and its **quality score** (``quality_score``, 0–1): a
  lookup on PubMed's publication-type field. Systematic reviews and randomised trials in
  humans rank above observational studies, which rank above animal, lab and single-case
  studies. PubMed has no publication type for animal or in-vitro work, so for PubMed
  records with no informative type a few fixed title/abstract cues decide ("mice",
  "cell line", "cohort"). Library records keep the type a person gave them; one with no
  type is ``unknown``, below every tagged type (§6 "Searching it").

Papers below ``min_relevance`` are dropped, not passed on: forty off-topic papers are the
same failure as none (§6 "When it runs"), and the library fallback (T12) fires on
``RerankResult.cleared_threshold`` being false. The rest are ordered by a blend of the two
scores (relevance first), ties broken by PubMed's own order, and capped.

Plain Python with no LangGraph or MCP code, so the MCP server's ``rerank_evidence`` tool
(T13) can wrap ``Reranker.rerank``.
"""
from __future__ import annotations

import enum
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Optional, Protocol, Sequence

from app.core.retrieval.mesh import LEXICON
from app.core.retrieval.planning import _VERB_RE, content_words, frame_claim, normalize_claim
from app.core.retrieval.schemas import ClaimFrame, Concept, EvidenceRecord

MAX_EVIDENCE_PER_CLAIM = 10  # §6 "Cap"


# ------------------------------------------------------------------ study type


class StudyType(str, enum.Enum):
    SYSTEMATIC_REVIEW = "systematic_review"  # incl. meta-analysis
    RCT = "rct"
    GUIDELINE = "guideline"
    CLINICAL_TRIAL = "clinical_trial"  # non-randomised or unspecified trial in humans
    OBSERVATIONAL = "observational"  # cohort, case-control, cross-sectional
    NARRATIVE_REVIEW = "narrative_review"
    CASE_REPORT = "case_report"
    ANIMAL = "animal"
    IN_VITRO = "in_vitro"  # lab, cell and in-silico (mechanistic) studies
    OPINION = "opinion"  # editorial, comment, letter, news
    OTHER = "other"  # tagged, but none of the above (e.g. food composition)
    UNKNOWN = "unknown"  # no study type at all


class EvidenceClass(str, enum.Enum):
    """The coarse distinction issue #32 asks for."""

    EVIDENCE_SYNTHESIS = "evidence_synthesis"
    HUMAN_CLINICAL = "human_clinical"
    HUMAN_OBSERVATIONAL = "human_observational"
    ANIMAL = "animal"
    MECHANISTIC = "mechanistic"
    GENERAL = "general"  # narrative reviews, opinion, nutrition/food science, unknown


# Methodological quality, independent of relevance. Unknown is below every tagged type.
QUALITY: dict[StudyType, float] = {
    StudyType.SYSTEMATIC_REVIEW: 1.0,
    StudyType.RCT: 0.9,
    StudyType.GUIDELINE: 0.85,
    StudyType.CLINICAL_TRIAL: 0.75,
    StudyType.OBSERVATIONAL: 0.55,
    StudyType.NARRATIVE_REVIEW: 0.35,
    StudyType.CASE_REPORT: 0.2,
    StudyType.ANIMAL: 0.2,
    StudyType.IN_VITRO: 0.15,
    StudyType.OPINION: 0.1,
    StudyType.OTHER: 0.1,
    StudyType.UNKNOWN: 0.0,
}

_CLASS: dict[StudyType, EvidenceClass] = {
    StudyType.SYSTEMATIC_REVIEW: EvidenceClass.EVIDENCE_SYNTHESIS,
    StudyType.GUIDELINE: EvidenceClass.EVIDENCE_SYNTHESIS,
    StudyType.RCT: EvidenceClass.HUMAN_CLINICAL,
    StudyType.CLINICAL_TRIAL: EvidenceClass.HUMAN_CLINICAL,
    StudyType.CASE_REPORT: EvidenceClass.HUMAN_CLINICAL,
    StudyType.OBSERVATIONAL: EvidenceClass.HUMAN_OBSERVATIONAL,
    StudyType.ANIMAL: EvidenceClass.ANIMAL,
    StudyType.IN_VITRO: EvidenceClass.MECHANISTIC,
    StudyType.NARRATIVE_REVIEW: EvidenceClass.GENERAL,
    StudyType.OPINION: EvidenceClass.GENERAL,
    StudyType.OTHER: EvidenceClass.GENERAL,
    StudyType.UNKNOWN: EvidenceClass.GENERAL,
}


def evidence_class(study_type: StudyType | str) -> EvidenceClass:
    return _CLASS[StudyType(study_type)]


# PubMed publication types (lower case) → study type, strongest first.
_PT_RULES: tuple[tuple[StudyType, frozenset[str]], ...] = (
    (StudyType.SYSTEMATIC_REVIEW, frozenset({"systematic review", "meta-analysis", "network meta-analysis"})),
    (StudyType.RCT, frozenset({"randomized controlled trial", "pragmatic clinical trial", "equivalence trial"})),
    (StudyType.GUIDELINE, frozenset({"practice guideline", "guideline", "consensus development conference"})),
    (StudyType.CLINICAL_TRIAL, frozenset({
        "clinical trial", "controlled clinical trial", "clinical trial, phase i", "clinical trial, phase ii",
        "clinical trial, phase iii", "clinical trial, phase iv", "adaptive clinical trial",
    })),
)
_PT_OBSERVATIONAL = frozenset({"observational study", "twin study"})
_PT_CASE = frozenset({"case reports"})
_PT_REVIEW = frozenset({"review", "scoping review"})
_PT_OPINION = frozenset({"editorial", "comment", "letter", "news", "newspaper article", "interview"})
_PT_VETERINARY = frozenset({
    "randomized controlled trial, veterinary", "clinical trial, veterinary", "observational study, veterinary",
})
_PT_UNINFORMATIVE = frozenset({
    "journal article", "research support, non-u.s. gov't", "research support, u.s. gov't, p.h.s.",
    "research support, n.i.h., extramural", "research support, n.i.h., intramural",
    "research support, u.s. gov't, non-p.h.s.", "english abstract", "comparative study",
    "multicenter study", "evaluation study", "validation study", "preprint",
})


def _cue(*words: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])(?:" + "|".join(words) + r")(?![\w-])")


# Fixed cues, read only when PubMed's publication types say nothing about the design.
_SR_CUE = _cue(r"systematic review", r"meta-analys[ie]s", r"meta analys[ie]s")
_RCT_CUE = _cue(r"randomi[sz]ed (?:controlled |clinical |placebo-controlled |double-blind )?trial",
                r"randomi[sz]ed,? (?:double-blind|placebo-controlled)", r"were randomi[sz]ed")
_TRIAL_CUE = _cue(r"clinical trial", r"open-label trial", r"pilot trial", r"single-arm")
_OBS_CUE = _cue(r"cohort", r"case-control", r"case control", r"cross-sectional", r"cross sectional",
                r"prospective study", r"retrospective study", r"population-based", r"registry",
                r"national survey", r"surveillance data", r"ecological study")
_CASE_CUE = _cue(r"case report", r"we report a case", r"we describe a case", r"a \d+-year-old")
_ANIMAL_CUE = _cue(r"mice", r"mouse", r"murine", r"rats?", r"rodents?", r"hamsters?", r"ferrets?",
                   r"guinea pigs?", r"piglets?", r"pigs", r"monkeys?", r"macaques?", r"zebrafish",
                   r"rabbits?", r"chickens?", r"broilers?", r"dogs", r"animal models?", r"in vivo model",
                   r"xenografts?")
_IN_VITRO_CUE = _cue(r"in vitro", r"cell lines?", r"cultured cells", r"cell culture", r"in silico",
                     r"molecular docking", r"hela", r"mcf-7", r"apoptosis in \w+ cells",
                     r"cancer cells", r"tumou?r cells", r"cells were treated", r"vero cells")
_HUMAN_CUE = _cue(r"patients", r"participants", r"volunteers", r"humans", r"adults", r"children",
                  r"women", r"men", r"subjects", r"infants", r"pregnant", r"people", r"individuals")
_REVIEW_CUE = _cue(r"narrative review", r"we review", r"this review", r"overview")
# Papers *about* a claim as a social phenomenon (misinformation research), not tests of it.
_DISCOURSE_CUE = _cue(r"misinformation", r"disinformation", r"conspiracy", r"conspiracies",
                      r"social media", r"twitter", r"tweets", r"youtube", r"tiktok", r"facebook",
                      r"content analysis", r"infodemic", r"vaccine hesitancy", r"belief in", r"arson")
_COMPOSITION_CUE = _cue(r"composition", r"hplc", r"antioxidant capacity", r"phenolic content",
                        r"content of", r"chemical profile", r"nutrient content")


def classify_study(record: EvidenceRecord) -> StudyType:
    """Study type of one record (§6 "Study type, scored separately from relevance")."""
    types = {t.strip().lower() for t in record.publication_type if t and t.strip()}
    if record.source == "library":
        # Scans carry no PubMed tags; the type comes from the person who uploaded it
        # (§6 "Building the library" step 1). No guessing from text.
        return _from_types(types) or StudyType.UNKNOWN

    if types & _PT_VETERINARY:
        return StudyType.ANIMAL
    for st, names in _PT_RULES:
        if types & names:
            return st

    text = normalize_claim(f"{record.title} {record.abstract}")
    if _IN_VITRO_CUE.search(text):
        return StudyType.IN_VITRO
    if _ANIMAL_CUE.search(text) and not _HUMAN_CUE.search(text):
        return StudyType.ANIMAL
    if types & _PT_CASE:
        return StudyType.CASE_REPORT
    if types & _PT_OBSERVATIONAL:
        return StudyType.OBSERVATIONAL
    if types & _PT_REVIEW:
        return StudyType.NARRATIVE_REVIEW
    if types & _PT_OPINION:
        return StudyType.OPINION

    # Only uninformative types ("Journal Article") or none: read the fixed cues.
    if _SR_CUE.search(text):
        return StudyType.SYSTEMATIC_REVIEW
    if _RCT_CUE.search(text):
        return StudyType.RCT
    if _TRIAL_CUE.search(text):
        return StudyType.CLINICAL_TRIAL
    if _CASE_CUE.search(text):
        return StudyType.CASE_REPORT
    if _OBS_CUE.search(text):
        return StudyType.OBSERVATIONAL
    if _REVIEW_CUE.search(text):
        return StudyType.NARRATIVE_REVIEW
    if _COMPOSITION_CUE.search(text):
        return StudyType.OTHER
    if not types:
        return StudyType.UNKNOWN
    return StudyType.OTHER


def _from_types(types: set[str]) -> Optional[StudyType]:
    if types & _PT_VETERINARY:
        return StudyType.ANIMAL
    for st, names in _PT_RULES:
        if types & names:
            return st
    for names, st in (
        (_PT_CASE, StudyType.CASE_REPORT),
        (_PT_OBSERVATIONAL, StudyType.OBSERVATIONAL),
        (_PT_REVIEW, StudyType.NARRATIVE_REVIEW),
        (_PT_OPINION, StudyType.OPINION),
    ):
        if types & names:
            return st
    # The library manifest may use our own names ("animal", "in_vitro", "rct").
    for t in types:
        try:
            return StudyType(t.replace(" ", "_").replace("-", "_"))
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------- relevance


class RelevanceModel(Protocol):
    """Optional learned relevance scorer (e.g. a biomedical cross-encoder) that replaces
    the lexical one. Returns one score in [0, 1] per record, in order."""

    def __call__(self, claim_text: str, records: Sequence[EvidenceRecord]) -> Sequence[float]: ...


@lru_cache(maxsize=None)
def _lexicon_terms(key: str) -> tuple[str, ...]:
    for entry in LEXICON:
        if entry.key == key:
            return tuple({*entry.phrases, *entry.synonyms, *([entry.mesh.lower()] if entry.mesh else [])})
    return ()


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern[str]:
    t = normalize_claim(term)
    # Light plural tolerance both ways: "vaccine" ~ "vaccines", "beverages" ~ "beverage".
    if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return re.compile(r"(?<![\w-])" + re.escape(t) + r"(?:e?s)?(?![\w-])")


def concept_terms(concept: Concept) -> tuple[str, ...]:
    terms = {concept.label, concept.matched_text, *concept.synonyms, *_lexicon_terms(concept.key)}
    if concept.mesh:
        terms.add(concept.mesh)
    return tuple(sorted(t for t in terms if t and len(normalize_claim(t)) >= 2))


def _found(terms: Iterable[str], text: str) -> bool:
    return any(_term_pattern(t).search(text) for t in terms)


TITLE_HIT = 1.0
ABSTRACT_HIT = 0.7
PARENT_HIT = 0.4  # only the broader heading ("beverages" for "hot drinks")


def _coverage(concepts: Sequence[Concept], title: str, abstract: str) -> Optional[float]:
    """Mean per-concept hit score; ``None`` when the claim has no concept on this side."""
    if not concepts:
        return None
    total = 0.0
    for c in concepts:
        terms = concept_terms(c)
        if _found(terms, title):
            total += TITLE_HIT
        elif _found(terms, abstract):
            total += ABSTRACT_HIT
        elif c.parent_mesh and _found((c.parent_mesh,), f"{title} {abstract}"):
            total += PARENT_HIT
    return total / len(concepts)


_STEM_RE = re.compile(r"(?:ing|ed|es|s)$")


def _stem(word: str) -> str:
    return _STEM_RE.sub("", word) if len(word) > 4 else word


@dataclass(frozen=True)
class RelevanceBreakdown:
    """Why a paper got its relevance score (kept for audit and tests)."""

    score: float
    intervention: Optional[float] = None
    outcome: Optional[float] = None
    population: float = 1.0
    keyword: Optional[float] = None
    non_human: bool = False


NON_HUMAN_FACTOR = 0.5
POPULATION_MISS_FACTOR = 0.8
DISCOURSE_FACTOR = 0.5


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.split(r"[\s\-/]+", text) if w}


def _implicit_side(frame: ClaimFrame, side: str) -> list[str]:
    """Content words on one side of the claim verb that no lexicon concept covered
    ("honey cures *cough*"), stemmed. Used when the lexicon found no concept on that
    side, so a missing outcome doesn't turn the check into "mentions the intervention"."""
    text = frame.normalized_text
    verb = _VERB_RE.search(text)
    if not verb:
        return []
    seg = text[: verb.start()] if side == "intervention" else text[verb.end() :]
    for c in (*frame.intervention, *frame.outcome, *frame.population, *frame.comparator):
        if c.matched_text:
            seg = seg.replace(c.matched_text, " ")
    words = []
    for w in content_words(normalize_claim(seg)):
        for part in re.split(r"[\-/]+", w):
            if len(part) > 2 and part not in ("associated", "related", "induced", "based"):
                words.append(_stem(part))
    return list(dict.fromkeys(words))


def _word_coverage(words: Sequence[str], title: str, abstract: str) -> Optional[float]:
    if not words:
        return None
    t, a = _words(title), _words(abstract)
    return sum(TITLE_HIT if w in t else ABSTRACT_HIT if w in a else 0.0 for w in words) / len(words)


def lexical_relevance(frame: ClaimFrame, record: EvidenceRecord, study: StudyType) -> RelevanceBreakdown:
    title = normalize_claim(record.title)
    abstract = normalize_claim(record.abstract)
    i_cov = _coverage(frame.intervention, title, abstract)
    o_cov = _coverage(frame.outcome, title, abstract)
    if frame.has_concepts:
        if i_cov is None:
            i_cov = _word_coverage(_implicit_side(frame, "intervention"), title, abstract)
        if o_cov is None:
            o_cov = _word_coverage(_implicit_side(frame, "outcome"), title, abstract)

    non_human = study in (StudyType.ANIMAL, StudyType.IN_VITRO)
    pop = NON_HUMAN_FACTOR if non_human else 1.0
    if _DISCOURSE_CUE.search(f"{title} {abstract}"):
        pop *= DISCOURSE_FACTOR
    if frame.population and not non_human:
        p_cov = _coverage(frame.population, title, abstract) or 0.0
        if p_cov == 0.0:
            pop *= POPULATION_MISS_FACTOR

    sides = [v for v in (i_cov, o_cov) if v is not None]
    if sides:
        core = math.prod(sides) ** (1 / len(sides))
        return RelevanceBreakdown(core * pop, i_cov, o_cov, pop, None, non_human)

    # No concept the lexicon knows: share of the claim's content words in the paper.
    words = [_stem(w) for w in (frame.keywords or content_words(frame.normalized_text))]
    if not words:
        return RelevanceBreakdown(0.0, population=pop, keyword=0.0, non_human=non_human)
    paper = {_stem(w) for w in f"{title} {abstract}".split()}
    title_words = {_stem(w) for w in title.split()}
    hits = sum(TITLE_HIT if w in title_words else ABSTRACT_HIT if w in paper else 0.0 for w in words)
    kw = hits / len(words)
    return RelevanceBreakdown(kw * pop, population=pop, keyword=kw, non_human=non_human)


# --------------------------------------------------------------------- ranking


@dataclass(frozen=True)
class RerankConfig:
    """Tunable by measurement (issue #32: "initial limit; tune by measurement")."""

    max_results: int = MAX_EVIDENCE_PER_CLAIM
    min_relevance: float = 0.4
    # Ordering blend: relevance dominates; study type breaks near-ties in its favour.
    relevance_weight: float = 0.7
    quality_weight: float = 0.3


DEFAULT_RERANK_CONFIG = RerankConfig()


@dataclass(frozen=True)
class ScoredEvidence:
    record: EvidenceRecord  # with relevance_score, study_type, quality_score set
    rank_score: float
    original_rank: int
    breakdown: Optional[RelevanceBreakdown] = None

    @property
    def relevance(self) -> float:
        return self.record.relevance_score or 0.0


@dataclass
class RerankResult:
    claim_text: str
    kept: list[EvidenceRecord]
    scored: list[ScoredEvidence] = field(default_factory=list)  # every input, best first
    dropped_below_threshold: list[str] = field(default_factory=list)  # evidence IDs
    dropped_over_cap: list[str] = field(default_factory=list)

    @property
    def cleared_threshold(self) -> bool:
        """False when no paper is relevant enough: the library fallback's trigger (§6)."""
        return bool(self.kept)


class Reranker:
    """Relevance + study-type scoring, threshold and cap for one claim's evidence."""

    def __init__(
        self,
        config: RerankConfig = DEFAULT_RERANK_CONFIG,
        relevance_model: Optional[RelevanceModel] = None,
    ) -> None:
        self.config = config
        self.relevance_model = relevance_model

    def score(self, claim_text: str, records: Sequence[EvidenceRecord]) -> list[ScoredEvidence]:
        frame = frame_claim(claim_text)
        studies = [classify_study(r) for r in records]
        breakdowns: list[Optional[RelevanceBreakdown]]
        if self.relevance_model is not None:
            raw = list(self.relevance_model(claim_text, records))
            if len(raw) != len(records):
                raise ValueError(f"relevance model returned {len(raw)} scores for {len(records)} records")
            rel = [min(1.0, max(0.0, float(x))) for x in raw]
            breakdowns = [None] * len(records)
        else:
            breakdowns = [lexical_relevance(frame, r, s) for r, s in zip(records, studies)]
            rel = [b.score for b in breakdowns]

        cfg = self.config
        out = []
        for i, (rec, st, rv, bd) in enumerate(zip(records, studies, rel, breakdowns)):
            quality = QUALITY[st]
            scored = rec.model_copy(
                update={
                    "relevance_score": round(rv, 4),
                    "study_type": st.value,
                    "quality_score": quality,
                }
            )
            rank = cfg.relevance_weight * rv + cfg.quality_weight * quality
            out.append(ScoredEvidence(scored, round(rank, 6), i, bd))
        out.sort(key=lambda s: (-s.rank_score, s.original_rank))
        return out

    def rerank(self, claim_text: str, records: Sequence[EvidenceRecord]) -> RerankResult:
        scored = self.score(claim_text, records)
        cfg = self.config
        above = [s for s in scored if s.relevance >= cfg.min_relevance]
        below = [s.record.evidence_id for s in scored if s.relevance < cfg.min_relevance]
        kept = above[: cfg.max_results]
        over = [s.record.evidence_id for s in above[cfg.max_results :]]
        return RerankResult(
            claim_text=claim_text,
            kept=[s.record for s in kept],
            scored=scored,
            dropped_below_threshold=below,
            dropped_over_cap=over,
        )


def rerank_evidence(
    claim_text: str,
    records: Sequence[EvidenceRecord],
    k: int = MAX_EVIDENCE_PER_CLAIM,
    *,
    reranker: Optional[Reranker] = None,
) -> list[EvidenceRecord]:
    """Functional form for the MCP tool (§6 "Retrieval as a shared service"):
    ``rerank_evidence(claim, records, k)``. ``k`` can only lower the cap of 10."""
    base = reranker or Reranker()
    k = max(0, min(k, MAX_EVIDENCE_PER_CLAIM))
    cfg = RerankConfig(
        max_results=k,
        min_relevance=base.config.min_relevance,
        relevance_weight=base.config.relevance_weight,
        quality_weight=base.config.quality_weight,
    )
    return Reranker(cfg, base.relevance_model).rerank(claim_text, records).kept


__all__ = [
    "DEFAULT_RERANK_CONFIG",
    "EvidenceClass",
    "MAX_EVIDENCE_PER_CLAIM",
    "QUALITY",
    "RelevanceBreakdown",
    "RelevanceModel",
    "RerankConfig",
    "RerankResult",
    "Reranker",
    "ScoredEvidence",
    "StudyType",
    "classify_study",
    "concept_terms",
    "evidence_class",
    "lexical_relevance",
    "rerank_evidence",
]
