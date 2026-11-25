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

OpenAI **reasoning** models (``reasoning: true`` under ``models:`` in routing.yaml; the
router passes it as ``request.params["reasoning"]``) are called through the Responses API
(T41): Chat Completions refuses function tools together with ``reasoning_effort``. Every
other OpenAI model keeps Chat Completions, unchanged.

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
    ModelTruncatedError,
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


def _reported_model(resp: Any) -> Optional[str]:
    """The model id the provider reports having served (``response.model``), if any."""
    model = getattr(resp, "model", None)
    return model if isinstance(model, str) and model else None


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
            response_model=_reported_model(resp),
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


def _responses_tools(tools: Optional[list[dict]]) -> Optional[list[dict]]:
    """Anthropic-style tools as Responses-API function tools (flat: ``name``,
    ``description`` and ``parameters`` sit beside ``type``, not under ``function``).
    ``strict`` is off: the nodes' schemas aren't written for strict mode (which needs
    every property required and ``additionalProperties: false``), and their parsers
    validate the arguments anyway, as on the other paths."""
    if not tools:
        return None
    return [
        {"type": "function", "name": t["name"], "description": t.get("description", ""),
         "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
         "strict": False}
        for t in tools
    ]


def _responses_input(messages: list[dict]) -> list[dict]:
    """Chat-style messages as Responses-API input items. String content passes through
    (an "easy" input message); a list of text blocks becomes ``input_text`` parts, or
    ``output_text`` for an assistant turn. The nodes send one user message with string
    content today."""
    items: list[dict] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            part = "output_text" if m.get("role") == "assistant" else "input_text"
            content = [{"type": part, "text": b.get("text", "")} if isinstance(b, dict) else
                       {"type": part, "text": str(b)} for b in content]
        items.append({"role": m.get("role", "user"), "content": content})
    return items


def _responses_usage(resp: Any) -> ModelResponse:
    """Usage of a Responses-API reply, as T39 records it for Chat Completions:
    ``output_tokens`` already includes the hidden reasoning tokens (billed as output), and
    ``output_tokens_details.reasoning_tokens`` is recorded alongside."""
    usage = getattr(resp, "usage", None)
    details = getattr(usage, "output_tokens_details", None)
    return ModelResponse(
        output=None,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        reasoning_tokens=int(getattr(details, "reasoning_tokens", 0) or 0),
        response_model=_reported_model(resp),
    )


class OpenAIModelClient:
    """``ModelClient`` over the OpenAI API (the routed critic, the fallback model and the
    routing experiment's OpenAI candidates).

    Per-model request settings come from the router (``routing.yaml`` ``models:``, T39),
    in ``request.params``:

    - ``reasoning: true`` (T41): the call goes to the **Responses API**
      (``responses.create``) with ``reasoning={"effort": reasoning_effort}``,
      ``max_output_tokens`` (the node's cap plus the step's reasoning allowance; it covers
      the hidden reasoning tokens too), the system prompt as ``instructions``, flat
      function tools and a forced ``{"type": "function", "name": ...}`` tool choice. No
      ``temperature`` unless ``send_temperature`` says so, and ``store: false`` (nothing
      is kept on OpenAI's side for later turns; the pipeline never chains responses).
      A reply cut off at the cap (status ``incomplete``, reason ``max_output_tokens``)
      raises ``ModelTruncatedError`` carrying the billed usage.
    - Otherwise **Chat Completions**, exactly as before: ``token_param`` names the output
      cap (``max_tokens`` or ``max_completion_tokens``), ``max_output_tokens`` is the cap,
      ``send_temperature: false`` drops ``temperature`` and ``reasoning_effort`` is sent
      as given. With no settings the request is exactly the pre-T39 one.

    The client never looks at the model id to decide any of this.
    """

    def __init__(self, sdk_client: Any = None, *, api_key: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if sdk_client is None:
            import openai

            sdk_client = openai.OpenAI(api_key=api_key, max_retries=0, timeout=timeout)
        self._sdk = sdk_client

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        if request.params.get("reasoning"):
            return self._complete_responses(model, request)
        return self._complete_chat(model, request)

    # -- Responses API (reasoning models, T41) --

    def _complete_responses(self, model: str, request: ModelRequest) -> ModelResponse:
        messages, tools, tool_choice, max_tokens, temperature = _split_input(request)
        kwargs: dict[str, Any] = {
            "model": model,
            "input": _responses_input(messages),
            "max_output_tokens": max_tokens,
            "store": False,
        }
        if request.system:
            kwargs["instructions"] = request.system
        if request.params.get("reasoning_effort"):
            kwargs["reasoning"] = {"effort": request.params["reasoning_effort"]}
        if request.params.get("send_temperature", False):
            kwargs["temperature"] = temperature
        forced = _forced_tool_name(tool_choice)
        if tools:
            kwargs["tools"] = _responses_tools(tools)
            if forced:
                kwargs["tool_choice"] = {"type": "function", "name": forced}
        try:
            resp = self._sdk.responses.create(**kwargs)
        except ModelCallError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to the router's kinds
            raise map_provider_error(exc) from exc

        result = _responses_usage(resp)
        status = getattr(resp, "status", None)
        if status == "incomplete":
            reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
            if reason == "max_output_tokens":
                raise ModelTruncatedError(
                    f"step {request.step!r}: {model} stopped at max_output_tokens={max_tokens} "
                    f"({result.reasoning_tokens} reasoning of {result.output_tokens} output tokens)",
                    response=result)
        if status == "failed":
            err = getattr(resp, "error", None)
            raise ModelCallError(
                f"step {request.step!r}: response failed: {getattr(err, 'code', None)}: "
                f"{getattr(err, 'message', None)}"[:500])

        output: Any = None
        texts: list[str] = []
        for item in getattr(resp, "output", None) or []:
            kind = getattr(item, "type", None)
            if kind == "function_call" and output is None and (forced is None or getattr(item, "name", None) == forced):
                try:
                    output = json.loads(getattr(item, "arguments", "") or "{}")
                except json.JSONDecodeError:
                    output = None  # the node's parser treats this as malformed output
            elif kind == "message":
                for part in getattr(item, "content", None) or []:
                    if getattr(part, "type", None) == "output_text":
                        texts.append(getattr(part, "text", "") or "")
        if output is None and not tools:
            output = "".join(texts)
        return result.model_copy(update={"output": output})

    # -- Chat Completions (every other OpenAI model; unchanged from T39) --

    def _complete_chat(self, model: str, request: ModelRequest) -> ModelResponse:
        messages, tools, tool_choice, max_tokens, temperature = _split_input(request)
        if request.system:
            messages = [{"role": "system", "content": request.system}, *messages]
        token_param = request.params.get("token_param") or "max_tokens"
        if token_param not in ("max_tokens", "max_completion_tokens"):
            raise ModelCallError(f"step {request.step!r}: unknown token_param {token_param!r}")
        kwargs: dict[str, Any] = {"model": model, "messages": messages, token_param: max_tokens}
        if request.params.get("send_temperature", True):
            kwargs["temperature"] = temperature
        if request.params.get("reasoning_effort"):
            kwargs["reasoning_effort"] = request.params["reasoning_effort"]
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
        details = getattr(usage, "completion_tokens_details", None)
        return ModelResponse(
            output=output,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            # completion_tokens already includes the hidden reasoning tokens (billed as output).
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            reasoning_tokens=int(getattr(details, "reasoning_tokens", 0) or 0),
            response_model=_reported_model(resp),
        )


def default_clients(*, anthropic_api_key: str = "", openai_api_key: str = "",
                    timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Real clients for the providers named in ``routing.yaml``. Constructed lazily by
    the graph provider, only when the graph flag is on."""
    return {
        "anthropic": AnthropicModelClient(api_key=anthropic_api_key, timeout=timeout),
        "openai": OpenAIModelClient(api_key=openai_api_key, timeout=timeout),
    }
