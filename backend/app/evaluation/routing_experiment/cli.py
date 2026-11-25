"""Command line for the routing experiment (T38). Run from ``backend/``.

Record retrieval once (free; PubMed E-utilities and the §6 reference allow-list, no
model calls)::

    python -m app.evaluation.routing_experiment freeze-evidence --out <dir>/frozen_evidence_tune.json

Dry run (the default; no model calls, prints item counts, estimated tokens and cost
per candidate per step)::

    python -m app.evaluation.routing_experiment run --frozen-evidence <file> --out <dir>

Paid run (needs BOTH --live and --max-usd; refuses before any call if the estimate is
over the cap; stops at the cap)::

    python -m app.evaluation.routing_experiment run --frozen-evidence <file> --out <dir> \\
        --live --max-usd 25

The golden set is read with ``git show origin/data/golden-label-set:...`` (tune split
only); ``--golden-dir`` reads a directory with the same layout instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from app.core.pipeline_options import DEFAULT_PIPELINE_OPTIONS_PATH, load_pipeline_options
from app.core.routing.config import RoutingConfigError, load_routing
from app.evaluation.routing_experiment import experiment as ex
from app.evaluation.routing_experiment.frozen import (
    DEFAULT_MODE,
    MODES,
    FrozenEvidence,
    FrozenEvidenceError,
    Recorder,
    write_frozen,
)
from app.evaluation.routing_experiment.golden import (
    DEFAULT_BASE,
    DEFAULT_REF,
    DirSource,
    GitSource,
    GoldenSetError,
    TuneSet,
)
from app.evaluation.routing_experiment.items import STEPS


def _tune(args) -> TuneSet:
    source = DirSource(Path(args.golden_dir)) if args.golden_dir else GitSource(args.golden_ref, args.golden_base)
    return TuneSet(source)


def _add_golden(p: argparse.ArgumentParser) -> None:
    p.add_argument("--golden-ref", default=DEFAULT_REF, help=f"git ref of the golden set (default {DEFAULT_REF})")
    p.add_argument("--golden-base", default=DEFAULT_BASE, help="dataset directory inside the ref")
    p.add_argument("--golden-dir", default=None, help="read the golden set from a directory instead of git")
    p.add_argument("--videos", nargs="*", default=None, help="limit to these tune video ids")


def cmd_freeze(args, *, recorder: Optional[Recorder] = None) -> int:
    tune = _tune(args)
    out = Path(args.out)
    existing = None
    if args.resume and out.exists():
        existing = json.loads(out.read_text()).get("claims")
    if recorder is None:  # pragma: no cover - network path; tests inject a recorder
        recorder = _network_recorder(no_references=args.no_references)
    claims = recorder.record(tune, only=args.videos, existing=existing)
    write_frozen(out, claims, golden=tune.source.describe(), budgets=recorder.budgets)
    n_ret = sum(len(c["retrieved"]) for c in claims.values())
    n_cit = sum(len(c["cited"]) for c in claims.values())
    print(json.dumps({"claims": len(claims), "retrieved_records": n_ret, "cited_records": n_cit,
                      "claims_with_errors": sum(1 for c in claims.values() if c["errors"]),
                      "out": str(out)}, indent=2))
    return 0


def _network_recorder(*, no_references: bool) -> Recorder:  # pragma: no cover - network
    import os

    from app.core.retrieval.pubmed import PubMedClient, shared_rate_limiter
    from app.core.retrieval.retriever import EvidenceRetriever

    email = os.environ.get("NCBI_EMAIL", "")
    limiter = shared_rate_limiter(False)  # 2.5 requests/second: under NCBI's 3/s without a key
    retriever = EvidenceRetriever(PubMedClient(email=email, rate_limiter=limiter), None)
    references = None
    if not no_references:
        from app.core.retrieval.references import ReferenceSearcher, load_reference_config
        from app.core.retrieval.references.snapshots import InMemorySnapshotStore

        references = ReferenceSearcher(load_reference_config(), snapshots=InMemorySnapshotStore(),
                                       rate_limiter=limiter)
    return Recorder(retriever, references, log=lambda m: print(m, file=sys.stderr, flush=True))


def cmd_run(args, *, client_factory=None) -> int:
    routing = load_routing(args.routing) if args.routing else load_routing()
    candidates = ex.load_candidates(args.candidates)
    tune = _tune(args)
    frozen = FrozenEvidence.load(Path(args.frozen_evidence), args.evidence_mode) if args.frozen_evidence else None
    steps = args.steps or list(STEPS)
    options = load_pipeline_options(args.pipeline_options)
    plan = ex.build_plan(tune, candidates, routing, steps=steps, frozen=frozen, videos=args.videos,
                         allow_assumed_evidence=not args.live, pipeline_options=options)

    if args.live and args.max_usd is None:
        print("refused: --live needs --max-usd <cap in USD>. Nothing was called.", file=sys.stderr)
        return 2
    if not args.live:
        report = ex.estimate(plan)
        if args.max_usd is not None:
            report["notes"].append("--max-usd given without --live: dry run only, nothing was called.")
        print(ex.render_markdown(report))
        if args.out:
            paths = ex.write_outputs(report, args.out)
            print(f"wrote {paths['report_json']} and {paths['report_md']}", file=sys.stderr)
        return 0

    kwargs = {"client_factory": client_factory} if client_factory else {}
    try:
        report = ex.live_run(plan, live=True, max_usd=args.max_usd, **kwargs)
    except ex.LiveRunRefused as exc:
        print(f"refused before any call: {exc}", file=sys.stderr)
        return 2
    out = args.out or "routing_experiment_out"
    paths = ex.write_outputs(report, out)
    print(Path(paths["report_md"]).read_text())
    print(json.dumps(paths, indent=2), file=sys.stderr)
    return 3 if report.get("stopped") else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.evaluation.routing_experiment", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("freeze-evidence", help="record retrieval for every tune claim (free; no model calls)")
    _add_golden(f)
    f.add_argument("--out", required=True, help="frozen evidence JSON to write")
    f.add_argument("--resume", action="store_true", help="keep claims already in --out")
    f.add_argument("--no-references", action="store_true", help="PubMed only (skip the §6 reference allow-list)")

    for name, help_ in (("run", "dry run by default; paid only with --live and --max-usd"),
                        ("dry-run", "estimate only (same as run without --live)")):
        r = sub.add_parser(name, help=help_)
        _add_golden(r)
        r.add_argument("--candidates", default=str(ex.DEFAULT_CANDIDATES_PATH))
        r.add_argument("--routing", default=None, help="routing table for prices and the base config")
        r.add_argument("--frozen-evidence", default=None, help="file from freeze-evidence (verify_claims)")
        r.add_argument("--evidence-mode", choices=MODES, default=DEFAULT_MODE)
        r.add_argument("--steps", nargs="*", choices=STEPS, default=None)
        r.add_argument("--pipeline-options", default=str(DEFAULT_PIPELINE_OPTIONS_PATH),
                       help="pipeline options YAML (extraction.use_ocr); point at a copy with "
                            "use_ocr: false for the no-OCR ablation")
        r.add_argument("--out", default=None, help="directory for report.json, report.md, routing_v2.yaml")
        if name == "run":
            r.add_argument("--live", action="store_true", help="make PAID model calls (needs --max-usd)")
            r.add_argument("--max-usd", type=float, default=None, help="hard USD cap for a live run")
        else:
            r.set_defaults(live=False, max_usd=None)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "freeze-evidence":
            return cmd_freeze(args)
        return cmd_run(args)
    except (GoldenSetError, FrozenEvidenceError, ex.ExperimentError, RoutingConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
