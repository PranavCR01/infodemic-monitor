"""Route on-screen text by kind (T68; design §2, §3, §15).

``vision_ocr`` reports each piece of on-screen text with a kind. This module decides
where each piece goes:

- ``title_or_claim_card`` -> claim extraction, as a timed OCR segment.
- ``subtitle`` -> dropped when it fuzzy-matches the transcript in the same time window
  (it repeats the speech; 459 of the golden set's 550 claims are ``claim_source=both``,
  mostly auto-subtitles). A subtitle that matches nothing said nearby (speech Whisper
  missed, or a caption in another language) goes to extraction like a card.
- ``document_or_chart`` -> never to extraction. Its one-line note is kept as a
  ``ScreenDocument`` and offered to find_study as a search hint (``hints_for``).

Plain code, deterministic, no model call. Matching is token containment: the share of
a subtitle's words found (exactly, or as a close misspelling: OCR misreads such as
"@ooks" for "looks") among the words spoken in its time window, padded by
``WINDOW_PAD_SECONDS`` on each side.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from app.core.extraction.vision_ocr import CARD, DOCUMENT, SUBTITLE, TimedText

WINDOW_PAD_SECONDS = 2.0
SUBTITLE_MATCH = 0.6      # share of the subtitle's words found in the speech window
FUZZY_WORD = 0.8          # difflib ratio for a misread word to count as found
HINT_PAD_SECONDS = 5.0    # a document shown within this many seconds of a claim is "near" it
MAX_HINTS = 3
HINT_MAX_CHARS = 160

_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Spoken:
    start: float
    end: float
    text: str


@dataclass
class RoutedScreenText:
    """Where each piece of on-screen text went."""

    to_extraction: list[TimedText] = field(default_factory=list)
    documents: list[TimedText] = field(default_factory=list)
    subtitles_dropped: list[TimedText] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "title_or_claim_card": sum(1 for s in self.to_extraction if s.kind == CARD),
            "subtitle_kept": sum(1 for s in self.to_extraction if s.kind == SUBTITLE),
            "subtitle_dropped": len(self.subtitles_dropped),
            "document_or_chart": len(self.documents),
        }


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").casefold()) if w != "_"]


def _found(word: str, pool: set[str]) -> bool:
    if word in pool:
        return True
    if len(word) < 4:
        return False
    near = [p for p in pool if abs(len(p) - len(word)) <= 2]
    return bool(difflib.get_close_matches(word, near, n=1, cutoff=FUZZY_WORD))


def containment(text: str, spoken: str) -> float:
    """Share of ``text``'s words found in ``spoken`` (0 when ``text`` has none)."""
    ws = words(text)
    if not ws:
        return 0.0
    pool = set(words(spoken))
    return sum(1 for w in ws if _found(w, pool)) / len(ws)


def speech_window(spoken: Sequence[Spoken], start: float, end: float,
                  pad: float = WINDOW_PAD_SECONDS) -> str:
    return " ".join(s.text for s in spoken if s.end >= start - pad and s.start <= end + pad)


def matches_speech(seg: TimedText, spoken: Sequence[Spoken], *, pad: float = WINDOW_PAD_SECONDS,
                   threshold: float = SUBTITLE_MATCH) -> bool:
    ws = words(seg.text)
    if not ws:
        return True  # nothing left to say
    window = speech_window(spoken, seg.start, seg.end, pad)
    need = 1.0 if len(ws) <= 2 else threshold  # "limit" alone must be said, not half-said
    return containment(seg.text, window) >= need


def spoken_from(transcript_segments: Optional[Iterable[dict]], transcript: str = "") -> list[Spoken]:
    """Timed speech for matching: Whisper's segments when kept, else the whole
    transcript as one window covering the video."""
    out = []
    for s in transcript_segments or []:
        text = str(s.get("text", "")).strip()
        if text:
            start = float(s.get("start", 0.0))
            out.append(Spoken(start, max(start, float(s.get("end", start))), text))
    if not out and (transcript or "").strip():
        out.append(Spoken(0.0, float("inf"), transcript))
    return out


def route(segs: Sequence[TimedText], spoken: Sequence[Spoken]) -> RoutedScreenText:
    out = RoutedScreenText()
    for s in segs:
        if s.kind == DOCUMENT:
            out.documents.append(s)
        elif s.kind == SUBTITLE and matches_speech(s, spoken):
            out.subtitles_dropped.append(s)
        else:
            out.to_extraction.append(s)
    return out


def hints_for(start: float, end: float, documents: Sequence, *, pad: float = HINT_PAD_SECONDS,
              limit: int = MAX_HINTS, fallback_all: bool = False) -> list[str]:
    """Search hints for a claim at ``start``-``end``: the notes of documents shown near
    it (overlapping first, then by distance). With ``fallback_all`` (the claim cites a
    study) and nothing near, every document the video shows, in order: a speaker often
    talks about a report after it has left the screen. At most ``limit``, deduplicated.
    ``documents``: anything with ``start``, ``end`` and ``note``."""
    def gap(d) -> float:
        return max(0.0, d.start - end, start - d.end)

    near = sorted((d for d in documents if gap(d) <= pad), key=lambda d: (gap(d), d.start))
    pool = near or (list(documents) if fallback_all else [])
    notes = [" ".join(str(d.note).split())[:HINT_MAX_CHARS] for d in pool]
    return [n for n in dict.fromkeys(notes) if n][:limit]


__all__ = [
    "RoutedScreenText", "Spoken", "containment", "hints_for", "matches_speech", "route", "spoken_from",
    "speech_window", "words",
]
