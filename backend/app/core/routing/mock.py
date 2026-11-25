"""Mock model client for tests and offline harness runs. Makes no network calls."""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Union

from app.core.routing.router import ModelCallError, ModelRequest, ModelResponse

Responder = Callable[[str, ModelRequest], Any]


class MockModelClient:
    """Returns canned outputs and can be told to fail.

    ``responder`` is either a fixed output, a dict keyed by step, or a callable
    ``(model, request) -> output``. ``failures`` is a queue of exceptions raised
    on successive calls before the responder is used (``None`` entries succeed).
    """

    def __init__(
        self,
        responder: Union[Responder, dict, Any] = None,
        *,
        failures: Optional[Iterable[Optional[ModelCallError]]] = None,
        input_tokens: int = 100,
        output_tokens: int = 50,
    ):
        self._responder = responder
        self._failures = list(failures or [])
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[tuple[str, ModelRequest]] = []

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        self.calls.append((model, request))
        if self._failures:
            failure = self._failures.pop(0)
            if failure is not None:
                raise failure
        r = self._responder
        if callable(r):
            output = r(model, request)
        elif isinstance(r, dict):
            output = r.get(request.step)
        else:
            output = r
        return ModelResponse(
            output=output, input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )
