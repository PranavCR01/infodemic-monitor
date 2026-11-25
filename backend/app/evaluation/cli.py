"""Command line for the evaluation framework. Run from ``backend/``:

    python -m app.evaluation validate-routing [config/routing.yaml]
    python -m app.evaluation dataset-info ../research/claim-level/dataset
    python -m app.evaluation agreement <first_dir> <second_dir>
    python -m app.evaluation run config/benchmarks/infodemic_v1.yaml --allow-paid
    python -m app.evaluation compare <candidate_run> <baseline_run> --primary macro_f1

``run`` calls the real configured provider and costs money, so it refuses to
start without ``--allow-paid``.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from app.core.routing.config import RoutingConfigError, load_routing
from app.evaluation.compare import compare_runs
from app.evaluation.dataset import DatasetError, labeller_agreement, load_dataset
from app.evaluation.runner import load_run, load_run_config, resolve, run_evaluation


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_validate_routing(args) -> int:
    try:
        cfg = load_routing(args.path)
    except RoutingConfigError as exc:
        print(f"invalid routing config: {exc}", file=sys.stderr)
        return 1
    _print({"version": cfg.version, "status": cfg.status, "hash": cfg.config_hash(),
            "steps": cfg.versions(),
            "unpriced_models": sorted({r.model for r in cfg.steps.values() if cfg.price(r.model) is None})})
    return 0


def cmd_dataset_info(args) -> int:
    try:
        ds = load_dataset(args.path, version=args.version)
    except DatasetError as exc:
        print(f"invalid dataset: {exc}", file=sys.stderr)
        return 1
    _print({
        "name": ds.name, "version": ds.version, "hash": ds.hash,
        **ds.summary(),
        "videos_with_inputs": len(ds.inputs),
        "coverage": ds.coverage(),
        "missing_categories": [c for c, n in ds.coverage().items() if n == 0],
        "label_inconsistencies": ds.label_inconsistencies(),
    })
    return 0


def cmd_agreement(args) -> int:
    report = labeller_agreement(load_dataset(args.first), load_dataset(args.second))
    _print(report.model_dump())
    return 0


def cmd_run(args) -> int:
    if not args.allow_paid:
        print("`run` calls the configured model provider and costs money; "
              "pass --allow-paid to confirm.", file=sys.stderr)
        return 2
    config = load_run_config(args.config)
    if config.pipeline.system != "baseline":
        print(f"system {config.pipeline.system!r} is not wired into the CLI yet "
              "(the graph lands with T11)", file=sys.stderr)
        return 2
    from app.core.inference import get_provider
    from app.evaluation.baseline import SingleCallBaseline

    routing = load_routing(resolve(config.pipeline.routing)) if config.pipeline.routing else None
    record = run_evaluation(config, SingleCallBaseline(get_provider()), routing=routing)
    _print(record.model_dump())
    return 0


def cmd_compare(args) -> int:
    result = compare_runs(
        load_run(args.candidate), load_run(args.baseline), args.primary,
        guards=args.guards, tolerance=args.tolerance,
    )
    _print(result.model_dump())
    return 0 if result.ships else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.evaluation")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("validate-routing")
    s.add_argument("path", nargs="?", default=None)
    s.set_defaults(func=cmd_validate_routing)

    s = sub.add_parser("dataset-info")
    s.add_argument("path")
    s.add_argument("--version", default="unversioned")
    s.set_defaults(func=cmd_dataset_info)

    s = sub.add_parser("agreement")
    s.add_argument("first")
    s.add_argument("second")
    s.set_defaults(func=cmd_agreement)

    s = sub.add_parser("run")
    s.add_argument("config")
    s.add_argument("--allow-paid", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("compare")
    s.add_argument("candidate")
    s.add_argument("baseline")
    s.add_argument("--primary", nargs="+", required=True)
    s.add_argument("--guards", nargs="*", default=["macro_f1", "cost_per_video"])
    s.add_argument("--tolerance", type=float, default=0.0)
    s.set_defaults(func=cmd_compare)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
