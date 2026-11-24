"""Routing configuration (design doc section 13).

The routing table says which provider, pinned model and prompt version each LLM
step uses, plus the fallback taken on timeouts and server errors. It is loaded
from ``backend/config/routing.yaml``; node code asks the router for a step and
never names a model itself.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# LLM steps of the target pipeline. plan_search is optional: rules first.
LLM_STEPS: tuple[str, ...] = (
    "extract_claims",
    "analyze_stance",
    "plan_search",
    "verify_claims",
    "critique",
    "judge_explanation",
)
REQUIRED_STEPS: tuple[str, ...] = (
    "extract_claims",
    "analyze_stance",
    "verify_claims",
    "critique",
    "judge_explanation",
)

FallbackTrigger = Literal["timeout", "5xx", "rate_limit", "connection"]

DEFAULT_ROUTING_PATH = Path(__file__).resolve().parents[3] / "config" / "routing.yaml"

_FLOATING_MARKERS = ("latest", "*", "<", ">")


class RoutingConfigError(ValueError):
    """The routing file is missing, malformed or breaks a routing rule."""


class ModelRef(BaseModel):
    provider: str
    model: str

    @field_validator("provider")
    @classmethod
    def _provider_nonempty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("provider must not be empty")
        return v

    @field_validator("model")
    @classmethod
    def _model_pinned(cls, v: str) -> str:
        """Pinned ids only: results must be reproducible (section 13)."""
        v = v.strip()
        if not v:
            raise ValueError("model id must not be empty")
        lowered = v.lower()
        for marker in _FLOATING_MARKERS:
            if marker in lowered:
                raise ValueError(
                    f"model id {v!r} is not pinned (contains {marker!r}); use an exact version"
                )
        return v

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"


class StepRoute(ModelRef):
    prompt: str
    fallback: Optional[ModelRef] = None  # overrides the global fallback for this step
    params: dict = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def _prompt_versioned(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt version must not be empty")
        return v


class FallbackPolicy(BaseModel):
    on: list[FallbackTrigger] = Field(default_factory=lambda: ["timeout", "5xx"])
    retries: int = Field(default=1, ge=0, le=5)
    use: Optional[ModelRef] = None


class ModelPrice(BaseModel):
    input: float = Field(ge=0)   # USD per 1M input tokens
    output: float = Field(ge=0)  # USD per 1M output tokens


TokenParam = Literal["max_tokens", "max_completion_tokens"]


class ModelSettings(BaseModel):
    """Per-model request settings (``models:`` in routing.yaml; task T39).

    A **reasoning** model (OpenAI GPT-5 class) spends hidden reasoning tokens that count
    against its output cap and are billed as output. For such a model the router:

    - names the cap ``max_completion_tokens`` (these models reject ``max_tokens``),
    - raises the step's cap by the step's ``reasoning_allowance`` so reasoning cannot
      use up the room for the visible answer (the node's own cap is the visible part),
    - sends no ``temperature`` (reasoning models accept only the default).

    ``token_param`` overrides the parameter name alone, for a non-reasoning model that
    also wants ``max_completion_tokens``. Models not listed keep today's request exactly.
    Settings are chosen here, by model id, never by name-sniffing in node or client code.
    """

    model_config = {"extra": "forbid"}

    reasoning: bool = False
    token_param: Optional[TokenParam] = None

    @property
    def output_param(self) -> str:
        return self.token_param or ("max_completion_tokens" if self.reasoning else "max_tokens")

    @property
    def sends_temperature(self) -> bool:
        return not self.reasoning


class RoutingConfig(BaseModel):
    version: str
    status: Literal["provisional", "evaluated"] = "provisional"
    steps: dict[str, StepRoute]
    fallback: FallbackPolicy = Field(default_factory=FallbackPolicy)
    pricing: dict[str, ModelPrice] = Field(default_factory=dict)
    models: dict[str, ModelSettings] = Field(default_factory=dict)
    # Extra output tokens per call, by step, added to a reasoning model's cap.
    reasoning_allowance: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_steps(self) -> "RoutingConfig":
        unknown = sorted(set(self.steps) - set(LLM_STEPS))
        if unknown:
            raise ValueError(f"unknown routing steps: {unknown}; known: {list(LLM_STEPS)}")
        missing = [s for s in REQUIRED_STEPS if s not in self.steps]
        if missing:
            raise ValueError(f"routing is missing required steps: {missing}")
        verify, critic = self.steps["verify_claims"], self.steps["critique"]
        if verify.key == critic.key and verify.prompt == critic.prompt:
            raise ValueError(
                "critique must use a different model or prompt from verify_claims "
                "(independence, section 8)"
            )
        bad = sorted(set(self.reasoning_allowance) - set(LLM_STEPS))
        if bad:
            raise ValueError(f"reasoning_allowance names unknown steps: {bad}")
        negative = sorted(k for k, v in self.reasoning_allowance.items() if v < 0)
        if negative:
            raise ValueError(f"reasoning_allowance must be >= 0: {negative}")
        for name, route in self.steps.items():
            for ref in (route, route.fallback or self.fallback.use):
                if ref is not None and self.is_reasoning(ref.model) and name not in self.reasoning_allowance:
                    raise ValueError(
                        f"step {name!r} can call reasoning model {ref.model!r} but has no "
                        f"reasoning_allowance; add one so reasoning cannot crowd out the answer"
                    )
        return self

    # -- per-model request settings (T39) --

    def model_settings(self, model: str) -> Optional[ModelSettings]:
        return self.models.get(model)

    def is_reasoning(self, model: str) -> bool:
        s = self.models.get(model)
        return bool(s and s.reasoning)

    def output_cap(self, step: str, model: str, visible: int) -> int:
        """The output cap sent for ``model`` on ``step``: the node's visible cap, plus the
        step's reasoning allowance when the model is a reasoning model."""
        if self.is_reasoning(model):
            return int(visible) + int(self.reasoning_allowance.get(step, 0))
        return int(visible)

    def route(self, step: str) -> StepRoute:
        try:
            return self.steps[step]
        except KeyError:
            raise RoutingConfigError(f"no route configured for step {step!r}") from None

    def fallback_for(self, step: str) -> Optional[ModelRef]:
        return self.route(step).fallback or self.fallback.use

    def price(self, model: str) -> Optional[ModelPrice]:
        return self.pricing.get(model)

    def to_yaml_dict(self) -> dict:
        routing: dict = {
            name: route.model_dump(exclude_none=True, exclude_defaults=True) | {
                "provider": route.provider, "model": route.model, "prompt": route.prompt,
            }
            for name, route in self.steps.items()
        }
        routing["fallback"] = self.fallback.model_dump(exclude_none=True)
        out: dict = {"version": self.version, "status": self.status, "routing": routing}
        if self.pricing:
            out["pricing"] = {k: v.model_dump() for k, v in self.pricing.items()}
        # Only when set, so the hash of a table without them is unchanged.
        if self.models:
            out["models"] = {k: v.model_dump(exclude_none=True) for k, v in self.models.items()}
        if self.reasoning_allowance:
            out["reasoning_allowance"] = dict(self.reasoning_allowance)
        return out

    def config_hash(self) -> str:
        """Stable hash of the routing table, recorded on every evaluation run."""
        canonical = json.dumps(self.to_yaml_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def versions(self) -> dict[str, dict[str, str]]:
        """Model and prompt version per step, for run records."""
        return {
            name: {"provider": r.provider, "model": r.model, "prompt": r.prompt}
            for name, r in self.steps.items()
        }


def parse_routing(data: dict) -> RoutingConfig:
    """Build a RoutingConfig from the YAML layout in section 13.

    ``routing:`` holds one entry per step plus an optional ``fallback`` entry.
    """
    if not isinstance(data, dict) or "routing" not in data:
        raise RoutingConfigError("routing file must have a top-level 'routing' mapping")
    routing = dict(data["routing"] or {})
    fallback = routing.pop("fallback", None)
    payload = {
        "version": data.get("version", "unversioned"),
        "status": data.get("status", "provisional"),
        "steps": routing,
        "pricing": data.get("pricing") or {},
        "models": data.get("models") or {},
        "reasoning_allowance": data.get("reasoning_allowance") or {},
    }
    if fallback is not None:
        payload["fallback"] = fallback
    try:
        return RoutingConfig.model_validate(payload)
    except ValueError as exc:
        raise RoutingConfigError(str(exc)) from exc


def load_routing(path: str | Path | None = None) -> RoutingConfig:
    path = Path(path) if path else DEFAULT_ROUTING_PATH
    if not path.exists():
        raise RoutingConfigError(f"routing file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise RoutingConfigError(f"routing file is not valid YAML: {exc}") from exc
    return parse_routing(data)


def dump_routing(config: RoutingConfig, path: str | Path) -> None:
    Path(path).write_text(yaml.safe_dump(config.to_yaml_dict(), sort_keys=False))
