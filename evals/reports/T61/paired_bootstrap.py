"""T61: paired-bootstrap 95% CIs for the prompt comparisons (no model calls).

Reads the runner's per_item.json files (one per comparison) and, for each pair of
candidates, resamples the SAME items for both (paired):

- extract_claims: resample videos (48). Metrics: claim P/R/F1 under the strict matcher
  (the runner's selection metric ``claim_f1``) and the meaning-based matcher (T45),
  pooled over the resampled videos exactly as the runner pools them.
- analyze_stance: resample claims (187). Metrics: macro-F1 over the labels present in
  the (resampled) gold set, as ``metrics.macro_f1`` does, and per-label recall.

Failed items score as the runner scores them: no claims (extraction), ``__none__``
(stance). Percentile intervals, B resamples, fixed seed. Run from ``backend/``:

    python ../evals/reports/T61/paired_bootstrap.py --B 10000 --seed 61 \
        ../evals/reports/T61/run_stance/per_item.json ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from app.evaluation import metrics as m
from app.evaluation.error_analysis import matching as mt
from app.evaluation.routing_experiment.items import STANCE_LABELS


def _f1(tp, n_gold, n_pred):
    p = np.where(n_pred > 0, tp / np.maximum(n_pred, 1), np.nan)
    r = np.where(n_gold > 0, tp / np.maximum(n_gold, 1), np.nan)
    f = np.where((p + r) > 0, 2 * p * r / np.where((p + r) > 0, p + r, 1), 0.0)
    f = np.where(np.isnan(p) | np.isnan(r), np.nan, f)
    return p, r, f


def _ci(diffs):
    d = diffs[~np.isnan(diffs)]
    if len(d) == 0:
        return None
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"lo": float(lo), "hi": float(hi), "n_defined": int(len(d)),
            "includes_zero": bool(lo <= 0 <= hi)}


def extraction(per_item: dict, a: str, b: str, B: int, rng) -> dict:
    rows_a, rows_b = per_item[a], per_item[b]
    ids = [r["item_id"] for r in rows_a]
    assert ids == [r["item_id"] for r in rows_b], "candidates saw different items"
    counts = {}
    for name, match in (("strict", mt.strict_match), ("meaning", mt.meaning_match)):
        for key, rows in ((a, rows_a), (b, rows_b)):
            arr = []
            for r in rows:
                gold = list(r["gold"])
                pred = [c["text"] for c in (r["output"] or [])]
                arr.append((len(match(gold, pred)), len(gold), len(pred)))
            counts[(name, key)] = np.array(arr, dtype=float)
    n = len(ids)
    idx = rng.integers(0, n, size=(B, n))
    out = {"n_items": n, "unit": "video", "metrics": {}}
    for name in ("strict", "meaning"):
        ca, cb = counts[(name, a)], counts[(name, b)]
        pa, ra, fa = _f1(*ca.sum(0))
        pb, rb, fb = _f1(*cb.sum(0))
        sa, sb = ca[idx].sum(1), cb[idx].sum(1)  # (B, 3)
        bpa, bra, bfa = _f1(sa[:, 0], sa[:, 1], sa[:, 2])
        bpb, brb, bfb = _f1(sb[:, 0], sb[:, 1], sb[:, 2])
        for met, va, vb, da, db in (("precision", pa, pb, bpa, bpb), ("recall", ra, rb, bra, brb),
                                    ("f1", fa, fb, bfa, bfb)):
            out["metrics"][f"{name}_{met}"] = {
                a: float(va), b: float(vb), "diff_b_minus_a": float(vb - va), "ci95": _ci(db - da)}
        out["metrics"][f"{name}_counts"] = {a: ca.sum(0).astype(int).tolist(), b: cb.sum(0).astype(int).tolist(),
                                            "fields": ["matched", "n_gold", "n_pred"]}
    return out


def _stance_scores(gold, pred):
    labels = list(STANCE_LABELS)
    prf = m.per_class_prf(gold, pred, labels)
    res = {"macro_f1": m.macro_f1(gold, pred, labels)}
    for lab in labels:
        res[f"recall_{lab}"] = prf[lab]["recall"]
    return res


def stance(per_item: dict, a: str, b: str, B: int, rng) -> dict:
    rows_a, rows_b = per_item[a], per_item[b]
    ids = [r["item_id"] for r in rows_a]
    assert ids == [r["item_id"] for r in rows_b], "candidates saw different items"
    gold = np.array([r["gold"] for r in rows_a])
    pa = np.array([str(r["output"]).upper() if r["output"] is not None else "__none__" for r in rows_a])
    pb = np.array([str(r["output"]).upper() if r["output"] is not None else "__none__" for r in rows_b])
    point_a, point_b = _stance_scores(list(gold), list(pa)), _stance_scores(list(gold), list(pb))
    n = len(ids)
    idx = rng.integers(0, n, size=(B, n))
    labels = list(STANCE_LABELS)
    # Vectorised per-label tp/fp/fn on each resample.
    boot = {k: [] for k in point_a}
    def per_resample(pred):
        f1s, recs = [], {}
        g = gold[idx]
        p = pred[idx]
        present = []
        for lab in labels:
            tp = ((g == lab) & (p == lab)).sum(1).astype(float)
            fp = ((g != lab) & (p == lab)).sum(1).astype(float)
            fn = ((g == lab) & (p != lab)).sum(1).astype(float)
            sup = tp + fn
            prec = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), np.nan)
            rec = np.where(sup > 0, tp / np.maximum(sup, 1), np.nan)
            # metrics.per_class_prf: f1 None when precision or recall undefined; macro counts it 0.
            f1 = np.where(np.isnan(prec) | np.isnan(rec), 0.0,
                          np.where(prec + rec > 0, 2 * prec * rec / np.where(prec + rec > 0, prec + rec, 1), 0.0))
            f1s.append(np.where(sup > 0, f1, np.nan))
            recs[lab] = rec
        f1s = np.vstack(f1s)
        macro = np.nanmean(f1s, axis=0)
        return macro, recs
    ma, ra = per_resample(pa)
    mb, rb = per_resample(pb)
    out = {"n_items": n, "unit": "claim", "gold_support": {lab: int((gold == lab).sum()) for lab in labels},
           "failed_items": {a: int((pa == "__none__").sum()), b: int((pb == "__none__").sum())},
           "metrics": {}}
    out["metrics"]["macro_f1"] = {a: point_a["macro_f1"], b: point_b["macro_f1"],
                                  "diff_b_minus_a": point_b["macro_f1"] - point_a["macro_f1"],
                                  "ci95": _ci(mb - ma)}
    for lab in labels:
        k = f"recall_{lab}"
        va, vb = point_a[k], point_b[k]
        out["metrics"][k] = {a: va, b: vb,
                             "diff_b_minus_a": None if va is None or vb is None else vb - va,
                             "ci95": _ci(rb[lab] - ra[lab])}
    # Confusion matrices (gold -> pred) for the report.
    for key, pred in ((a, pa), (b, pb)):
        cm = {}
        for g, p in zip(gold, pred):
            cm.setdefault(g, {}).setdefault(p, 0)
            cm[g][p] += 1
        out.setdefault("confusion", {})[key] = cm
    # Discordant pairs (one right, the other wrong).
    ok_a, ok_b = pa == gold, pb == gold
    out["discordant"] = {f"only_{a}_correct": int((ok_a & ~ok_b).sum()),
                         f"only_{b}_correct": int((~ok_a & ok_b).sum())}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--B", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=61)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    results = {"B": args.B, "seed": args.seed, "method": "paired percentile bootstrap", "comparisons": {}}
    for f in args.files:
        doc = json.loads(Path(f).read_text())
        for step, cands in doc["steps"].items():
            keys = sorted(cands)  # v2 < v3, v1 < v2: a = current prompt, b = T45 candidate
            if len(keys) != 2:
                print(f"{f}: {step}: expected 2 complete candidates, got {keys}; skipped", file=sys.stderr)
                continue
            a, b = keys
            rng = np.random.default_rng(args.seed)
            fn = extraction if step == "extract_claims" else stance
            name = f"{Path(f).parent.name}:{step}"
            results["comparisons"][name] = {"a": a, "b": b, "golden": doc.get("golden"),
                                            "pipeline_options": doc.get("pipeline_options"),
                                            **fn(cands, a, b, args.B, rng)}
    text = json.dumps(results, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
