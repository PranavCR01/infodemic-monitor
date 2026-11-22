"""Guardrail limits, loaded from ``backend/config/guardrails.yaml`` (§15)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

DEFAULT_GUARDRAILS_PATH = Path(__file__).resolve().parents[3] / "config" / "guardrails.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RateLimit(_Strict):
    requests: PositiveInt
    window_seconds: PositiveInt


class InputLimits(_Strict):
    max_file_bytes: PositiveInt
    min_duration_seconds: float = 0
    max_duration_seconds: PositiveInt
    allowed_containers: list[str]
    max_transcript_chars: PositiveInt
    max_segments: PositiveInt
    max_segment_chars: PositiveInt
    max_claims_per_video: PositiveInt
    uploads_per_user_per_day: PositiveInt
    rate_limit: RateLimit


class ToolLimits(_Strict):
    approved: list[str]
    allowed_hosts: list[str]
    allowed_path_prefix: str = "/"
    timeout_seconds: float = Field(gt=0)
    max_query_chars: PositiveInt
    max_query_terms: PositiveInt
    max_results: PositiveInt
    max_response_bytes: PositiveInt
    max_calls_per_run: PositiveInt

    @field_validator("allowed_hosts")
    @classmethod
    def _exact_hosts(cls, v: list[str]) -> list[str]:
        out = []
        for host in v:
            host = host.strip().lower()
            if not host or "*" in host or "/" in host or ":" in host:
                raise ValueError(f"allowed host {host!r} must be an exact hostname")
            out.append(host)
        return out


class GuardrailConfig(_Strict):
    version: str
    input: InputLimits
    tools: ToolLimits


def parse_guardrails(data: dict) -> GuardrailConfig:
    return GuardrailConfig.model_validate(data)


@lru_cache(maxsize=4)
def load_guardrails(path: str | Path = DEFAULT_GUARDRAILS_PATH) -> GuardrailConfig:
    return parse_guardrails(yaml.safe_load(Path(path).read_text()))
