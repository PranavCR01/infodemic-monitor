"""T50: the vitamin K job (5cc07f48) as a search regression, before vs after.

For each of the job's 13 claims (the T49 fixture, ``app/tests/fixtures/prod_5cc07f48``;
its claim texts are RECONSTRUCTED, see its ``_provenance``), run the planner's queries
against live PubMed for the full budget (3 rounds), rerank, and report whether a
vitamin K / VKDB paper was retrieved and kept. Expected after T50 (BUILD_QUEUE row):
c1-c7, c9 and c12 find vitamin K / VKDB papers.

"before" is the production query trail recorded in the fixture (every query searched
'vitamin'); "after" is the rewritten planner, rules only (no model: the search
assistant, translator and find-the-study step are not used). Run from backend/:

    python scripts/t50_vitamin_k_regression.py --out ../evals/reports/T50/vitamin_k.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.retrieval.planning import QueryPlanner  # noqa: E402
from app.core.retrieval.pubmed import PubMedClient  # noqa: E402
from app.core.retrieval.rerank import Reranker  # noqa: E402
from app.core.retrieval.retriever import EvidenceRetriever, merge_evidence  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "app" / "tests" / "fixtures" / "prod_5cc07f48" / "vitamin_k_job.json"
EXPECTED = {"c1", "c2", "c3", "c4", "c5", "c6", "c7", "c9", "c12"}
_VITK = re.compile(r"vitamin[\s-]*k(?![a-z])|phytonadione|phylloquinone|vkdb", re.I)


def is_vitamin_k(rec) -> bool:
    return bool(_VITK.search(f"{rec.title} {rec.abstract}"))


def record_fixture(out_dir: Path, top: int = 5) -> None:
    """Record the live E-utilities answers for every query the rewritten planner runs on
    the job's 13 claims into the ``RecordedPubMed`` layout, trimmed (top ``top`` PMIDs per
    search, ``<ReferenceList>`` removed), for the CI regression set (D8)."""
    import re as _re

    import httpx

    from app.core.retrieval.pubmed import EFETCH_URL, ESEARCH_URL, TOOL_NAME

    job = json.loads(FIXTURE.read_text())
    context = [c["text"] for c in job["claims"]]
    planner = QueryPlanner()
    (out_dir / "esearch").mkdir(parents=True, exist_ok=True)
    (out_dir / "efetch").mkdir(parents=True, exist_ok=True)
    index, pmids = {}, set()
    for c in job["claims"]:
        for q in planner.ladder(c["text"], claim_kind=c["claim_kind"], context=context)[:3]:
            if q in index:
                continue
            time.sleep(0.4)
            r = httpx.get(ESEARCH_URL, params={"db": "pubmed", "tool": TOOL_NAME, "term": q, "retmax": 20,
                                               "retmode": "json", "sort": "relevance"}, timeout=30).json()
            ids = r["esearchresult"]["idlist"][:top]
            r["esearchresult"]["idlist"], r["esearchresult"]["retmax"] = ids, str(len(ids))
            name = f"search_{len(index) + 1:02d}.json"
            (out_dir / "esearch" / name).write_text(json.dumps(r, indent=1))
            index[q] = name
            pmids.update(ids)
    (out_dir / "esearch" / "index.json").write_text(json.dumps(index, indent=1))
    todo = sorted(pmids)
    for i in range(0, len(todo), 50):
        time.sleep(0.4)
        xml = httpx.get(EFETCH_URL, params={"db": "pubmed", "tool": TOOL_NAME, "id": ",".join(todo[i:i + 50]),
                                            "rettype": "abstract", "retmode": "xml"}, timeout=60).text
        for art in _re.findall(r"<PubmedArticle>.*?</PubmedArticle>", xml, _re.S):
            pmid = _re.search(r'<PMID Version="\d+">(\d+)</PMID>', art).group(1)
            art = _re.sub(r"<ReferenceList>.*?</ReferenceList>", "", art, flags=_re.S)
            (out_dir / "efetch" / f"{pmid}.xml").write_text(art)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out")
    ap.add_argument("--cache")
    ap.add_argument("--record-fixture", help="write the CI regression fixture (RecordedPubMed layout) here")
    args = ap.parse_args(argv)
    if args.record_fixture:
        record_fixture(Path(args.record_fixture))
        return 0
    sys.path.insert(0, str(HERE))
    from t50_search_recall import FileCache  # noqa: E402

    job = json.loads(FIXTURE.read_text())
    claims = job["claims"]
    context = [c["text"] for c in claims]
    cache = FileCache(Path(args.cache)) if args.cache else None
    retriever = EvidenceRetriever(PubMedClient(), cache)
    planner, reranker = QueryPlanner(), Reranker()
    rows = []
    for c in claims:
        plan = planner.plan(c["text"], claim_kind=c["claim_kind"], context=context)
        evidence, queries = [], []
        for _ in range(3):
            q = planner.next_query(c["text"], queries, plan=plan)
            if q is None:
                break
            queries.append(q)
            evidence = merge_evidence(evidence, retriever.retrieve(q).records)
        kept = reranker.rerank(c["text"], evidence, c["claim_kind"]).kept if evidence else []
        before_q = [r["query"] for r in c["search_trail"]]
        rows.append({
            "claim": c["claim_id"], "text": c["text"], "expected": c["claim_id"] in EXPECTED,
            "before_queries": before_q, "after_queries": queries, "kinds": [plan.kind_of(q) for q in queries],
            "context_concept": plan.context_concept,
            "retrieved": len(evidence), "vitk_retrieved": sum(map(is_vitamin_k, evidence)),
            "kept": len(kept), "vitk_kept": sum(map(is_vitamin_k, kept)),
            "first_kept": [f"{r.title[:90]} (PMID {r.pmid})" for r in kept[:2]],
        })
    if cache:
        cache.save()
    exp = [r for r in rows if r["expected"]]
    ok = [r for r in exp if r["vitk_kept"]]
    lines = ["# T50: vitamin K job 5cc07f48, search regression (rules only, live PubMed)", "",
             "Claim texts are the T49 RECONSTRUCTED fixture (no production DB access); before = the "
             "fixture's production query trail, after = the rewritten planner with the video's claims as context.",
             "", f"Expected claims (c1-c7, c9, c12) with a vitamin K / VKDB paper kept: **{len(ok)}/{len(exp)}** "
             f"(retrieved: {sum(1 for r in exp if r['vitk_retrieved'])}/{len(exp)}).", "",
             "| claim | expected | before: queries | after: queries (kind) | retrieved (vit K) | kept (vit K) |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        aq = "<br>".join(f"`{q[:110]}` ({k})" for q, k in zip(r["after_queries"], r["kinds"]))
        bq = "<br>".join(f"`{q[:60]}`" for q in dict.fromkeys(r["before_queries"]))
        lines.append(f"| {r['claim']} | {'yes' if r['expected'] else 'no'} | {bq} | {aq} | "
                     f"{r['retrieved']} ({r['vitk_retrieved']}) | {r['kept']} ({r['vitk_kept']}) |")
    lines += ["", "## First kept papers", ""]
    for r in rows:
        lines.append(f"- {r['claim']} \"{r['text'][:80]}\": " + ("; ".join(r["first_kept"]) or "none kept"))
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
        Path(args.out).with_suffix(".json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
