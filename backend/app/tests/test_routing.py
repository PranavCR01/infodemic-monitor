"""Model routing (design doc section 13). All model calls are mocked."""
import ast
from pathlib import Path

import pytest

from app.core.routing import (
    DEFAULT_ROUTING_PATH,
    ModelRouter,
    ModelServerError,
    ModelTimeoutError,
    RoutingConfigError,
    RoutingError,
    load_routing,
    parse_routing,
)
from app.core.routing.config import REQUIRED_STEPS, dump_routing
from app.core.routing.mock import MockModelClient
from app.core.routing.router import ModelCallError


def _cfg(**overrides):
    data = {
        "version": "test_v1",
        "routing": {
            "extract_claims": {"provider": "anthropic", "model": "small-1", "prompt": "extract_v1"},
            "analyze_stance": {"provider": "anthropic", "model": "medium-1", "prompt": "stance_v1"},
            "verify_claims": {"provider": "anthropic", "model": "strong-1", "prompt": "verify_v1"},
            "critique": {"provider": "openai", "model": "other-1", "prompt": "critic_v1"},
            "judge_explanation": {"provider": "anthropic", "model": "medium-1", "prompt": "explain_v1"},
            "fallback": {"on": ["timeout", "5xx"], "retries": 1,
                         "use": {"provider": "openai", "model": "backup-1"}},
        },
        "pricing": {"strong-1": {"input": 4.0, "output": 20.0}},
    }
    for step, value in overrides.items():
        if value is None:
            data["routing"].pop(step, None)
        else:
            data["routing"][step] = value
    return parse_routing(data)


# --- config ------------------------------------------------------------------

def test_repo_routing_file_is_valid_and_covers_required_steps():
    cfg = load_routing()
    assert set(REQUIRED_STEPS) <= set(cfg.steps)
    assert cfg.status == "provisional"  # no measured routing decision yet
    for route in cfg.steps.values():
        assert route.prompt and route.model and "latest" not in route.model


def test_critic_independent_of_verifier_in_repo_config():
    cfg = load_routing()
    v, c = cfg.route("verify_claims"), cfg.route("critique")
    assert (v.key, v.prompt) != (c.key, c.prompt)


@pytest.mark.parametrize("model", ["claude-latest", "gpt-4o-latest", "<pinned id>", "model-*", ""])
def test_unpinned_model_ids_are_rejected(model):
    with pytest.raises(RoutingConfigError):
        _cfg(verify_claims={"provider": "anthropic", "model": model, "prompt": "verify_v1"})


def test_missing_required_step_is_rejected():
    with pytest.raises(RoutingConfigError, match="missing required steps"):
        _cfg(verify_claims=None)


def test_unknown_step_is_rejected():
    with pytest.raises(RoutingConfigError, match="unknown routing steps"):
        _cfg(summarize={"provider": "x", "model": "y-1", "prompt": "p1"})


def test_prompt_version_is_required():
    with pytest.raises(RoutingConfigError):
        _cfg(analyze_stance={"provider": "anthropic", "model": "m-1", "prompt": ""})


def test_critic_identical_to_verifier_is_rejected():
    same = {"provider": "anthropic", "model": "strong-1", "prompt": "verify_v1"}
    with pytest.raises(RoutingConfigError, match="independence"):
        _cfg(critique=same)
    # Same model with a different prompt is allowed ("a different model or prompt").
    _cfg(critique={**same, "prompt": "critic_v1"})


def test_plan_search_is_optional_rules_first():
    cfg = _cfg()
    assert "plan_search" not in cfg.steps
    with pytest.raises(RoutingConfigError):
        cfg.route("plan_search")


def test_config_hash_is_stable_and_changes_with_content(tmp_path):
    a, b = _cfg(), _cfg()
    assert a.config_hash() == b.config_hash()
    c = _cfg(analyze_stance={"provider": "anthropic", "model": "medium-2", "prompt": "stance_v1"})
    assert c.config_hash() != a.config_hash()
    path = tmp_path / "routing.yaml"
    dump_routing(a, path)
    assert load_routing(path).config_hash() == a.config_hash()


def test_missing_or_bad_file(tmp_path):
    with pytest.raises(RoutingConfigError, match="not found"):
        load_routing(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("routing: [unclosed")
    with pytest.raises(RoutingConfigError):
        load_routing(bad)


def test_node_code_does_not_hardcode_routed_model_ids():
    """Model ids live in config/routing.yaml only, never in new code (build rule)."""
    models = {r.model for r in load_routing().steps.values()}
    app_dir = Path(__file__).resolve().parents[1]
    roots = [app_dir / "core" / "routing", app_dir / "evaluation"]
    for root in roots:
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert node.value not in models, f"{path} hardcodes model id {node.value!r}"


def test_default_routing_path_is_inside_backend():
    # The Docker image only copies backend/, so the routing file must live there.
    assert DEFAULT_ROUTING_PATH.parts[-3:] == ("backend", "config", "routing.yaml")


# --- router ------------------------------------------------------------------

def test_router_calls_configured_model_and_records_versions():
    client = MockModelClient({"verify_claims": {"verdict": "CONTRADICTED"}},
                             input_tokens=1000, output_tokens=500)
    router = ModelRouter(_cfg(), {"anthropic": client, "openai": MockModelClient()})
    result = router.call("verify_claims", {"claim": "x"})
    assert result.output == {"verdict": "CONTRADICTED"}
    model, request = client.calls[0]
    assert model == "strong-1" and request.prompt_version == "verify_v1"
    rec = result.record
    assert (rec.provider, rec.model, rec.prompt_version) == ("anthropic", "strong-1", "verify_v1")
    assert rec.fallback_used is False and rec.attempts == 1
    assert rec.cost_usd == pytest.approx((1000 * 4.0 + 500 * 20.0) / 1e6)
    assert router.records == [rec]


def test_unpriced_model_reports_unknown_cost_not_zero():
    router = ModelRouter(_cfg(), {"anthropic": MockModelClient("ok")})
    assert router.call("analyze_stance", "x").record.cost_usd is None


def test_retry_then_success_on_primary():
    primary = MockModelClient("ok", failures=[ModelTimeoutError()])
    router = ModelRouter(_cfg(), {"anthropic": primary, "openai": MockModelClient("fallback")})
    result = router.call("extract_claims", "x")
    assert result.output == "ok"
    assert result.record.attempts == 2 and not result.record.fallback_used


@pytest.mark.parametrize("error", [ModelTimeoutError(), ModelServerError(status=503)])
def test_fallback_after_retries_is_recorded(error):
    primary = MockModelClient("primary", failures=[error, error])
    backup = MockModelClient("fallback")
    router = ModelRouter(_cfg(), {"anthropic": primary, "openai": backup})
    result = router.call("verify_claims", "x")
    assert result.output == "fallback"
    rec = result.record
    assert rec.fallback_used and rec.fallback_reason == error.kind
    assert (rec.provider, rec.model) == ("openai", "backup-1")
    assert rec.prompt_version == "verify_v1"  # same prompt version, recorded
    assert rec.attempts == 3
    assert backup.calls[0][0] == "backup-1"


def test_non_fallback_errors_are_not_retried():
    class BadRequest(ModelCallError):
        kind = "bad_request"

    primary = MockModelClient("x", failures=[BadRequest("400")])
    backup = MockModelClient("fallback")
    router = ModelRouter(_cfg(), {"anthropic": primary, "openai": backup})
    with pytest.raises(RoutingError) as info:
        router.call("verify_claims", "x")
    assert info.value.record.attempts == 1 and not backup.calls
    assert "bad_request" in info.value.record.error


def test_fallback_failure_raises_with_record():
    t = ModelTimeoutError()
    router = ModelRouter(
        _cfg(), {"anthropic": MockModelClient(failures=[t, t]), "openai": MockModelClient(failures=[t])}
    )
    with pytest.raises(RoutingError) as info:
        router.call("verify_claims", "x")
    assert info.value.record.fallback_used and info.value.record.error.startswith("timeout")


def test_step_level_fallback_overrides_global():
    cfg = _cfg(verify_claims={"provider": "anthropic", "model": "strong-1", "prompt": "verify_v1",
                              "fallback": {"provider": "anthropic", "model": "strong-0"}})
    t = ModelTimeoutError()
    primary = MockModelClient("ok", failures=[t, t])
    router = ModelRouter(cfg, {"anthropic": primary, "openai": MockModelClient()})
    assert router.call("verify_claims", "x").record.model == "strong-0"


def test_no_fallback_configured_raises_after_retries():
    cfg = parse_routing({
        "version": "v", "routing": {
            **{k: v for k, v in _cfg().to_yaml_dict()["routing"].items() if k != "fallback"},
            "fallback": {"on": ["timeout"], "retries": 0},
        }})
    router = ModelRouter(cfg, {"anthropic": MockModelClient(failures=[ModelTimeoutError()])})
    with pytest.raises(RoutingError):
        router.call("extract_claims", "x")


def test_missing_client_is_a_routing_error():
    router = ModelRouter(_cfg(), {"anthropic": MockModelClient("ok")})
    with pytest.raises(RoutingError, match="no client registered"):
        router.call("critique", "x")  # critique routes to openai, which is not registered


def test_latency_uses_injected_clock():
    ticks = iter([10.0, 10.25])
    router = ModelRouter(_cfg(), {"anthropic": MockModelClient("ok")}, clock=lambda: next(ticks))
    assert router.call("extract_claims", "x").record.latency_ms == 250
