"""Claim matchers for extraction scoring (T43).

**Strict** (what T38 scored with): ``metrics.match_claims``: token Jaccard over all
lower-cased alphanumeric tokens, stop words included, threshold 0.5, greedy one-to-one.
A faithful paraphrase usually fails it: "turmeric cures cancer" vs "the speaker says
turmeric can cure cancer" share 2 of 8 tokens (0.25).

**Meaning-based** (``meaning_match``), deterministic, no model and no embeddings (none
is a dependency). It is the rule the golden set's blind re-label used to pair the two
labelling passes (``research/claim-level/dataset/scripts/compare_blind.py`` on
``data/golden-label-set``), minus its hand-made matches:

1. Content words: lower-case, accents stripped, words of 3+ letters/digits, minus a
   fixed English/Spanish/French stop-word list, then a light suffix strip (plural -s,
   -es, -ies→y, -ing, -ed, then a final -e) so "cure"/"cures"/"cured"/"curing" agree.
2. Similarity: overlap coefficient |A ∩ B| / min(|A|, |B|), with at least 2 shared
   content words (so a two-word fragment can't match any claim that mentions both).
3. A pair is a candidate when similarity >= 0.6, or >= 0.34 when both claims carry a
   time span and the spans overlap once each is widened by 3 s.
4. Candidates are taken greedily, best first, one-to-one.

It is more lenient than a human reading for meaning in one direction (a short claim
contained in a long compound one matches) and stricter in another (synonyms with no
shared words don't match). Both directions are reported next to the strict numbers;
neither replaces reading the examples.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Sequence

from app.evaluation import metrics as m

STRICT_THRESHOLD = 0.5
MEANING_THRESHOLD = 0.6
MEANING_THRESHOLD_TIMED = 0.34
TIME_TOLERANCE_SECONDS = 3.0
MIN_SHARED = 2

# compare_blind.py's list, unchanged, so the ceiling and the re-score use one rule.
STOP = frozenset("""the and that this with your you are for from but not have has had
will can its it's into than then they them their there what when which who why
how all any just like really also very more most some such about over only one
two three been being was were our out get got going gonna lot much many those
these his her him she he que los las del una por con para como son mas pero sus
esta este esto puede pueden tus muy est les des une qui pour dans pas sur plus
ton tes elle ils avec cette vous tout""".split())

_WORD = re.compile(r"[a-z0-9]{3,}")


def _stem(w: str) -> str:
    if w.isdigit() or len(w) <= 3:
        return w
    for suf, rep in (("ies", "y"), ("ing", ""), ("es", ""), ("ed", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: len(w) - len(suf)] + rep
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def content_tokens(text: str) -> set[str]:
    s = unicodedata.normalize("NFKD", (text or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return {_stem(w) for w in _WORD.findall(s) if w not in STOP}


def overlap_coefficient(a: str, b: str) -> float:
    A, B = content_tokens(a), content_tokens(b)
    if not A or not B:
        return 0.0
    shared = len(A & B)
    if shared < min(MIN_SHARED, len(A), len(B)):
        return 0.0
    return shared / min(len(A), len(B))


def coverage(text: str, source: str) -> float:
    """Share of ``text``'s content words that appear in ``source`` (grounding)."""
    A = content_tokens(text)
    if not A:
        return 0.0
    return len(A & content_tokens(source)) / len(A)


Span = Optional[tuple[float, float]]


def _time_ok(a: Span, b: Span, tol: float = TIME_TOLERANCE_SECONDS) -> bool:
    if a is None or b is None:
        return False
    return a[0] - tol <= b[1] and b[0] - tol <= a[1]


def strict_match(gold: Sequence[str], pred: Sequence[str]) -> list[tuple[int, int, float]]:
    """T38's matcher, unchanged."""
    return m.match_claims(list(gold), list(pred), STRICT_THRESHOLD)


def meaning_match(
    gold: Sequence[str],
    pred: Sequence[str],
    gold_spans: Optional[Sequence[Span]] = None,
    pred_spans: Optional[Sequence[Span]] = None,
) -> list[tuple[int, int, float]]:
    """Greedy one-to-one (gold index, pred index, similarity) pairs under the rule above."""
    gs = list(gold_spans) if gold_spans is not None else [None] * len(gold)
    ps = list(pred_spans) if pred_spans is not None else [None] * len(pred)
    cand = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            s = overlap_coefficient(g, p)
            if s >= MEANING_THRESHOLD or (s >= MEANING_THRESHOLD_TIMED and _time_ok(gs[gi], ps[pi])):
                cand.append((s, gi, pi))
    used_g, used_p, out = set(), set(), []
    for s, gi, pi in sorted(cand, key=lambda x: (-x[0], x[1], x[2])):
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        out.append((gi, pi, s))
    return sorted(out)


def prf(n_matched: int, n_gold: int, n_pred: int) -> dict[str, Optional[float]]:
    return m.extraction_prf(n_matched, n_gold, n_pred)
