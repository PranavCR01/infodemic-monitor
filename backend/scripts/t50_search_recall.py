"""T50: search recall on the golden **tune** split, before vs after the planning rewrite.

Two stages, so "before" and "after" are scored with one yardstick:

1. ``record``: for every tune claim, run the planner's queries against live PubMed (the
   same ``EvidenceRetriever`` the pipeline uses; NCBI E-utilities, <= 2.5 requests a
   second, no key) for up to the full budget of 3 rounds, and save what each round
   returned plus what the reranker kept. No model is called: the planner runs rules-only
   (no search assistant, no translator, no find-the-study step).
2. ``score``: a claim counts as *found* when at least one retrieved record is on topic
   for the claim's intervention, using the T49 deterministic check
   (``app.core.graph.unproven_guard.on_topic``) from the code being scored. Also: how
   many claims retrieve a PMID the golden set cites. Non-English claims are reported
   separately (``app.core.retrieval.language.detect_language``).

Test split never read: ``TuneSet`` drops every non-tune row before anything else sees it.

Run from backend/:

    python scripts/t50_search_recall.py record --out ../evals/reports/T50/before.json   # on the old code
    python scripts/t50_search_recall.py record --out ../evals/reports/T50/after.json
    python scripts/t50_search_recall.py score ../evals/reports/T50/before.json ../evals/reports/T50/after.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.retrieval.pubmed import PubMedClient  # noqa: E402
from app.core.retrieval.rerank import Reranker  # noqa: E402
from app.core.retrieval.retriever import EvidenceRetriever, merge_evidence  # noqa: E402
from app.core.retrieval.schemas import EvidenceRecord  # noqa: E402
from app.evaluation.routing_experiment.golden import DirSource, TuneSet  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "research" / "claim-level" / "dataset"
ROUNDS = 3


class FileCache:
    """A JSON-file query cache, so the after-run doesn't re-fetch what the before-run
    already fetched (same keys as the pipeline's cache)."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=0):  # noqa: ARG002
        self.data[key] = value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data))


def _video_context(video) -> list[str]:
    return [c.text for c in video.claims]


def record(out: Path, cache_path: Path, limit: int | None = None) -> None:
    from app.core.retrieval.planning import QueryPlanner

    tune = TuneSet(DirSource(DATASET))
    cache = FileCache(cache_path)
    retriever = EvidenceRetriever(PubMedClient(), cache)
    planner = QueryPlanner()  # rules only: no model
    reranker = Reranker()
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    claims_out = {}
    n = 0
    t0 = time.time()
    for vid in tune.video_ids:
        video = tune.videos[vid]
        context = _video_context(video)
        for row in video.claims:
            n += 1
            if limit and n > limit:
                break
            plan = None
            if hasattr(planner, "plan"):
                plan = planner.plan(row.text, claim_kind=row.kind, context=context)
            rounds, evidence = [], []
            already: list[str] = []
            for i in range(1, ROUNDS + 1):
                if plan is not None:
                    q = planner.next_query(row.text, already, plan=plan)
                else:
                    q = planner.next_query(row.text, already)
                    if q is None:  # old behaviour: repeat the broadest query
                        q = already[-1] if already else row.text
                if q is None:
                    rounds.append({"round": i, "stopped": "ladder_exhausted"})
                    break
                repeat = q in already
                already.append(q)
                try:
                    res = retriever.retrieve(q)
                except Exception as exc:  # noqa: BLE001
                    rounds.append({"round": i, "query": q, "error": type(exc).__name__})
                    continue
                evidence = merge_evidence(evidence, res.records)
                rounds.append({"round": i, "query": q, "repeat": repeat, "hits": res.pmids_found,
                               "ids": [r.evidence_id for r in res.records]})
            kept = reranker.rerank(row.text, evidence, row.kind).kept if evidence else []
            claims_out[row.key] = {
                "text": row.text, "kind": row.kind,
                "golden_cited": [p for p in (*row.supporting, *row.contradicting)],
                "plan": plan.describe() if plan is not None else None,
                "rounds": rounds,
                "records": {r.evidence_id: {"title": r.title, "abstract": r.abstract[:3000], "pmid": r.pmid,
                                            "year": r.publication_year} for r in evidence},
                "kept": [r.evidence_id for r in kept],
            }
            if n % 10 == 0:
                cache.save()
                print(f"{n} claims, {time.time() - t0:.0f}s", file=sys.stderr)
    cache.save()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_revision": rev, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "split": "tune", "rounds": ROUNDS, "claims": claims_out}, ensure_ascii=False))


def _found(claim: dict, ids: list[str], yardstick: str = "intervention") -> tuple[bool, bool]:
    """(on topic, golden PMID among ``ids``). ``yardstick``: ``intervention`` is the T49
    check alone; ``claim`` uses it when the claim has a recognised intervention and
    otherwise the claim's own concepts (``find_study.topic_match``), the same rule that
    decides when find-the-study fires: the T49 fallback requires every leftover word
    ("also", "loves", "acid"), so no paper is ever on topic for such claims."""
    from app.core.graph.state import GraphClaim
    from app.core.graph.unproven_guard import intervention_terms, on_topic_ids
    from app.core.retrieval.find_study import topic_match

    gc = GraphClaim(claim_id="c", claim_text=claim["text"], claim_category="other",
                    source_segment_ids=["s"], start_seconds=0, end_seconds=1)
    recs = [EvidenceRecord(evidence_id=i, source="pubmed", title=claim["records"][i]["title"],
                           abstract=claim["records"][i]["abstract"]) for i in ids if i in claim["records"]]
    if yardstick == "claim" and intervention_terms(claim["text"]).source != "concept":
        on_topic = any(topic_match(claim["text"], r.title, r.abstract) for r in recs)
    else:
        on_topic = bool(on_topic_ids(gc, recs))
    golden = {p.replace("PMID:", "") for p in claim["golden_cited"] if p.startswith("PMID:")}
    pmids = {claim["records"][i]["pmid"] for i in ids if i in claim["records"]}
    return on_topic, bool(golden & pmids)


def score_file(path: Path) -> dict:
    from app.core.retrieval.language import detect_language

    data = json.loads(path.read_text())
    rows = {}
    for key, c in data["claims"].items():
        retrieved = list(c["records"])
        r1 = [i for rnd in c["rounds"][:1] for i in rnd.get("ids", [])]
        on_any, gold_any = _found(c, retrieved)
        on_r1, _ = _found(c, r1)
        on_kept, gold_kept = _found(c, c["kept"])
        on_kept_claim, _ = _found(c, c["kept"], "claim")
        lang = detect_language(c["text"])
        has_gold = any(p.startswith("PMID:") for p in c["golden_cited"])
        rows[key] = {"on_topic": on_any, "on_topic_round1": on_r1, "on_topic_kept": on_kept,
                     "golden_hit": gold_any, "has_golden_pmid": has_gold, "lang": lang,
                     # D8 (lead, 2026-11-26): strict = a golden-cited PMID kept by the
                     # reranker; lenient = strict or an on-topic kept record.
                     "strict": gold_kept, "lenient": gold_kept or on_kept,
                     "lenient_claim": gold_kept or on_kept_claim,
                     "retrieved": len(retrieved), "kept": len(c["kept"]),
                     "queries": [r.get("query") for r in c["rounds"] if r.get("query")],
                     "repeats": sum(1 for r in c["rounds"] if r.get("repeat")),
                     "stopped": any(r.get("stopped") for r in c["rounds"])}
    return {"code_revision": data.get("code_revision"), "rows": rows}


def _summary(rows: dict, keys: list[str]) -> dict:
    n = len(keys)
    pick = lambda f: sum(1 for k in keys if rows[k][f])  # noqa: E731
    gold_keys = [k for k in keys if rows[k]["has_golden_pmid"]]
    return {"claims": n, "strict": sum(1 for k in gold_keys if rows[k].get("strict")),
            "lenient": pick("lenient") if all("lenient" in rows[k] for k in keys) else 0,
            "lenient_claim": pick("lenient_claim") if all("lenient_claim" in rows[k] for k in keys) else 0,
            "on_topic": pick("on_topic"), "on_topic_round1": pick("on_topic_round1"),
            "on_topic_kept": pick("on_topic_kept"), "empty": sum(1 for k in keys if rows[k]["retrieved"] == 0),
            "repeat_rounds": sum(rows[k]["repeats"] for k in keys),
            "golden_claims": len(gold_keys), "golden_hit": sum(1 for k in gold_keys if rows[k]["golden_hit"])}


def score(before: Path, after: Path, out: Path | None) -> str:
    b, a = score_file(before), score_file(after)
    keys = sorted(set(b["rows"]) & set(a["rows"]))
    non_en = [k for k in keys if a["rows"][k]["lang"] not in ("en", "und")]
    en = [k for k in keys if k not in non_en]
    pct = lambda x, n: f"{x}/{n} ({100 * x / n:.1f}%)" if n else "0/0"  # noqa: E731
    lines = ["# T50: search recall on the tune split (rules only, no model)", "",
             f"Before: code {str(b['code_revision'])[:12]}; after: code {str(a['code_revision'])[:12]}. "
             f"Live PubMed, up to {ROUNDS} rounds per claim. On topic = the T49 deterministic check "
             "(`unproven_guard.on_topic`, from the after code, for both runs).", "",
             "## D8 search quality bar (lead, 2026-11-26)", "",
             "Strict: a golden-cited PMID is among the records the reranker kept (claims with a golden PMID). "
             "Lenient: strict, or at least one kept record is on topic. Target: lenient >= 80%. Two on-topic "
             "yardsticks: *intervention* = the T49 check only (for a claim with no recognised intervention it "
             "needs every leftover word, e.g. 'also loves acid', so it under-counts); *claim* = the T49 check "
             "when the claim has a recognised intervention, else one of the claim's concepts in the record "
             "(the rule that triggers find-the-study).", "",
             "| set | claims | lenient (intervention) before → after | lenient (claim) before → after | "
             "strict before → after |", "| --- | --- | --- | --- | --- |"]
    for name, ks in (("all tune claims", keys), ("English", en), ("non-English", non_en)):
        sb, sa = _summary(b["rows"], ks), _summary(a["rows"], ks)
        n = sb["claims"]
        lines.append(f"| {name} | {n} | {pct(sb['lenient'], n)} → {pct(sa['lenient'], n)} | "
                     f"{pct(sb['lenient_claim'], n)} → {pct(sa['lenient_claim'], n)} | "
                     f"{pct(sb['strict'], sb['golden_claims'])} → {pct(sa['strict'], sa['golden_claims'])} |")
    sa_all = _summary(a["rows"], keys)
    best = max(sa_all["lenient"], sa_all["lenient_claim"])
    lines += ["", f"Target lenient >= 80%: **{'met' if best >= 0.8 * len(keys) else 'not met'}** rules-only "
              f"(intervention {pct(sa_all['lenient'], len(keys))}, claim {pct(sa_all['lenient_claim'], len(keys))}); "
              "the model helpers (assistant, translation, find-the-study) are not in these numbers.", "",
             "## Retrieval detail", "",
             "| set | claims | on topic (any round) before → after | round 1 only | kept by reranker | "
             "empty searches | repeated rounds | golden PMID retrieved |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, ks in (("all tune claims", keys), ("English", en), ("non-English", non_en)):
        sb, sa = _summary(b["rows"], ks), _summary(a["rows"], ks)
        n = sb["claims"]
        lines.append(
            f"| {name} | {n} | {pct(sb['on_topic'], n)} → {pct(sa['on_topic'], n)} | "
            f"{pct(sb['on_topic_round1'], n)} → {pct(sa['on_topic_round1'], n)} | "
            f"{pct(sb['on_topic_kept'], n)} → {pct(sa['on_topic_kept'], n)} | {sb['empty']} → {sa['empty']} | "
            f"{sb['repeat_rounds']} → {sa['repeat_rounds']} | "
            f"{pct(sb['golden_hit'], sb['golden_claims'])} → {pct(sa['golden_hit'], sa['golden_claims'])} |")
    gained = [k for k in keys if a["rows"][k]["on_topic"] and not b["rows"][k]["on_topic"]]
    lost = [k for k in keys if b["rows"][k]["on_topic"] and not a["rows"][k]["on_topic"]]
    lines += ["", f"Gained on topic: {len(gained)}; lost: {len(lost)}.", ""]
    if lost:
        lines += ["## Lost", ""] + [f"- {k}: before {b['rows'][k]['queries'][:1]} → after {a['rows'][k]['queries'][:2]}"
                                     for k in lost] + [""]
    lines += ["## Non-English claims", ""]
    for k in non_en:
        lines.append(f"- {k} ({a['rows'][k]['lang']}): {b['rows'][k]['on_topic']} → {a['rows'][k]['on_topic']}; "
                     f"after queries {a['rows'][k]['queries'][:2]}")
    text = "\n".join(lines) + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        (out.parent / "recall_rows.json").write_text(json.dumps({"before": b, "after": a}, indent=1, ensure_ascii=False))
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--out", required=True)
    r.add_argument("--cache", default=str(REPO / "evals" / "reports" / "T50" / "pubmed_cache.json"))
    r.add_argument("--limit", type=int)
    s = sub.add_parser("score")
    s.add_argument("before")
    s.add_argument("after")
    s.add_argument("--out")
    args = ap.parse_args(argv)
    if args.cmd == "record":
        record(Path(args.out), Path(args.cache), args.limit)
    else:
        print(score(Path(args.before), Path(args.after), Path(args.out) if args.out else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
