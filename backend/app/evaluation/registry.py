"""Evaluation registry (T63; design §13, §14).

One JSON file per evaluation measurement at ``evals/registry/<run_id>.json``. A record
is one metric of one run: a run that reports three metrics (for example strict and two
lenient recalls) writes three records that share a ``run_group``. Every evaluation task
adds its own record(s) as part of its deliverable (``automation/TASK_PROMPT.md``).

Rules a record must follow (checked by ``load_registry`` and the validation test):

- The file name is ``<run_id>.json``; run ids are unique.
- ``split`` is ``tune`` or ``test`` (golden set), or ``null`` when the data is not one
  golden split (a synthetic set, or a check over the whole golden set); ``notes`` then
  says why.
- ``synthetic: true`` for self-made data (not the golden set); ``golden_set_ref`` is then
  normally ``null``.
- ``models`` lists the model(s) and prompt(s) measured; ``[]`` means no model was
  involved (deterministic code); ``null`` means the report does not say.
- ``value`` and ``ci95`` are copied from the report, never recomputed here. A field the
  report does not give is ``null`` and ``notes`` says so.
- ``cost_usd`` is the provider-billed spend of the run group (repeated on each record of
  the group; count it once per ``run_group``). ``0`` means no paid call was made.
- ``report_path`` is repo-relative and must exist.

The JSON schema at ``evals/eval_record.schema.json`` is generated from ``EvalRecord``
(``python -m app.evaluation.registry schema``); a test keeps the two in step.

``python -m app.evaluation.registry validate [dir]`` checks a registry directory.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

SCHEMA_VERSION = "1"

# Pipeline steps in graph order (the node names of ``app.core.graph.nodes.NODE_OUTPUTS``;
# a test checks they match). The admin API sorts records by this order.
PIPELINE_STEPS: tuple[str, ...] = (
    "load_artifacts",
    "transcribe_audio",
    "extract_ocr",
    "fuse_modalities",
    "extract_claims",
    "analyze_stance",
    "plan_retrieval",
    "retrieve_evidence",
    "rerank_evidence",
    "verify_claims",
    "critique_verification",
    "judge_classification",
    "validate_result",
    "route_for_review",
    "human_review",
    "persist_result",
)

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_TASK = re.compile(r"^T\d{2,3}$")

# Repo root: backend/app/evaluation/registry.py -> parents[3]. In the backend image the
# source lives at /app/backend/app/..., so this is /app, where the Dockerfile copies
# evals/registry.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_DIR = REPO_ROOT / "evals" / "registry"
SCHEMA_PATH = REPO_ROOT / "evals" / "eval_record.schema.json"


class ModelRef(BaseModel):
    """A model and the prompt it ran with, as the report names them."""

    model_config = ConfigDict(extra="forbid")

    provider: Optional[str] = Field(None, description="anthropic, openai, ... (null if the report does not say)")
    model: str = Field(..., min_length=1, description="Model id as reported, e.g. claude-sonnet-5-5")
    prompt: Optional[str] = Field(None, description="Prompt id, e.g. extract_v2 (null if none or not reported)")
    role: Optional[str] = Field(None, description="What the model did in this run, when more than one ran")


class CI95(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: float
    high: float
    method: Optional[str] = Field(None, description="e.g. bootstrap over videos, 1000 resamples")

    @model_validator(mode="after")
    def _ordered(self) -> "CI95":
        if self.low > self.high:
            raise ValueError("ci95.low must be <= ci95.high")
        return self


class EvalRecord(BaseModel):
    """One metric of one evaluation run."""

    model_config = ConfigDict(extra="forbid", title="EvalRecord")

    schema_version: Literal["1"] = SCHEMA_VERSION
    run_id: str = Field(..., description="Unique id; the file is evals/registry/<run_id>.json")
    run_group: Optional[str] = Field(
        None, description="Records from the same run share this; cost_usd is per group")
    date: _dt.date = Field(..., description="Date the run was made (YYYY-MM-DD)")
    task: str = Field(..., description="Build task id, e.g. T38")
    pipeline_step: str = Field(..., description="Graph node the metric measures (PIPELINE_STEPS)")
    split: Optional[Literal["tune", "test"]] = Field(
        ..., description="Golden-set split; null when the data is not one golden split (see notes)")
    synthetic: bool = Field(..., description="True when the data is self-made, not the golden set")
    golden_set_ref: Optional[str] = Field(
        ..., description="Golden-set branch@commit the labels came from; null if none")
    models: Optional[list[ModelRef]] = Field(
        ..., description="Models and prompts measured; [] = no model; null = not reported")
    variant: Optional[str] = Field(
        None, description="Configuration measured when a run compares several (e.g. baseline)")
    metric_name: str = Field(..., min_length=1)
    value: Optional[float] = Field(..., description="Metric value as reported; null if not computable")
    ci95: Optional[CI95] = Field(..., description="95% CI as reported; null if the report has none")
    n_items: Optional[int] = Field(..., ge=0, description="Items the metric is computed over")
    n_unit: Optional[str] = Field(None, description="What n_items counts: claims, videos, items, ...")
    cost_usd: Optional[float] = Field(..., ge=0, description="Spend of the run group; 0 = no paid call")
    report_path: str = Field(..., min_length=1, description="Repo-relative path of the report")
    notes: str = Field("", description="Caveats, and why any field is null")

    @field_validator("run_id")
    @classmethod
    def _run_id(cls, v: str) -> str:
        if not _RUN_ID.match(v):
            raise ValueError("run_id: letters, digits, '.', '_' and '-' only (3-128 chars)")
        return v

    @field_validator("task")
    @classmethod
    def _task(cls, v: str) -> str:
        if not _TASK.match(v):
            raise ValueError("task must look like T38")
        return v

    @field_validator("pipeline_step")
    @classmethod
    def _step(cls, v: str) -> str:
        if v not in PIPELINE_STEPS:
            raise ValueError(f"pipeline_step must be one of {', '.join(PIPELINE_STEPS)}")
        return v

    @field_validator("report_path")
    @classmethod
    def _relative(cls, v: str) -> str:
        if v.startswith("/") or ".." in Path(v).parts:
            raise ValueError("report_path must be repo-relative")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "EvalRecord":
        if self.split is None and not self.notes.strip():
            raise ValueError("split is null: notes must say why")
        if self.value is None and not self.notes.strip():
            raise ValueError("value is null: notes must say why")
        return self



def step_index(step: str) -> int:
    """Position of ``step`` in graph order."""
    return PIPELINE_STEPS.index(step)


class RegistryError(ValueError):
    """The registry directory holds an invalid or inconsistent record."""


def registry_dir() -> Path:
    """``EVALS_REGISTRY_DIR`` if set, else ``<repo root>/evals/registry``."""
    env = os.environ.get("EVALS_REGISTRY_DIR", "").strip()
    return Path(env) if env else DEFAULT_REGISTRY_DIR


def load_record(path: Path) -> EvalRecord:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"{path.name}: not readable JSON ({exc})") from exc
    try:
        rec = EvalRecord.model_validate(data)
    except ValidationError as exc:
        raise RegistryError(f"{path.name}: {exc}") from exc
    if path.name != f"{rec.run_id}.json":
        raise RegistryError(f"{path.name}: file name must be {rec.run_id}.json")
    return rec


def load_registry(directory: Optional[Path] = None, *, check_reports_under: Optional[Path] = None
                  ) -> list[EvalRecord]:
    """Every record in ``directory`` (default ``registry_dir()``), sorted by pipeline
    step, then date (newest first), then run id. Raises ``RegistryError`` on the first
    invalid file. With ``check_reports_under`` set, each ``report_path`` must exist
    under it (the repo root; the backend image does not ship the reports)."""
    d = Path(directory) if directory is not None else registry_dir()
    if not d.is_dir():
        raise RegistryError(f"registry directory not found: {d}")
    records = [load_record(p) for p in sorted(d.glob("*.json"))]
    seen: set[str] = set()
    for r in records:
        if r.run_id in seen:  # unreachable with run_id == file name, kept as a guard
            raise RegistryError(f"duplicate run_id {r.run_id}")
        seen.add(r.run_id)
        if check_reports_under is not None and not (check_reports_under / r.report_path).exists():
            raise RegistryError(f"{r.run_id}: report_path {r.report_path} does not exist")
    return sort_records(records)


def sort_records(records: list[EvalRecord]) -> list[EvalRecord]:
    return sorted(records, key=lambda r: (step_index(r.pipeline_step), -r.date.toordinal(), r.run_id))


def json_schema() -> dict:
    schema = EvalRecord.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "evals/eval_record.schema.json"
    return schema


def _main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"schema", "validate"}:
        print("usage: python -m app.evaluation.registry schema | validate [dir]", file=sys.stderr)
        return 2
    if argv[0] == "schema":
        print(json.dumps(json_schema(), indent=2, sort_keys=True))
        return 0
    directory = Path(argv[1]) if len(argv) > 1 else registry_dir()
    try:
        records = load_registry(directory, check_reports_under=REPO_ROOT)
    except RegistryError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {len(records)} records in {directory}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
