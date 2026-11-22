"""Choose the passage of a reference page to quote for a claim (§6 "the quoted passage").

Deterministic: the page text is split into paragraph-sized passages (never longer than
``max_chars``), each scored by the share of the claim's content words it contains, with
a small bonus for the claim's numbers (doses, ages, limits, rates), which is what a
fact of record usually turns on. The quote is the page's own text, unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.core.retrieval.planning import content_words, normalize_claim

_STEM = re.compile(r"(?:ing|ed|es|s)$")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
NUMBER_BONUS = 0.15


def _stem(w: str) -> str:
    return _STEM.sub("", w) if len(w) > 4 else w


def claim_terms(claim_text: str) -> list[str]:
    return [_stem(w) for w in content_words(normalize_claim(claim_text))]


def _terms_in(text: str) -> set[str]:
    return {_stem(w) for w in normalize_claim(text).split()}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def split_passages(text: str, max_chars: int) -> list[str]:
    """Paragraphs, with long ones cut at sentence ends (or hard-cut) to ``max_chars``."""
    out: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if len(para) <= max_chars:
            out.append(para)
            continue
        cur = ""
        for sent in _SENTENCE.split(para):
            while len(sent) > max_chars:
                if cur:
                    out.append(cur)
                    cur = ""
                out.append(sent[:max_chars])
                sent = sent[max_chars:]
            if cur and len(cur) + 1 + len(sent) > max_chars:
                out.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}".strip()
        if cur:
            out.append(cur)
    return out


@dataclass(frozen=True)
class Passage:
    text: str
    overlap: float  # share of the claim's content words in the passage (with the title)
    score: float


def score_passage(claim_text: str, passage: str, title: str = "") -> Passage:
    terms = claim_terms(claim_text)
    found = _terms_in(f"{title} {passage}")
    overlap = (sum(1 for t in terms if t in found) / len(terms)) if terms else 0.0
    nums = _numbers(claim_text)
    bonus = NUMBER_BONUS * (len(nums & _numbers(passage)) / len(nums)) if nums else 0.0
    return Passage(passage, round(overlap, 4), round(min(1.0, overlap + bonus), 4))


def best_passage(claim_text: str, text: str, *, title: str = "", max_chars: int = 1200,
                 min_overlap: float = 0.3) -> Optional[Passage]:
    """The highest-scoring passage, or ``None`` when no passage reaches ``min_overlap``.
    Ties go to the earlier passage."""
    best: Optional[Passage] = None
    for chunk in split_passages(text, max_chars):
        p = score_passage(claim_text, chunk, title)
        if p.overlap < min_overlap:
            continue
        if best is None or p.score > best.score:
            best = p
    return best
