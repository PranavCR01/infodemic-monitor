"""Guardrails for the LangGraph pipeline (design doc §15).

- ``untrusted``: fence transcripts, captions, claims and abstracts; per-step prompt
  builders; the untrusted-data rules every system prompt ends with.
- ``injection``: deterministic injection tripwire, neutralising and review reasons.
- ``outputs``: strict output schemas and citation checks.
- ``guarded_router``: the only way nodes call a model.
- ``tools``: approved retrieval functions, HTTP allowlist, timeouts, size limits.
- ``limits``: upload, duration, quota, rate and per-video work limits.

Limits live in ``backend/config/guardrails.yaml``.
"""
from app.core.guardrails.config import GuardrailConfig, load_guardrails, parse_guardrails
from app.core.guardrails.guarded_router import GuardedResult, GuardedRouter, UnguardedPromptError
from app.core.guardrails.injection import (
    GUARDRAIL_ERROR_PREFIX,
    InjectionFinding,
    detect,
    guardrail_review_reasons,
    neutralise,
    scan_state,
)
from app.core.guardrails.outputs import OUTPUT_SCHEMAS, OutputViolation, check_verification, parse_output
from app.core.guardrails.untrusted import (
    PROMPT_BUILDERS,
    UNTRUSTED_DATA_NOTICE,
    GuardedPrompt,
    UntrustedBlock,
    fence,
    guarded_system_prompt,
)

__all__ = [
    "GUARDRAIL_ERROR_PREFIX", "OUTPUT_SCHEMAS", "PROMPT_BUILDERS", "UNTRUSTED_DATA_NOTICE",
    "GuardedPrompt", "GuardedResult", "GuardedRouter", "GuardrailConfig", "InjectionFinding",
    "OutputViolation", "UnguardedPromptError", "UntrustedBlock", "check_verification", "detect",
    "fence", "guarded_system_prompt", "guardrail_review_reasons", "load_guardrails", "neutralise",
    "parse_guardrails", "parse_output", "scan_state",
]
