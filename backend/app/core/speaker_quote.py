"""The "The speaker says" quote: the transcript words that carry a claim (T65 e).

The result page and the export used to quote the first segment of the claim's span. In
job d2bf4179 that was often the tail of the previous sentence. Here the quote is the
segment, or the run of adjacent segments, inside the claim's span (and its source
segments) whose words overlap the claim's words most, using the T45 Unicode tokens.

- Candidates: speech segments overlapping ``[start, end]``, plus the claim's
  ``source_segment_ids`` that are speech segments; in time order.
- Score of a run of adjacent candidates: how many distinct content words of the claim
  it contains. A segment is added to a run only if it raises the score, so the quote
  stays as short as the claim allows. Ties go to the shorter, then the earlier run.
- No candidate shares a content word with the claim: no quote (``None``), rather than a
  quote that does not say the claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from app.core.text_tokens import word_tokens

MAX_RUN = 3
# Function words that would make any segment "overlap" any claim (English; other
# languages fall back to plain token overlap, which still ranks segments correctly).
_STOP = frozenset(
    "a an the and or but of to in on at for from by with as is are was were be been being it its "
    "this that these those there their they them we our you your he she his her i me my not no "
    "do does did so if than then can could will would should may might just very more most less "
    "into about over up out what which who whom how when where why all any some such also".split()
)


@dataclass(frozen=True)
class QuoteSegment:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class SpeakerQuote:
    text: str
    segment_ids: tuple[str, ...]
    start_seconds: float
    end_seconds: float
    score: int


def content_words(text: Optional[str]) -> set[str]:
    toks = word_tokens(text)
    content = {t for t in toks if t not in _STOP and not (t.isascii() and len(t) < 2)}
    return content or set(toks)


def _candidates(segments: Sequence[QuoteSegment], start: float, end: float,
                source_ids: Iterable[str]) -> list[QuoteSegment]:
    ids = set(source_ids or ())
    eps = 1e-6
    picked = [s for s in segments
              if s.segment_id in ids or (s.start_seconds < end - eps and s.end_seconds > start + eps)]
    return sorted(picked, key=lambda s: (s.start_seconds, s.segment_id))


def best_overlap_quote(claim_text: str, segments: Sequence[QuoteSegment], start: float, end: float,
                       source_ids: Iterable[str] = (), max_run: int = MAX_RUN) -> Optional[SpeakerQuote]:
    claim = content_words(claim_text)
    cands = _candidates(segments, start, end, source_ids)
    if not claim or not cands:
        return None
    words = [content_words(s.text) & claim for s in cands]
    best: Optional[tuple[int, int, int, int]] = None  # (score, -length, -index, end index)
    for i in range(len(cands)):
        if not words[i]:
            continue
        covered = set(words[i])
        j = i
        key = (len(covered), -1, -i, i)
        best = key if best is None or key > best else best
        while j + 1 < len(cands) and j + 1 - i + 1 <= max_run:
            gain = words[j + 1] - covered
            if not gain:
                break
            j += 1
            covered |= gain
            key = (len(covered), -(j - i + 1), -i, j)
            best = key if key > best else best
    if best is None:
        return None
    score, neg_len, neg_i, j = best
    run = cands[-neg_i: j + 1]
    return SpeakerQuote(
        text=" ".join(" ".join(s.text.split()) for s in run),
        segment_ids=tuple(s.segment_id for s in run),
        start_seconds=run[0].start_seconds, end_seconds=run[-1].end_seconds, score=score,
    )
