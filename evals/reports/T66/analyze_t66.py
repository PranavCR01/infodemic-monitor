"""T66 report numbers, computed only from saved outputs (videos/*.json, spend.json) and
the tune-only copy of the golden set. No model calls, no network.

    cd backend && python ../evals/reports/T66/analyze_t66.py --data <tune copy dir>

Writes ``analysis.json`` (every number in README.md) and ``wrong_cases.md`` (side-by-side
gold vs our claims for every wrong label, the material the hand attribution is based on).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "backend"))

from app.core.retrieval.find_study import topic_match  # noqa: E402
from app.core.retrieval.planning import frame_claim  # noqa: E402
from app.evaluation import metrics as M  # noqa: E402
from app.evaluation.dataset import load_dataset  # noqa: E402
from app.evaluation.error_analysis.bootstrap import bootstrap_ci, paired_margin_ci  # noqa: E402

LABELS = ["MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"]
B, SEED = 10_000, 66
# Gap (b): a claim about treating or preventing something (claim text, case-insensitive).
TREAT = re.compile(r"\b(cure[sd]?|curing|treat\w*|prevent\w*|heal\w*|reverse[sd]?|remed\w*|therap\w*|"
                   r"protect\w*|boost\w*|fight\w*|kill\w*|lower\w*|reduc\w*|improv\w*|relie\w*|"
                   r"work[s]? (for|against)|helps?|stops?|block\w*|detox\w*|clear\w*|fix\w*)\b", re.I)
JUDGED = {"SUPPORTED", "CONTRADICTED"}


def _concepts(cs) -> set[str]:
    return {(c.mesh or c.label or c.matched_text).lower() for c in cs}


def interventions(text: str) -> set[str]:
    return _concepts(frame_claim(text).intervention)


def outcomes(text: str) -> set[str]:
    return _concepts(frame_claim(text).outcome)


def gaps(claims: list[dict], label: str, rule: str | None, deciding: list[str], reviewed: bool) -> dict:
    """claims: [{id, text, stance, verdict, on_topic (int|None)}]. Returns which gaps fire."""
    by = {c["id"]: c for c in claims}
    with_v = [c for c in claims if c["verdict"]]
    out = {}
    sup = sum(c["verdict"] == "SUPPORTED" for c in with_v)
    out["a"] = bool(label == "MISINFO" and len(deciding) == 1 and with_v and sup / len(with_v) > 0.5)
    endorsed_ie_treat = [c["id"] for c in claims if c["stance"] == "ENDORSES" and c["verdict"] == "INSUFFICIENT_EVIDENCE"
                         and TREAT.search(c["text"] or "")]
    out["b"] = bool(label == "NO_MISINFO" and endorsed_ie_treat and not reviewed)
    out["b_claims"] = endorsed_ie_treat if out["b"] else []
    refuted_false = [c["id"] for c in claims if c["stance"] == "REFUTES" and c["verdict"] == "CONTRADICTED"]
    out["c"] = bool(label == "MISINFO" and refuted_false)
    out["c_claims"] = refuted_false if out["c"] else []
    pairs = []
    for i, x in enumerate(with_v):
        for y in with_v[i + 1:]:
            vs = {x["verdict"], y["verdict"]}
            if "SUPPORTED" in vs and vs & {"CONTRADICTED", "UNSUPPORTED"}:
                shared = interventions(x["text"]) & interventions(y["text"])
                ox, oy = outcomes(x["text"]), outcomes(y["text"])
                # Same intervention AND same outcome (or one names no outcome): a real conflict,
                # not "X lowers A" vs "X causes B".
                if shared and (not ox or not oy or ox & oy):
                    pairs.append([x["id"], y["id"], sorted(shared)[0]])
    out["d"] = bool(pairs)
    out["d_pairs"] = pairs
    thin = [c["id"] for c in claims if c["verdict"] == "UNSUPPORTED" and c["on_topic"] is not None and c["on_topic"] < 3]
    out["e"] = bool(thin)
    out["e_claims"] = thin
    out["e_deciding"] = [c for c in thin if c in deciding and rule in ("unproven", None)]
    return out


def gold_view(v) -> dict:
    claims = [{"id": c.claim_id, "text": c.claim_text, "stance": c.stance, "verdict": c.verdict,
               "on_topic": len(c.evidence)} for c in v.claims]
    label = v.label.value
    # Gold has no stored deciding claims: recompute them with the §9 order on gold claims.
    deciding, rule = gold_deciding(claims)
    return {"claims": claims, "label": label, "basis": v.misinfo_basis, "reviewed": bool(v.review_reasons),
            "review_reasons": v.review_reasons, "rule": rule, "deciding": deciding}


def gold_deciding(claims):
    ef = [c["id"] for c in claims if c["stance"] == "ENDORSES" and c["verdict"] == "CONTRADICTED"]
    dt = [c["id"] for c in claims if c["stance"] == "REFUTES" and c["verdict"] == "SUPPORTED"]
    un = [c["id"] for c in claims if c["stance"] == "ENDORSES" and c["verdict"] == "UNSUPPORTED"]
    rf = [c["id"] for c in claims if c["stance"] == "REFUTES" and c["verdict"] == "CONTRADICTED"]
    jd = [c["id"] for c in claims if c["verdict"] in JUDGED]
    for ids, rule in ((ef, "endorsed_contradicted"), (dt, "refuted_supported"), (un, "unproven"),
                      (rf, "refuted_contradicted"), (jd, "judged_nothing_false_endorsed")):
        if ids:
            return ids, rule
    return [], "nothing_judged/no_claims"


def our_view(rec: dict) -> dict:
    st = rec["state"]
    fr = st.get("final_result") or {}
    stances = st.get("stance_results") or {}
    verdicts = st.get("verification_results") or {}
    kept: dict[str, list] = {}
    for key in ("reranked_evidence", "found_study_evidence", "library_evidence"):
        for cid, recs in (st.get(key) or {}).items():
            for e in recs or []:
                if e["evidence_id"] not in {x["evidence_id"] for x in kept.get(cid, [])}:
                    kept.setdefault(cid, []).append(e)
    reasons = st.get("review_reasons") or []
    claims = []
    for c in st.get("claims") or []:
        cid = c["claim_id"]
        ev = kept.get(cid, [])
        vr = verdicts.get(cid) or {}
        raw = vr.get("verdict")
        cited = bool(vr.get("supporting_evidence_ids") or vr.get("contradicting_evidence_ids"))
        # What the judge saw (routing.verdicts_for_judge, §8): a claim whose critic still
        # objected when the budget ran out abstains as INSUFFICIENT_EVIDENCE, unless it
        # cited nothing and was already IE/UNSUPPORTED.
        abstained = f"budget_exhausted:{cid}" in reasons and raw is not None and not (
            raw in ("INSUFFICIENT_EVIDENCE", "UNSUPPORTED") and not cited)
        eff = "INSUFFICIENT_EVIDENCE" if abstained else raw
        on = sum(topic_match(c["claim_text"], e.get("title") or "", e.get("abstract") or "") for e in ev)
        claims.append({"id": cid, "text": c["claim_text"], "stance": (stances.get(cid) or {}).get("stance"),
                       "verdict": eff, "raw_verdict": raw, "abstained_budget": abstained,
                       "kept": len(ev), "on_topic": on,
                       "requires_verification": c.get("requires_verification"), "kind": c.get("claim_kind")})
    return {"claims": claims, "label": rec["label"], "basis": fr.get("misinfo_basis"), "rule": fr.get("decision_rule"),
            "deciding": fr.get("claim_ids") or [], "reviewed": bool(st.get("requires_human_review")),
            "review_reasons": st.get("review_reasons") or []}


def macro(g, p):
    return M.macro_f1(g, p, LABELS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    ds = load_dataset(a.data, with_inputs=False)
    assert all(v.split == "tune" for v in ds.videos)
    gold = {v.video_id: v for v in ds.videos}
    order = json.loads((HERE / "order.json").read_text())["order"]
    recs = {p.stem: json.loads(p.read_text()) for p in (HERE / "videos").glob("*.json")}
    status = {vid: recs[vid]["status"] if vid in recs else "not_run" for vid in order}
    finished = [v for v in order if status[v] == "finished"]
    fallback = [v for v in order if status[v] == "graph_fallback"]

    rows = []
    for vid in finished:
        g, o = gold_view(gold[vid]), our_view(recs[vid])
        rows.append({"video_id": vid, "gold": g, "ours": o})
    for r in rows:
        o = r["ours"]
        _, rule_eff = gold_deciding(o["claims"])
        o["rule_recomputed_effective"] = rule_eff
        raw_claims = [{**c, "verdict": c["raw_verdict"]} for c in o["claims"]]
        _, rule_raw = gold_deciding(raw_claims)
        o["label_if_no_budget_abstention"] = _rule_label(rule_raw)
        o["n_abstained_budget"] = sum(c["abstained_budget"] for c in o["claims"])
    gl = [r["gold"]["label"] for r in rows]
    pl = [r["ours"]["label"] for r in rows]
    n = len(rows)

    def acc_idx(idx):
        return M.accuracy([gl[i] for i in idx], [pl[i] for i in idx])

    def f1_idx(idx):
        return macro([gl[i] for i in idx], [pl[i] for i in idx])

    out: dict = {"n_declared": len(order), "status_counts": dict(Counter(status.values())),
                 "finished": finished, "graph_fallback": fallback,
                 "not_run": [v for v in order if status[v].startswith("not_run")]}
    out["confusion"] = M.confusion_matrix(gl, pl, LABELS)
    out["per_class"] = M.per_class_prf(gl, pl, LABELS)
    out["accuracy"] = bootstrap_ci(n, acc_idx, n=B, seed=SEED) if n else None
    out["macro_f1"] = bootstrap_ci(n, f1_idx, n=B, seed=SEED) if n else None
    # Sensitivity: graph fallbacks counted as wrong (CANNOT_RECOGNIZE with no answer).
    if fallback:
        gl2 = gl + [gold[v].label.value for v in fallback]
        pl2 = pl + ["FALLBACK"] * len(fallback)
        out["sensitivity_fallbacks_wrong"] = {"n": len(gl2), "accuracy": M.accuracy(gl2, pl2),
                                              "macro_f1": M.macro_f1(gl2, pl2, LABELS)}
    # MISINFO basis
    out["basis"] = [{"video_id": r["video_id"], "gold": r["gold"]["basis"], "ours": r["ours"]["basis"]}
                    for r in rows if r["gold"]["label"] == "MISINFO" or r["ours"]["label"] == "MISINFO"]
    out["basis_confusion"] = dict(Counter(f"{b['gold']}->{b['ours']}" for b in out["basis"]))
    both_m = [b for b in out["basis"] if b["gold"] and b["ours"]]
    out["basis_agree_when_both_misinfo"] = [sum(b["gold"] == b["ours"] for b in both_m), len(both_m)]
    # Review routing
    gr = [r["gold"]["reviewed"] for r in rows]
    orv = [r["ours"]["reviewed"] for r in rows]
    out["review"] = {"agree": sum(x == y for x, y in zip(gr, orv)), "n": n,
                     "kappa": M.cohens_kappa(gr, orv),
                     "gold_yes_ours_yes": sum(x and y for x, y in zip(gr, orv)),
                     "gold_yes_ours_no": sum(x and not y for x, y in zip(gr, orv)),
                     "gold_no_ours_yes": sum((not x) and y for x, y in zip(gr, orv)),
                     "gold_no_ours_no": sum((not x) and (not y) for x, y in zip(gr, orv))}
    if n:
        out["review"]["agreement_ci"] = bootstrap_ci(
            n, lambda idx: sum(gr[i] == orv[i] for i in idx) / len(idx), n=B, seed=SEED)
    # Wrong labels with review status (a wrong label sent to review is caught by a person)
    out["wrong"] = [{"video_id": r["video_id"], "gold": r["gold"]["label"], "gold_basis": r["gold"]["basis"],
                     "ours": r["ours"]["label"], "ours_basis": r["ours"]["basis"], "rule": r["ours"]["rule"],
                     "deciding": r["ours"]["deciding"], "sent_to_review": r["ours"]["reviewed"]}
                    for r in rows if r["gold"]["label"] != r["ours"]["label"]]
    out["budget_abstention"] = {
        "videos_with_any": sum(r["ours"]["n_abstained_budget"] > 0 for r in rows),
        "claims_abstained": sum(r["ours"]["n_abstained_budget"] for r in rows),
        "claims_total": sum(len(r["ours"]["claims"]) for r in rows),
        "recomputed_rule_matches_actual": [
            r["video_id"] for r in rows if _rule_label(r["ours"]["rule_recomputed_effective"]) == r["ours"]["label"]],
        "recomputed_rule_differs": [
            {"video_id": r["video_id"], "actual": r["ours"]["rule"], "recomputed": r["ours"]["rule_recomputed_effective"]}
            for r in rows if _rule_label(r["ours"]["rule_recomputed_effective"]) != r["ours"]["label"]],
        "counterfactual_raw_verdicts": [
            {"video_id": r["video_id"], "gold": r["gold"]["label"], "actual": r["ours"]["label"],
             "raw": r["ours"]["label_if_no_budget_abstention"]} for r in rows
            if r["ours"]["label_if_no_budget_abstention"] != r["ours"]["label"]],
        "counterfactual_accuracy": M.accuracy(gl, [r["ours"]["label_if_no_budget_abstention"] for r in rows]) if rows else None,
    }
    # Gold label vs §9 rules applied to gold claims (consistency of the golden set itself)
    out["gold_rule_label_mismatch_finished"] = [
        r["video_id"] for r in rows if _rule_label(r["gold"]["rule"]) != r["gold"]["label"]]

    # Policy gaps
    def gap_counts(views):
        c = Counter()
        detail = {}
        for vid, v in views:
            gp = gaps(v["claims"], v["label"], v["rule"], v["deciding"], v["reviewed"])
            for k in "abcde":
                if gp[k]:
                    c[k] += 1
                    detail.setdefault(k, []).append({"video_id": vid, **{x: gp[x] for x in gp if x.startswith(k + "_")}})
            c["e_claims_total"] += len(gp["e_claims"])
            c["e_deciding_total"] += len(gp["e_deciding"])
            c["d_pairs_total"] += len(gp["d_pairs"])
        return dict(c), detail

    gc_f, gd_f = gap_counts([(r["video_id"], r["gold"]) for r in rows])
    oc_f, od_f = gap_counts([(r["video_id"], r["ours"]) for r in rows])
    gc_all, gd_all = gap_counts([(vid, gold_view(gold[vid])) for vid in order])

    def raw_view(o):
        cl = [{**c, "verdict": c["raw_verdict"]} for c in o["claims"]]
        dec, rule = gold_deciding(cl)
        return {**o, "claims": cl, "label": _rule_label(rule), "rule": rule, "deciding": dec}
    rc_f, rd_f = gap_counts([(r["video_id"], raw_view(r["ours"])) for r in rows])
    out["gaps"] = {"gold_on_finished": gc_f, "ours_on_finished": oc_f, "gold_on_all_48": gc_all,
                   "ours_raw_verdicts_on_finished": rc_f, "detail_ours_raw_finished": rd_f,
                   "detail_gold_finished": gd_f, "detail_ours_finished": od_f, "detail_gold_all": gd_all}

    # Cost & latency (every video that ran, finished or fallback; not-run excluded)
    ran = finished + fallback
    costs = [recs[v]["cost_usd"] for v in ran]
    lats = [recs[v]["latency_ms"] / 1000 for v in ran]
    calls = [len(recs[v]["model_calls"]) for v in ran]
    nclaims = [len(recs[v]["state"].get("claims") or []) for v in ran]
    out["cost"] = {"n": len(ran), "median": statistics.median(costs) if costs else None,
                   "p90": M.percentile(costs, 90) if costs else None, "total_ran": sum(costs),
                   "max": max(costs) if costs else None}
    out["latency_s"] = {"median": statistics.median(lats) if lats else None,
                        "p90": M.percentile(lats, 90) if lats else None, "total": sum(lats),
                        "max": max(lats) if lats else None}
    out["calls_per_video_median"] = statistics.median(calls) if calls else None
    out["claims_per_video"] = {"ours_median": statistics.median(nclaims) if nclaims else None,
                               "ours_total": sum(nclaims),
                               "gold_total_same_videos": sum(len(gold[v].claims) for v in ran)}
    step_cost = Counter()
    for v in ran:
        for m in recs[v]["model_calls"]:
            step_cost[m["step"]] += m.get("cost_usd") or 0.0
    out["cost_by_step_model_calls"] = {k: round(x, 4) for k, x in step_cost.items()}
    out["spend"] = json.loads((HERE / "spend.json").read_text())
    out["per_video"] = {v: {"status": status[v], "gold": gold[v].label.value,
                            "ours": recs[v]["label"] if v in recs else None,
                            "cost_usd": recs[v]["cost_usd"] if v in recs else None,
                            "latency_s": round(recs[v]["latency_ms"] / 1000, 1) if v in recs else None,
                            "n_claims_ours": len(recs[v]["state"].get("claims") or []) if v in recs else None,
                            "n_claims_gold": len(gold[v].claims)} for v in order}
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1, default=str))
    write_wrong_cases(rows)
    print(json.dumps({k: out[k] for k in ("status_counts", "accuracy", "macro_f1", "review", "cost", "latency_s")},
                     indent=1, default=str))
    return 0


def _rule_label(rule):
    return {"endorsed_contradicted": "MISINFO", "refuted_supported": "MISINFO", "unproven": "MISINFO",
            "refuted_contradicted": "DEBUNKING", "judged_nothing_false_endorsed": "NO_MISINFO"}.get(rule, "CANNOT_RECOGNIZE")


def write_wrong_cases(rows) -> None:
    lines = ["# T66 wrong labels: gold vs ours, side by side (generated by analyze_t66.py)", ""]
    for r in rows:
        g, o = r["gold"], r["ours"]
        if g["label"] == o["label"]:
            continue
        lines += [f"## {r['video_id']}: gold {g['label']} ({g['basis']}) vs ours {o['label']} ({o['basis']})",
                  f"- ours: rule `{o['rule']}`, deciding {o['deciding']}, review {o['reviewed']} {o['review_reasons']}",
                  f"- gold: §9 on gold claims -> `{g['rule']}` deciding {g['deciding']}; review reasons {g['review_reasons']}",
                  "", "Gold claims:"]
        for c in g["claims"]:
            lines.append(f"- {c['id']} [{c['stance']}/{c['verdict']}, {c['on_topic']} cited] {c['text']}")
        lines.append("")
        lines.append("Our claims:")
        for c in o["claims"]:
            ab = f" (raw {c['raw_verdict']}, abstained: critic budget)" if c["abstained_budget"] else ""
            lines.append(f"- {c['id']} [{c['stance']}/{c['verdict']}{ab}, kept {c['kept']}, on-topic {c['on_topic']}] {c['text']}")
        matches = M.match_claims([c["text"] for c in g["claims"]], [c["text"] for c in o["claims"]], threshold=0.3)
        lines.append("")
        lines.append("Token-overlap matches (>=0.3): " + ", ".join(
            f"{g['claims'][gi]['id']}~{o['claims'][pi]['id']} ({s:.2f})" for gi, pi, s in matches))
        lines.append("")
    (HERE / "wrong_cases.md").write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
