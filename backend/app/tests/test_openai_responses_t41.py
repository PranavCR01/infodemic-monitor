"""T41: OpenAI reasoning models go through the Responses API.

Mocked only: either a fake ``sdk.responses.create`` or the real ``openai`` SDK over an
``httpx.MockTransport`` (no request leaves the process; the key is a dummy string).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.core.routing.clients import OpenAIModelClient
from app.core.routing.config import load_routing, parse_routing
from app.core.routing.mock import MockModelClient
from app.core.routing.router import (
    ModelCallError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequest,
    ModelResponse,
    ModelRouter,
    ModelServerError,
    ModelTimeoutError,
    ModelTruncatedError,
    RoutingError,
)
from app.evaluation.routing_experiment.cost import SpendGuard

REASONER = "reasoner-2026-01-01"  # arbitrary id: the API choice comes from routing.yaml, not names
PLAIN = "plain-2024-08-06"
STANCE_TOOL = {"name": "record_stance", "description": "Record the stance.",
               "input_schema": {"type": "object", "properties": {"stance": {"type": "string"}},
                                "required": ["stance"]}}
OTHER_TOOL = {"name": "other", "description": "", "input_schema": {"type": "object", "properties": {}}}


def routing(*, models=None, steps=None, fallback=None, pricing=None):
    base = {
        "extract_claims": {"provider": "anthropic", "model": "claude-haiku-5-5", "prompt": "extract_v2"},
        "analyze_stance": {"provider": "openai", "model": REASONER, "prompt": "stance_v1"},
        "verify_claims": {"provider": "anthropic", "model": "claude-opus-5-5", "prompt": "verify_v3"},
        "critique": {"provider": "openai", "model": PLAIN, "prompt": "critic_v1"},
        "judge_explanation": {"provider": "anthropic", "model": "claude-sonnet-5-5", "prompt": "explain_v2"},
    }
    base.update(steps or {})
    base["fallback"] = fallback or {"on": ["timeout", "5xx"], "retries": 0,
                                    "use": {"provider": "openai", "model": PLAIN}}
    return parse_routing({
        "version": "t41", "routing": base,
        "models": models if models is not None else {
            REASONER: {"reasoning": True, "reasoning_effort": "high"}, PLAIN: {"reasoning": False}},
        "reasoning_allowance": {"extract_claims": 1500, "analyze_stance": 800, "verify_claims": 2500},
        "pricing": pricing or {REASONER: {"input": 2.0, "output": 12.0}, PLAIN: {"input": 2.5, "output": 10.0}},
    })


def stance_body(max_tokens=512, tools=(STANCE_TOOL,)):
    return {"messages": [{"role": "user", "content": "claim text"}], "tools": list(tools),
            "tool_choice": {"type": "tool", "name": "record_stance"}, "max_tokens": max_tokens, "temperature": 0}


# --------------------------------------------------------------------------- fakes


def fn_call(name="record_stance", arguments='{"stance": "ENDORSES"}'):
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id="call_1", status="completed")


def message(text):
    return SimpleNamespace(type="message", role="assistant",
                           content=[SimpleNamespace(type="output_text", text=text, annotations=[])])


def response(output, *, status="completed", reason=None, model=REASONER + "-2026-03-01",
             inp=120, out=700, reasoning=600, error=None):
    return SimpleNamespace(
        id="resp_1", model=model, status=status, error=error,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        output=output,
        usage=SimpleNamespace(input_tokens=inp, output_tokens=out, total_tokens=inp + out,
                              output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
                              input_tokens_details=SimpleNamespace(cached_tokens=0)))


class FakeSDK:
    """``openai.OpenAI`` stand-in: records each call by API and replies from a queue."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.responses_sent: list[dict] = []
        self.chat_sent: list[dict] = []
        outer = self

        class Responses:
            def create(self, **kw):
                outer.responses_sent.append(kw)
                return outer._next()

        class Completions:
            def create(self, **kw):
                outer.chat_sent.append(kw)
                return outer._next()

        self.responses = Responses()
        self.chat = SimpleNamespace(completions=Completions())

    def _next(self):
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, BaseException):
            raise r
        return r


def chat_reply():
    call = SimpleNamespace(function=SimpleNamespace(name="record_stance", arguments='{"stance": "REFUTES"}'))
    return SimpleNamespace(model=PLAIN, choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
                           usage=SimpleNamespace(prompt_tokens=50, completion_tokens=20))


def router_with(sdk, **kw):
    return ModelRouter(routing(**kw), {"openai": OpenAIModelClient(sdk), "anthropic": MockModelClient("x")})


# --------------------------------------------------------------------------- request


def test_reasoning_model_request_payload_is_exact():
    sdk = FakeSDK(response([SimpleNamespace(type="reasoning", summary=[]), fn_call()]))
    res = router_with(sdk).call("analyze_stance", stance_body(), system="You are the stance analyser.")
    assert sdk.chat_sent == []
    assert sdk.responses_sent == [{
        "model": REASONER,
        "input": [{"role": "user", "content": "claim text"}],
        "instructions": "You are the stance analyser.",
        "max_output_tokens": 512 + 800,           # node cap + analyze_stance reasoning allowance
        "reasoning": {"effort": "high"},          # the model's configured effort
        "store": False,
        "tools": [{"type": "function", "name": "record_stance", "description": "Record the stance.",
                   "parameters": STANCE_TOOL["input_schema"], "strict": False}],
        "tool_choice": {"type": "function", "name": "record_stance"},
    }]
    assert res.output == {"stance": "ENDORSES"}


def test_step_effort_override_and_default_effort_are_sent_as_reasoning_effort():
    sdk = FakeSDK(response([fn_call()]))
    router_with(sdk, steps={"analyze_stance": {"provider": "openai", "model": REASONER, "prompt": "stance_v1",
                                               "reasoning_effort": "low"}}).call("analyze_stance", stance_body())
    assert sdk.responses_sent[-1]["reasoning"] == {"effort": "low"}
    router_with(sdk, models={REASONER: {"reasoning": True}}).call("analyze_stance", stance_body())
    assert sdk.responses_sent[-1]["reasoning"] == {"effort": "medium"}  # T39's default
    assert all("reasoning_effort" not in kw for kw in sdk.responses_sent)


def test_unforced_tools_send_no_tool_choice():
    sdk = FakeSDK(response([fn_call()]))
    body = stance_body()
    del body["tool_choice"]
    router_with(sdk).call("analyze_stance", body)
    assert "tool_choice" not in sdk.responses_sent[0] and len(sdk.responses_sent[0]["tools"]) == 1


def test_text_request_has_no_tools_and_no_instructions_without_system():
    sdk = FakeSDK(response([SimpleNamespace(type="reasoning", summary=[]), message('{"a": '), message("1}")]))
    out = router_with(sdk).call("analyze_stance", "render this")
    kw = sdk.responses_sent[0]
    assert kw["input"] == [{"role": "user", "content": "render this"}]
    assert not {"tools", "tool_choice", "instructions", "temperature"} & set(kw)
    assert out.output == '{"a": 1}'


def test_block_content_becomes_input_and_output_text_parts():
    sdk = FakeSDK(response([fn_call()]))
    body = stance_body()
    body["messages"] = [{"role": "user", "content": [{"type": "text", "text": "q"}]},
                        {"role": "assistant", "content": [{"type": "text", "text": "a"}]}]
    router_with(sdk).call("analyze_stance", body)
    assert sdk.responses_sent[0]["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "q"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "a"}]}]


def test_non_reasoning_openai_model_keeps_chat_completions_unchanged():
    sdk = FakeSDK(chat_reply())
    res = router_with(sdk).call("critique", stance_body(1024), system="SYS")
    assert sdk.responses_sent == []
    assert sdk.chat_sent == [{
        "model": PLAIN,
        "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "claim text"}],
        "max_tokens": 1024, "temperature": 0.0,
        "tools": [{"type": "function", "function": {"name": "record_stance", "description": "Record the stance.",
                                                     "parameters": STANCE_TOOL["input_schema"]}}],
        "tool_choice": {"type": "function", "function": {"name": "record_stance"}},
    }]
    assert res.output == {"stance": "REFUTES"}


def test_unlisted_model_keeps_chat_completions():
    sdk = FakeSDK(chat_reply())
    router_with(sdk, models={REASONER: {"reasoning": True}}).call("critique", stance_body(1024))
    assert sdk.responses_sent == [] and sdk.chat_sent[0]["max_tokens"] == 1024


def test_the_api_choice_comes_from_the_request_params_not_the_model_name():
    sdk = FakeSDK(chat_reply())
    client = OpenAIModelClient(sdk)
    client.complete("gpt-5-looking-name", ModelRequest(step="s", prompt_version="v", input=stance_body()))
    assert len(sdk.chat_sent) == 1 and sdk.responses_sent == []
    sdk2 = FakeSDK(response([fn_call()]))
    OpenAIModelClient(sdk2).complete("plain-looking-name", ModelRequest(
        step="s", prompt_version="v", input=stance_body(), params={"reasoning": True, "max_output_tokens": 99}))
    assert sdk2.responses_sent[0]["max_output_tokens"] == 99 and sdk2.chat_sent == []


def test_prepare_marks_reasoning_models_only():
    router = ModelRouter(routing(), {})
    req = ModelRequest(step="analyze_stance", prompt_version="v", input=stance_body())
    assert router.prepare(REASONER, req).params["reasoning"] is True
    assert router.prepare(PLAIN, req).params["reasoning"] is False
    assert "reasoning" not in router.prepare("unlisted-2024-01-01", req).params


def test_shipped_routing_marks_the_openai_candidates_and_not_the_critic():
    shipped = load_routing()
    assert shipped.is_reasoning("gpt-5.6-luna") and shipped.is_reasoning("gpt-5.6-terra")
    assert not shipped.is_reasoning("gpt-4o-2024-08-06")


def test_fallback_from_reasoning_to_plain_switches_api():
    boom = type("InternalServerError", (Exception,), {"status_code": 500})("boom")
    sdk = FakeSDK(boom, chat_reply())
    res = router_with(sdk).call("analyze_stance", stance_body())
    assert res.record.fallback_used and res.record.model == PLAIN
    assert len(sdk.responses_sent) == 1 and len(sdk.chat_sent) == 1
    assert sdk.chat_sent[0]["max_tokens"] == 512 and res.output == {"stance": "REFUTES"}


# --------------------------------------------------------------------------- response


def test_usage_reasoning_tokens_and_reported_model_are_recorded():
    sdk = FakeSDK(response([fn_call()], inp=1000, out=900, reasoning=640))
    res = router_with(sdk).call("analyze_stance", stance_body())
    r = res.record
    assert (r.input_tokens, r.output_tokens, r.reasoning_tokens) == (1000, 900, 640)
    assert r.response_model == REASONER + "-2026-03-01" and r.reasoning_effort == "high"
    # output_tokens already includes reasoning (billed as output): not added twice.
    assert r.cost_usd == pytest.approx((1000 * 2.0 + 900 * 12.0) / 1e6)


def test_only_the_forced_tool_call_is_read():
    sdk = FakeSDK(response([fn_call(name="other", arguments='{"x": 1}'), fn_call()]))
    out = router_with(sdk).call("analyze_stance", stance_body(tools=(OTHER_TOOL, STANCE_TOOL)))
    assert out.output == {"stance": "ENDORSES"}


@pytest.mark.parametrize("output", [
    [message("I think it endorses.")],               # text instead of the forced call
    [fn_call(arguments='{"stance": ')],              # malformed arguments
    [fn_call(name="other")],                          # wrong tool
    [],
])
def test_missing_or_bad_tool_call_gives_none_for_the_node_parser(output):
    sdk = FakeSDK(response(output))
    assert router_with(sdk).call("analyze_stance", stance_body()).output is None


def test_missing_usage_details_and_model_are_tolerated():
    reply = SimpleNamespace(status="completed", output=[fn_call()], usage=SimpleNamespace(input_tokens=3, output_tokens=4))
    out = OpenAIModelClient(FakeSDK(reply)).complete(
        "m", ModelRequest(step="s", prompt_version="v", input=stance_body(), params={"reasoning": True}))
    assert out.output == {"stance": "ENDORSES"}
    assert (out.input_tokens, out.output_tokens, out.reasoning_tokens, out.response_model) == (3, 4, 0, None)


# --------------------------------------------------------------------------- incomplete / failed


def truncated():
    return response([SimpleNamespace(type="reasoning", summary=[])], status="incomplete",
                    reason="max_output_tokens", inp=1000, out=1312, reasoning=1312)


def test_incomplete_at_max_output_tokens_raises_truncation_with_usage():
    client = OpenAIModelClient(FakeSDK(truncated()))
    req = ModelRouter(routing(), {}).prepare(REASONER, ModelRequest(step="analyze_stance", prompt_version="v",
                                                                     input=stance_body()))
    with pytest.raises(ModelTruncatedError) as ei:
        client.complete(REASONER, req)
    err = ei.value
    assert err.kind == "truncated" and "max_output_tokens=1312" in str(err)
    assert isinstance(err.response, ModelResponse) and err.response.output is None
    assert (err.response.input_tokens, err.response.output_tokens, err.response.reasoning_tokens) == (1000, 1312, 1312)


def test_truncation_does_not_retry_or_fall_back_and_the_record_keeps_the_billed_tokens():
    sdk = FakeSDK(truncated())
    router = router_with(sdk, fallback={"on": ["timeout", "5xx"], "retries": 1,
                                        "use": {"provider": "openai", "model": PLAIN}})
    with pytest.raises(RoutingError) as ei:
        router.call("analyze_stance", stance_body())
    rec = ei.value.record
    assert len(sdk.responses_sent) == 1 and sdk.chat_sent == [] and not rec.fallback_used
    assert rec.error.startswith("truncated:")
    assert (rec.output_tokens, rec.reasoning_tokens) == (1312, 1312)
    assert rec.response_model == REASONER + "-2026-03-01"
    assert rec.cost_usd == pytest.approx((1000 * 2.0 + 1312 * 12.0) / 1e6)
    assert router.records == [rec]


def test_spend_guard_books_a_truncated_calls_reported_usage():
    guard = SpendGuard(cap_usd=10.0, pricing=dict(routing().pricing))
    client = guard.wrap(OpenAIModelClient(FakeSDK(truncated())))
    req = ModelRouter(routing(), {}).prepare(REASONER, ModelRequest(step="analyze_stance", prompt_version="v",
                                                                     input=stance_body()))
    with pytest.raises(ModelTruncatedError):
        client.complete(REASONER, req)
    assert guard.calls == 1 and guard.spent_usd == pytest.approx((1000 * 2.0 + 1312 * 12.0) / 1e6)


def test_incomplete_for_another_reason_is_not_truncation():
    sdk = FakeSDK(response([], status="incomplete", reason="content_filter"))
    assert router_with(sdk).call("analyze_stance", stance_body()).output is None


def test_failed_status_is_a_plain_call_error():
    sdk = FakeSDK(response([], status="failed", error=SimpleNamespace(code="server_error", message="oops")))
    with pytest.raises(RoutingError) as ei:
        router_with(sdk).call("analyze_stance", stance_body())
    assert "server_error: oops" in ei.value.record.error and not ei.value.record.fallback_used


# --------------------------------------------------------------------------- errors (real SDK exception types)


_REQ = httpx.Request("POST", "https://api.openai.invalid/v1/responses")


def _status_error(cls, code, msg):
    return cls(msg, response=httpx.Response(code, request=_REQ), body=None)


@pytest.mark.parametrize("exc, kind", [
    (openai.APITimeoutError(request=_REQ), ModelTimeoutError),
    (openai.APIConnectionError(request=_REQ), ModelConnectionError),
    (_status_error(openai.RateLimitError, 429, "slow down"), ModelRateLimitError),
    (_status_error(openai.InternalServerError, 500, "boom"), ModelServerError),
])
def test_sdk_errors_map_to_router_kinds(exc, kind):
    client = OpenAIModelClient(FakeSDK(exc))
    with pytest.raises(kind):
        client.complete(REASONER, ModelRequest(step="s", prompt_version="v", input=stance_body(),
                                               params={"reasoning": True}))


def test_bad_request_is_a_plain_call_error_with_its_status():
    exc = _status_error(openai.BadRequestError, 400, "Unsupported parameter: 'temperature'")
    client = OpenAIModelClient(FakeSDK(exc))
    with pytest.raises(ModelCallError) as ei:
        client.complete(REASONER, ModelRequest(step="s", prompt_version="v", input=stance_body(),
                                               params={"reasoning": True}))
    assert type(ei.value) is ModelCallError and ei.value.status == 400 and ei.value.kind == "error"


# --------------------------------------------------------------------------- the real SDK, mocked transport


def _real_sdk(handler):
    # Dummy key: the transport is a local mock and nothing leaves the process.
    return openai.OpenAI(api_key="sk-test-dummy", base_url="https://api.openai.invalid/v1", max_retries=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _response_json(output, *, status="completed", incomplete=None):
    return {
        "id": "resp_1", "object": "response", "created_at": 1764000000, "model": "gpt-5.6-terra-2026-10-01",
        "status": status, "incomplete_details": incomplete, "error": None,
        "output": output, "parallel_tool_calls": True, "tool_choice": {"type": "function", "name": "record_stance"},
        "tools": [], "usage": {"input_tokens": 1200, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                               "output_tokens": 950, "output_tokens_details": {"reasoning_tokens": 800},
                               "total_tokens": 2150},
    }


def test_real_sdk_accepts_the_request_and_its_response_parses():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "body": json.loads(request.content)})
        return httpx.Response(200, json=_response_json([
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "record_stance",
             "arguments": '{"stance": "REFUTES"}', "status": "completed"},
        ]))

    cfg = routing(steps={"analyze_stance": {"provider": "openai", "model": "gpt-5.6-terra", "prompt": "stance_v1"}},
                  models={"gpt-5.6-terra": {"reasoning": True, "reasoning_effort": "medium"}, PLAIN: {"reasoning": False}},
                  pricing={"gpt-5.6-terra": {"input": 2.0, "output": 12.0}})
    res = ModelRouter(cfg, {"openai": OpenAIModelClient(_real_sdk(handler))}).call(
        "analyze_stance", stance_body(), system="SYS")
    assert seen[0]["path"] == "/v1/responses"
    body = seen[0]["body"]
    assert body["model"] == "gpt-5.6-terra" and body["reasoning"] == {"effort": "medium"}
    assert body["max_output_tokens"] == 1312 and body["tool_choice"] == {"type": "function", "name": "record_stance"}
    assert body["tools"][0]["name"] == "record_stance" and body["instructions"] == "SYS" and body["store"] is False
    assert not {"max_tokens", "max_completion_tokens", "temperature", "reasoning_effort", "messages"} & set(body)
    r = res.record
    assert res.output == {"stance": "REFUTES"}
    assert (r.input_tokens, r.output_tokens, r.reasoning_tokens) == (1200, 950, 800)
    assert r.response_model == "gpt-5.6-terra-2026-10-01"


def test_real_sdk_incomplete_response_is_truncation():
    def handler(request):
        return httpx.Response(200, json=_response_json([{"type": "reasoning", "id": "rs_1", "summary": []}],
                                                       status="incomplete",
                                                       incomplete={"reason": "max_output_tokens"}))

    client = OpenAIModelClient(_real_sdk(handler))
    with pytest.raises(ModelTruncatedError) as ei:
        client.complete("gpt-5.6-luna", ModelRequest(step="s", prompt_version="v", input=stance_body(),
                                                     params={"reasoning": True, "max_output_tokens": 1312}))
    assert ei.value.response.reasoning_tokens == 800


def test_real_sdk_400_maps_to_a_plain_call_error():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "bad", "type": "invalid_request_error",
                                                    "param": None, "code": None}})

    client = OpenAIModelClient(_real_sdk(handler))
    with pytest.raises(ModelCallError) as ei:
        client.complete("gpt-5.6-luna", ModelRequest(step="s", prompt_version="v", input=stance_body(),
                                                     params={"reasoning": True}))
    assert type(ei.value) is ModelCallError and ei.value.status == 400
