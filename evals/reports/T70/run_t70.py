"""T70: the PROPOSED paid tune-split run with claim context on. PROPOSE ONLY.

Nothing here spends money unless the lead approves the run and its cap directly. The run
is the T66 runner (``evals/reports/T66/run_t66.py``, the full production graph wiring,
every provider client inside the routing experiment's ``SpendGuard``) with two changes:

- ``routing.CLAIM_CONTEXT = True`` before the graph is built;
- routing.yaml as merged, with ``extract_claims`` on ``extract_v5`` and ``verify_claims``
  on ``verify_v4`` (the prompts the switch requires; same models).

Subcommands, run from ``backend/``:

    python ../evals/reports/T70/run_t70.py materialize --out <dir>     # tune split only
    python ../evals/reports/T70/run_t70.py estimate --data <dir>       # no model calls
    python ../evals/reports/T70/run_t70.py run --data <dir> --max-usd X --approved-by NAME --live
        PAID. Refused unless --live, --approved-by and --max-usd are all given, --max-usd is
        at most HARD_CAP_USD, and EVAL_ANTHROPIC_API_KEY is set. Runs the proposed videos
        (T66's 18 finished + v21 + v135, the trigger) in T66's declared order. Each video's
        full state goes to ``videos/<id>.json``.

The test split is never read: ``materialize`` keeps tune rows only (T66's function).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

HARD_CAP_USD = 35.0  # the runner refuses any larger --max-usd; the lead sets the real cap
CONTEXT_PROMPTS = {"extract_claims": "extract_v5", "verify_claims": "verify_v4"}
T66_DIR = REPO / "evals" / "reports" / "T66"
TRIGGER = "v135"


def _t66():
    spec = importlib.util.spec_from_file_location("run_t66", T66_DIR / "run_t66.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.VIDEOS_DIR = HERE / "videos"  # never write into T66's results
    mod.HERE = HERE  # run records go under T70/runs
    return mod


def context_routing():
    """routing.yaml as merged, with the two context prompts (same models)."""
    from app.core.routing import config as rc

    base = rc._T70_ORIGINAL_LOAD() if hasattr(rc, "_T70_ORIGINAL_LOAD") else rc.load_routing()
    steps = dict(base.steps)
    for step, prompt in CONTEXT_PROMPTS.items():
        steps[step] = steps[step].model_copy(update={"prompt": prompt})
    return base.model_copy(update={"steps": steps})


def switch_on() -> None:
    """CLAIM_CONTEXT on and every load_routing() returning the context routing."""
    from app.core.graph import routing as rt
    from app.core.routing import config as rc

    rt.CLAIM_CONTEXT = True
    if not hasattr(rc, "_T70_ORIGINAL_LOAD"):
        rc._T70_ORIGINAL_LOAD = rc.load_routing
        rc.load_routing = lambda path=None: context_routing()


def proposed_videos(t66) -> list[str]:
    finished = sorted(p.stem for p in (T66_DIR / "videos").glob("*.json"))
    order = json.loads((T66_DIR / "order.json").read_text())["order"]
    chosen = [v for v in order if v in set(finished) | {TRIGGER}]
    return [TRIGGER, *[v for v in chosen if v != TRIGGER]]


def estimate(data: Path) -> dict:
    """No calls. T66's own estimator with the T70 prompt sizes, calibrated by T66's actual
    spend: on T66's 18 finished videos the real cost was ``ratio`` times T66's expected
    estimate, so the calibrated figure is expected x ratio."""
    t66 = _t66()
    ds = t66.load_tune(data)
    base = t66.estimate(ds)
    switch_on()
    ctx = t66.estimate(ds)
    videos = proposed_videos(t66)
    actual = {}
    for p in (T66_DIR / "videos").glob("*.json"):
        rec = json.loads(p.read_text())
        actual[rec["video_id"]] = (rec["status"], float(rec.get("cost_usd") or 0.0))
    finished = [v for v, (s, _) in actual.items() if s == "finished"]
    ratio = sum(actual[v][1] for v in finished) / sum(base["per_video"][v]["expected_usd"] for v in finished)
    rows = {}
    for v in videos:
        b, c = base["per_video"][v], ctx["per_video"][v]
        rows[v] = {"t66_actual_usd": actual.get(v, (None, None))[1], "t66_status": actual.get(v, (None, None))[0],
                   "expected_usd_t66_prompts": b["expected_usd"], "expected_usd_t70_prompts": c["expected_usd"],
                   "calibrated_usd": round(c["expected_usd"] * ratio, 4), "upper_usd": c["upper_usd"]}
    tot = lambda k: round(sum(r[k] or 0 for r in rows.values()), 2)  # noqa: E731
    return {
        "videos": videos, "n_videos": len(videos), "calibration_ratio_actual_over_expected_t66": round(ratio, 3),
        "total_expected_usd_t66_prompts": tot("expected_usd_t66_prompts"),
        "total_expected_usd_t70_prompts": tot("expected_usd_t70_prompts"),
        "total_calibrated_usd": tot("calibrated_usd"), "total_upper_usd": tot("upper_usd"),
        "t66_actual_usd_same_videos": tot("t66_actual_usd"),
        "proposed_cap_usd": 30.0, "hard_cap_in_runner_usd": HARD_CAP_USD, "per_video": rows,
        "routing": context_routing().versions(), "dataset_hash": ds.hash,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("materialize"); m.add_argument("--out", required=True)
    e = sub.add_parser("estimate"); e.add_argument("--data", required=True)
    r = sub.add_parser("run")
    r.add_argument("--data", required=True)
    r.add_argument("--max-usd", type=float, required=True)
    r.add_argument("--approved-by", required=True, help="who approved this run and cap, as recorded in the queue")
    r.add_argument("--live", action="store_true", help="really call the models (paid)")
    r.add_argument("--reserve", type=float, default=2.5)
    a = ap.parse_args(argv)
    t66 = _t66()
    if a.cmd == "materialize":
        print(json.dumps(t66.materialize(Path(a.out)), indent=2))
        return 0
    if a.cmd == "estimate":
        print(json.dumps(estimate(Path(a.data)), indent=2))
        return 0
    if not a.live:
        print("refused: a paid run needs --live (and the lead's direct approval of the run and its cap)")
        return 2
    if not (0 < a.max_usd <= HARD_CAP_USD):
        print(f"refused: --max-usd must be in (0, {HARD_CAP_USD}]")
        return 2
    if not a.approved_by.strip() or not os.environ.get("EVAL_ANTHROPIC_API_KEY"):
        print("refused: --approved-by and EVAL_ANTHROPIC_API_KEY are required")
        return 2
    switch_on()
    (HERE / "videos").mkdir(exist_ok=True)
    (HERE / "approval.json").write_text(json.dumps({"approved_by": a.approved_by, "max_usd": a.max_usd}, indent=2))
    order = json.loads((T66_DIR / "order.json").read_text())
    # T66's run(): same order check, same guard, same NOT RUN rules; only our videos.
    order_path = HERE / "order.json"
    order_path.write_text(json.dumps(order, indent=2))
    return t66.main(["run", "--data", a.data, "--max-usd", str(a.max_usd), "--reserve", str(a.reserve),
                     "--order", str(order_path), "--only", *proposed_videos(t66)])


if __name__ == "__main__":
    raise SystemExit(main())
