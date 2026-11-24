"""Model router: resolve a step to its configured model, call it, retry, fall back.

Clients are injected per provider, so tests use ``MockModelClient`` and no
real API is called. Every call produces a ``CallRecord`` with the model and
prompt version that produced the output and whether the fallback was used
(section 13: "The fallback is recorded on the result").
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.core.routing.config import ModelRef, RoutingConfig


# --- Errors a client raises -------------------------------------------------

class ModelCallError(Exception):
    """Base class for provider errors. ``kind`` matches FallbackPolicy.on."""

    kind: str = "error"

    def __init__(self, message: str = "", *, status: Optional[int] = None):
        super().__init__(message or self.kind)
        self.status = status


class ModelTimeoutError(ModelCallError):
    kind = "timeout"


class ModelServerError(ModelCallError):
    kind = "5xx"


class ModelRateLimitError(ModelCallError):
    kind = "rate_limit"


class ModelConnectionError(ModelCallError):
    kind = "connection"


class RoutingError(Exception):
    """The step could not be served by its primary model or its fallback."""

    def __init__(self, message: str, record: "CallRecord"):
        super().__init__(message)
        self.record = record


# --- Request / response -----------------------------------------------------

class ModelRequest(BaseModel):
    step: str
    prompt_version: str
    input: Any
    system: Optional[str] = None
    params: dict = Field(default_factory=dict)


DEFAULT_MAX_TOKENS = 1024


def visible_output_cap(request: "ModelRequest") -> int:
    """The output cap the node asked for (its visible answer): ``max_tokens`` in a
    messages dict, else in the route's params, else the default."""
    body = request.input
    if isinstance(body, dict) and body.get("max_tokens"):
        return int(body["max_tokens"])
    return int(request.params.get("max_tokens") or DEFAULT_MAX_TOKENS)


def request_output_cap(request: "ModelRequest") -> int:
    """The cap the client will actually send: the router's per-model cap when it set
    one (``params.max_output_tokens``), else the node's visible cap."""
    cap = request.params.get("max_output_tokens")
    return int(cap) if cap else visible_output_cap(request)


class ModelResponse(BaseModel):
    output: Any
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class ModelClient(Protocol):
    def complete(self, model: str, request: ModelRequest) -> ModelResponse: ...


class CallRecord(BaseModel):
    step: str
    provider: str
    model: str
    prompt_version: str
    attempts: int = 0
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Optional[float] = None  # None when the model has no configured price
    error: Optional[str] = None


class RoutedResult(BaseModel):
    output: Any
    record: CallRecord


# --- Router -----------------------------------------------------------------

class ModelRouter:
    def __init__(
        self,
        config: RoutingConfig,
        clients: dict[str, ModelClient],
        *,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self.config = config
        self.clients = {k.lower(): v for k, v in clients.items()}
        self._clock = clock
        self.records: list[CallRecord] = []

    def route(self, step: str):
        return self.config.route(step)

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> RoutedResult:
        route = self.config.route(step)
        policy = self.config.fallback
        request = ModelRequest(
            step=step, prompt_version=route.prompt, input=input, system=system,
            params=dict(route.params),
        )
        record = CallRecord(
            step=step, provider=route.provider, model=route.model, prompt_version=route.prompt,
        )
        start = self._clock()
        last_error: Optional[ModelCallError] = None

        try:
            for _ in range(1 + policy.retries):
                record.attempts += 1
                try:
                    resp = self._client(route.provider).complete(
                        route.model, self.prepare(route.model, request))
                    return self._finish(record, resp, start)
                except ModelCallError as exc:
                    if exc.kind not in policy.on:
                        raise
                    last_error = exc

            fallback = self.config.fallback_for(step)
            if fallback is None:
                raise last_error  # type: ignore[misc]
            record.fallback_used = True
            record.fallback_reason = last_error.kind if last_error else None
            record.provider, record.model = fallback.provider, fallback.model
            record.attempts += 1
            resp = self._client(fallback.provider).complete(
                fallback.model, self.prepare(fallback.model, request))
            return self._finish(record, resp, start)
        except ModelCallError as exc:
            record.error = f"{exc.kind}: {exc}"
            record.latency_ms = self._elapsed_ms(start)
            self.records.append(record)
            raise RoutingError(f"step {step!r} failed: {record.error}", record) from exc

    # -- helpers --

    def prepare(self, model: str, request: ModelRequest) -> ModelRequest:
        """Apply ``model``'s request settings from the routing table (T39). Done per
        attempt, because the fallback can be a different kind of model. A model with no
        entry under ``models:`` gets the request unchanged."""
        settings = self.config.model_settings(model)
        if settings is None:
            return request
        params = dict(request.params)
        params["token_param"] = settings.output_param
        params["max_output_tokens"] = self.config.output_cap(request.step, model, visible_output_cap(request))
        params["send_temperature"] = settings.sends_temperature
        return request.model_copy(update={"params": params})

    def _client(self, provider: str) -> ModelClient:
        try:
            return self.clients[provider]
        except KeyError:
            raise ModelConnectionError(f"no client registered for provider {provider!r}") from None

    def _finish(self, record: CallRecord, resp: ModelResponse, start: float) -> RoutedResult:
        record.latency_ms = self._elapsed_ms(start)
        record.input_tokens = resp.input_tokens
        record.output_tokens = resp.output_tokens
        record.cost_usd = self.cost(record.model, resp.input_tokens, resp.output_tokens)
        self.records.append(record)
        return RoutedResult(output=resp.output, record=record)

    def _elapsed_ms(self, start: float) -> int:
        return int(round((self._clock() - start) * 1000))

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
        price = self.config.price(model)
        if price is None:
            return None
        return (input_tokens * price.input + output_tokens * price.output) / 1_000_000


def single_step_config(base: RoutingConfig, step: str, candidate: ModelRef, prompt: str) -> RoutingConfig:
    """A copy of ``base`` with one step pointed at a candidate (used by the routing harness)."""
    steps = dict(base.steps)
    steps[step] = steps[step].model_copy(
        update={"provider": candidate.provider, "model": candidate.model, "prompt": prompt}
    )
    data = base.model_dump()
    data["steps"] = {k: v.model_dump() for k, v in steps.items()}
    return RoutingConfig.model_validate(data)  # re-run the routing rules
