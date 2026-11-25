"""Bootstrap confidence intervals over items (T43, §14).

Resample items with replacement (``n`` times, fixed seed), recompute the step metric on
each resample, and take the 2.5th and 97.5th percentiles. For two candidates scored on
the same items the resample is *paired* (the same item indices for both), so the CI of
the margin reflects how often the ranking would flip, not just each score's spread.

Extraction resamples videos (an item is a video's whole claim list, and F1 is pooled
over the resample); stance and verify resample claims, with macro-F1 over the labels
present in each resample, as the experiment scores them.
"""
from __future__ import annotations

import random
from typing import Any, Callable, Optional, Sequence

Metric = Callable[[Sequence[int]], Optional[float]]

DEFAULT_RESAMPLES = 1000
DEFAULT_SEED = 43


def percentile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        raise ValueError("no values")
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _indices(n_items: int, n: int, seed: int) -> list[list[int]]:
    rng = random.Random(seed)
    return [[rng.randrange(n_items) for _ in range(n_items)] for _ in range(n)]


def bootstrap_ci(n_items: int, metric: Metric, *, n: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED,
                 alpha: float = 0.05) -> dict[str, Any]:
    """``metric(indices)`` scores the items at ``indices``. Resamples where the metric
    is undefined (None) are dropped and counted."""
    point = metric(list(range(n_items)))
    vals = []
    for idx in _indices(n_items, n, seed):
        v = metric(idx)
        if v is not None:
            vals.append(v)
    vals.sort()
    return {"point": point, "lo": percentile(vals, alpha / 2) if vals else None,
            "hi": percentile(vals, 1 - alpha / 2) if vals else None,
            "n_resamples": n, "n_undefined": n - len(vals)}


def paired_margin_ci(n_items: int, metric_a: Metric, metric_b: Metric, *, n: int = DEFAULT_RESAMPLES,
                     seed: int = DEFAULT_SEED, alpha: float = 0.05) -> dict[str, Any]:
    """CI of ``metric_a - metric_b`` on the same resampled items, and the share of
    resamples where ``a`` is not ahead (a > b fails)."""
    full = list(range(n_items))
    pa, pb = metric_a(full), metric_b(full)
    diffs = []
    for idx in _indices(n_items, n, seed):
        a, b = metric_a(idx), metric_b(idx)
        if a is not None and b is not None:
            diffs.append(a - b)
    diffs.sort()
    return {
        "point": None if pa is None or pb is None else pa - pb,
        "lo": percentile(diffs, alpha / 2) if diffs else None,
        "hi": percentile(diffs, 1 - alpha / 2) if diffs else None,
        "share_not_ahead": (sum(d <= 0 for d in diffs) / len(diffs)) if diffs else None,
        "n_resamples": n,
    }
