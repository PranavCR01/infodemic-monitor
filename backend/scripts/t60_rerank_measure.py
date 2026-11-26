"""T60: reranker relevance by measurement (target design §6 "Reranking", §14).

Compares the lexical relevance scorer (``rerank.lexical_relevance``) with the MedCPT
cross-encoder (``ncbi/MedCPT-Cross-Encoder``, run locally through the ``RelevanceModel``
hook) on a relevance set built from real retrieved records. No model API calls; the only
network use is NCBI E-utilities (free) in ``build`` and the Hugging Face download of the
MedCPT weights in ``score``/``latency`` (cached outside the repo, never committed).

Run from backend/:

    # 1. pick the claims and fetch their candidate records (NCBI, <= 3 requests/s)
    python scripts/t60_rerank_measure.py build --out ../evals/reports/T60/candidates.json
    # 2. labels are written by hand into ../evals/reports/T60/labels.json (see the README)
    # 3. score both scorers, threshold sweep
    python scripts/t60_rerank_measure.py score --candidates ../evals/reports/T60/candidates.json \
        --labels ../evals/reports/T60/labels.json --out ../evals/reports/T60/results.json
    # 3b. subsets (English / non-English), claims-with-relevant ranking, paired bootstrap
    python scripts/t60_rerank_measure.py compare --candidates ../evals/reports/T60/candidates.json \
        --labels ../evals/reports/T60/labels.json --results ../evals/reports/T60/results.json \
        --medcpt-threshold 0.5 --out ../evals/reports/T60/compare.json
    # 4. CPU latency and memory, pinned to N cores (run once per core count)
    taskset -c 0 python scripts/t60_rerank_measure.py latency --threads 1 \
        --candidates ../evals/reports/T60/candidates.json --out ../evals/reports/T60/latency_1cpu.json

``score`` and ``latency`` need ``torch`` and ``transformers`` (not in requirements.txt). Set
``HF_HUB_DISABLE_XET=1``: the Xet transfer path stalled behind the proxy, while the plain
HTTPS download (huggingface.co → us.aws.cdn.hf.co) worked.

Claim selection (deterministic, tune split only; the test split is never read):
``evals/reports/T50/tune_paid.json`` claims with >= 20 retrieved records, sorted by id;
24 evenly spaced English claims and 5 evenly spaced non-English claims, plus the vitamin K
job's c8 ("bleeding in the brain ... death") with the records production retrieved for it
(job 5cc07f48, query "bleeding brain permanent neurological death").
The candidate pool per claim is the first 20 records in retrieval order. Their abstracts and
publication types are re-fetched from PubMed so both scorers see the same, complete input.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import resource
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.retrieval.pubmed import parse_efetch  # noqa: E402
from app.core.retrieval.rerank import (  # noqa: E402
    DEFAULT_RERANK_CONFIG,
    Reranker,
    RerankConfig,
)
from app.core.retrieval.schemas import EvidenceRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TUNE = ROOT / "evals" / "reports" / "T50" / "tune_paid.json"
PROD_VITK = ROOT / "backend" / "app" / "tests" / "fixtures" / "prod_5cc07f48" / "vitamin_k_job.real.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
POOL = 20
N_EN, N_NON_EN = 24, 5
VITK_C8_QUERY = "bleeding brain permanent neurological death"


# ----------------------------------------------------------------------- build


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "infodemic-monitor-eval/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def _efetch(pmids: Sequence[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(pmids), 150):
        batch = pmids[i : i + 150]
        q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
        for art in parse_efetch(_get(f"{EUTILS}/efetch.fcgi?{q}").decode("utf-8")):
            out[art.pmid] = art.to_json()
        time.sleep(0.4)
    return out


def _spaced(items: list[str], n: int) -> list[str]:
    if len(items) <= n:
        return items
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def select_claims(tune: dict) -> list[tuple[str, dict]]:
    cl = tune["claims"]
    eligible = [k for k in sorted(cl) if len(cl[k]["records"]) >= POOL]
    en = [k for k in eligible if cl[k]["plan"]["language"] == "en"]
    non_en = [k for k in eligible if cl[k]["plan"]["language"] != "en"]
    return [(k, cl[k]) for k in _spaced(en, N_EN) + _spaced(non_en, N_NON_EN)]


def build(out: Path) -> None:
    tune = json.loads(TUNE.read_text())
    assert tune["split"] == "tune", "only the tune split may be read"
    claims: list[dict[str, Any]] = []
    for cid, c in select_claims(tune):
        pmids = [r["pmid"] for r in list(c["records"].values())[:POOL] if r.get("pmid")]
        claims.append({"claim_id": cid, "text": c["text"], "kind": c["kind"],
                       "language": c["plan"]["language"], "pmids": pmids,
                       "lexical_kept_in_run": [k.removeprefix("ev_") for k in c["kept"]]})

    # Vitamin K job c8, production's own query and kept list.
    prod = json.loads(PROD_VITK.read_text())
    c8 = next(c for c in prod["claims"] if c["claim_id"] == "c8")
    q = urllib.parse.urlencode({"db": "pubmed", "term": VITK_C8_QUERY, "retmax": POOL,
                                "retmode": "json", "sort": "relevance"})
    live = json.loads(_get(f"{EUTILS}/esearch.fcgi?{q}"))["esearchresult"]["idlist"]
    prod_kept = [e["pmid"] for e in c8["evidence"]]
    pmids = list(dict.fromkeys(live + prod_kept))
    claims.append({"claim_id": "vitk:c8", "text": c8["text"], "kind": c8["claim_kind"],
                   "language": "en", "pmids": pmids, "lexical_kept_in_run": prod_kept,
                   "note": "production query re-run live on PubMed; production's 10 kept PMIDs added "
                           "if live search no longer returns them"})

    every = sorted({p for c in claims for p in c["pmids"]})
    arts = _efetch(every)
    for c in claims:
        c["records"] = [arts[p] for p in c["pmids"] if p in arts]
        c["missing"] = [p for p in c["pmids"] if p not in arts]
        del c["pmids"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"pool_per_claim": POOL, "source": str(TUNE.relative_to(ROOT)),
                               "claims": claims}, indent=1, ensure_ascii=False))
    print(f"{len(claims)} claims, {sum(len(c['records']) for c in claims)} records -> {out}")


# ---------------------------------------------------------------------- score


def to_records(c: dict) -> list[EvidenceRecord]:
    return [EvidenceRecord(evidence_id=f"ev_{r['pmid']}", source="pubmed", title=r["title"],
                           abstract=r.get("abstract") or "", pmid=r["pmid"],
                           publication_year=r.get("publication_year"),
                           publication_type=r.get("publication_types") or [])
            for r in c["records"]]


def medcpt_model(threads: Optional[int] = None):
    from app.core.retrieval.cross_encoder import CrossEncoderRelevance

    return CrossEncoderRelevance(threads=threads)


def _p_at(kept: list[str], rel: set[str], k: int) -> Optional[float]:
    top = kept[:k]
    if not top:
        return None
    return sum(p in rel for p in top) / len(top)


def evaluate(claims: list[dict], labels: dict[str, dict[str, int]], scores: dict[str, dict[str, float]],
             threshold: float, min_label: int) -> dict[str, Any]:
    """Pipeline metrics at one threshold: the real Reranker (blend with study quality, cap 10)
    with relevance fixed to the given scores. P@k over the records kept (a claim with nothing
    kept is counted separately, not as 0); recall = relevant kept / relevant in the pool."""

    class Fixed:
        def __init__(self, s: dict[str, float]):
            self.s = s

        def __call__(self, claim_text, records):
            return [self.s[r.evidence_id] for r in records]

    p3, p10, rec, kept_n, offtopic_kept = [], [], [], 0, 0
    empty, rel_total, rel_kept = 0, 0, 0
    per_claim = {}
    for c in claims:
        cid = c["claim_id"]
        lab = labels[cid]
        rel = {f"ev_{p}" for p, v in lab.items() if v >= min_label}
        cfg = RerankConfig(min_relevance=threshold)
        res = Reranker(cfg, Fixed(scores[cid])).rerank(c["text"], to_records(c), c["kind"])
        kept = [r.evidence_id for r in res.kept]
        kept_n += len(kept)
        offtopic_kept += sum(lab[k.removeprefix("ev_")] == 0 for k in kept)
        a, b = _p_at(kept, rel, 3), _p_at(kept, rel, 10)
        if a is None:
            empty += 1
        else:
            p3.append(a)
            p10.append(b)
        rel_total += len(rel)
        rel_kept += len(rel & set(kept))
        if rel:
            rec.append(len(rel & set(kept)) / len(rel))
        per_claim[cid] = {"kept": [k.removeprefix("ev_") for k in kept], "p@3": a, "p@10": b,
                          "relevant": len(rel), "relevant_kept": len(rel & set(kept))}
    mean = lambda xs: round(statistics.mean(xs), 3) if xs else None  # noqa: E731
    return {"threshold": threshold, "p@3": mean(p3), "p@10": mean(p10),
            "recall_macro": mean(rec), "recall_micro": round(rel_kept / rel_total, 3) if rel_total else None,
            "claims_nothing_kept": empty, "kept_total": kept_n, "not_relevant_kept": offtopic_kept,
            "claims_with_relevant": len(rec), "per_claim": per_claim}


def ranking_only(claims, labels, scores, min_label) -> dict[str, Any]:
    """Pure ranking quality, no threshold: relevance score only (no study-type blend)."""
    p3, p10, ap = [], [], []
    for c in claims:
        cid = c["claim_id"]
        rel = {f"ev_{p}" for p, v in labels[cid].items() if v >= min_label}
        order = sorted(scores[cid], key=lambda e: -scores[cid][e])
        p3.append(sum(e in rel for e in order[:3]) / 3)
        p10.append(sum(e in rel for e in order[:10]) / 10)
        if rel:
            hits, s = 0, 0.0
            for i, e in enumerate(order, 1):
                if e in rel:
                    hits += 1
                    s += hits / i
            ap.append(s / len(rel))
    return {"p@3": round(statistics.mean(p3), 3), "p@10": round(statistics.mean(p10), 3),
            "MAP": round(statistics.mean(ap), 3)}


def score(cand: Path, labels_path: Path, out: Path) -> None:
    data = json.loads(cand.read_text())
    claims = data["claims"]
    labels = {cid: v["labels"] for cid, v in json.loads(labels_path.read_text())["claims"].items()}
    for c in claims:
        missing = {r["pmid"] for r in c["records"]} - set(labels[c["claim_id"]])
        assert not missing, f"{c['claim_id']}: unlabelled {sorted(missing)}"

    lex: dict[str, dict[str, float]] = {}
    med: dict[str, dict[str, float]] = {}
    logits: dict[str, dict[str, float]] = {}
    base = Reranker()
    model = medcpt_model()
    for c in claims:
        recs = to_records(c)
        lex[c["claim_id"]] = {s.record.evidence_id: s.relevance for s in base.score(c["text"], recs, c["kind"])}
        lg = model.logits(c["text"], recs)
        logits[c["claim_id"]] = {r.evidence_id: round(x, 4) for r, x in zip(recs, lg)}
        med[c["claim_id"]] = {r.evidence_id: model.squash(x) for r, x in zip(recs, lg)}

    sweep = [round(x * 0.05, 2) for x in range(0, 20)]
    result: dict[str, Any] = {"n_claims": len(claims),
                              "n_records": sum(len(c["records"]) for c in claims),
                              "default_threshold": DEFAULT_RERANK_CONFIG.min_relevance,
                              "medcpt_squash": model.squash_doc}
    for name, sc in (("lexical", lex), ("medcpt", med)):
        result[name] = {}
        for lab_name, min_label in (("strict", 2), ("lenient", 1)):
            result[name][lab_name] = {
                "ranking_only": ranking_only(claims, labels, sc, min_label),
                "sweep": [evaluate(claims, labels, sc, t, min_label) for t in sweep],
            }
    result["scores"] = {"lexical": lex, "medcpt": med, "medcpt_logits": logits}
    out.write_text(json.dumps(result, indent=1))
    print(f"-> {out}")


# -------------------------------------------------------------------- compare


def _subset_metrics(claims, labels, scores, threshold, min_label) -> dict[str, Any]:
    ev = evaluate(claims, labels, scores, threshold, min_label)
    with_rel = [c for c in claims if any(v >= min_label for v in labels[c["claim_id"]].values())]
    ev.pop("per_claim")
    ev["ranking_only_claims_with_relevant"] = (
        ranking_only(with_rel, labels, scores, min_label) if with_rel else None)
    ev["n_claims"] = len(claims)
    return ev


def _paired_bootstrap(claims, labels, sa, ta, sb, tb, min_label, metric, n=2000, seed=60):
    """Paired bootstrap over claims of mean(metric_b - metric_a); claims where either side
    has no value (nothing kept, or no relevant record for recall) are dropped."""
    import random

    def per_claim(scores, t):
        return evaluate(claims, labels, scores, t, min_label)["per_claim"]

    pa, pb = per_claim(sa, ta), per_claim(sb, tb)

    def val(pc):
        if metric == "recall":
            return None if pc["relevant"] == 0 else pc["relevant_kept"] / pc["relevant"]
        return pc[metric]

    diffs = [val(pb[c["claim_id"]]) - val(pa[c["claim_id"]]) for c in claims
             if val(pa[c["claim_id"]]) is not None and val(pb[c["claim_id"]]) is not None]
    if not diffs:
        return None
    rng = random.Random(seed)
    boots = sorted(statistics.mean(rng.choice(diffs) for _ in diffs) for _ in range(n))
    return {"n_claims": len(diffs), "mean_diff": round(statistics.mean(diffs), 3),
            "ci95": [round(boots[int(0.025 * n)], 3), round(boots[int(0.975 * n) - 1], 3)]}


def compare(cand: Path, labels_path: Path, results: Path, out: Path, medcpt_t: float) -> None:
    claims = json.loads(cand.read_text())["claims"]
    labels = {cid: v["labels"] for cid, v in json.loads(labels_path.read_text())["claims"].items()}
    res = json.loads(results.read_text())
    lex, med = res["scores"]["lexical"], res["scores"]["medcpt"]
    lex_t = DEFAULT_RERANK_CONFIG.min_relevance
    subsets = {"all": claims,
               "english": [c for c in claims if c["language"] == "en"],
               "non_english": [c for c in claims if c["language"] != "en"]}
    report: dict[str, Any] = {"lexical_threshold": lex_t, "medcpt_threshold": medcpt_t, "subsets": {}}
    for name, cs in subsets.items():
        report["subsets"][name] = {
            lab: {"lexical": _subset_metrics(cs, labels, lex, lex_t, ml),
                  "medcpt": _subset_metrics(cs, labels, med, medcpt_t, ml)}
            for lab, ml in (("strict", 2), ("lenient", 1))}
    report["bootstrap_medcpt_minus_lexical"] = {
        name: {lab: {m: _paired_bootstrap(cs, labels, lex, lex_t, med, medcpt_t, ml, m)
                     for m in ("p@3", "p@10", "recall")}
               for lab, ml in (("strict", 2), ("lenient", 1))}
        for name, cs in subsets.items()}
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


# -------------------------------------------------------------------- latency


def latency(cand: Path, threads: int, out: Path, repeats: int) -> None:
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    claims = json.loads(cand.read_text())["claims"]
    t0 = time.perf_counter()
    model = medcpt_model(threads=threads)
    model.logits("warm up", to_records(claims[0])[:1])
    load_s = time.perf_counter() - t0
    rss_loaded = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    med_times, lex_times = [], []
    base = Reranker()
    for _ in range(repeats):
        for c in claims:
            recs = to_records(c)
            t = time.perf_counter()
            model(c["text"], recs)
            med_times.append(time.perf_counter() - t)
            t = time.perf_counter()
            base.score(c["text"], recs, c["kind"])
            lex_times.append(time.perf_counter() - t)
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    def pct(xs, q):
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, math.ceil(q * len(xs)) - 1)] * 1000, 1)

    res = {"threads": threads, "affinity_cpus": len(os.sched_getaffinity(0)),
           "records_per_claim_mean": round(statistics.mean(len(c["records"]) for c in claims), 1),
           "model_load_s": round(load_s, 2),
           "medcpt_ms_per_claim": {"median": pct(med_times, 0.5), "p95": pct(med_times, 0.95),
                                   "max": round(max(med_times) * 1000, 1)},
           "lexical_ms_per_claim": {"median": pct(lex_times, 0.5), "p95": pct(lex_times, 0.95)},
           "peak_rss_mb": {"python_start": round(rss0 / 1024), "model_loaded": round(rss_loaded / 1024),
                           "after_runs": round(rss_peak / 1024)},
           "runs": len(med_times)}
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--candidates", type=Path, required=True)
    s.add_argument("--labels", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    cp = sub.add_parser("compare")
    cp.add_argument("--candidates", type=Path, required=True)
    cp.add_argument("--labels", type=Path, required=True)
    cp.add_argument("--results", type=Path, required=True)
    cp.add_argument("--medcpt-threshold", type=float, default=0.5)
    cp.add_argument("--out", type=Path, required=True)
    lt = sub.add_parser("latency")
    lt.add_argument("--candidates", type=Path, required=True)
    lt.add_argument("--threads", type=int, required=True)
    lt.add_argument("--repeats", type=int, default=2)
    lt.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.out)
    elif a.cmd == "score":
        score(a.candidates, a.labels, a.out)
    elif a.cmd == "compare":
        compare(a.candidates, a.labels, a.results, a.out, a.medcpt_threshold)
    else:
        latency(a.candidates, a.threads, a.out, a.repeats)


if __name__ == "__main__":
    main()
