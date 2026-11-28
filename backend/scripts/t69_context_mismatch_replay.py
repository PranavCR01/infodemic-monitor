"""T69: offline replay gate for the context-mismatch label rule (design §9). No model calls.

Rule (``routing.CONTEXT_MISMATCH_RULE``): the only ENDORSES + CONTRADICTED claim, whose
contradicting records are all narrative reviews or lab / modelling studies and which the
verifier's structured ``evidence_context`` field marked as another population or exposure
setting, can't decide; review reason ``contradiction_context_mismatch:<cid>``, label falls
through.

Baseline is what ships today (T67 change 1 ON, change 2 OFF, change 3 ON; T64 guard).
Three configurations:

- ``off``: as shipped.
- ``on``: + the T69 switch. No stored verdict predates the new structured field, so the
  verifier's mismatch code is absent everywhere and the rule cannot fire on stored data.
- ``upper``: + the T69 switch, *assuming the verifier flagged a mismatch on every
  CONTRADICTED verdict* (a counterfactual worst case). Only the deterministic parts of
  the rule (sole deciding claim; all contradicting records narrative review / modelling)
  then limit it, so this bounds how many labels the rule could ever change on this data.

Inputs (tune split only; the test split is never read):
A. ``--t66 <dir>``: the finished T66 videos' stored final states (as T67's replay A).
B. The golden set's own claims for every in-scope tune video (as T67's replay B), which
   includes v135 (the trigger video; not among T66's 18 finished videos).

    python scripts/t69_context_mismatch_replay.py --t66 ../evals/reports/T66/videos \\
        --out ../evals/reports/T69/results.json --report ../evals/reports/T69/replay.md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import t67_label_rules_replay as t67  # noqa: E402

from app.core.graph import judge as jg  # noqa: E402
from app.core.graph import routing as rt  # noqa: E402
from app.core.graph.state import Verdict  # noqa: E402

LABELS = t67.LABELS
CONFIGS = ("off", "on", "upper")
CONFIG_NAMES = {
    "off": "as shipped (T69 switch off)",
    "on": "T69 switch on (stored verdicts)",
    "upper": "T69 switch on, mismatch assumed on every CONTRADICTED verdict (upper bound)",
}
# Videos T67 fixed on the T66 states (change 1, ON by lead decision): must not regress.
T67_FIXED = ("v71", "v78", "v87", "v122")
REASON = "judge:" + jg.FLAG_CONTEXT_MISMATCH


@contextmanager
def config(name: str):
    old = (rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE, jg.ANALYSIS_INCOMPLETE_RULE,
           rt.CONTEXT_MISMATCH_RULE, jg.context_mismatch_kind)
    rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE, jg.ANALYSIS_INCOMPLETE_RULE = (
        True, False, True)  # as shipped (T67 merge 11d1eae + lead decision 65a247b)
    rt.CONTEXT_MISMATCH_RULE = name != "off"
    if name == "upper":
        jg.context_mismatch_kind = (
            lambda v: "different_exposure_setting" if v.verdict == Verdict.CONTRADICTED else None)
    try:
        yield
    finally:
        (rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE, jg.ANALYSIS_INCOMPLETE_RULE,
         rt.CONTEXT_MISMATCH_RULE, jg.context_mismatch_kind) = old


def replay(states: list[tuple[str, str, dict]]) -> list[dict]:
    rows = []
    for vid, gold, state in states:
        row = {"video_id": vid, "gold": gold}
        for name in CONFIGS:
            with config(name):
                row[name] = t67.run_judge(state)
        rows.append(row)
    return rows


def t66_states(directory: str, gold: dict[str, dict]) -> tuple[list, list[str]]:
    import glob

    out, excluded = [], []
    for path in sorted(glob.glob(str(Path(directory) / "*.json"))):
        rec = json.loads(Path(path).read_text())
        if rec.get("status") != "finished":
            excluded.append(f"{rec.get('video_id')} (status {rec.get('status')!r})")
            continue
        state = t67.apply_t64_guard(t67._STATE.validate_python(rec["state"]))
        out.append((rec["video_id"], gold[rec["video_id"]]["video_level_label"], state))
    return out, excluded


def golden_states(gold: dict[str, dict], claims: list[dict], frozen: dict) -> tuple[list, list[str]]:
    cache = t67.evidence_cache()
    by_video: dict[str, list[dict]] = {}
    for r in claims:
        by_video.setdefault(r["video_id"], []).append(r)
    out, missing = [], []
    for vid in sorted((v for v in gold if t67.in_scope(gold[v])), key=lambda x: (len(x), x)):
        state = t67.golden_state(vid, by_video.get(vid, []), frozen, cache, missing)
        out.append((vid, gold[vid]["video_level_label"], state))
    return out, missing


def accuracy(rows: list[dict], key: str) -> int:
    return sum(r[key]["label"] == r["gold"] for r in rows)


def section(title: str, rows: list[dict], focus: tuple[str, ...] = ()) -> tuple[list[str], dict]:
    lines = [f"### {title}: {len(rows)} videos", ""]
    summary: dict = {}
    for key in CONFIGS:
        m, ok = t67.matrix(rows, key)
        fired = sum(any(x.startswith(REASON) for x in r[key]["reasons"]) for r in rows)
        reviewed = sum(r[key]["review"] for r in rows)
        summary[key] = {"correct": ok, "n": len(rows), "accuracy": round(ok / len(rows), 4) if rows else None,
                        "reviewed": reviewed, "rule_fired": fired}
        lines.append(f"**{CONFIG_NAMES[key]}**: accuracy {ok}/{len(rows)}; sent to review {reviewed}/{len(rows)}; "
                     f"`contradiction_context_mismatch` fired on {fired} video(s)")
        lines.append("")
        lines.append("| gold \\ ours | " + " | ".join(LABELS) + " |")
        lines.append("|---|" + "---|" * len(LABELS))
        for i, g in enumerate(LABELS):
            lines.append(f"| {g} | " + " | ".join(str(x) for x in m[i]) + " |")
        lines.append("")
    lines.append("Per video (label, rule; ✱ = rule fired; ▼ = worse than `off` vs gold):")
    lines.append("")
    lines.append("| video | gold | " + " | ".join(CONFIGS) + " |")
    lines.append("|---|---|" + "---|" * len(CONFIGS))
    worse: dict[str, list[str]] = {k: [] for k in CONFIGS}
    changed: dict[str, list[str]] = {k: [] for k in CONFIGS}
    for r in rows:
        cells = []
        for key in CONFIGS:
            x = r[key]
            mark = "✱" if any(y.startswith(REASON) for y in x["reasons"]) else ""
            if t67.worse(r["gold"], r["off"]["label"], x["label"]):
                worse[key].append(r["video_id"])
                mark += "▼"
            if x["label"] != r["off"]["label"]:
                changed[key].append(r["video_id"])
            cells.append(f"{t67.lab(x)} `{x['rule']}`{mark}")
        tag = " (T67-fixed)" if r["video_id"] in focus else ""
        lines.append(f"| {r['video_id']}{tag} | {r['gold']} | " + " | ".join(cells) + " |")
    lines.append("")
    for key in CONFIGS:
        summary[key]["worse"] = worse[key]
        summary[key]["changed"] = changed[key]
    return lines, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--t66", required=True)
    ap.add_argument("--frozen")
    ap.add_argument("--out")
    ap.add_argument("--report")
    args = ap.parse_args(argv)

    gold, claims = t67.tune_rows()
    a_states, excluded = t66_states(args.t66, gold)
    b_states, missing = golden_states(gold, claims, t67.load_frozen(args.frozen))
    a_rows, b_rows = replay(a_states), replay(b_states)
    rev = t67.code_revision()

    la, sa = section("A. T66 stored states (tune)", a_rows, T67_FIXED)
    lb, sb = section("B. Golden claims (tune, in scope)", b_rows)
    t67_fixed = {r["video_id"]: {k: r[k]["label"] for k in CONFIGS} for r in a_rows if r["video_id"] in T67_FIXED}
    v135 = next((r for r in b_rows if r["video_id"] == "v135"), None)
    head = [
        "# T69 replay: contradiction_context_mismatch (offline, no model calls)",
        "",
        f"Code: `{rev}`. Tune split only. Baseline = as shipped (T67 change 1 on, change 2 off, change 3 on; T64 guard).",
        f"A excluded: {', '.join(excluded) or 'none'}. B evidence IDs not in the offline cache: {len(missing)}.",
        "",
        "The production v135 fixture (jobs cf2ea579 / f85f2daa) was not in the repo; see report.md.",
        "",
        f"T67-fixed videos (A): " + ", ".join(f"{v}: {d}" for v, d in sorted(t67_fixed.items())),
        "",
        f"Golden v135 (B): " + (", ".join(f"{k} {v135[k]['label']}" for k in CONFIGS) if v135 else "not found"),
        "",
    ]
    text = "\n".join(head + la + lb) + "\n"
    results = {"code_revision": rev, "excluded": excluded, "missing_evidence": missing,
               "summary": {"A": sa, "B": sb}, "t67_fixed": t67_fixed, "A": a_rows, "B": b_rows}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(results, indent=1, default=str) + "\n")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text)
    print(json.dumps({"A": sa, "B": sb, "t67_fixed": t67_fixed}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
