"""Claims that cite a specific study (T50 items e and i, design §6 "Planning the search").

"A 2026 JAMA study of 5 million babies found ..." names one paper. A topic search
for the claim's words may never surface it among thousands of related papers, so such
a claim first gets a **citation lookup**: the journal as ``[ta]`` (PubMed's journal
title abbreviation), the year as ``[dp]`` (publication date) and the claim's topic
terms. The same cue also decides when the find-the-study step runs (``find_study``).

Deterministic and offline. A claim *cites a study* when it names a known journal, or
when it says study / trial / published / researchers together with a year, a sample
size or an institution. A year alone ("given routinely since 1961") is not a citation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Surface form (lower case, regex) → PubMed [ta] abbreviation. Ambiguous one-word
# titles (Nature, Science, Cell, Circulation, Pediatrics) only count after "published
# in" / "journal", so "the science says" or "blood circulation" is not a citation.
_JOURNALS: tuple[tuple[str, str], ...] = (
    (r"jama pediatrics", "JAMA Pediatr"),
    (r"jama network open", "JAMA Netw Open"),
    (r"jama internal medicine", "JAMA Intern Med"),
    (r"jama", "JAMA"),
    (r"journal of the american medical association", "JAMA"),
    (r"new england journal(?: of medicine)?", "N Engl J Med"),
    (r"nejm", "N Engl J Med"),
    (r"the lancet|lancet", "Lancet"),
    (r"british medical journal|the bmj|bmj", "BMJ"),
    (r"annals of internal medicine", "Ann Intern Med"),
    (r"plos one", "PLoS One"),
    (r"cochrane(?: review| database)?", "Cochrane Database Syst Rev"),
    (r"nature medicine", "Nat Med"),
    (r"american journal of clinical nutrition", "Am J Clin Nutr"),
    (r"journal of the american college of cardiology", "J Am Coll Cardiol"),
    (r"mmwr", "MMWR Morb Mortal Wkly Rep"),
)
_AMBIGUOUS_JOURNALS: tuple[tuple[str, str], ...] = (
    (r"nature", "Nature"), (r"science", "Science"), (r"cell", "Cell"),
    (r"circulation", "Circulation"), (r"pediatrics", "Pediatrics"),
)
_JOURNAL_RES = [(re.compile(r"(?<![\w-])(?:" + p + r")(?![\w-])"), ta) for p, ta in _JOURNALS]
_AMBIGUOUS_RES = [
    (re.compile(r"(?:published in|journal|revista|revue)\s+(?:the\s+)?(?:" + p + r")(?![\w-])"), ta)
    for p, ta in _AMBIGUOUS_JOURNALS
]
_STUDY_RE = re.compile(
    r"(?<![\w-])(?:study|studies|trial|trials|published|researchers|scientists|meta-analysis|"
    r"review|cohort|estudio|estudios|investigadores|étude|études|chercheurs)(?![\w-])"
)
_YEAR_RE = re.compile(r"(?<!\d)(19[6-9]\d|20[0-4]\d)(?!\d)")
_SAMPLE_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[,.\s]\d{3})+|\d+(?:\.\d+)?\s?(?:million|thousand|mil|millones)|\d{2,})\s+"
    r"(?:people|participants|patients|children|kids|babies|infants|newborns|women|men|adults|"
    r"subjects|individuals|mothers|personas|pacientes|niños|bebés|personnes|patients)"
)
_INSTITUTION_RE = re.compile(
    r"(?<![\w-])(?:harvard|stanford|johns hopkins|mayo clinic|oxford|cambridge|yale|"
    r"university of [a-z]+|universidad de [a-z]+|université de [a-z]+|"
    r"children's hospital of [a-z]+|nih|national institutes of health)(?![\w-])"
)


@dataclass(frozen=True)
class CitationCue:
    """What the claim says about the study it cites."""

    journal: Optional[str] = None  # PubMed [ta] abbreviation
    year: Optional[int] = None
    sample_size: Optional[str] = None
    institution: Optional[str] = None
    signals: tuple[str, ...] = field(default=())

    @property
    def cites_study(self) -> bool:
        return bool(self.signals)

    def describe(self) -> dict:
        return {"journal": self.journal, "year": self.year, "sample_size": self.sample_size,
                "institution": self.institution}


def citation_cue(normalized_text: str) -> CitationCue:
    """The citation the claim makes, if any. ``normalized_text`` is lower case
    (``planning.normalize_claim``)."""
    t = normalized_text
    journal = next((ta for rx, ta in _JOURNAL_RES if rx.search(t)), None)
    if journal is None:
        journal = next((ta for rx, ta in _AMBIGUOUS_RES if rx.search(t)), None)
    year_m = _YEAR_RE.search(t)
    sample_m = _SAMPLE_RE.search(t)
    inst_m = _INSTITUTION_RE.search(t)
    signals: list[str] = []
    if journal:
        signals.append("journal")
    elif _STUDY_RE.search(t) and (year_m or sample_m or inst_m):
        signals += [s for s, m in (("year", year_m), ("sample_size", sample_m), ("institution", inst_m)) if m]
    if not signals:
        return CitationCue()
    return CitationCue(
        journal=journal,
        year=int(year_m.group(1)) if year_m else None,
        sample_size=sample_m.group(0) if sample_m else None,
        institution=inst_m.group(0) if inst_m else None,
        signals=tuple(signals),
    )


__all__ = ["CitationCue", "citation_cue"]
