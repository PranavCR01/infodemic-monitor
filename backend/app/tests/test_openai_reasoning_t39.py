"""T39: GPT-5-class (reasoning) models get ``max_completion_tokens`` and raised caps.

Mocked SDK clients only: no API is called and no key is read.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.routing.clients import AnthropicModelClient, OpenAIModelClient
from app.core.routing.config import (
    RoutingConfigError,
    load_routing,
    parse_routing,
)
from app.core.routing.mock import MockModelClient
from app.core.routing.router import (
    ModelCallError,
    ModelRequest,
    ModelRouter,
    ModelServerError,
    request_output_cap,
)
from app.evaluation.routing_experiment import experiment as ex
from app.evaluation.routing_experiment.cost import GuardedClient, SpendGuard
from app.evaluation.routing_experiment.runners import requests_for
from app.tests import test_routing_experiment as rx

REASONER = "reasoner-2026-01-01"   # an arbitrary pinned id: settings come from config, not names
MINI = "small-reasoner-2026-01-01"
PLAIN = "plain-2024-08-06"

NODE_CAPS = {"extract_claims": 2048, "analyze_stance": 512, "verify_claims": 1024}
ALLOWANCE = {"extract_claims": 1500, "analyze_stance": 800, "verify_claims": 2500}


def routing(*, models=None, allowance=None, steps=None, fallback=None, pricing=None):
    base = {
        "extract_claims": {"provider": "anthropic", "model": "claude-haiku-5-5", "prompt": "extract_v2"},
        "analyze_stance": {"provider": "anthropic", "model": "claude-sonnet-5-5", "prompt": "stance_v1"},
        "verify_claims": {"provider": "anthropic", "model": "claude-opus-5-5", "prompt": "verify_v3"},
        "critique": {"provider": "openai", "model": PLAIN, "prompt": "critic_v1"},
        "judge_explanation": {"provider": "anthropic", "model": "claude-sonnet-5-5", "prompt": "explain_v2"},
    }
    base.update(steps or {})
    base["fallback"] = fallback or {"on": ["timeout", "5xx"], "retries": 0, "use": {"provider": "openai", "model": PLAIN}}
    data = {"version": "t39", "routing": base,
            "models": {REASONER: {"reasoning": True}, MINI: {"reasoning": True}} if models is None else models,
            "reasoning_allowance": ALLOWANCE if allowance is None else allowance,
            "pricing": pricing or {}}
    return parse_routing(data)


class FakeOpenAI:
    """Stands in for ``openai.OpenAI``: records every create() call's kwargs."""

    def __init__(self, tool="record_stance", arguments='{"stance": "ENDORSES"}', fail_first=0):
        self.sent: list[dict] = []
        self.fail_first = fail_first
        outer = self

        class Completions:
            def create(self, **kw):
                outer.sent.append(kw)
                if outer.fail_first:
                    outer.fail_first -= 1
                    raise type("InternalServerError", (Exception,), {"status_code": 500})("boom")
                call = SimpleNamespace(function=SimpleNamespace(name=tool, arguments=arguments))
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
                    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=900))

        self.chat = SimpleNamespace(completions=Completions())


class FakeAnthropic:
    def __init__(self):
        self.sent: list[dict] = []
        outer = self

        class Messages:
            def create(self, **kw):
                outer.sent.append(kw)
                return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="record_stance",
                                                                input={"stance": "ENDORSES"})],
                                       usage=SimpleNamespace(input_tokens=5, output_tokens=2))

        self.messages = Messages()


def stance_body(max_tokens=512):
    tool = {"name": "record_stance", "description": "d", "input_schema": {"type": "object", "properties": {}}}
    return {"messages": [{"role": "user", "content": "claim"}], "tools": [tool],
            "tool_choice": {"type": "tool", "name": "record_stance"}, "max_tokens": max_tokens, "temperature": 0}


# ------------------------------------------------------------------ the client


def test_reasoning_model_gets_max_completion_tokens_and_no_temperature():
    sdk = FakeOpenAI()
    router = ModelRouter(routing(steps={"analyze_stance": {"provider": "openai", "model": MINI, "prompt": "stance_v1"}}),
                         {"openai": OpenAIModelClient(sdk), "anthropic": MockModelClient("unused")})
    out = router.call("analyze_stance", stance_body())
    assert out.output == {"stance": "ENDORSES"}
    sent = sdk.sent[0]
    assert "max_tokens" not in sent and "temperature" not in sent
    assert sent["max_completion_tokens"] == 512 + 800  # visible answer + the stance reasoning allowance
    assert sent["model"] == MINI


def test_unlisted_openai_model_request_is_unchanged():
    """A model with no ``models:`` entry is called exactly as before T39."""
    sdk = FakeOpenAI()
    router = ModelRouter(routing(models={}), {"openai": OpenAIModelClient(sdk)})
    router.call("critique", stance_body(1024))
    sent = sdk.sent[0]
    assert sent["max_tokens"] == 1024 and sent["temperature"] == 0.0
    assert "max_completion_tokens" not in sent


def test_non_reasoning_entry_keeps_max_tokens_and_temperature():
    sdk = FakeOpenAI()
    router = ModelRouter(routing(models={PLAIN: {"reasoning": False}}), {"openai": OpenAIModelClient(sdk)})
    router.call("critique", stance_body(1024))
    assert sdk.sent[0]["max_tokens"] == 1024 and sdk.sent[0]["temperature"] == 0.0


def test_token_param_alone_renames_the_cap_without_raising_it():
    sdk = FakeOpenAI()
    cfg = routing(models={PLAIN: {"token_param": "max_completion_tokens"}})
    ModelRouter(cfg, {"openai": OpenAIModelClient(sdk)}).call("critique", stance_body(1024))
    sent = sdk.sent[0]
    assert sent["max_completion_tokens"] == 1024 and "max_tokens" not in sent and sent["temperature"] == 0.0


def test_client_reads_settings_from_the_request_not_the_model_name():
    """The client never inspects the model id: the same id is sent either way."""
    sdk = FakeOpenAI()
    client = OpenAIModelClient(sdk)
    plain = ModelRequest(step="analyze_stance", prompt_version="v", input=stance_body())
    client.complete("gpt-5-looking-name", plain)
    assert sdk.sent[-1]["max_tokens"] == 512 and "max_completion_tokens" not in sdk.sent[-1]
    tuned = plain.model_copy(update={"params": {"token_param": "max_completion_tokens",
                                                "max_output_tokens": 1312, "send_temperature": False}})
    client.complete("anything", tuned)
    assert sdk.sent[-1]["max_completion_tokens"] == 1312 and "temperature" not in sdk.sent[-1]
    with pytest.raises(ModelCallError, match="token_param"):
        client.complete("x", plain.model_copy(update={"params": {"token_param": "max_output"}}))


@pytest.mark.parametrize("step", sorted(NODE_CAPS))
def test_every_experiment_step_gets_its_allowance_on_the_real_node_cap(tmp_path, step):
    """The node bodies (rendered by the real nodes) keep their visible caps; a reasoning
    model's request carries the cap plus that step's T38 allowance."""
    p = rx.plan(tmp_path, steps=(step,))
    item = next(i for i in p.items[step] if requests_for(step, i, p.candidates.candidates[step][0].prompt))
    system, body = requests_for(step, item, p.candidates.candidates[step][0].prompt)[0]
    assert body["max_tokens"] == NODE_CAPS[step]  # nodes unchanged
    prompt = p.candidates.candidates[step][0].prompt
    cfg = routing(steps={step: {"provider": "openai", "model": REASONER, "prompt": prompt}})
    sdk = FakeOpenAI(tool=body["tool_choice"]["name"], arguments="{}")
    ModelRouter(cfg, {"openai": OpenAIModelClient(sdk), "anthropic": MockModelClient("x")}).call(
        step, body, system=system)
    assert sdk.sent[0]["max_completion_tokens"] == NODE_CAPS[step] + ALLOWANCE[step]
    assert {"max_tokens", "temperature"}.isdisjoint(sdk.sent[0])


def test_fallback_gets_its_own_settings():
    """Settings are applied per attempt: a reasoning primary failing over to a plain
    fallback sends max_tokens to the fallback, and the reverse."""
    sdk = FakeOpenAI(fail_first=1)
    cfg = routing(steps={"analyze_stance": {"provider": "openai", "model": MINI, "prompt": "stance_v1"}})
    res = ModelRouter(cfg, {"openai": OpenAIModelClient(sdk)}).call("analyze_stance", stance_body())
    assert res.record.fallback_used and res.record.model == PLAIN
    assert sdk.sent[0]["max_completion_tokens"] == 1312 and "max_tokens" not in sdk.sent[0]
    assert sdk.sent[1]["max_tokens"] == 512 and sdk.sent[1]["temperature"] == 0.0

    sdk2 = FakeOpenAI(fail_first=1)
    cfg2 = routing(steps={"analyze_stance": {"provider": "openai", "model": PLAIN, "prompt": "stance_v1"}},
                   fallback={"on": ["5xx"], "retries": 0, "use": {"provider": "openai", "model": MINI}},
                   allowance={**ALLOWANCE, "critique": 1000, "judge_explanation": 1000})
    ModelRouter(cfg2, {"openai": OpenAIModelClient(sdk2)}).call("analyze_stance", stance_body())
    assert sdk2.sent[0]["max_tokens"] == 512
    assert sdk2.sent[1]["max_completion_tokens"] == 1312 and "temperature" not in sdk2.sent[1]


def test_original_request_is_not_mutated():
    cfg = routing(steps={"analyze_stance": {"provider": "openai", "model": MINI, "prompt": "stance_v1"}})
    router = ModelRouter(cfg, {})
    req = ModelRequest(step="analyze_stance", prompt_version="stance_v1", input=stance_body())
    prepared = router.prepare(MINI, req)
    assert req.params == {} and prepared.params["max_output_tokens"] == 1312
    assert request_output_cap(req) == 512 and request_output_cap(prepared) == 1312


# ------------------------------------------------------------------ Anthropic and the live pipeline


def test_anthropic_request_is_unchanged_for_the_shipped_routing_table():
    shipped = load_routing()
    router = ModelRouter(shipped, {})
    for step, route in shipped.steps.items():
        if route.provider != "anthropic":
            continue
        req = ModelRequest(step=step, prompt_version=route.prompt, input=stance_body(), params=dict(route.params))
        assert router.prepare(route.model, req) is req  # no settings: same object, same request
    sdk = FakeAnthropic()
    ModelRouter(shipped, {"anthropic": AnthropicModelClient(sdk), "openai": MockModelClient("x")}).call(
        "analyze_stance", stance_body())
    assert sdk.sent[0]["max_tokens"] == 512 and "max_completion_tokens" not in sdk.sent[0]


def test_shipped_routing_table_has_the_t38_allowances_and_no_reasoning_route():
    shipped = load_routing()
    assert shipped.reasoning_allowance == ALLOWANCE
    # Nothing the live pipeline routes to today is a reasoning model, so its caps are unchanged.
    for step, route in shipped.steps.items():
        assert not shipped.is_reasoning(route.model)
        assert shipped.output_cap(step, route.model, 512) == 512
    assert not shipped.is_reasoning(shipped.fallback.use.model)


# ------------------------------------------------------------------ config rules


def test_reasoning_model_on_a_step_without_allowance_is_refused():
    with pytest.raises(RoutingConfigError, match="reasoning_allowance"):
        routing(steps={"critique": {"provider": "openai", "model": REASONER, "prompt": "critic_v1"}})
    with pytest.raises(RoutingConfigError, match="reasoning_allowance"):  # global fallback covers every step
        routing(fallback={"on": ["5xx"], "use": {"provider": "openai", "model": REASONER}})


@pytest.mark.parametrize("models, allowance, match", [
    ({REASONER: {"token_param": "max_output"}}, None, "token_param"),
    ({REASONER: {"reasoning": True, "effort": "high"}}, None, "effort"),
    (None, {"extract_claims": -1}, ">= 0"),
    (None, {"not_a_step": 10}, "unknown steps"),
])
def test_bad_model_settings_are_refused(models, allowance, match):
    with pytest.raises(RoutingConfigError, match=match):
        routing(models=models, allowance=allowance)


def test_hash_is_unchanged_without_the_new_sections_and_round_trips_with_them(tmp_path):
    from app.core.routing.config import dump_routing

    without = routing(models={}, allowance={})
    assert "models" not in without.to_yaml_dict() and "reasoning_allowance" not in without.to_yaml_dict()
    with_ = routing()
    assert with_.config_hash() != without.config_hash()
    dump_routing(with_, tmp_path / "r.yaml")
    again = load_routing(tmp_path / "r.yaml")
    assert again.config_hash() == with_.config_hash() and again.is_reasoning(MINI)


# ------------------------------------------------------------------ spend guard and estimator


def test_spend_guard_reserves_the_raised_cap():
    from app.core.routing.config import ModelPrice

    guard = SpendGuard(cap_usd=10_000, pricing={MINI: ModelPrice(input=0, output=1_000_000)})
    cfg = routing(steps={"analyze_stance": {"provider": "openai", "model": MINI, "prompt": "stance_v1"}})
    guarded = GuardedClient(MockModelClient({"stance": "ENDORSES"}), guard)
    req = ModelRouter(cfg, {}).prepare(MINI, ModelRequest(step="analyze_stance", prompt_version="v",
                                                          input=stance_body()))
    assert guard.reserve(MINI, req) == pytest.approx(1312.0)  # $1/token output: the whole raised cap
    guarded.complete(MINI, req)


def reasoning_plan(tmp_path, routing_cfg, reasoning_tokens=800):
    p = rx.plan(tmp_path, steps=("analyze_stance",))
    p.candidates.candidates["analyze_stance"].append(ex.ExperimentCandidate(
        provider="openai", model=MINI, prompt="stance_v1", reasoning_tokens=reasoning_tokens))
    p.routing = routing_cfg
    return p


def test_dry_run_estimate_uses_the_raised_caps(tmp_path):
    from app.core.routing.config import ModelPrice

    priced = {"claude-haiku-5-5": {"input": 0.1, "output": 0.5}, "claude-sonnet-5-5": {"input": 2, "output": 10},
              MINI: {"input": 1.0, "output": 1.0}}
    est = ex.estimate(reasoning_plan(tmp_path, routing(pricing=priced)))
    rows = {r["model"]: r for r in est["steps"]["analyze_stance"]["candidates"]}
    plain, mini = rows["claude-haiku-5-5"], rows[MINI]
    assert plain["output_cap_tokens"] == plain["max_output_tokens"] == 512 * plain["calls"]  # unchanged
    assert mini["output_cap_tokens"] == (512 + 800) * mini["calls"]
    rep = mini["upper_bound_output_tokens"] // mini["output_cap_tokens"]
    price = ModelPrice(input=1.0, output=1.0)
    assert mini["upper_bound_usd"] == pytest.approx(
        (mini["input_tokens"] * rep * 1.25 * price.input + mini["output_cap_tokens"] * rep * price.output) / 1e6,
        abs=1e-3)
    assert est["reasoning_config_problems"] == []


def test_live_run_refuses_a_reasoning_candidate_not_marked_in_routing(tmp_path):
    priced = {"claude-haiku-5-5": {"input": 0.1, "output": 0.5}, "claude-sonnet-5-5": {"input": 2, "output": 10},
              MINI: {"input": 1.0, "output": 1.0}}
    p = reasoning_plan(tmp_path, routing(models={}, pricing=priced))
    est = ex.estimate(p)
    assert any("reasoning: true" in x for x in est["reasoning_config_problems"])
    # Estimated as a reasoning model anyway, so the bound isn't understated.
    mini = next(r for r in est["steps"]["analyze_stance"]["candidates"] if r["model"] == MINI)
    assert mini["output_cap_tokens"] == (512 + 800) * mini["calls"]
    with pytest.raises(ex.LiveRunRefused, match="reasoning"):
        ex.live_run(p, live=True, max_usd=1000, client_factory=rx.never_called)
    assert "Reasoning-model settings missing" in ex.render_markdown(est)


def test_shipped_candidates_are_flagged_until_the_lead_marks_them(tmp_path):
    """The TODO GPT-5 candidates expect reasoning tokens; until routing.yaml marks their
    real ids ``reasoning: true`` the dry run lists them and a live run refuses."""
    p = rx.plan(tmp_path)
    p.candidates = ex.load_candidates(ex.DEFAULT_CANDIDATES_PATH)
    problems = ex.reasoning_config_problems(p)
    assert len(problems) == 3 and all("TODO" in x for x in problems)


def test_live_run_sends_max_completion_tokens_end_to_end(tmp_path):
    """A guarded live run (mocked SDK) of a priced, marked reasoning candidate: every
    OpenAI request carries max_completion_tokens at the raised cap and no temperature."""
    priced = {"claude-haiku-5-5": {"input": 0.1, "output": 0.5}, "claude-sonnet-5-5": {"input": 2, "output": 10},
              MINI: {"input": 1.0, "output": 1.0}}
    p = reasoning_plan(tmp_path, routing(pricing=priced))
    sdk = FakeOpenAI(tool="record_stance",
                     arguments='{"stance": "ENDORSES", "stance_segment_ids": [], "rationale": "r"}')
    factory = lambda: {"anthropic": MockModelClient(rx.responder), "openai": OpenAIModelClient(sdk)}  # noqa: E731
    report = ex.live_run(p, live=True, max_usd=1000, client_factory=factory)
    assert sdk.sent and report["spend"]["calls"] > 0
    for kw in sdk.sent:
        assert kw["model"] == MINI and kw["max_completion_tokens"] == 512 + 800
        assert "max_tokens" not in kw and "temperature" not in kw


def test_server_error_from_reasoning_model_still_maps_to_fallback_kind():
    sdk = FakeOpenAI(fail_first=5)
    client = OpenAIModelClient(sdk)
    req = ModelRouter(routing(), {}).prepare(MINI, ModelRequest(step="analyze_stance", prompt_version="v",
                                                                input=stance_body()))
    with pytest.raises(ModelServerError):
        client.complete(MINI, req)
