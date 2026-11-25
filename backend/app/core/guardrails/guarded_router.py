"""``GuardedRouter``: the only way graph nodes call a model (§15).

It wraps ``ModelRouter`` (which owns model choice, retries and fallback) and adds:

- **Fenced input only.** ``call`` takes a ``GuardedPrompt``. A raw string or dict is
  refused, as is a system prompt that doesn't end with the untrusted-data rules.
- **Data out, never actions.** The answer is parsed into the step's strict schema
  (``outputs.parse_output``). There is no tool-use loop: a model can't ask for a
  tool, a URL or a command, because nothing here would run one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.guardrails.outputs import _Out, parse_output
from app.core.guardrails.untrusted import GuardedPrompt, is_guarded_system_prompt
from app.core.routing.router import CallRecord, ModelRouter


class UnguardedPromptError(TypeError):
    """A node tried to send a model input that was not built by the guardrails."""


@dataclass
class GuardedResult:
    output: _Out
    record: CallRecord
    prompt: GuardedPrompt


class GuardedRouter:
    def __init__(self, router: ModelRouter):
        self.router = router

    @property
    def records(self) -> list[CallRecord]:
        return self.router.records

    def call(self, prompt: GuardedPrompt, schema: Optional[type[_Out]] = None) -> GuardedResult:
        """Call the model for ``prompt.step``. Raises ``UnguardedPromptError`` for an
        unfenced prompt, ``OutputViolation`` for an answer outside the schema and
        ``RoutingError`` when no model could answer."""
        if not isinstance(prompt, GuardedPrompt):
            raise UnguardedPromptError(
                f"model input must be a GuardedPrompt, got {type(prompt).__name__}; "
                "build it with app.core.guardrails.untrusted"
            )
        if not is_guarded_system_prompt(prompt.system):
            raise UnguardedPromptError(f"{prompt.step}: system prompt lacks the untrusted-data rules")
        result = self.router.call(prompt.step, prompt.render(), system=prompt.system)
        output = parse_output(prompt.step, result.output, schema)
        return GuardedResult(output=output, record=result.record, prompt=prompt)
