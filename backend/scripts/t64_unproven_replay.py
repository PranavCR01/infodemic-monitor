"""T64: replay the unproven-label rules on the tune split (design §7, §9).

The T49 replay (``t49_unproven_guard_replay.py``) extended to every rule T64 adds and to
every **tune** video with at least one golden UNSUPPORTED claim (not only the 5 the golden
set labels MISINFO (unproven)), so every tune label change shows. For each such claim the
evidence the verifier would see is checked by the guard of the code under test; siblings
(rule b) are the video's other golden claims with their golden verdicts; then the
backend judge runs on the video's golden stances and verdicts. Rule (f)
(``main_claims_unchecked``) is reported for every tune video. No model calls.

Run it twice on the same evidence, once with each code version, and diff the JSON:

    # the code under test (this branch)
    python scripts/t64_unproven_replay.py --frozen <frozen_evidence_tune.json> \\
        --live <live.json> --out after.json
    # the code before T64 (a worktree of origin/langgraph-build)
    T64_BACKEND=<worktree>/backend python scripts/t64_unproven_replay.py ... --out before.json
    python scripts/t64_unproven_replay.py --diff before.json after.json --report report.md

Evidence sources (both tune-only):

- ``frozen``: the T38 frozen evidence (``origin/data/t38-frozen-evidence``), the records
  the pipeline's own retrieval kept, re-ranked by the code under test (so rule e shows);
- ``live``: a fresh rules-only recording (``--record live.json``: the planner's queries
  against live PubMed, full budget of 3 rounds, no model, every record with its
  publication type), re-ranked by the code under test. This is the T50 replay's source.

Categories: golden claims carry none. A golden UNSUPPORTED claim is
``treatment_efficacy`` unless the frozen recording's extracted category is ``prevention``
(T30: the labeller applied the efficacy rule); every other claim takes the frozen
recording's category when there is one, else ``unknown``.

Test split never read: ``TuneSet`` drops every non-tune row before anything else.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = os.environ.get("T64_BACKEND") or os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)

from app.core.graph import unproven_guard as ug  # noqa: E402
from app.core.graph.state import EvidenceRecord, GraphClaim, Verdict, VerificationResult  # noqa: E402
from app.core.retrieval.rerank import Reranker  # noqa: E402
from app.evaluation import judge_crosscheck as xc  # noqa: E402
from app.evaluation.routing_experiment.golden import DirSource, TuneSet  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "research" / "claim-level" / "dataset"
FROZEN_REF = "origin/data/t38-frozen-evidence:frozen_evidence_tune.json"
ROUNDS = 3
EFFICACY = ("treatment_efficacy", "prevention")


def code_revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=BACKEND, capture_output=True, text=True).stdout.strip()


def has_t64() -> bool:
    return hasattr(ug, "apply_sibling_rule")


# ------------------------------------------------------------------ live recording


def record(tune: TuneSet, out: Path, keys: set[str]) -> None:
    """Rules-only live PubMed recording for the given claim keys (publication types kept)."""
    from app.core.retrieval.planning import QueryPlanner
    from app.core.retrieval.pubmed import PubMedClient
    from app.core.retrieval.retriever import EvidenceRetriever, merge_evidence

    retriever = EvidenceRetriever(PubMedClient(), None)
    planner = QueryPlanner()
    claims = {}
    t0 = time.time()
    for vid in tune.video_ids:
        video = tune.videos[vid]
        context = [c.text for c in video.claims]
        for row in video.claims:
            if row.key not in keys:
                continue
            plan = planner.plan(row.text, claim_kind=row.kind, context=context)
            rounds, evidence, already = [], [], []
            for i in range(1, ROUNDS + 1):
                q = planner.next_query(row.text, already, plan=plan)
                if q is None:
                    rounds.append({"round": i, "stopped": "ladder_exhausted"})
                    break
                already.append(q)
                try:
                    res = retriever.retrieve(q)
                except Exception as exc:  # noqa: BLE001
                    rounds.append({"round": i, "query": q, "error": type(exc).__name__})
                    continue
                evidence = merge_evidence(evidence, res.records)
                rounds.append({"round": i, "query": q, "hits": res.pmids_found})
            claims[row.key] = {"text": row.text, "kind": row.kind, "rounds": rounds,
                               "records": [e.model_dump(exclude_none=True) for e in evidence]}
            print(f"{row.key}: {len(evidence)} records, {time.time() - t0:.0f}s", file=sys.stderr)
    out.write_text(json.dumps({"split": "tune", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "code_revision": code_revision(), "rounds": ROUNDS, "claims": claims},
                              ensure_ascii=False))


# ------------------------------------------------------------------ evidence


def load_frozen(path: str | None) -> dict:
    if path:
        return json.loads(Path(path).read_text())
    out = subprocess.run(["git", "show", FROZEN_REF], cwd=REPO, capture_output=True, check=True)
    return json.loads(out.stdout)


def frozen_evidence(frozen: dict, key: str) -> list[EvidenceRecord] | None:
    raw = frozen["claims"].get(key)
    if raw is None:
        return None
    return [EvidenceRecord.model_validate(r) for r in raw.get("retrieved") or []]


def live_evidence(live: dict, key: str) -> list[EvidenceRecord] | None:
    raw = live["claims"].get(key)
    if raw is None:
        return None
    return [EvidenceRecord.model_validate(r) for r in raw.get("records") or []]


# ------------------------------------------------------------------ replay


def category(frozen: dict, row) -> str:
    cat = ((frozen["claims"].get(row.key) or {}).get("claim_category") or "").strip()
    if row.verdict == "UNSUPPORTED":
        return cat if cat in EFFICACY else "treatment_efficacy"
    return cat or "unknown"


def replay(tune: TuneSet, frozen: dict, source: str, live: dict | None) -> dict:
    reranker = Reranker()
    videos = []
    for vid in tune.video_ids:
        video = tune.videos[vid]
        rows = list(video.claims)
        gclaims = [GraphClaim(claim_id=r.claim_id, claim_text=r.text, claim_category=category(frozen, r),
                              claim_kind=r.kind, source_segment_ids=["s"], start_seconds=r.start, end_seconds=r.end)
                   for r in rows]
        results = {r.claim_id: VerificationResult(
            claim_id=r.claim_id, verdict=Verdict(r.verdict),
            supporting_evidence_ids=list(r.supporting), contradicting_evidence_ids=list(r.contradicting))
            for r in rows}
        details = []
        for r, gc in zip(rows, gclaims):
            if r.verdict != "UNSUPPORTED":
                continue
            ev = frozen_evidence(frozen, r.key) if source == "frozen" else live_evidence(live or {"claims": {}}, r.key)
            recorded = ev is not None
            ev = reranker.rerank(r.text, ev, r.kind).kept if ev else []
            res = ug.apply_unproven_guard(gc, ev, results[r.claim_id])
            results[r.claim_id] = res
            details.append({"claim": r.key, "text": r.text, "recorded": recorded, "kept": len(ev),
                            "on_topic": len(ug.on_topic_ids(gc, ev)),
                            "kept_types": sorted({ug._study_type(e) for e in ev}) if hasattr(ug, "_study_type") else [],
                            "after_guard": res.verdict.value,
                            "limitation": (res.limitations or [""])[-1] if res.verdict != Verdict.UNSUPPORTED else ""})
        if has_t64():
            results = ug.apply_sibling_rule(gclaims, results)
            for d in details:
                cid = d["claim"].split(":")[1]
                if results[cid].verdict != Verdict(d["after_guard"]):
                    d["after_guard"] = results[cid].verdict.value
                    d["limitation"] = results[cid].limitations[-1]
        claims = tuple(xc.GoldenClaim(r.claim_id, r.stance, results[r.claim_id].verdict.value,
                                      tuple(results[r.claim_id].supporting_evidence_ids),
                                      tuple(results[r.claim_id].contradicting_evidence_ids), gc.claim_category)
                       for r, gc in zip(rows, gclaims))
        out = xc.run_backend(xc.GoldenVideo(video_id=vid, out_of_scope=False, recorded_label="",
                                            recorded_review_reasons=(), claims=claims))
        videos.append({"video_id": vid, "label": out.label, "basis": out.basis, "reasons": sorted(out.reasons),
                       "unsupported_claims": details,
                       "with_sibling_limitations": [r.claim_id for r in rows if r.claim_id in results
                                                    and ug.__dict__.get("SIBLING_LIMITATION", "-")
                                                    in results[r.claim_id].limitations]})
    return {"source": source, "code_revision": code_revision(), "t64": has_t64(), "videos": videos}


def tune_unproven_ids() -> list[str]:
    import csv
    import io

    rows = csv.DictReader(io.StringIO((DATASET / "videos.csv").read_text(encoding="utf-8")))
    return [r["video_id"] for r in rows if (r.get("split") or "").strip() == "tune"
            and (r.get("misinfo_basis") or "").strip() == "unproven"]


def render_diff(before: list[dict], after: list[dict], unproven: list[str]) -> str:
    lines = ["# T64 tune replay: label changes, before → after", "",
             f"Before: code {before[0]['code_revision'][:12]} (langgraph-build). After: code "
             f"{after[0]['code_revision'][:12]} (auto/T64). Golden set: in-repo `research/claim-level/dataset`, "
             "tune split only; golden stances and verdicts, with each golden UNSUPPORTED claim re-checked by the "
             "guard on the evidence the verifier would see. No model calls.", ""]
    for b, a in zip(before, after):
        bv = {v["video_id"]: v for v in b["videos"]}
        av = {v["video_id"]: v for v in a["videos"]}
        kept_b = [v for v in unproven if bv[v]["label"] == "MISINFO" and bv[v]["basis"] == "unproven"]
        kept_a = [v for v in unproven if av[v]["label"] == "MISINFO" and av[v]["basis"] == "unproven"]
        lines += [f"## Evidence `{a['source']}`", "",
                  f"Tune unproven videos keeping MISINFO (unproven): before {len(kept_b)}/{len(unproven)} "
                  f"({', '.join(kept_b) or 'none'}), after {len(kept_a)}/{len(unproven)} ({', '.join(kept_a) or 'none'}).",
                  ""]
        changed = [v for v in av if (bv[v]["label"], bv[v]["basis"]) != (av[v]["label"], av[v]["basis"])]
        lines += [f"Videos whose label changes: {len(changed)} of {len(av)} tune videos.", ""]
        if changed:
            lines += ["| video | before | after | why (golden UNSUPPORTED claims after the guard) |",
                      "| --- | --- | --- | --- |"]
            for v in changed:
                why = "; ".join(f"{d['claim'].split(':')[1]} → {d['after_guard']}"
                                + (f" `{d['limitation']}`" if d["limitation"] else "")
                                + f" ({d['kept']} kept, {d['on_topic']} on topic, types {d['kept_types']})"
                                for d in av[v]["unsupported_claims"])
                lab = lambda x: x["label"] + (f" ({x['basis']})" if x["basis"] else "")  # noqa: E731
                lines.append(f"| {v} | {lab(bv[v])} | {lab(av[v])} | {why} |")
            lines.append("")
        claim_changes = [(v, db, da) for v in av for db, da in zip(bv[v]["unsupported_claims"], av[v]["unsupported_claims"])
                         if db["after_guard"] != da["after_guard"]]
        lines += ["Every golden UNSUPPORTED claim whose verdict changes (label may not):", ""]
        lines += [f"- {da['claim']} \"{da['text'][:80]}\": {db['after_guard']} → {da['after_guard']} "
                  f"`{da['limitation']}` ({da['kept']} kept, {da['on_topic']} on topic, types {da['kept_types']})"
                  for v, db, da in claim_changes] or ["- none"]
        gained = [v for v in av if "main_claims_unchecked" in av[v]["reasons"]]
        lines += ["", f"`main_claims_unchecked` (f) raised on: {', '.join(gained) or 'none'} "
                  "(categories from the frozen recording; golden claims have none).", ""]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--frozen", help="frozen_evidence_tune.json (default: git show from the data branch)")
    ap.add_argument("--live", help="live rules-only recording (from --record)")
    ap.add_argument("--record", help="write a live recording here and exit")
    ap.add_argument("--out", help="results JSON")
    ap.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--report")
    args = ap.parse_args(argv)
    tune = TuneSet(DirSource(DATASET))
    if args.diff:
        before, after = (json.loads(Path(p).read_text()) for p in args.diff)
        text = render_diff(before, after, [v for v in tune.video_ids if v in tune_unproven_ids()])
        print(text)
        if args.report:
            Path(args.report).write_text(text)
        return 0
    frozen = load_frozen(args.frozen)
    if args.record:
        keys = {r.key for v in tune.video_ids for r in tune.videos[v].claims if r.verdict == "UNSUPPORTED"}
        record(tune, Path(args.record), keys)
        return 0
    live = json.loads(Path(args.live).read_text()) if args.live else None
    results = [replay(tune, frozen, "frozen", None)]
    if live:
        results.append(replay(tune, frozen, "live", live))
    text = json.dumps(results, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
