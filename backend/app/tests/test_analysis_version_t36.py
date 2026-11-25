"""T36: traceable analysis version on results (design §12, §14).

``pipeline_version`` on a graph result reads ``graph_v1+<short git sha>+p<8-char
routing hash>``; the routing snapshot the hash covers is stored on the result row and
returned by ``GET /jobs/{id}/result``. Old ``graph_v1`` rows still read. No model,
PubMed or network call is made: models go through a scripted client.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.routing.config import load_routing, parse_routing
from app.core.routing.version import (
    UNKNOWN_SHA,
    analysis_version,
    git_short_sha,
    parse_analysis_version,
    routing_hash,
    routing_snapshot,
    snapshot_matches,
)
from app.tests import test_graph_integration as gi

BACKEND = Path(__file__).resolve().parents[2]
SHA = "3f9c2ab8e41d0c7f5a6b9e2d1c0f8a7b6e5d4c3b"
VERSION_RE = re.compile(r"^graph_v1\+[0-9a-f]{7}\+p[0-9a-f]{8}$")


def _yaml_dict(**step_overrides) -> dict:
    import yaml

    data = yaml.safe_load((BACKEND / "config" / "routing.yaml").read_text())
    for step, changes in step_overrides.items():
        data["routing"][step] = {**data["routing"][step], **changes}
    return data


# ------------------------------------------------------------------ git sha


def test_sha_from_railway_then_git_sha_then_unknown():
    assert git_short_sha({"RAILWAY_GIT_COMMIT_SHA": SHA, "GIT_SHA": "a" * 40}) == SHA[:7]
    assert git_short_sha({"GIT_SHA": "ABCDEF0123"}) == "abcdef0"
    assert git_short_sha({"RAILWAY_GIT_COMMIT_SHA": "", "GIT_SHA": "1234567"}) == "1234567"
    assert git_short_sha({}) == UNKNOWN_SHA


def test_non_sha_values_are_never_copied_into_the_version():
    # Only a hex sha is accepted, so a misconfigured variable can't leak into a report.
    assert git_short_sha({"GIT_SHA": "sk-ant-secret-value"}) == UNKNOWN_SHA
    assert git_short_sha({"RAILWAY_GIT_COMMIT_SHA": "main+dirty", "GIT_SHA": SHA}) == SHA[:7]


def test_default_reads_os_environ(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("GIT_SHA", SHA)
    assert git_short_sha() == SHA[:7]
    monkeypatch.delenv("GIT_SHA")
    assert git_short_sha() == UNKNOWN_SHA


# ------------------------------------------------------------------ hash and snapshot


def test_version_string_format():
    v = analysis_version("graph_v1", load_routing(), env={"RAILWAY_GIT_COMMIT_SHA": SHA})
    assert VERSION_RE.match(v), v
    assert v.startswith(f"graph_v1+{SHA[:7]}+p")
    assert len(v) <= 64  # fits results.pipeline_version String(64)
    assert analysis_version("graph_v1", load_routing(), env={}).startswith("graph_v1+unknown+p")


def test_hash_is_deterministic_and_independent_of_key_order():
    data = _yaml_dict()
    a = routing_snapshot(parse_routing(data))
    reordered = {**data, "routing": dict(reversed(list(data["routing"].items())))}
    b = routing_snapshot(parse_routing(reordered))
    assert a == b and a["hash"] == b["hash"]
    assert routing_snapshot(load_routing())["hash"] == a["hash"]
    assert re.fullmatch(r"[0-9a-f]{8}", a["hash"])
    # the stored snapshot rehashes to its own hash
    assert routing_hash(json.loads(json.dumps(a))) == a["hash"]


@pytest.mark.parametrize("step,change", [
    ("verify_claims", {"prompt": "verify_v4"}),
    ("critique", {"model": "gpt-4o-2024-11-20"}),
    ("extract_claims", {"provider": "openai", "model": "gpt-4o-2024-08-06"}),
])
def test_hash_changes_with_prompt_or_model_routing(step, change):
    base = routing_snapshot(parse_routing(_yaml_dict()))["hash"]
    assert routing_snapshot(parse_routing(_yaml_dict(**{step: change})))["hash"] != base


def test_hash_changes_with_fallback_but_not_with_prices_or_labels():
    data = _yaml_dict()
    base = routing_snapshot(parse_routing(data))["hash"]
    fb = json.loads(json.dumps(data))
    fb["routing"]["fallback"]["retries"] = 2
    assert routing_snapshot(parse_routing(fb))["hash"] != base
    priced = json.loads(json.dumps(data))
    priced["pricing"]["claude-opus-5-5"]["input"] = 99.0
    priced["version"] = "routing_v1-relabelled"
    assert routing_snapshot(parse_routing(priced))["hash"] == base


def test_snapshot_holds_prompt_versions_per_node_and_no_secrets():
    cfg = load_routing()
    snap = routing_snapshot(cfg)
    assert snap["routing_version"] == cfg.version
    assert set(snap["steps"]) == set(cfg.steps)
    for name, route in cfg.steps.items():
        assert snap["steps"][name] == {"provider": route.provider, "model": route.model, "prompt": route.prompt} | (
            {"fallback": {"provider": route.fallback.provider, "model": route.fallback.model}} if route.fallback else {})
    assert snap["fallback"]["use"] == {"provider": cfg.fallback.use.provider, "model": cfg.fallback.use.model}
    assert "pricing" not in snap
    json.dumps(snap)  # JSON column


def test_key_like_params_are_dropped_from_the_snapshot(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-appear")
    data = _yaml_dict(analyze_stance={"params": {"temperature": 0, "api_key": "sk-ant-should-never-appear",
                                                 "auth_token": "t0k"}})
    snap = routing_snapshot(parse_routing(data))
    assert snap["steps"]["analyze_stance"]["params"] == {"temperature": 0}
    v = analysis_version("graph_v1", parse_routing(data), env={"GIT_SHA": SHA})
    blob = json.dumps(snap) + v
    assert "sk-ant" not in blob and "t0k" not in blob


# ------------------------------------------------------------------ parsing old and new


def test_parse_new_and_old_versions():
    new = parse_analysis_version("graph_v1+3f9c2ab+p1a2b3c4d")
    assert (new.base, new.git_sha, new.routing_hash, new.traceable) == ("graph_v1", "3f9c2ab", "1a2b3c4d", True)
    unknown = parse_analysis_version("graph_v1+unknown+p1a2b3c4d")
    assert unknown.git_sha == "unknown" and unknown.traceable
    for old in ("graph_v1", "graph-v1", "t24-crosscheck"):
        p = parse_analysis_version(old)
        assert p.base == old and p.git_sha is None and p.routing_hash is None and not p.traceable
    assert parse_analysis_version(None) is None and parse_analysis_version("") is None


def test_snapshot_matches_only_its_own_version():
    snap = routing_snapshot(load_routing())
    assert snapshot_matches(f"graph_v1+abc1234+p{snap['hash']}", snap)
    assert not snapshot_matches("graph_v1+abc1234+p00000000", snap)
    assert not snapshot_matches("graph_v1", snap)
    assert not snapshot_matches(f"graph_v1+abc1234+p{snap['hash']}", None)


# ------------------------------------------------------------------ production wiring


def test_build_graph_provider_uses_traceable_version(monkeypatch):
    from types import SimpleNamespace

    import app.core.inference as inference
    from app.core.inference.providers import graph_provider as gp

    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", SHA)
    monkeypatch.setattr(inference, "get_provider", lambda: gi.FakeSingleCall())
    settings = SimpleNamespace(
        ANTHROPIC_API_KEY="dummy", OPENAI_API_KEY="dummy", GRAPH_MODEL_TIMEOUT_SECONDS=1.0,
        NCBI_API_KEY="", NCBI_EMAIL="", RETRIEVAL_MAX_RESULTS_PER_QUERY=5, GRAPH_SHARED_RETRIEVAL=False,
        REDIS_URL="", USE_REFERENCE_SOURCES=False, GRAPH_TIMEOUT_SECONDS=5.0, GRAPH_PIPELINE_VERSION="graph_v1",
    )
    provider = gp.build_graph_provider(settings)
    snap = routing_snapshot(load_routing())
    assert provider.pipeline_version == f"graph_v1+{SHA[:7]}+p{snap['hash']}"
    assert provider.routing_snapshot == snap
    assert "dummy" not in json.dumps(provider.routing_snapshot)


def test_graph_flag_still_defaults_off():
    from app.core.config import Settings

    assert Settings.model_fields["USE_GRAPH_PIPELINE"].default is False
    assert Settings.model_fields["GRAPH_PIPELINE_VERSION"].default == "graph_v1"


# ------------------------------------------------------------------ persistence


def _traceable_provider(**kw):
    cfg = load_routing()
    return gi.make_provider(pipeline_version=analysis_version("graph_v1", cfg, env={"GIT_SHA": SHA}),
                            routing_snapshot=routing_snapshot(cfg), **kw)


def test_result_row_stores_version_and_snapshot():
    from app.db.models.result import Result
    from app.services.pipeline_result_service import persist_outcome

    db = gi._db()
    gi._job(db)
    outcome = _traceable_provider().run(gi.fusion(), job_id="job-1", video_id="vid-1")
    assert outcome.pipeline == "graph"
    persist_outcome(db, "job-1", gi.fusion(), outcome)
    res = db.query(Result).one()
    snap = routing_snapshot(load_routing())
    assert res.pipeline_version == f"graph_v1+{SHA[:7]}+p{snap['hash']}"
    assert res.routing_snapshot == snap
    assert res.model_used.startswith("graph_v1/")  # model_used keeps its pre-T36 form


def test_fallback_before_any_state_still_gets_the_version():
    from app.db.models.result import Result
    from app.services.pipeline_result_service import persist_outcome

    def explode(state):
        raise RuntimeError("boom")

    db = gi._db()
    gi._job(db)
    outcome = _traceable_provider(node_overrides={gi.r.RERANK_EVIDENCE: explode}).run(gi.fusion(), job_id="job-1")
    assert outcome.fallback_used
    persist_outcome(db, "job-1", gi.fusion(), outcome)
    res = db.query(Result).one()
    assert VERSION_RE.match(res.pipeline_version) and res.routing_snapshot["hash"] in res.pipeline_version


def test_resumed_old_state_keeps_graph_v1_and_no_mismatched_snapshot():
    """A run that started before T36 keeps its stored 'graph_v1'; no snapshot is paired with it."""
    from app.db.models.result import Result
    from app.services.pipeline_result_service import persist_outcome

    db = gi._db()
    gi._job(db)
    outcome = _traceable_provider().run(gi.fusion(), job_id="job-1", video_id="vid-1")
    outcome.state = {**outcome.state, "pipeline_version": "graph_v1"}
    persist_outcome(db, "job-1", gi.fusion(), outcome)
    res = db.query(Result).one()
    assert res.pipeline_version == "graph_v1" and res.routing_snapshot is None


# ------------------------------------------------------------------ API


def test_result_api_returns_snapshot_and_tolerates_old_rows():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routers import jobs as jobs_router
    from app.db.models.result import Result
    from app.tests import test_result_api_t26 as t26

    db = t26._session()
    t26._seed_graph_job(db)  # a pre-T36 row: pipeline_version "graph_v1", no snapshot
    app = FastAPI()
    app.include_router(jobs_router.router)
    app.dependency_overrides[t26.get_db] = lambda: db
    app.dependency_overrides[t26.get_current_user] = lambda: t26.ALICE
    client = TestClient(app)

    old = client.get("/jobs/job-a/result").json()
    assert old["pipeline_version"] == "graph_v1" and old["routing_snapshot"] is None

    snap = routing_snapshot(load_routing())
    res = db.query(Result).filter_by(job_id="job-a").one()
    res.pipeline_version = f"graph_v1+{SHA[:7]}+p{snap['hash']}"
    res.routing_snapshot = snap
    db.commit()
    new = client.get("/jobs/job-a/result").json()
    assert new["pipeline_version"] == res.pipeline_version
    assert new["routing_snapshot"] == snap


# ------------------------------------------------------------------ migration


def test_migration_adds_nullable_json_column_and_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    # One head; later migrations (T34's 0016) chain on 0015.
    heads = script.get_heads()
    assert len(heads) == 1
    assert "0015" in {r.revision for r in script.walk_revisions("base", heads[0])}
    rev = script.get_revision("0015")
    assert rev.down_revision == "0014"
    src = Path(rev.path).read_text()
    assert '"routing_snapshot"' in src and "nullable=True" in src and "drop_column" in src
