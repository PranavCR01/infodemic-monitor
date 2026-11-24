"""Provider clients for ``ModelRouter`` (design §13; written for T11, issue #38).

The router owns model choice, retries and fallback; a client only turns one
``ModelRequest`` into one provider call. The model id always comes from the router
(``routing.yaml``), never from this file.

Two request shapes reach a client:

- **Forced tool call** (stance, verifier, critic, judge explanation, claim extraction):
  ``request.input`` is ``{messages, tools, tool_choice, max_tokens, temperature}`` with
  Anthropic-style tools (``name``, ``description``, ``input_schema``). The client returns
  the tool's input as a dict in ``ModelResponse.output``. A reply without the forced
  tool call gives ``output=None``; the node's parser rejects it (its safe default).
- **Rendered text** (T10's ``GuardedRouter``): ``request.input`` is a string. It is
  sent as one user message and the reply text is returned; ``parse_output`` reads it as
  JSON.

Provider errors are mapped onto the router's error kinds (``timeout``, ``5xx``,
``rate_limit``, ``connection``) so the fallback policy in ``routing.yaml`` applies.
Any other provider error (400, auth, ...) is re-raised as a plain ``ModelCallError``,
which the router does not retry or fall back on.

The SDK client is injected, so tests pass a fake and no API is called.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.core.routing.router import (
    DEFAULT_MAX_TOKENS,
    ModelCallError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelServerError,
    ModelTimeoutError,
    request_output_cap,
)
DEFAULT_TIMEOUT_SECONDS = 60.0


def map_provider_error(exc: BaseException) -> ModelCallError:
    """Map an SDK exception (anthropic or openai, which share class names) to a router
    error kind. Matching by class name keeps this file free of SDK imports."""
    names = {c.__name__ for c in type(exc).__mro__}
    status = getattr(exc, "status_code", None)
    msg = f"{type(exc).__name__}: {exc}"[:500]
    if "APITimeoutError" in names or isinstance(exc, TimeoutError):
        return ModelTimeoutError(msg)
    if "RateLimitError" in names or status == 429:
        return ModelRateLimitError(msg, status=429)
    if "InternalServerError" in names or (isinstance(status, int) and status >= 500):
        return ModelServerError(msg, status=status)
    if "APIConnectionError" in names or isinstance(exc, ConnectionError):
        return ModelConnectionError(msg)
    return ModelCallError(msg, status=status)


def _split_input(request: ModelRequest) -> tuple[list[dict], Optional[list[dict]], Optional[dict], int, float]:
    body = request.input
    if isinstance(body, str):
        return [{"role": "user", "content": body}], None, None, request_output_cap(request), 0.0
    if not isinstance(body, dict) or "messages" not in body:
        raise ModelCallError(f"step {request.step!r}: request input must be a string or a messages dict")
    return (
        list(body["messages"]),
        body.get("tools"),
        body.get("tool_choice"),
        request_output_cap(request),
        float(body.get("temperature", request.params.get("temperature", 0.0))),
    )


def _forced_tool_name(tool_choice: Optional[dict]) -> Optional[str]:
    if not tool_choice:
        return None
    if tool_choice.get("type") == "tool":
        return tool_choice.get("name")
    if tool_choice.get("type") == "function":
        return (tool_choice.get("function") or {}).get("name")
    return None


class AnthropicModelClient:
    """``ModelClient`` over the Anthropic Messages API."""

    def __init__(self, sdk_client: Any = None, *, api_key: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if sdk_client is None:
            import anthropic

            # The router owns retries; the SDK must not retry on its own.
            sdk_client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=timeout)
        self._sdk = sdk_client
        self._no_forced_tool: set[str] = set()  # models that refused a forced tool_choice

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        messages, tools, tool_choice, max_tokens, temperature = _split_input(request)
        # No sampling parameters: current Claude models reject ``temperature`` (400) and
        # the current SDK no longer accepts the argument at all (T18 smoke run). The
        # nodes' ``temperature: 0`` still applies to the OpenAI client.
        del temperature
        kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, messages=messages)
        if request.system:
            kwargs["system"] = request.system
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        forced = _forced_tool_name(tool_choice)
        if forced and model in self._no_forced_tool:
            kwargs = _unforced(kwargs, forced)
        try:
            try:
                resp = self._sdk.messages.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                if not (forced and _rejects_forced_tool(exc)) or kwargs.get("tool_choice", {}).get("type") == "auto":
                    raise
                # Some current Claude models refuse a forced tool
                # call with a 400. Ask for the tool in the prompt instead (tool_choice
                # auto); a reply without the call still parses as None, the node's safe
                # default. Remembered per model so the 400 is paid once per process.
                self._no_forced_tool.add(model)
                resp = self._sdk.messages.create(**_unforced(kwargs, forced))
        except ModelCallError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to the router's kinds
            raise map_provider_error(exc) from exc

        output: Any = None
        texts: list[str] = []
        for block in getattr(resp, "content", None) or []:
            kind = getattr(block, "type", None)
            if kind == "tool_use" and (forced is None or getattr(block, "name", None) == forced):
                output = dict(getattr(block, "input", None) or {})
                break
            if kind == "text":
                texts.append(getattr(block, "text", ""))
        if output is None and not tools:
            output = "".join(texts)
        usage = getattr(resp, "usage", None)
        return ModelResponse(
            output=output,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


# Thinking is always on for the models that refuse a forced tool call, and thinking
# tokens count against max_tokens: without headroom a step's small cap (stance: 512) can
# run out before the tool call is written. Only tokens actually generated are billed.
UNFORCED_MIN_MAX_TOKENS = 8192


def _rejects_forced_tool(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    return status == 400 and "tool_choice" in str(exc) and "not supported" in str(exc)


def _unforced(kwargs: dict[str, Any], tool_name: str) -> dict[str, Any]:
    out = dict(kwargs)
    out["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}
    out["max_tokens"] = max(int(out.get("max_tokens") or 0), UNFORCED_MIN_MAX_TOKENS)
    instruction = f"Answer only by calling the `{tool_name}` tool exactly once. Do not reply with text."
    system = out.get("system")
    if isinstance(system, list):
        out["system"] = [*system, {"type": "text", "text": instruction}]
    else:
        out["system"] = f"{system}\n\n{instruction}" if system else instruction
    return out


def _openai_tools(tools: Optional[list[dict]]) -> Optional[list[dict]]:
    if not tools:
        return None
    return [
        {"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
        }}
        for t in tools
    ]


class OpenAIModelClient:
    """``ModelClient`` over the OpenAI Chat Completions API (the routed critic and the
    fallback model).

    Per-model request settings come from the router (``routing.yaml`` ``models:``, T39),
    in ``request.params``: ``token_param`` names the output cap (OpenAI reasoning
    models reject ``max_tokens`` and need ``max_completion_tokens``, which also covers
    their hidden reasoning tokens), ``max_output_tokens`` is the cap including the step's
    reasoning allowance, and ``send_temperature: false`` drops ``temperature``. With no
    settings the request is exactly the pre-T39 one (``max_tokens`` + ``temperature``).
    """

    def __init__(self, sdk_client: Any = None, *, api_key: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if sdk_client is None:
            import openai

            sdk_client = openai.OpenAI(api_key=api_key, max_retries=0, timeout=timeout)
        self._sdk = sdk_client

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        messages, tools, tool_choice, max_tokens, temperature = _split_input(request)
        if request.system:
            messages = [{"role": "system", "content": request.system}, *messages]
        token_param = request.params.get("token_param") or "max_tokens"
        if token_param not in ("max_tokens", "max_completion_tokens"):
            raise ModelCallError(f"step {request.step!r}: unknown token_param {token_param!r}")
        kwargs: dict[str, Any] = {"model": model, "messages": messages, token_param: max_tokens}
        if request.params.get("send_temperature", True):
            kwargs["temperature"] = temperature
        forced = _forced_tool_name(tool_choice)
        if tools:
            kwargs["tools"] = _openai_tools(tools)
            if forced:
                kwargs["tool_choice"] = {"type": "function", "function": {"name": forced}}
        try:
            resp = self._sdk.chat.completions.create(**kwargs)
        except ModelCallError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise map_provider_error(exc) from exc

        choices = getattr(resp, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        output: Any = None
        for call in getattr(message, "tool_calls", None) or []:
            fn = getattr(call, "function", None)
            if fn is not None and (forced is None or getattr(fn, "name", None) == forced):
                try:
                    output = json.loads(getattr(fn, "arguments", "") or "{}")
                except json.JSONDecodeError:
                    output = None  # the node's parser treats this as malformed output
                break
        if output is None and not tools:
            output = getattr(message, "content", "") or ""
        usage = getattr(resp, "usage", None)
        return ModelResponse(
            output=output,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )


def default_clients(*, anthropic_api_key: str = "", openai_api_key: str = "",
                    timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Real clients for the providers named in ``routing.yaml``. Constructed lazily by
    the graph provider, only when the graph flag is on."""
    return {
        "anthropic": AnthropicModelClient(api_key=anthropic_api_key, timeout=timeout),
        "openai": OpenAIModelClient(api_key=openai_api_key, timeout=timeout),
    }
