"""T53: summarise the T50 paid runs (no network, no model call).

Reads the paid-run records written by ``t50_paid_runs.py run`` and prints Markdown
sections for ``evals/reports/T50/paid_run.md``: per-helper cost/latency, every helper
failure (Crossref-only DOI cases listed apart), the vitamin K c2-c5 result, and spend.

    python scripts/t53_paid_report.py --vitk ../evals/reports/T50/vitk_paid.json \
        --tune ../evals/reports/T50/tune_paid.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

JAMA_PMID = "42986716"
JAMA_DOI = "10.1001/jama.2026.21764"
CROSSREF_REASONS = ("DOI not in PubMed or Crossref",)


def _crossref_only(cand: dict) -> bool:
    """A DOI-only candidate that PubMed did not have and Crossref (blocked here) could not check."""
    return (not cand.get("pmid") and cand.get("doi")
            and ((cand["outcome"] == "not_found" and cand.get("reason") in CROSSREF_REASONS)
                 or (cand["outcome"] == "error" and cand.get("via") in (None, "crossref"))))


def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return 0
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def helper_table(data: dict) -> list[str]:
    steps: dict[str, list[dict]] = {}
    for c in data["calls"]:
        steps.setdefault(c["step"], []).append(c)
    lines = ["| helper | calls | errors | fallback used | cost USD (tokens) | mean cost/call | "
             "latency median ms | latency p90 ms | max ms |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for step in ("plan_search", "translate_claim", "find_study"):
        cs = steps.get(step, [])
        cost = sum(c.get("cost_usd") or 0 for c in cs)
        lat = [c["latency_ms"] for c in cs]
        lines.append(f"| {step} | {len(cs)} | {sum(1 for c in cs if c.get('error'))} | "
                     f"{sum(1 for c in cs if c.get('fallback_used'))} | {cost:.4f} | "
                     f"{(cost / len(cs)) if cs else 0:.5f} | {statistics.median(lat) if lat else 0:.0f} | "
                     f"{_pct(lat, 0.9)} | {max(lat) if lat else 0} |")
    searches = sum((c.get("find_study") or {}).get("web_searches", 0) for c in data["claims"].values())
    lines += ["", f"Web searches: {searches} (${searches * 0.01:.2f} in search fees, on top of the token cost "
              "above). Spend recorded by the run's cap: "
              f"**${data['spent_usd']:.4f}** of a ${data['cap_usd']:.2f} cap; stopped: {data['stopped']}."]
    return lines


def per_claim(data: dict) -> list[str]:
    lat = [c["latency_ms"] for c in data["claims"].values()]
    fs = [c["find_study"] for c in data["claims"].values() if c.get("find_study")]
    fs_cost = [f["cost_usd"] or 0 for f in fs]
    n = len(data["claims"])
    return [f"Claims: {n}. Claim latency (plan + 3 PubMed rounds + rerank + find-the-study): median "
            f"{statistics.median(lat):.0f} ms, p90 {_pct(lat, 0.9)} ms, max {max(lat)} ms. "
            f"Cost per claim: {data['spent_usd'] / n:.5f} USD on average; find-the-study claims "
            f"{len(fs)}, mean {statistics.mean(fs_cost) if fs_cost else 0:.4f} USD (tokens), "
            f"max {max(fs_cost) if fs_cost else 0:.4f} USD."]


def failures(data: dict, label: str) -> list[str]:
    out, xref = [], []
    for c in data["calls"]:
        if c.get("error") or c.get("fallback_used"):
            out.append(f"- {label} call `{c['step']}`: error={c.get('error')!r}, fallback={c.get('fallback_used')} "
                       f"({c.get('fallback_reason')}), attempts={c.get('attempts')}, {c['latency_ms']} ms")
    for key, c in data["claims"].items():
        p = c.get("plan") or {}
        if p.get("translation_error"):
            out.append(f"- {label} {key} translate_claim: {p['translation_error']}")
        if p.get("assistant_error"):
            out.append(f"- {label} {key} plan_search: {p['assistant_error']}")
        f = c.get("find_study")
        if not f:
            continue
        if f.get("error"):
            out.append(f"- {label} {key} find_study: {f['error']}")
        for cand in f["candidates"]:
            if cand["outcome"] in ("verified_pubmed", "verified_journal_doi", "duplicate"):
                continue
            line = (f"- {label} {key} candidate pmid={cand.get('pmid')} doi={cand.get('doi')}: "
                    f"{cand['outcome']} ({cand.get('reason')}; via {cand.get('via')})")
            (xref if _crossref_only(cand) else out).append(line)
        if not f["candidates"] and not f.get("error"):
            out.append(f"- {label} {key} find_study: no candidate proposed ({f['web_searches']} searches)")
    return out, xref


def vitk(data: dict) -> list[str]:
    lines = ["| claim | proposed? | verified? | kept? | result | failed at | candidates | cost USD | latency ms |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for cid in ("c2", "c3", "c4", "c5"):
        c = data["claims"].get(cid)
        if c is None:
            lines.append(f"| {cid} | - | - | - | not run | run stopped before it | | | |")
            continue
        f = c.get("find_study") or {"candidates": []}
        cands = f["candidates"]
        prop = any(x.get("pmid") == JAMA_PMID or (x.get("doi") or "").lower() == JAMA_DOI for x in cands)
        ver = [x for x in cands if x.get("pmid") == JAMA_PMID and x["outcome"].startswith("verified")]
        kept_pmids = {c["records"][i]["pmid"] for i in c["kept"] if i in c["records"]}
        kept = JAMA_PMID in kept_pmids
        where = "" if kept else ("proposal" if not prop else "verification" if not ver else "reranker")
        cs = "; ".join(f"{x.get('pmid') or '-'}/{x.get('doi') or '-'}: {x['outcome']}" for x in cands) or "none"
        lines.append(f"| {cid} | {'yes' if prop else 'no'} | {'yes' if ver else 'no'} | {'yes' if kept else 'no'} | "
                     f"**{'PASS' if kept else 'FAIL'}** | {where or '-'} | {cs} | {f.get('cost_usd') or 0:.4f} | "
                     f"{c['latency_ms']} |")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vitk")
    ap.add_argument("--tune")
    a = ap.parse_args()
    for label, p in (("vitamin K", a.vitk), ("tune", a.tune)):
        if not p:
            continue
        d = json.loads(Path(p).read_text())
        print(f"\n### {label}\n")
        print("\n".join(helper_table(d)))
        print()
        print("\n".join(per_claim(d)))
        if label == "vitamin K":
            print("\n" + "\n".join(vitk(d)))
        f, x = failures(d, label)
        print(f"\nFailures ({len(f)}):\n" + ("\n".join(f) or "none"))
        print(f"\nCrossref-only DOI candidates ({len(x)}):\n" + ("\n".join(x) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
