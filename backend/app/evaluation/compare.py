"""Compare a candidate run with the baseline (section 14).

"A change ships only if it beats the baseline on the metrics that matter for
its step without making the final label or cost worse."
"""
from __future__ import annotations

from typing import Optional, Sequence

from pydantic import BaseModel

from app.evaluation.records import RunRecord
from app.evaluation.scoring import LOWER_IS_BETTER

DEFAULT_GUARDS = ("macro_f1", "cost_per_video")


class MetricDelta(BaseModel):
    metric: str
    baseline: Optional[float]
    candidate: Optional[float]
    delta: Optional[float]
    improved: Optional[bool]
    worse: Optional[bool]


class Comparison(BaseModel):
    ships: bool
    reasons: list[str]
    primary: list[MetricDelta]
    guards: list[MetricDelta]


def _scalar(run: RunRecord, metric: str) -> Optional[float]:
    value = run.metrics.get(metric)
    return float(value) if isinstance(value, (int, float)) else None


def _delta(metric: str, base: RunRecord, cand: RunRecord, tolerance: float) -> MetricDelta:
    b, c = _scalar(base, metric), _scalar(cand, metric)
    if b is None or c is None:
        return MetricDelta(metric=metric, baseline=b, candidate=c, delta=None, improved=None, worse=None)
    gain = (b - c) if metric in LOWER_IS_BETTER else (c - b)
    return MetricDelta(
        metric=metric, baseline=b, candidate=c, delta=c - b,
        improved=gain > tolerance, worse=gain < -tolerance,
    )


def compare_runs(
    candidate: RunRecord,
    baseline: RunRecord,
    primary: Sequence[str],
    guards: Sequence[str] = DEFAULT_GUARDS,
    *,
    tolerance: float = 0.0,
    allow_missing_guards: Sequence[str] = (),
) -> Comparison:
    """``allow_missing_guards`` names guards that may be unknown (e.g. cost of an
    unpriced model) without blocking; by default an unknown guard blocks, because
    "not worse" can't be shown for a number nobody measured."""
    reasons: list[str] = []
    if candidate.dataset_hash != baseline.dataset_hash:
        reasons.append("runs used different datasets (hash mismatch); not comparable")
    if candidate.split != baseline.split:
        reasons.append(f"runs used different splits ({candidate.split} vs {baseline.split})")
    if not primary:
        reasons.append("no primary metric given for this step")

    prim = [_delta(name, baseline, candidate, tolerance) for name in primary]
    grd = [_delta(name, baseline, candidate, tolerance) for name in guards]

    for d in prim:
        if d.improved is None:
            reasons.append(f"{d.metric}: missing on one of the runs")
        elif not d.improved:
            reasons.append(f"{d.metric}: does not beat the baseline ({d.candidate} vs {d.baseline})")
    for d in grd:
        if d.worse:
            reasons.append(f"{d.metric}: worse than the baseline ({d.candidate} vs {d.baseline})")
        elif d.improved is None and d.metric not in allow_missing_guards:
            reasons.append(f"{d.metric}: missing on one of the runs")
    return Comparison(ships=not reasons, reasons=reasons, primary=prim, guards=grd)
