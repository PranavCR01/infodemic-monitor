"""Routing harness: pick each step's model from measurements (section 13).

"Every candidate model runs on the step's labelled test set; the one with the
best score on that step's metric wins, as long as its cost and latency are
within budget. When two are close, the cheaper or faster one wins."

``evaluate_candidate`` runs one candidate over a step's test items through the
real ``ModelRouter`` (so retries, fallbacks and cost accounting are exercised
exactly as in production), with whatever clients it is given: mocks in tests,
real provider clients in a paid run. ``select_model`` applies the rule above;
``apply_selection`` writes the winner into a new routing table.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from pydantic import BaseModel, Field

from app.core.routing.config import REQUIRED_STEPS, ModelRef, RoutingConfig
from app.core.routing.router import ModelClient, ModelRouter, RoutingError, single_step_config
from app.evaluation import metrics as m

# The metric each step is selected on (section 14, "Metrics for each step").
STEP_METRICS: dict[str, str] = {
    "extract_claims": "claim_f1",
    "analyze_stance": "stance_macro_f1",
    "plan_search": "retrieval_recall_at_k",
    "verify_claims": "verification_macro_f1",
    "critique": "critic_errors_caught",
    "judge_explanation": "explanation_rating",  # needs human ratings; no automatic scorer
}


class StepItem(BaseModel):
    """One labelled test item for a step: the model's input and the gold answer."""

    item_id: str
    input: Any
    gold: Any


class Candidate(BaseModel):
    provider: str
    model: str
    prompt: str

    @property
    def ref(self) -> ModelRef:
        return ModelRef(provider=self.provider, model=self.model)


class CandidateResult(BaseModel):
    candidate: Candidate
    step: str
    metric: str
    score: Optional[float]
    n_items: int
    n_failed: int
    fallbacks_used: int
    cost_per_item: Optional[float]
    latency_p95_ms: Optional[float]


class Budget(BaseModel):
    max_cost_per_item: Optional[float] = None
    max_latency_p95_ms: Optional[float] = None
    max_failure_rate: float = 0.0


class Selection(BaseModel):
    step: str
    winner: Optional[CandidateResult]
    reason: str
    ranked: list[CandidateResult] = Field(default_factory=list)
    excluded: dict[str, str] = Field(default_factory=dict)


Scorer = Callable[[Sequence[Any], Sequence[Any]], Optional[float]]


# --- Standard scorers ---------------------------------------------------------

def label_macro_f1(labels: Sequence[str]) -> Scorer:
    """Scorer for steps whose output is one label per item (stance, verdict)."""
    def score(gold: Sequence[Any], outputs: Sequence[Any]) -> Optional[float]:
        preds = [str(o).upper() if o is not None else "__none__" for o in outputs]
        return m.macro_f1(list(gold), preds, labels)
    return score


def claim_set_f1(threshold: float = 0.5) -> Scorer:
    """Scorer for extraction: gold and output are lists of claim texts per item."""
    def score(gold: Sequence[Any], outputs: Sequence[Any]) -> Optional[float]:
        matched = n_gold = n_pred = 0
        for g, o in zip(gold, outputs):
            o = list(o or [])
            matched += len(m.match_claims(list(g), o, threshold))
            n_gold += len(g)
            n_pred += len(o)
        if n_gold and not n_pred:
            return 0.0  # extracted nothing: a zero, not "unscored" (which would drop it from selection)
        return m.extraction_prf(matched, n_gold, n_pred)["f1"]
    return score


# --- Harness ------------------------------------------------------------------

def evaluate_candidate(
    step: str,
    candidate: Candidate,
    items: Sequence[StepItem],
    *,
    base_config: RoutingConfig,
    clients: dict[str, ModelClient],
    scorer: Scorer,
    metric: Optional[str] = None,
    clock: Optional[Callable[[], float]] = None,
    run_item: Optional[Callable[[ModelRouter, StepItem], Any]] = None,
    after_item: Optional[Callable[[StepItem, Any], None]] = None,
) -> CandidateResult:
    """Run one candidate over ``items``.

    By default each item's ``input`` is sent to the router as one request. With
    ``run_item`` the caller drives the item instead (e.g. through the real graph node,
    so prompts, repairs and output checks match production) and returns the output to
    score; the item still counts as failed when any of its calls errored or was served
    by the fallback model. ``after_item(item, output)`` runs after each item and may
    raise to stop the run (the routing experiment's spend cap).
    """
    config = single_step_config(base_config, step, candidate.ref, candidate.prompt)
    router = ModelRouter(config, clients, **({"clock": clock} if clock else {}))
    outputs: list[Any] = []
    failed = fallbacks = 0
    for item in items:
        if run_item is not None:
            start = len(router.records)
            output = run_item(router, item)
            records = router.records[start:]
            if any(r.fallback_used for r in records):
                fallbacks += 1
                failed += 1
                output = None
            elif any(r.error for r in records):
                failed += 1
                output = None
            outputs.append(output)
            if after_item is not None:
                after_item(item, output)
            continue
        try:
            result = router.call(step, item.input)
        except RoutingError:
            failed += 1
            outputs.append(None)  # a failed item scores as wrong, not as skipped
            if after_item is not None:
                after_item(item, None)
            continue
        if result.record.fallback_used:
            # The fallback model answered: that output doesn't measure this candidate.
            fallbacks += 1
            failed += 1
            outputs.append(None)
        else:
            outputs.append(result.output)
        if after_item is not None:
            after_item(item, outputs[-1])
    costs = [r.cost_usd for r in router.records]
    cost = sum(costs) / len(items) if items and all(c is not None for c in costs) else None
    return CandidateResult(
        candidate=candidate, step=step, metric=metric or STEP_METRICS.get(step, "score"),
        score=scorer([i.gold for i in items], outputs) if items else None,
        n_items=len(items), n_failed=failed, fallbacks_used=fallbacks,
        cost_per_item=cost,
        latency_p95_ms=m.percentile([r.latency_ms for r in router.records], 95),
    )


def select_model(
    results: Sequence[CandidateResult],
    budget: Budget = Budget(),
    *,
    tie_margin: float = 0.01,
) -> Selection:
    if not results:
        return Selection(step="", winner=None, reason="no candidates evaluated")
    step = results[0].step
    excluded: dict[str, str] = {}
    eligible: list[CandidateResult] = []
    for r in results:
        key = f"{r.candidate.provider}/{r.candidate.model}@{r.candidate.prompt}"
        if r.score is None:
            excluded[key] = "no score"
        elif r.n_items and r.n_failed / r.n_items > budget.max_failure_rate:
            excluded[key] = (
                f"failure rate {r.n_failed}/{r.n_items} over budget "
                f"({r.fallbacks_used} served by the fallback model)"
            )
        elif budget.max_cost_per_item is not None and (r.cost_per_item is None or r.cost_per_item > budget.max_cost_per_item):
            excluded[key] = "cost unknown" if r.cost_per_item is None else f"cost {r.cost_per_item:.6f} over budget"
        elif budget.max_latency_p95_ms is not None and (r.latency_p95_ms is None or r.latency_p95_ms > budget.max_latency_p95_ms):
            excluded[key] = f"p95 latency {r.latency_p95_ms} over budget"
        else:
            eligible.append(r)

    if not eligible:
        return Selection(step=step, winner=None, reason="no candidate within budget", excluded=excluded)

    ranked = sorted(eligible, key=lambda r: -r.score)
    best = ranked[0].score
    close = [r for r in ranked if best - r.score <= tie_margin]
    inf = float("inf")
    winner = min(close, key=lambda r: (
        r.cost_per_item if r.cost_per_item is not None else inf,
        r.latency_p95_ms if r.latency_p95_ms is not None else inf,
        -r.score,
    ))
    if len(close) > 1:
        reason = f"within {tie_margin} of the best {r_metric(ranked)}; cheapest/fastest of {len(close)} wins"
    else:
        reason = f"best {r_metric(ranked)} ({best:.4f}) within budget"
    return Selection(step=step, winner=winner, reason=reason, ranked=ranked, excluded=excluded)


def r_metric(ranked: Sequence[CandidateResult]) -> str:
    return ranked[0].metric if ranked else "score"


def apply_selection(config: RoutingConfig, selections: Sequence[Selection], *, version: str) -> RoutingConfig:
    """A new routing table with each selected step pointed at its winner.

    Status becomes ``evaluated`` only when every required step has a measured winner.
    """
    data = config.model_dump()
    chosen = {s.step for s in selections if s.winner}
    for s in selections:
        if s.winner is None:
            continue
        c = s.winner.candidate
        data["steps"][s.step].update(provider=c.provider, model=c.model, prompt=c.prompt)
    data["version"] = version
    data["status"] = "evaluated" if set(REQUIRED_STEPS) <= chosen else "provisional"
    return RoutingConfig.model_validate(data)
