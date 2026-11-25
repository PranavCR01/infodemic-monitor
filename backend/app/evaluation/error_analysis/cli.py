"""T43 error analysis CLI (no model calls). Run from ``backend/``::

    # gold changes between two golden commits (tune split only)
    python -m app.evaluation.error_analysis gold-diff --old 0fbc68a --new dcf77b0

    # ceiling: blind re-label second pass vs first pass, strict and meaning matchers
    python -m app.evaluation.error_analysis ceiling --first 0fbc68a --blind-ref dcf77b0

    # full analysis of a run that saved per_item.json (T43 runner change)
    python -m app.evaluation.error_analysis analyze --per-item <dir>/per_item.json \\
        --golden-ref 0fbc68a --rescore-ref dcf77b0 --out <dir>/error_analysis.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from app.evaluation.error_analysis.analyze import analyze
from app.evaluation.error_analysis.goldset import blind_ceiling, gold_diff
from app.evaluation.routing_experiment.golden import DEFAULT_BASE, DirSource, GitSource, GoldenSetError, TuneSet


def _tune(ref: str, base: str, golden_dir: Optional[str] = None) -> TuneSet:
    return TuneSet(DirSource(Path(golden_dir)) if golden_dir else GitSource(ref, base))


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.evaluation.error_analysis", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--golden-base", default=DEFAULT_BASE)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("gold-diff")
    d.add_argument("--old", required=True)
    d.add_argument("--new", required=True)
    c = sub.add_parser("ceiling")
    c.add_argument("--first", required=True, help="golden ref whose claims are the first pass")
    c.add_argument("--blind-ref", required=True, help="golden ref that holds blind/model_relabel_claims.csv")
    a = sub.add_parser("analyze")
    a.add_argument("--per-item", required=True)
    a.add_argument("--golden-ref", required=True, help="golden ref the run used")
    a.add_argument("--rescore-ref", default=None)
    a.add_argument("--resamples", type=int, default=1000)
    a.add_argument("--out", default=None)
    args = p.parse_args(argv)
    try:
        if args.command == "gold-diff":
            res = gold_diff(_tune(args.old, args.golden_base), _tune(args.new, args.golden_base))
        elif args.command == "ceiling":
            res = blind_ceiling(_tune(args.first, args.golden_base), _tune(args.blind_ref, args.golden_base))
        else:
            payload = json.loads(Path(args.per_item).read_text())
            rescore = _tune(args.rescore_ref, args.golden_base) if args.rescore_ref else None
            res = analyze(payload, _tune(args.golden_ref, args.golden_base), rescore_tune=rescore, n=args.resamples)
    except GoldenSetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(res, indent=1, ensure_ascii=False, default=str)
    if getattr(args, "out", None):
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0
