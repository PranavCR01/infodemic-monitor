"""Evaluation registry and GET /v1/admin/evals (T63).

Registry: every file in ``evals/registry`` validates against ``EvalRecord`` (and the
committed JSON schema, when ``jsonschema`` is installed), names a report that exists,
and the committed schema matches the model. API: admin 200, reviewer/analyst 403, no
token 401, through the real ``get_current_user`` with HS256 test tokens.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import admin
from app.core.config import settings
from app.evaluation import registry as reg

SECRET = "test-secret-not-real-0123456789abcdef"
REGISTRY_FILES = sorted(reg.DEFAULT_REGISTRY_DIR.glob("*.json"))


# --------------------------------------------------------------------- registry


def test_registry_is_not_empty():
    assert len(REGISTRY_FILES) >= 30


@pytest.mark.parametrize("path", REGISTRY_FILES, ids=lambda p: p.name)
def test_every_registry_file_validates(path: Path):
    rec = reg.load_record(path)
    assert (reg.REPO_ROOT / rec.report_path).exists(), rec.report_path
    if rec.split is None or rec.value is None or rec.n_items is None or rec.cost_usd is None:
        assert rec.notes.strip()
    if rec.synthetic:
        assert "SYNTHETIC" in rec.notes


def test_whole_registry_loads_with_report_check():
    records = reg.load_registry(reg.DEFAULT_REGISTRY_DIR, check_reports_under=reg.REPO_ROOT)
    assert len(records) == len(REGISTRY_FILES)
    keys = [(reg.step_index(r.pipeline_step), -r.date.toordinal(), r.run_id) for r in records]
    assert keys == sorted(keys)


def test_registry_files_validate_against_committed_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(reg.SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for p in REGISTRY_FILES:
        errors = list(validator.iter_errors(json.loads(p.read_text())))
        assert not errors, (p.name, [e.message for e in errors])


def test_committed_schema_matches_model():
    committed = json.loads(reg.SCHEMA_PATH.read_text())
    assert committed == json.loads(json.dumps(reg.json_schema())), (
        "regenerate: python -m app.evaluation.registry schema > ../evals/eval_record.schema.json")


def test_pipeline_steps_match_graph_nodes():
    from app.core.graph.nodes import NODE_OUTPUTS

    assert set(reg.PIPELINE_STEPS) == set(NODE_OUTPUTS)


def test_backfill_covers_the_requested_tasks_and_not_running_ones():
    tasks = {reg.load_record(p).task for p in REGISTRY_FILES}
    assert {"T05", "T07", "T24", "T38", "T43", "T49", "T50", "T53"} <= tasks
    # T60 and T61 add their own records; the T63 backfill must not have made any for them.
    for p in REGISTRY_FILES:
        rec = reg.load_record(p)
        if rec.task in {"T60", "T61"}:
            assert rec.run_group and rec.run_group.startswith(rec.task), p.name


def test_synthetic_sets_are_flagged():
    for p in REGISTRY_FILES:
        rec = reg.load_record(p)
        if rec.task in {"T05", "T07"}:
            assert rec.synthetic and rec.split is None and rec.golden_set_ref is None


def _valid(**over) -> dict:
    base = {
        "run_id": "T99-example", "date": "2026-11-26", "task": "T99",
        "pipeline_step": "verify_claims", "split": "tune", "synthetic": False,
        "golden_set_ref": "origin/data/golden-label-set@abc", "models": [],
        "metric_name": "macro_f1", "value": 0.5, "ci95": None, "n_items": 10,
        "cost_usd": 0.0, "report_path": "evals/reports/T49/report.md", "notes": "",
    }
    base.update(over)
    return base


@pytest.mark.parametrize("over", [
    {"split": "dev"},
    {"pipeline_step": "make_coffee"},
    {"task": "38"},
    {"run_id": "bad id with spaces"},
    {"report_path": "/etc/passwd"},
    {"report_path": "../outside.md"},
    {"ci95": {"low": 0.6, "high": 0.4}},
    {"n_items": -1},
    {"cost_usd": -0.01},
    {"unexpected": 1},
    {"split": None},          # null split needs notes
    {"value": None},          # null value needs notes
    {"models": [{"provider": "anthropic"}]},  # model id required
])
def test_invalid_records_are_rejected(over):
    with pytest.raises(ValueError):
        reg.EvalRecord.model_validate(_valid(**over))


def test_file_name_must_match_run_id(tmp_path):
    (tmp_path / "other-name.json").write_text(json.dumps(_valid()))
    with pytest.raises(reg.RegistryError, match="file name"):
        reg.load_registry(tmp_path)


def test_missing_report_is_rejected(tmp_path):
    (tmp_path / "T99-example.json").write_text(json.dumps(_valid(report_path="evals/reports/nope.md")))
    with pytest.raises(reg.RegistryError, match="does not exist"):
        reg.load_registry(tmp_path, check_reports_under=reg.REPO_ROOT)


def test_cli_validate(capsys):
    assert reg._main(["validate", str(reg.DEFAULT_REGISTRY_DIR)]) == 0
    assert "ok:" in capsys.readouterr().out


# --------------------------------------------------------------------- API


def token(sub: str, app_role=None, user_role=None) -> str:
    claims = {"sub": sub, "aud": "authenticated", "role": "authenticated",
              "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    if app_role is not None:
        claims["app_metadata"] = {"provider": "email", "role": app_role}
    if user_role is not None:
        claims["user_metadata"] = {"role": user_role}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


ADMIN = auth(token("admin-1", app_role="admin"))
REVIEWER = auth(token("reviewer-1", app_role="reviewer"))
ANALYST = auth(token("analyst-1"))
SELF_PROMOTED = auth(token("analyst-2", user_role="admin"))  # user_metadata is ignored


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.delenv("EVALS_REGISTRY_DIR", raising=False)
    monkeypatch.delenv("EVALS_REPORT_BASE_URL", raising=False)
    app = FastAPI()
    app.include_router(admin.router)
    return TestClient(app)


def test_admin_gets_the_registry(client):
    r = client.get("/v1/admin/evals", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(REGISTRY_FILES) == len(body["items"])
    assert body["step_order"] == list(reg.PIPELINE_STEPS)
    assert sum(g["count"] for g in body["groups"]) == body["total"]
    idx = [it["step_index"] for it in body["items"]]
    assert idx == sorted(idx)
    assert [g["step"] for g in body["groups"]] == list(dict.fromkeys(it["pipeline_step"] for it in body["items"]))
    for it in body["items"]:
        for field in ("run_id", "pipeline_step", "split", "synthetic", "report_path", "report_url",
                      "metric_name", "value", "ci95", "n_items", "cost_usd", "models", "notes", "task", "date"):
            assert field in it
        assert it["report_url"] == admin.DEFAULT_REPORT_BASE_URL + it["report_path"]
    t05 = [it for it in body["items"] if it["task"] == "T05"]
    assert t05 and all(it["synthetic"] for it in t05)


def test_non_admins_get_403(client):
    for headers in (REVIEWER, ANALYST, SELF_PROMOTED):
        r = client.get("/v1/admin/evals", headers=headers)
        assert r.status_code == 403, headers


def test_no_token_gets_401(client):
    assert client.get("/v1/admin/evals").status_code == 401
    assert client.get("/v1/admin/evals", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_403_comes_before_reading_the_registry(client, monkeypatch, tmp_path):
    monkeypatch.setenv("EVALS_REGISTRY_DIR", str(tmp_path / "missing"))
    assert client.get("/v1/admin/evals", headers=ANALYST).status_code == 403
    assert client.get("/v1/admin/evals", headers=ADMIN).status_code == 500


def test_filters(client):
    tune = client.get("/v1/admin/evals?split=tune", headers=ADMIN).json()
    assert tune["total"] > 0 and all(it["split"] == "tune" for it in tune["items"])
    none = client.get("/v1/admin/evals?split=none", headers=ADMIN).json()
    assert none["total"] > 0 and all(it["split"] is None for it in none["items"])
    syn = client.get("/v1/admin/evals?synthetic=true", headers=ADMIN).json()
    assert {it["task"] for it in syn["items"]} == {"T05", "T07"}
    steps = client.get("/v1/admin/evals?step=extract_claims,verify_claims", headers=ADMIN).json()
    assert {it["pipeline_step"] for it in steps["items"]} == {"extract_claims", "verify_claims"}
    t38 = client.get("/v1/admin/evals?task=T38", headers=ADMIN).json()
    assert t38["total"] == 9
    assert client.get("/v1/admin/evals?step=nope", headers=ADMIN).status_code == 422
    assert client.get("/v1/admin/evals?split=dev", headers=ADMIN).status_code == 422


def test_registry_dir_and_base_url_overrides(client, monkeypatch, tmp_path):
    (tmp_path / "T99-example.json").write_text(json.dumps(_valid()))
    monkeypatch.setenv("EVALS_REGISTRY_DIR", str(tmp_path))
    monkeypatch.setenv("EVALS_REPORT_BASE_URL", "https://example.test/blob/x")
    body = client.get("/v1/admin/evals", headers=ADMIN).json()
    assert body["total"] == 1
    assert body["items"][0]["report_url"] == "https://example.test/blob/x/evals/reports/T49/report.md"


def test_route_is_mounted_on_the_app(monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    c = TestClient(app)  # no context manager: the lifespan (migrations) does not run
    assert c.get("/v1/admin/evals").status_code == 401
    assert c.get("/v1/admin/evals", headers=ANALYST).status_code == 403
    assert c.get("/v1/admin/evals", headers=ADMIN).status_code == 200


def test_dockerfiles_ship_the_registry():
    for name in ("Dockerfile", "Dockerfile.gpu"):
        text = (reg.REPO_ROOT / "backend" / name).read_text()
        assert "COPY evals/registry/ ./evals/registry/" in text, name
