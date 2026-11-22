"""Run a system over the dataset and record everything (section 14).

A run stores its config hash, the git revision, the dataset hash, model and
prompt versions, every prediction and every trace, so any number can be
reproduced and any error traced back to the step that caused it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, Field, field_validator

from app.core.routing.config import RoutingConfig
from app.core.schemas.pipeline import MisinfoLabel
from app.evaluation.dataset import Dataset, VideoInput, load_dataset
from app.evaluation.records import RunRecord, VideoPrediction
from app.evaluation.scoring import METRIC_NAMES, score_predictions

BACKEND_DIR = Path(__file__).resolve().parents[2]


# --- Run configuration --------------------------------------------------------

class DatasetRef(BaseModel):
    path: str
    version: str = "unversioned"
    hash: Optional[str] = None


class PipelineRef(BaseModel):
    system: str = "baseline"
    routing: Optional[str] = None
    code_revision: Optional[str] = None  # filled from git when omitted


class SaveOptions(BaseModel):
    predictions: bool = True
    traces: bool = True


class RunConfig(BaseModel):
    benchmark: str
    dataset: DatasetRef
    split: str = "test"
    pipeline: PipelineRef = Field(default_factory=PipelineRef)
    metrics: list[str] = Field(default_factory=lambda: ["macro_f1"])
    save: SaveOptions = Field(default_factory=SaveOptions)
    output_dir: str = "eval_runs"

    @field_validator("metrics")
    @classmethod
    def _known_metrics(cls, v: list[str]) -> list[str]:
        unknown = [name for name in v if name not in METRIC_NAMES]
        if unknown:
            raise ValueError(f"unknown metrics {unknown}; known: {list(METRIC_NAMES)}")
        return v

    def config_hash(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def load_run_config(path: str | Path) -> RunConfig:
    return RunConfig.model_validate(yaml.safe_load(Path(path).read_text()))


def resolve(path: str, base: Path = BACKEND_DIR) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (base / p).resolve()


def git_revision(cwd: Path = BACKEND_DIR) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


# --- Systems under test -------------------------------------------------------

@runtime_checkable
class EvaluationSystem(Protocol):
    name: str

    def predict(self, video: VideoInput) -> VideoPrediction: ...

    def versions(self) -> dict[str, Any]: ...


# --- Runner -------------------------------------------------------------------

def run_evaluation(
    config: RunConfig,
    system: EvaluationSystem,
    *,
    dataset: Optional[Dataset] = None,
    routing: Optional[RoutingConfig] = None,
    output_dir: Optional[str | Path] = None,
    code_revision: Optional[str] = None,
    clock: Callable[[], float] = time.perf_counter,
) -> RunRecord:
    if dataset is None:
        dataset = load_dataset(
            resolve(config.dataset.path), version=config.dataset.version,
            expected_hash=config.dataset.hash,
        )
    elif config.dataset.hash and config.dataset.hash != dataset.hash:
        raise ValueError(f"dataset hash mismatch: config pins {config.dataset.hash}, got {dataset.hash}")

    videos = dataset.split(config.split)
    missing = [v.video_id for v in videos if v.video_id not in dataset.inputs]
    if missing:
        raise ValueError(f"no inputs for videos {missing}; add them to inputs.jsonl")

    started = _now()
    predictions: dict[str, VideoPrediction] = {}
    for v in videos:
        t0 = clock()
        try:
            pred = system.predict(dataset.inputs[v.video_id])
            if pred.video_id != v.video_id:
                pred = pred.model_copy(update={"video_id": v.video_id})
        except Exception as exc:  # a failed video is recorded, not fatal to the run
            pred = VideoPrediction(
                video_id=v.video_id, label=MisinfoLabel.CANNOT_RECOGNIZE,
                error=f"{type(exc).__name__}: {exc}",
            )
        if pred.latency_ms is None:
            pred.latency_ms = int(round((clock() - t0) * 1000))
        if pred.cost_usd is None and pred.model_calls:
            costs = [c.cost_usd for c in pred.model_calls]
            if all(c is not None for c in costs):
                pred.cost_usd = sum(costs)
        predictions[v.video_id] = pred

    all_metrics, failures = score_predictions(videos, predictions)
    selected = {name: all_metrics.get(name) for name in config.metrics}

    record = RunRecord(
        run_id=f"{config.benchmark}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}",
        benchmark=config.benchmark,
        system=system.name,
        split=config.split,
        started_at=started,
        finished_at=_now(),
        config_hash=config.config_hash(),
        code_revision=code_revision or config.pipeline.code_revision or git_revision(),
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        dataset_hash=dataset.hash,
        routing_version=routing.version if routing else None,
        routing_hash=routing.config_hash() if routing else None,
        model_versions=system.versions(),
        n_videos=len(videos),
        n_errors=sum(1 for p in predictions.values() if p.error),
        metrics=selected,
        tracked_failures=failures,
    )

    out_root = Path(output_dir) if output_dir else resolve(config.output_dir)
    record.output_dir = str(save_run(record, predictions, out_root / record.run_id, config.save))
    return record


def save_run(record: RunRecord, predictions: dict[str, VideoPrediction], directory: Path,
             options: SaveOptions = SaveOptions()) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    record = record.model_copy(update={"output_dir": str(directory)})
    (directory / "run.json").write_text(record.model_dump_json(indent=2))
    if options.predictions:
        with (directory / "predictions.jsonl").open("w") as fh:
            for p in predictions.values():
                fh.write(p.model_dump_json(exclude={"trace"}) + "\n")
    if options.traces:
        with (directory / "traces.jsonl").open("w") as fh:
            for p in predictions.values():
                fh.write(json.dumps({
                    "video_id": p.video_id,
                    "trace": p.trace,
                    "model_calls": [c.model_dump() for c in p.model_calls],
                }) + "\n")
    return directory


def load_run(path: str | Path) -> RunRecord:
    path = Path(path)
    if path.is_dir():
        path = path / "run.json"
    return RunRecord.model_validate_json(path.read_text())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
