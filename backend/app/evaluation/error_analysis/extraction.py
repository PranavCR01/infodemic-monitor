"""Sort extraction errors into categories (T43). Deterministic; no model.

Input per video: the gold claims (text, source speech/screen/both, time span), the
predicted claims as the routing run saved them (text, span, source pieces), and the
video's transcript and on-screen text. Claims the **strict** matcher paired are correct;
every other gold and predicted claim gets exactly one category, first rule that fires:

Unmatched **gold** claim
1. ``split_or_merged``: overlap coefficient >= 0.5 with 2+ predictions, or with a
   prediction the strict matcher already paired (one prediction covering two claims).
2. ``reworded_same_meaning``: the meaning matcher pairs it with an unmatched prediction.
3. ``screen_only_missed``: its gold source is ``screen`` (on-screen text only).
4. ``missed``.

Unmatched **predicted** claim
1. ``split_or_merged``: overlap >= 0.5 with a gold claim that is already paired or
   split, or with 2+ gold claims (a fragment of a split, or a merge).
2. ``reworded_same_meaning``: paired by the meaning matcher (the other half of 2 above).
3. ``translated``: under half of its content words occur in the video, and it is in a
   different language from the video (``guess_lang``: script, then stop words). The
   golden set quotes claims in the original language (dataset README, "Other languages:
   quote in the original"), so a translation can be right and still never match.
4. ``hallucinated``: under half of its content words occur in the transcript or the
   on-screen text (not grounded in the video).
5. ``ocr_noise_derived``: every source piece it cites is on-screen text (``o…`` ids),
   or, without saved sources, its words are covered by on-screen text (>= 0.6) and not
   by the transcript (< 0.4).
6. ``non_health_or_not_a_claim``: the rest: grounded, not a reword or fragment of any
   gold claim. These are over-extractions under the golden set's rules (§5: not health,
   not checkable, opinion, instruction) **or** claims the gold set missed; telling those
   apart needs a person, so the worked examples quote them.

Category names follow the T43 task. Thresholds are fixed here, not tuned on outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.evaluation.error_analysis import matching as mt

GOLD_CATEGORIES = ("reworded_same_meaning", "split_or_merged", "screen_only_missed", "missed")
PRED_CATEGORIES = ("reworded_same_meaning", "split_or_merged", "translated", "hallucinated",
                   "ocr_noise_derived", "non_health_or_not_a_claim")
PART_OVERLAP = 0.5
GROUNDED = 0.5


_LANG_STOP = {
    "en": frozenset("the and is are of to you that it this with for not".split()),
    "es": frozenset("el los las que y es por con para del una pero muy".split()),
    "fr": frozenset("le les et est des une pour que dans pas avec sur".split()),
}


def guess_lang(text: str) -> Optional[str]:
    """Coarse language guess: ``non_latin`` when most letters are outside ASCII
    (e.g. Devanagari), else en/es/fr by stop-word hits (2+ needed), else ``latin``."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    if sum(ch.isascii() for ch in letters) / len(letters) < 0.5:
        return "non_latin"
    words = text.lower().split()
    hits = {k: sum(w.strip(".,;:!?\"'()[]") in v for w in words) for k, v in _LANG_STOP.items()}
    best = max(hits, key=lambda k: hits[k])
    return best if hits[best] >= 2 else "latin"


def different_language(a: Optional[str], b: Optional[str]) -> bool:
    """Only a clear difference counts: Latin vs non-Latin script, or two identified
    Latin-script languages that differ. ``latin`` (unidentified) never differs from en/es/fr."""
    if not a or not b:
        return False
    if (a == "non_latin") != (b == "non_latin"):
        return True
    return a in _LANG_STOP and b in _LANG_STOP and a != b


@dataclass(frozen=True)
class Claim:
    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    source: str = ""                       # gold: speech | screen | both
    source_segment_ids: tuple[str, ...] = ()

    @property
    def span(self) -> Optional[tuple[float, float]]:
        if self.start is None:
            return None
        return (self.start, self.end if self.end is not None else self.start)


@dataclass
class VideoErrors:
    video_id: str
    n_gold: int
    n_pred: int
    strict_pairs: list[tuple[int, int, float]]
    meaning_pairs: list[tuple[int, int, float]]
    gold: dict[int, str] = field(default_factory=dict)   # unmatched gold index -> category
    pred: dict[int, str] = field(default_factory=dict)   # unmatched pred index -> category


def categorise(video_id: str, gold: Sequence[Claim], pred: Sequence[Claim], *,
               transcript_text: str = "", screen_text: str = "") -> VideoErrors:
    g_text = [c.text for c in gold]
    p_text = [c.text for c in pred]
    strict = mt.strict_match(g_text, p_text)
    meaning = mt.meaning_match(g_text, p_text, [c.span for c in gold], [c.span for c in pred])
    sg = {gi for gi, _, _ in strict}
    sp = {pi for _, pi, _ in strict}
    out = VideoErrors(video_id, len(gold), len(pred), strict, meaning)

    # Meaning pairs among the strict leftovers only, so a strict pair never blocks a reword.
    lg = [i for i in range(len(gold)) if i not in sg]
    lp = [i for i in range(len(pred)) if i not in sp]
    rew = mt.meaning_match([g_text[i] for i in lg], [p_text[i] for i in lp],
                           [gold[i].span for i in lg], [pred[i].span for i in lp])
    rew_g = {lg[a]: lp[b] for a, b, _ in rew}
    rew_p = {p: g for g, p in rew_g.items()}

    def hits_for_gold(gi: int) -> list[int]:
        return [pi for pi in range(len(pred)) if mt.overlap_coefficient(g_text[gi], p_text[pi]) >= PART_OVERLAP]

    def hits_for_pred(pi: int) -> list[int]:
        return [gi for gi in range(len(gold)) if mt.overlap_coefficient(g_text[gi], p_text[pi]) >= PART_OVERLAP]

    for gi in lg:
        hits = hits_for_gold(gi)
        if len(hits) >= 2 or any(pi in sp for pi in hits):
            out.gold[gi] = "split_or_merged"
        elif gi in rew_g:
            out.gold[gi] = "reworded_same_meaning"
        elif gold[gi].source == "screen":
            out.gold[gi] = "screen_only_missed"
        else:
            out.gold[gi] = "missed"

    for pi in lp:
        hits = hits_for_pred(pi)
        ids = pred[pi].source_segment_ids
        if (len(hits) >= 2 or any(gi in sg or out.gold.get(gi) == "split_or_merged" for gi in hits)
                or out.gold.get(rew_p.get(pi, -1)) == "split_or_merged"):
            out.pred[pi] = "split_or_merged"
        elif pi in rew_p:
            out.pred[pi] = "reworded_same_meaning"
        elif mt.coverage(p_text[pi], transcript_text + " " + screen_text) < GROUNDED:
            lp_, lv_ = guess_lang(p_text[pi]), guess_lang(transcript_text + " " + screen_text)
            out.pred[pi] = "translated" if different_language(lp_, lv_) else "hallucinated"
        elif (ids and all(s.startswith("o") for s in ids)) or (
                not ids and mt.coverage(p_text[pi], screen_text) >= 0.6
                and mt.coverage(p_text[pi], transcript_text) < 0.4):
            out.pred[pi] = "ocr_noise_derived"
        else:
            out.pred[pi] = "non_health_or_not_a_claim"
    return out


def summarise(videos: Sequence[VideoErrors]) -> dict:
    n_gold = sum(v.n_gold for v in videos)
    n_pred = sum(v.n_pred for v in videos)
    ns = sum(len(v.strict_pairs) for v in videos)
    nm = sum(len(v.meaning_pairs) for v in videos)
    g = {c: 0 for c in GOLD_CATEGORIES}
    p = {c: 0 for c in PRED_CATEGORIES}
    for v in videos:
        for c in v.gold.values():
            g[c] += 1
        for c in v.pred.values():
            p[c] += 1
    return {
        "n_gold": n_gold, "n_pred": n_pred,
        "strict": {"matched": ns, **mt.prf(ns, n_gold, n_pred)},
        "meaning": {"matched": nm, **mt.prf(nm, n_gold, n_pred)},
        "unmatched_gold": g, "unmatched_pred": p,
    }
