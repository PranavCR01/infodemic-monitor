"""Per-step metrics (design doc section 14, "Metrics for each step").

Pure functions over plain values, so each one is unit-testable on its own and
any system's predictions can be scored the same way. Functions return ``None``
where a metric is undefined (e.g. no items) rather than a misleading zero.
"""
from __future__ import annotations

import math
from typing import Hashable, Iterable, Optional, Sequence

from app.core.text_tokens import word_tokens

LABELS = ("MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE")
VERDICTS = ("SUPPORTED", "CONTRADICTED", "MIXED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE")  # UNSUPPORTED: T30
STANCE_LABELS = ("ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR")


# --- Judge rules (section 9), used to sanity-check gold labels ---------------

MISINFO_BASES = ("contradicted", "denies_supported", "unproven")


def _misinfo_basis(claims: list[tuple[str, str]]) -> Optional[str]:
    if any(s == "ENDORSES" and v == "CONTRADICTED" for s, v in claims):
        return "contradicted"
    if any(s == "REFUTES" and v == "SUPPORTED" for s, v in claims):
        return "denies_supported"  # the speaker denies something true (always reviewed)
    if any(s == "ENDORSES" and v == "UNSUPPORTED" for s, v in claims):
        return "unproven"  # T30: an endorsed efficacy claim nothing supports (always reviewed)
    return None


def misinfo_basis(claims: Iterable[tuple[str, str]]) -> Optional[str]:
    """The §9 ``misinfo_basis`` for (stance, verdict) pairs; ``None`` unless MISINFO."""
    return _misinfo_basis(list(claims))


def judge_label(claims: Iterable[tuple[str, str]]) -> str:
    """Video label from (stance, verdict) pairs, exactly as the section 9 rules.

    An ``UNSUPPORTED`` verdict is taken as already eligible (an endorsed efficacy
    claim, as the golden set uses it); the graph checks that before its judge.
    """
    claims = list(claims)
    if _misinfo_basis(claims):
        return "MISINFO"
    if any(s == "REFUTES" and v == "CONTRADICTED" for s, v in claims):
        return "DEBUNKING"
    if any(v in ("SUPPORTED", "CONTRADICTED") for _, v in claims):
        return "NO_MISINFO"
    # REFUTES + MIXED/INSUFFICIENT also lands here (sent to review as a possible debunk).
    return "CANNOT_RECOGNIZE"


# --- Classification ---------------------------------------------------------

def confusion_matrix(
    gold: Sequence[Hashable], pred: Sequence[Hashable], labels: Sequence[Hashable]
) -> dict[Hashable, dict[Hashable, int]]:
    """``matrix[gold][pred]`` counts. Predictions outside ``labels`` are kept as extra columns."""
    _same_length(gold, pred)
    matrix: dict = {g: {p: 0 for p in labels} for g in labels}
    for g, p in zip(gold, pred):
        row = matrix.setdefault(g, {p2: 0 for p2 in labels})
        row[p] = row.get(p, 0) + 1
    return matrix


def per_class_prf(
    gold: Sequence[Hashable], pred: Sequence[Hashable], labels: Sequence[Hashable]
) -> dict[Hashable, dict[str, Optional[float]]]:
    _same_length(gold, pred)
    out = {}
    for label in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        precision = _div(tp, tp + fp)
        recall = _div(tp, tp + fn)
        if precision is None or recall is None:
            f1 = None
        else:
            f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        out[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return out


def macro_f1(gold: Sequence[Hashable], pred: Sequence[Hashable], labels: Sequence[Hashable]) -> Optional[float]:
    """Mean F1 over the labels present in the gold set (absent classes are skipped)."""
    if not gold:
        return None
    prf = per_class_prf(gold, pred, labels)
    scores = [
        (v["f1"] if v["f1"] is not None else 0.0)
        for label, v in prf.items() if v["support"]
    ]
    return sum(scores) / len(scores) if scores else None


def accuracy(gold: Sequence[Hashable], pred: Sequence[Hashable]) -> Optional[float]:
    _same_length(gold, pred)
    return _div(sum(1 for g, p in zip(gold, pred) if g == p), len(gold))


def cohens_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> Optional[float]:
    """Cohen's kappa for two labellers. 1.0 when both agree on a single class throughout."""
    _same_length(a, b)
    n = len(a)
    if n == 0:
        return None
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    labels = set(a) | set(b)
    expected = sum((list(a).count(lab) / n) * (list(b).count(lab) / n) for lab in labels)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


# --- Claim extraction -------------------------------------------------------

def _tokens(text: str) -> set[str]:
    # Unicode-aware since T45 (app.core.text_tokens); identical to the old
    # [a-z0-9]+ on ASCII text. Before, Devanagari text had no tokens at all.
    return set(word_tokens(text))


def text_similarity(a: str, b: str) -> float:
    """Token Jaccard similarity. A deliberately simple default matcher; swap in embeddings later."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0  # two empty/punctuation-only strings; no longer true of non-Latin text (T45)
    return len(ta & tb) / len(ta | tb)


def match_claims(
    gold_texts: Sequence[str], pred_texts: Sequence[str], threshold: float = 0.5
) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matching of predicted to gold claims, best pairs first."""
    pairs = sorted(
        ((text_similarity(g, p), gi, pi) for gi, g in enumerate(gold_texts) for pi, p in enumerate(pred_texts)),
        reverse=True,
    )
    used_g, used_p, out = set(), set(), []
    for sim, gi, pi in pairs:
        if sim < threshold:
            break
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        out.append((gi, pi, sim))
    return sorted(out)


def extraction_prf(n_matched: int, n_gold: int, n_pred: int) -> dict[str, Optional[float]]:
    precision = _div(n_matched, n_pred)
    recall = _div(n_matched, n_gold)
    if precision is None or recall is None or precision + recall == 0:
        f1 = None if precision is None or recall is None else 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


# --- Retrieval --------------------------------------------------------------

def precision_at_k(relevant: Iterable[str], ranked: Sequence[str], k: int) -> Optional[float]:
    """Share of the top k that is relevant. The denominator is always k: an empty slot
    (a list shorter than k) counts as not relevant, so a ranker can't raise its score by
    returning fewer papers."""
    if k <= 0:
        return None
    relevant = set(relevant)
    return sum(1 for doc in list(ranked[:k]) if doc in relevant) / k


def recall_at_k(relevant: Iterable[str], ranked: Sequence[str], k: int) -> Optional[float]:
    relevant = set(relevant)
    if not relevant:
        return None
    return len(relevant & set(ranked[:k])) / len(relevant)


def ndcg_at_k(relevant: Iterable[str], ranked: Sequence[str], k: int) -> Optional[float]:
    """Binary-relevance nDCG@k."""
    relevant = set(relevant)
    if not relevant:
        return None
    dcg = sum(1 / math.log2(i + 2) for i, doc in enumerate(ranked[:k]) if doc in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / ideal


# --- Citations --------------------------------------------------------------

def citation_validity(cited: Iterable[str], retrieved: Iterable[str]) -> tuple[int, int]:
    """(valid, total): cited evidence IDs that were actually retrieved for the claim."""
    cited = list(cited)
    retrieved = set(retrieved)
    return sum(1 for c in cited if c in retrieved), len(cited)


# --- Critic -----------------------------------------------------------------

def critic_metrics(items: Iterable[tuple[bool, bool]]) -> dict[str, Optional[float]]:
    """Items are (verifier_was_wrong, critic_intervened).

    errors_caught: share of real verifier errors the critic challenged.
    unnecessary_retry_rate: share of critic interventions on verdicts that were right.
    """
    items = list(items)
    wrong = [i for w, i in items if w]
    interventions = [w for w, i in items if i]
    return {
        "errors_caught": _div(sum(wrong), len(wrong)),
        "unnecessary_retry_rate": _div(sum(1 for w in interventions if not w), len(interventions)),
        "n": len(items),
    }


# --- Calibration ------------------------------------------------------------

def reliability_bins(
    confidences: Sequence[float], correct: Sequence[bool], n_bins: int = 10
) -> list[dict]:
    """Equal-width bins over [0, 1]: count, mean confidence and accuracy per bin."""
    _same_length(confidences, correct)
    bins = [{"lower": i / n_bins, "upper": (i + 1) / n_bins, "count": 0,
             "mean_confidence": None, "accuracy": None} for i in range(n_bins)]
    sums = [[0.0, 0] for _ in range(n_bins)]
    for c, ok in zip(confidences, correct):
        c = min(max(float(c), 0.0), 1.0)
        idx = min(int(c * n_bins), n_bins - 1)
        bins[idx]["count"] += 1
        sums[idx][0] += c
        sums[idx][1] += int(bool(ok))
    for b, (conf_sum, hits) in zip(bins, sums):
        if b["count"]:
            b["mean_confidence"] = conf_sum / b["count"]
            b["accuracy"] = hits / b["count"]
    return bins


def expected_calibration_error(
    confidences: Sequence[float], correct: Sequence[bool], n_bins: int = 10
) -> Optional[float]:
    n = len(confidences)
    if n == 0:
        return None
    return sum(
        b["count"] / n * abs(b["accuracy"] - b["mean_confidence"])
        for b in reliability_bins(confidences, correct, n_bins) if b["count"]
    )


# --- Review -----------------------------------------------------------------

def review_metrics(sent_to_review: Sequence[bool], overturned: Sequence[Optional[bool]] = ()) -> dict:
    """Share sent to review, and reviewer overturn rate over reviewed cases with an outcome."""
    outcomes = [o for o in overturned if o is not None]
    return {
        "review_share": _div(sum(map(bool, sent_to_review)), len(sent_to_review)),
        "overturn_rate": _div(sum(map(bool, outcomes)), len(outcomes)),
    }


# --- Operations -------------------------------------------------------------

def percentile(values: Sequence[float], q: float) -> Optional[float]:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def latency_summary(latencies_ms: Sequence[float]) -> dict[str, Optional[float]]:
    return {"median_ms": percentile(latencies_ms, 50), "p95_ms": percentile(latencies_ms, 95)}


# --- Transcription / OCR ----------------------------------------------------

def _edit_distance(a: Sequence, b: Sequence) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def word_error_rate(reference: str, hypothesis: str) -> Optional[float]:
    ref = reference.lower().split()
    if not ref:
        return None
    return _edit_distance(ref, hypothesis.lower().split()) / len(ref)


def character_accuracy(reference: str, hypothesis: str) -> Optional[float]:
    """1 - character error rate, floored at 0 (OCR metric)."""
    if not reference:
        return None
    return max(0.0, 1 - _edit_distance(reference, hypothesis) / len(reference))


# --- helpers ----------------------------------------------------------------

def _div(num: float, den: float) -> Optional[float]:
    return None if den == 0 else num / den


def _same_length(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")
