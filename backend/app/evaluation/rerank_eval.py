"""Reranker relevance check (target design §6, §14 "Retrieval"; issue #32).

Scores the reranker on a hand-labelled relevance set and compares it with the order
PubMed returned the same papers in. Metrics per claim, averaged over claims:

- **precision@5** (the issue's metric), strict: relevant = label 2 ("tests the claim");
  lenient: label ≥ 1. The denominator is always 5, so dropping papers below the
  relevance threshold can't inflate it.
- **nDCG@10** and **recall@10** (§14's retrieval metrics), strict labels.
- **off-topic kept**: label-0 papers that survive the threshold and cap.

Two baselines on the same papers: PubMed's order cut to 10 (what the stub reranker
does), and the expected precision@5 of a random order (the base rate of relevant papers).

    python -m app.evaluation.rerank_eval [--path FILE] [--out results.json]

The default set (``app/tests/fixtures/rerank/relevance_set.jsonl``) is synthetic and was
labelled by the agent that wrote the reranker; see that file's builder for why its
numbers are optimistic.
"""
from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from statistics import mean
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict

from app.core.retrieval.rerank import MAX_EVIDENCE_PER_CLAIM, Reranker
from app.core.retrieval.retriever import pubmed_url
from app.core.retrieval.schemas import EvidenceRecord
from app.evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k

RELEVANCE_SET = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "rerank" / "relevance_set.jsonl"


class LabelledPaper(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    claim: str
    pubmed_rank: int
    pmid: str
    title: str
    abstract: str = ""
    publication_type: list[str] = []
    label: int  # 0 not evidence, 1 related/indirect, 2 tests the claim

    def record(self) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=f"ev_{self.pmid}", source="pubmed", pmid=self.pmid, title=self.title,
            abstract=self.abstract, publication_type=list(self.publication_type),
            source_url=pubmed_url(self.pmid),
        )


def load_relevance_set(path: Path | str = RELEVANCE_SET) -> "OrderedDict[str, list[LabelledPaper]]":
    claims: OrderedDict[str, list[LabelledPaper]] = OrderedDict()
    for line in Path(path).read_text().splitlines():
        if line.strip():
            p = LabelledPaper.model_validate_json(line)
            claims.setdefault(p.claim_id, []).append(p)
    for papers in claims.values():
        papers.sort(key=lambda p: p.pubmed_rank)
        if len({p.claim for p in papers}) != 1:
            raise ValueError(f"claim {papers[0].claim_id} has more than one claim text")
    return claims


def _ranking_metrics(ranked: Sequence[str], strict: set[str], lenient: set[str], off_topic: set[str]) -> dict:
    return {
        "precision_at_5": precision_at_k(strict, ranked, 5),
        "precision_at_5_lenient": precision_at_k(lenient, ranked, 5),
        "ndcg_at_10": ndcg_at_k(strict, ranked, 10),
        "recall_at_10": recall_at_k(strict, ranked, 10),
        "off_topic_kept": sum(1 for e in ranked[:MAX_EVIDENCE_PER_CLAIM] if e in off_topic),
        "returned": len(ranked[:MAX_EVIDENCE_PER_CLAIM]),
    }


def _avg(rows: list[dict], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r[key] is not None]
    return round(mean(vals), 4) if vals else None


def evaluate(
    claims: "OrderedDict[str, list[LabelledPaper]] | None" = None,
    reranker: Optional[Reranker] = None,
) -> dict:
    claims = claims if claims is not None else load_relevance_set()
    reranker = reranker or Reranker()
    per_claim = []
    for cid, papers in claims.items():
        records = [p.record() for p in papers]
        strict = {f"ev_{p.pmid}" for p in papers if p.label >= 2}
        lenient = {f"ev_{p.pmid}" for p in papers if p.label >= 1}
        off = {f"ev_{p.pmid}" for p in papers if p.label == 0}
        result = reranker.rerank(papers[0].claim, records)
        reranked = [r.evidence_id for r in result.kept]
        pubmed = [r.evidence_id for r in records][:MAX_EVIDENCE_PER_CLAIM]
        per_claim.append({
            "claim_id": cid,
            "claim": papers[0].claim,
            "candidates": len(papers),
            "relevant": len(strict),
            # Expected precision@5 of a uniformly random order: the share of relevant papers.
            "random_precision_at_5": round(len(strict) / len(papers), 4),
            # Best possible precision@5: every relevant paper first.
            "ceiling_precision_at_5": round(min(5, len(strict)) / 5, 4),
            "pubmed": _ranking_metrics(pubmed, strict, lenient, off),
            "reranked": _ranking_metrics(reranked, strict, lenient, off),
            "reranked_ids": reranked,
            "study_types": {s.record.evidence_id: s.record.study_type for s in result.scored},
        })
    summary = {}
    for side in ("pubmed", "reranked"):
        rows = [c[side] for c in per_claim]
        summary[side] = {k: _avg(rows, k) for k in rows[0]} if rows else {}
        if rows:
            summary[side]["off_topic_kept"] = sum(r["off_topic_kept"] for r in rows)
            summary[side]["returned"] = sum(r["returned"] for r in rows)
    summary["random_precision_at_5"] = _avg(per_claim, "random_precision_at_5")
    summary["ceiling_precision_at_5"] = _avg(per_claim, "ceiling_precision_at_5")
    return {"claims": len(per_claim), "summary": summary, "per_claim": per_claim}


def format_report(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"Reranker relevance check: {report['claims']} claims",
        f"{'metric':26} {'PubMed order':>13} {'reranked':>10}",
    ]
    for key in ("precision_at_5", "precision_at_5_lenient", "ndcg_at_10", "recall_at_10", "off_topic_kept", "returned"):
        lines.append(f"{key:26} {str(s['pubmed'][key]):>13} {str(s['reranked'][key]):>10}")
    lines.append(f"{'random order precision@5':26} {str(s['random_precision_at_5']):>13}")
    lines.append(f"{'best possible precision@5':26} {str(s['ceiling_precision_at_5']):>13}")
    lines.append("")
    lines.append(f"{'claim':6} {'P@5 pubmed':>10} {'P@5 rerank':>10}  claim text")
    for c in report["per_claim"]:
        lines.append(
            f"{c['claim_id']:6} {c['pubmed']['precision_at_5']:>10.2f} {c['reranked']['precision_at_5']:>10.2f}  {c['claim']}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--path", default=str(RELEVANCE_SET))
    ap.add_argument("--out", default=None, help="write the full report as JSON")
    args = ap.parse_args(argv)
    report = evaluate(load_relevance_set(args.path))
    print(format_report(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
