"""T67: offline replay of the two label-rule changes (design §8, §9, §11). No model calls.

Change 1 (``routing.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED``): when the §8 loop budget
runs out and the critic still objects, the judge keeps the verifier's stored verdict
(review reason ``second_check_disagreed:<cid>``) instead of INSUFFICIENT_EVIDENCE.
Change 2 (``judge.THIN_CONTRADICTION_RULE``): an ENDORSES / REFUTES + CONTRADICTED claim
decides only on >= 2 on-topic contradicting records or >= 1 systematic review / RCT /
guideline; otherwise it can't decide (review reason ``thin_contradiction:<cid>``).

Four configurations, each with the T64 guard as merged: (a) T64 only, (b) + change 1,
(c) + change 2, (d) + both. Two inputs:

A. ``--t66 <dir>``: the finished T66 videos' stored final states (``videos/<id>.json`` from
   ``origin/auto/T66``, PR #146, pipeline at 3372ef3, pre-T64 upstream). A video whose
   ``status`` is not ``finished`` (v21: cut off by the spend cap) is excluded. The replay
   re-applies only the T64 guard (``apply_unproven_guard`` on stored UNSUPPORTED verdicts
   with the claim's reranked records, then ``apply_sibling_rule``), the judge and the
   review rule; extraction, retrieval, verification, the critic and validation are not
   re-run (the stored ``validation_errors`` are kept).
B. The golden set's own claims for every in-scope **tune** video: golden stances and
   verdicts, each golden UNSUPPORTED claim re-checked by the guard on the T38 frozen
   evidence (as T64's replay did), and each cited evidence ID turned into a record from
   the golden set's offline evidence cache (``evidence_cache/search`` titles and
   publication types, ``evidence_cache/abstract`` text, ``reference_citations.csv``
   passages) so the thin-contradiction check sees real text and study types. There is no
   critic in the golden set, so change 1 cannot fire on B: (b) = (a) and (d) = (c) there.

Test split never read: only ``split == tune`` rows of ``videos.csv`` / ``claims.csv``.

    python scripts/t67_label_rules_replay.py --t66 <dir with v*.json> \\
        --frozen <frozen_evidence_tune.json> --out <results.json> --report <report.md>
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from pydantic import TypeAdapter  # noqa: E402

from app.core.graph import judge as jg  # noqa: E402
from app.core.graph import review_policy as rp  # noqa: E402
from app.core.graph import routing as rt  # noqa: E402
from app.core.graph import unproven_guard as ug  # noqa: E402
from app.core.graph.routing import DEFAULT_BUDGETS  # noqa: E402
from app.core.graph.state import (  # noqa: E402
    EvidenceRecord,
    GraphClaim,
    PipelineState,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.core.graph.verifier import MAX_EVIDENCE_PER_CLAIM  # noqa: E402

REPO = BACKEND.parent
DATASET = REPO / "research" / "claim-level" / "dataset"
FROZEN_REF = "origin/data/t38-frozen-evidence:frozen_evidence_tune.json"
LABELS = ("MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE")
CONFIGS = {"a": (False, False), "b": (True, False), "c": (False, True), "d": (True, True)}
CONFIG_NAMES = {"a": "T64 only", "b": "T64 + change 1", "c": "T64 + change 2", "d": "T64 + both"}
EFFICACY = ("treatment_efficacy", "prevention")
# "Further from MISINFO" (gate): MISINFO 0, CANNOT_RECOGNIZE 1 (undecided, goes to a
# person), NO_MISINFO / DEBUNKING 2 (the video is cleared).
MISINFO_DISTANCE = {"MISINFO": 0, "CANNOT_RECOGNIZE": 1, "NO_MISINFO": 2, "DEBUNKING": 2}
_STATE = TypeAdapter(PipelineState)


@contextmanager
def config(change1: bool, change2: bool):
    old = rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE
    rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE = change1, change2
    try:
        yield
    finally:
        rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE = old


def code_revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=BACKEND, capture_output=True, text=True).stdout.strip()


def tune_rows() -> tuple[dict[str, dict], list[dict]]:
    videos = [r for r in csv.DictReader(io.StringIO((DATASET / "videos.csv").read_text(encoding="utf-8")))
              if (r.get("split") or "").strip() == "tune"]
    ids = {r["video_id"] for r in videos}
    claims = [r for r in csv.DictReader(io.StringIO((DATASET / "claims.csv").read_text(encoding="utf-8")))
              if r.get("video_id") in ids]
    return {r["video_id"]: r for r in videos}, claims


def in_scope(row: dict) -> bool:
    return "out_of_scope" not in (row.get("case_tags") or "")


# ------------------------------------------------------------------ judge + review


def run_judge(state: PipelineState) -> dict:
    final, errors = jg.judge(state)
    state = dict(state)
    state["final_result"] = final
    state.setdefault("validation_errors", [])
    decision = rp.evaluate(state)
    return {"label": final.classification.value, "basis": final.misinfo_basis or "",
            "rule": final.decision_rule, "deciding": list(final.claim_ids),
            "review": decision.requires_review, "reasons": list(decision.reasons),
            "judge_errors": [e.message for e in errors]}


def apply_t64_guard(state: PipelineState) -> PipelineState:
    """The verify node's T64 post-processing (verifier.make_verify_claims) on stored verdicts."""
    claims = {c.claim_id: c for c in state.get("claims") or []}
    results = dict(state.get("verification_results") or {})
    reranked = state.get("reranked_evidence") or {}
    for cid, v in list(results.items()):
        if cid in claims and v.verdict == Verdict.UNSUPPORTED:
            ev = list(reranked.get(cid, []))[:MAX_EVIDENCE_PER_CLAIM]
            results[cid] = ug.apply_unproven_guard(claims[cid], ev, v)
    results = ug.apply_sibling_rule(list(claims.values()), results)
    out = dict(state)
    out["verification_results"] = results
    return out


# ------------------------------------------------------------------ A: T66 states


def replay_t66(directory: str, gold: dict[str, dict]) -> tuple[list[dict], list[str]]:
    rows, excluded = [], []
    for path in sorted(glob.glob(str(Path(directory) / "*.json"))):
        rec = json.loads(Path(path).read_text())
        if rec.get("status") != "finished":
            excluded.append(f"{rec.get('video_id')} (status {rec.get('status')!r})")
            continue
        state = apply_t64_guard(_STATE.validate_python(rec["state"]))
        out = {"video_id": rec["video_id"], "gold": gold[rec["video_id"]]["video_level_label"],
               "t66_stored": rec.get("label")}
        for key, flags in CONFIGS.items():
            with config(*flags):
                out[key] = run_judge(state)
                out[key]["second_check_kept"] = rt.second_check_disagreed_ids(state, DEFAULT_BUDGETS)
        rows.append(out)
    return rows, excluded


# ------------------------------------------------------------------ B: golden claims


def evidence_cache() -> dict[str, EvidenceRecord]:
    titles: dict[str, dict] = {}
    for f in glob.glob(str(DATASET / "evidence_cache" / "search" / "*.json")):
        for r in json.loads(Path(f).read_text()).get("records") or []:
            if r.get("pmid"):
                titles.setdefault(str(r["pmid"]), r)
    texts: dict[str, str] = {}
    for f in glob.glob(str(DATASET / "evidence_cache" / "abstract" / "*.json")):
        j = json.loads(Path(f).read_text())
        if j.get("pmid") and j.get("text"):
            texts[str(j["pmid"])] = j["text"]
    out: dict[str, EvidenceRecord] = {}
    for pmid in set(titles) | set(texts):
        t = titles.get(pmid) or {}
        types = t.get("pubtypes") or []
        if isinstance(types, str):
            types = [x.strip(" '\"") for x in types.strip("[]").split(",") if x.strip(" '\"")]
        out[f"PMID:{pmid}"] = EvidenceRecord(
            evidence_id=f"PMID:{pmid}", source="pubmed", pmid=pmid, title=t.get("title") or "",
            abstract=texts.get(pmid) or "", publication_type=list(types))
    for r in csv.DictReader(io.StringIO((DATASET / "reference_citations.csv").read_text(encoding="utf-8"))):
        out.setdefault(r["evidence_id"], EvidenceRecord(
            evidence_id=r["evidence_id"], source="reference", title=r.get("source_org") or "",
            abstract=r.get("quoted_passage") or "", source_url=r.get("url") or None))
    return out


def load_frozen(path: str | None) -> dict:
    if path:
        return json.loads(Path(path).read_text())
    return json.loads(subprocess.run(["git", "show", FROZEN_REF], cwd=REPO, capture_output=True, check=True).stdout)


def frozen_category(frozen: dict, key: str, verdict: str) -> str:
    """As T64's replay: UNSUPPORTED is efficacy unless the recording says prevention."""
    cat = ((frozen["claims"].get(key) or {}).get("claim_category") or "").strip()
    if verdict == "UNSUPPORTED":
        return cat if cat in EFFICACY else "treatment_efficacy"
    return cat or "unknown"


def golden_state(vid: str, rows: list[dict], frozen: dict, cache: dict[str, EvidenceRecord],
                 missing: list[str]) -> PipelineState:
    from app.core.retrieval.rerank import Reranker

    s = initial_state(job_id=f"t67-{vid}", video_id=vid, media_uri=f"golden://{vid}", pipeline_version="t67-replay")
    claims, stances, verdicts, evidence = [], {}, {}, {}
    reranker = Reranker()
    for i, r in enumerate(rows):
        cid, key = r["claim_id"], f"{vid}:{r['claim_id']}"
        verdict = r["claim_verdict"].strip().upper()
        gc = GraphClaim(claim_id=cid, claim_text=r["claim_text"].strip(),
                        claim_category=frozen_category(frozen, key, verdict),
                        claim_kind=(r.get("claim_kind") or "research_question").strip() or "research_question",
                        source_segment_ids=[], start_seconds=float(i), end_seconds=float(i) + 1)
        claims.append(gc)
        stances[cid] = StanceResult(claim_id=cid, stance=Stance(r["speaker_stance"].strip().upper()),
                                    stance_segment_ids=[])
        sup = [x.strip() for x in (r.get("evidence_supporting") or "").split(";") if x.strip()]
        con = [x.strip() for x in (r.get("evidence_contradicting") or "").split(";") if x.strip()]
        res = VerificationResult(claim_id=cid, verdict=Verdict(verdict),
                                 supporting_evidence_ids=sup, contradicting_evidence_ids=con)
        if res.verdict == Verdict.UNSUPPORTED:  # T64 guard on the frozen evidence (T64 replay)
            raw = (frozen["claims"].get(key) or {}).get("retrieved")
            ev = [EvidenceRecord.model_validate(x) for x in raw or []]
            ev = reranker.rerank(gc.claim_text, ev, gc.claim_kind).kept if ev else []
            res = ug.apply_unproven_guard(gc, ev, res)
        verdicts[cid] = res
        recs = []
        for eid in dict.fromkeys([*sup, *con]):
            if eid in cache:
                recs.append(cache[eid])
            else:
                missing.append(f"{key}:{eid}")
                recs.append(EvidenceRecord(evidence_id=eid, source="pubmed", title="", study_type="unknown"))
        if recs:
            evidence[cid] = recs
    verdicts = ug.apply_sibling_rule(claims, verdicts)
    attempts = {c.claim_id: DEFAULT_BUDGETS.max_retrieval_attempts for c in claims}
    s.update(claims=claims, stance_results=stances, verification_results=verdicts,
             retrieved_evidence=evidence, retrieval_attempts=attempts)
    return s


def replay_golden(gold: dict[str, dict], claims: list[dict], frozen: dict) -> tuple[list[dict], list[str]]:
    cache = evidence_cache()
    by_video: dict[str, list[dict]] = {}
    for r in claims:
        by_video.setdefault(r["video_id"], []).append(r)
    out, missing = [], []
    for vid in sorted((v for v in gold if in_scope(gold[v])), key=lambda x: (len(x), x)):
        state = golden_state(vid, by_video.get(vid, []), frozen, cache, missing)
        row = {"video_id": vid, "gold": gold[vid]["video_level_label"]}
        for key, flags in CONFIGS.items():
            with config(*flags):
                row[key] = run_judge(state)
        row["thin"] = [
            {"claim": cid, "stance": state["stance_results"][cid].stance.value,
             "contradicting": list(state["verification_results"][cid].contradicting_evidence_ids)}
            for cid in (f.rsplit(":", 1)[1] for f in row["c"]["reasons"] if f.startswith("judge:thin_contradiction:"))
        ]
        out.append(row)
    return out, missing


# ------------------------------------------------------------------ report


def matrix(rows: list[dict], key: str) -> tuple[list[list[int]], int]:
    m = [[0] * 4 for _ in LABELS]
    for r in rows:
        m[LABELS.index(r["gold"])][LABELS.index(r[key]["label"])] += 1
    return m, sum(m[i][i] for i in range(4))


def worse(gold: str, old: str, new: str) -> bool:
    if old == gold and new != gold:
        return True
    return gold == "MISINFO" and MISINFO_DISTANCE[new] > MISINFO_DISTANCE[old]


def lab(x: dict) -> str:
    return x["label"] + (f" ({x['basis']})" if x["basis"] else "")


def section(name: str, rows: list[dict]) -> tuple[list[str], dict]:
    lines, summary = [f"### {name}: {len(rows)} videos", ""], {}
    for key in CONFIGS:
        m, ok = matrix(rows, key)
        reviewed = sum(r[key]["review"] for r in rows)
        reasons = Counter(x.split(":")[0] if not x.startswith("judge:") else "judge:" + x.split(":")[1]
                          for r in rows for x in r[key]["reasons"])
        summary[key] = {"correct": ok, "n": len(rows), "accuracy": round(ok / len(rows), 4) if rows else None,
                        "reviewed": reviewed,
                        "second_check_disagreed": reasons.get("second_check_disagreed", 0),
                        "thin_contradiction": reasons.get("judge:thin_contradiction", 0),
                        "matrix": m}
        lines += [f"**({key}) {CONFIG_NAMES[key]}**: accuracy {ok}/{len(rows)} = {ok / len(rows):.3f}; "
                  f"sent to review {reviewed}/{len(rows)}; reasons added: "
                  f"`second_check_disagreed` ×{summary[key]['second_check_disagreed']}, "
                  f"`thin_contradiction` ×{summary[key]['thin_contradiction']}", "",
                  "| gold \\ ours | " + " | ".join(LABELS) + " | n |", "|---" * 6 + "|"]
        lines += [f"| **{g}** | " + " | ".join(f"**{c}**" if i == j else str(c) for j, c in enumerate(m[i]))
                  + f" | {sum(m[i])} |" for i, g in enumerate(LABELS)]
        lines.append("")
    for key in ("b", "c", "d"):
        changed = [r for r in rows if (r["a"]["label"], r["a"]["basis"]) != (r[key]["label"], r[key]["basis"])]
        bad = [r["video_id"] for r in changed if worse(r["gold"], r["a"]["label"], r[key]["label"])]
        summary[key]["changed"] = [r["video_id"] for r in changed]
        summary[key]["worse"] = bad
        lines += [f"Label changes ({key}) vs (a): {len(changed)}"
                  + (f"; **worse: {', '.join(bad)}**" if bad else "; none worse"), ""]
        if changed:
            lines += ["| video | gold | (a) | (" + key + ") | rule (" + key + ") | verdict |", "| --- | --- | --- | --- | --- | --- |"]
            for r in changed:
                verdict = ("worse" if worse(r["gold"], r["a"]["label"], r[key]["label"])
                           else "fixed" if r[key]["label"] == r["gold"] else "neutral")
                lines.append(f"| {r['video_id']} | {r['gold']} | {lab(r['a'])} | {lab(r[key])} | "
                             f"`{r[key]['rule']}` | {verdict} |")
            lines.append("")
    return lines, summary


def render(a_rows, excluded, b_rows, missing, rev) -> tuple[str, dict]:
    lines = ["# T67 replay: critic-budget and thin-contradiction label rules", "",
             f"Code {rev[:12]} (auto/T67). No model calls. Configurations: "
             + "; ".join(f"({k}) {v}" for k, v in CONFIG_NAMES.items()) + ".", ""]
    la, sa = section("A. T66 stored states", a_rows)
    lines += ["## A. T66 finished videos (stored states)", "",
              "Pipeline states from T66 (PR #146, `origin/auto/T66`), run at 3372ef3 (pre-T64 upstream). "
              "The replay re-applies only the T64 guard, the judge and the review rule; extraction, "
              "retrieval, verification, the critic and validation are not re-run.",
              f"Excluded: {', '.join(excluded) or 'none'} (not run, never scored).", ""] + la
    lb, sb = section("B. golden claims, in-scope tune", b_rows)
    lines += ["## B. Golden claims, all in-scope tune videos", "",
              "Golden stances and verdicts; the T64 guard re-checks golden UNSUPPORTED claims on the T38 "
              "frozen evidence. Cited records come from the golden set's offline evidence cache. No critic, "
              "so change 1 cannot fire here: (b) = (a), (d) = (c).",
              f"Cited evidence IDs not in the offline cache (treated as empty records): {len(missing)}"
              + (f" ({', '.join(missing)})" if missing else ""), ""] + lb
    thin = [(r["video_id"], t) for r in b_rows for t in r["thin"]]
    lines += ["Thin contradictions on golden claims (config c):", ""]
    lines += [f"- {v}:{t['claim']} ({t['stance']}), contradicting {', '.join(t['contradicting']) or 'none'}"
              for v, t in thin] or ["- none"]
    lines.append("")
    return "\n".join(lines) + "\n", {"A": sa, "B": sb}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--t66", required=True, help="directory with T66 videos/<id>.json")
    ap.add_argument("--frozen", help="frozen_evidence_tune.json (default: git show from the data branch)")
    ap.add_argument("--out")
    ap.add_argument("--report")
    args = ap.parse_args(argv)
    gold, claims = tune_rows()
    a_rows, excluded = replay_t66(args.t66, gold)
    b_rows, missing = replay_golden(gold, claims, load_frozen(args.frozen))
    rev = code_revision()
    text, summary = render(a_rows, excluded, b_rows, missing, rev)
    if args.report:
        Path(args.report).write_text(text)
    if args.out:
        Path(args.out).write_text(json.dumps({"code_revision": rev, "excluded": excluded, "missing_evidence": missing,
                                              "summary": summary, "A": a_rows, "B": b_rows},
                                             indent=1, ensure_ascii=False) + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
