"""Choose the passage of a reference page to quote for a claim (§6 "the quoted passage").

Deterministic: the page text is split into paragraph-sized passages (never longer than
``max_chars``), each scored by the share of the claim's content words it contains, with
a small bonus for the claim's numbers (doses, ages, limits, rates), which is what a
fact of record usually turns on. The quote is the page's own text, unchanged.

Real publisher pages (CDC schedules, T19) break one statement over several short
blocks ("Doses are given at:" / "12–15 months old" / "1st dose"), so a candidate can
also be a window of consecutive whole paragraphs, up to ``window_chars`` and
``WINDOW_PARAGRAPHS``. The window is quoted as it appears on the page (paragraphs
joined by a blank line, so it is still a substring of the snapshot). Equal scores go
to the shorter candidate, so a window wins only when it adds claim content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.core.retrieval.planning import content_words, normalize_claim

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
NUMBER_BONUS = 0.15
WINDOW_PARAGRAPHS = 6


def _stem(w: str) -> str:
    """A light plural/verb-ending stemmer. Plurals lose only what the plural added, so
    "doses"/"dose" and "vaccines"/"vaccine" match (the earlier strip of a bare "es"
    turned them into "dos"/"vaccin" against "dose"/"vaccine": T19)."""
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "zes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    return w


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


def candidate_passages(text: str, max_chars: int, window_chars: int) -> list[str]:
    """Every paragraph-sized passage (as ``split_passages``), plus windows of up to
    ``WINDOW_PARAGRAPHS`` consecutive whole paragraphs totalling at most
    ``window_chars``, in page order."""
    out: list[str] = []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    for i, para in enumerate(paras):
        out.extend(split_passages(para, max_chars))
        if len(para) > window_chars:
            continue
        window = para
        for nxt in paras[i + 1: i + WINDOW_PARAGRAPHS]:
            if len(window) + 2 + len(nxt) > window_chars:
                break
            window = f"{window}\n\n{nxt}"
            out.append(window)
    return out


def best_passage(claim_text: str, text: str, *, title: str = "", max_chars: int = 1200,
                 min_overlap: float = 0.3, window_chars: Optional[int] = None) -> Optional[Passage]:
    """The highest-scoring passage, or ``None`` when no passage reaches ``min_overlap``.
    Ties go to the shorter passage, then the earlier one. ``window_chars`` (default
    half of ``max_chars``) caps multi-paragraph windows; 0 turns them off."""
    window_chars = max_chars // 2 if window_chars is None else min(window_chars, max_chars)
    best: Optional[Passage] = None
    for chunk in candidate_passages(text, max_chars, window_chars):
        p = score_passage(claim_text, chunk, title)
        if p.overlap < min_overlap:
            continue
        if best is None or p.score > best.score or (p.score == best.score and len(p.text) < len(best.text)):
            best = p
    return best
