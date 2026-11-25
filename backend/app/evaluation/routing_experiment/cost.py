"""Cost estimates and the spend guard for the routing experiment.

Prices come from ``config/routing.yaml``'s ``pricing`` table (USD per million tokens).
A candidate whose model has no price there is reported as unpriced in a dry run and is
refused by a live run: an unknown cost cannot be held under a cap.

Token counts in a dry run are estimates from the rendered requests (characters / 3.5,
plus a fixed allowance for the tool-use scaffolding the provider adds), not a provider
tokenizer; they err high on English text. The expected output is a per-step allowance;
the upper bound assumes every call writes its full output cap and every repair fires. For
a reasoning model the cap is the node's visible ``max_tokens`` plus the step's
``reasoning_allowance`` from routing.yaml (T39), the same cap the router sends.

``SpendGuard`` wraps every provider client in a live run. Before each call it reserves
the call's worst case (estimated input + ``max_tokens`` output, priced) and refuses the
call if that could cross the cap; after the call it books the actual cost from the
usage the API returned. The input estimate is scaled by the largest ratio of reported
to estimated input tokens seen so far (at least 1.25), so if a provider counts more
tokens than the estimate, later reservations grow to match. The running total can pass
the cap only if a provider reports more input than that margin on a single call, and
then by at most that one call; the run stops right after it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.routing.config import ModelPrice, RoutingConfig
from app.core.routing.router import ModelCallError, ModelRequest, ModelResponse, request_output_cap

CHARS_PER_TOKEN = 3.5
TOOL_OVERHEAD_TOKENS = 350  # tool-use system scaffolding added by the provider
# Expected output tokens per call (a forced tool call's arguments), by step.
EXPECTED_OUTPUT_TOKENS: dict[str, int] = {
    "extract_claims": 600,
    "analyze_stance": 150,
    "verify_claims": 400,
}


def estimate_input_tokens(system: Optional[str], body: Any) -> int:
    if isinstance(body, dict):
        text = json.dumps(body.get("messages", []), ensure_ascii=False) + json.dumps(body.get("tools") or [])
    else:
        text = str(body or "")
    return int(math.ceil((len(system or "") + len(text)) / CHARS_PER_TOKEN)) + TOOL_OVERHEAD_TOKENS


def max_output_tokens(body: Any, default: int = 1024) -> int:
    if isinstance(body, dict) and body.get("max_tokens"):
        return int(body["max_tokens"])
    return default


def price_usd(price: Optional[ModelPrice], input_tokens: float, output_tokens: float) -> Optional[float]:
    if price is None:
        return None
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000


# ------------------------------------------------------------------ spend guard


class SpendCapError(ModelCallError):
    """A call was refused because it could cross the USD cap (or has no price).
    Its kind is not a fallback trigger, so the router neither retries nor falls back."""

    kind = "spend_cap"


class SpendCapReached(Exception):
    """Raised between items to stop the experiment once the guard has refused a call."""


@dataclass
class SpendGuard:
    cap_usd: float
    pricing: dict[str, ModelPrice]
    spent_usd: float = 0.0
    calls: int = 0
    refused: int = 0
    by_model: dict[str, float] = field(default_factory=dict)
    exhausted: bool = False
    input_ratio: float = 1.25  # reported / estimated input tokens, the largest seen (>= 1.25)

    def __post_init__(self) -> None:
        if not (self.cap_usd > 0):
            raise ValueError("the spend cap must be a positive number of USD")

    def reserve(self, model: str, request: ModelRequest) -> float:
        price = self.pricing.get(model)
        if price is None:
            self.refused += 1
            self.exhausted = True
            raise SpendCapError(f"model {model!r} has no price in the routing table; refusing a paid call")
        # The cap the client will send: for a reasoning model that is the router's raised
        # cap (visible answer + the step's reasoning allowance), not the node's (T39).
        worst = price_usd(price, estimate_input_tokens(request.system, request.input) * self.input_ratio,
                          request_output_cap(request))
        assert worst is not None
        if self.spent_usd + worst > self.cap_usd:
            self.refused += 1
            self.exhausted = True
            raise SpendCapError(
                f"spend cap: ${self.spent_usd:.4f} spent, this call could cost up to ${worst:.4f}, "
                f"cap ${self.cap_usd:.2f}")
        return worst

    def book(self, model: str, response: Optional[ModelResponse], reserved: float,
             estimated_input: Optional[int] = None) -> float:
        cost = None
        if response is not None and (response.input_tokens or response.output_tokens):
            cost = price_usd(self.pricing.get(model), response.input_tokens, response.output_tokens)
            if estimated_input and response.input_tokens:
                self.input_ratio = max(self.input_ratio, response.input_tokens / estimated_input)
        if cost is None:
            cost = reserved  # no usage reported: book the worst case
        self.spent_usd += cost
        self.calls += 1
        self.by_model[model] = self.by_model.get(model, 0.0) + cost
        if self.spent_usd >= self.cap_usd:
            self.exhausted = True
        return cost

    def wrap(self, client: Any) -> "GuardedClient":
        return GuardedClient(client, self)

    def check(self) -> None:
        if self.exhausted:
            raise SpendCapReached(f"stopped at the spend cap (${self.spent_usd:.4f} of ${self.cap_usd:.2f})")

    def summary(self) -> dict:
        return {"cap_usd": self.cap_usd, "spent_usd": round(self.spent_usd, 6), "calls": self.calls,
                "refused_calls": self.refused, "stopped_at_cap": self.exhausted,
                "by_model": {k: round(v, 6) for k, v in self.by_model.items()}}


class GuardedClient:
    def __init__(self, inner: Any, guard: SpendGuard):
        self.inner = inner
        self.guard = guard

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        reserved = self.guard.reserve(model, request)
        try:
            response = self.inner.complete(model, request)
        except Exception as exc:
            # A failed call may still have been billed (e.g. a timeout after generation):
            # book the reservation to stay on the safe side, unless the error carries the
            # usage the provider reported (T41: a reply truncated at the output cap).
            billed = getattr(exc, "response", None)
            if isinstance(billed, ModelResponse):
                self.guard.book(model, billed, reserved, estimate_input_tokens(request.system, request.input))
            else:
                self.guard.book(model, None, reserved)
            raise
        self.guard.book(model, response, reserved, estimate_input_tokens(request.system, request.input))
        return response


def experiment_pricing(routing: RoutingConfig) -> dict[str, ModelPrice]:
    return dict(routing.pricing)
