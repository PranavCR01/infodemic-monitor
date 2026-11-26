"""The vitamin K production job 5cc07f48, from its real stored rows (T49, T50).

``fixtures/prod_5cc07f48/vitamin_k_job.real.json`` was copied from production by the
coordinating session (public video content only). It replaces the RECONSTRUCTED fixture
T49 shipped with. Evidence rows carry PMID, title, year, publication type and the
verifier's relation, not abstracts; the verifier's answers are rebuilt from the stored
verdict, explanation, limitations and relations.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from app.core.graph.state import EvidenceRecord

REAL = Path(__file__).parent / "fixtures" / "prod_5cc07f48" / "vitamin_k_job.real.json"


def load_real() -> dict:
    return json.loads(REAL.read_text())


def stance_of(c: dict) -> str:
    return (c.get("stances") or [{"stance": "UNCLEAR"}])[0]["stance"]


def evidence_of(c: dict) -> list[EvidenceRecord]:
    out = []
    for e in c.get("evidence") or []:
        try:
            types = ast.literal_eval(e.get("publication_type") or "[]")
        except (ValueError, SyntaxError):
            types = []
        year = e.get("year")
        out.append(EvidenceRecord(
            evidence_id=f"ev_{e['pmid']}", source="pubmed", pmid=e["pmid"], title=e["title"],
            publication_year=int(year) if year and str(year).isdigit() else None,
            publication_type=list(types), source_url=f"https://pubmed.ncbi.nlm.nih.gov/{e['pmid']}/"))
    return out


def verifier_answer(c: dict) -> dict | None:
    """The stored verdict as the verifier's answer; None when nothing was retrieved (the
    verifier then never calls the model)."""
    if not c.get("evidence"):
        return None
    rel = lambda r: [f"ev_{e['pmid']}" for e in c["evidence"] if e.get("relation") == r]  # noqa: E731
    return {"verdict": c["verdict"], "supporting_evidence_ids": rel("SUPPORTS"),
            "contradicting_evidence_ids": rel("CONTRADICTS"), "explanation": c.get("explanation") or "",
            "limitations": [x for x in (c.get("limitations") or []) if x != "no evidence was retrieved for this claim"],
            "raw_confidence": 0.6}


def claims_as_job(job: dict) -> list[dict]:
    """The claims in the simple shape the retrieval scripts and tests use."""
    return [{"claim_id": c["claim_id"], "text": c["text"], "category": c["category"],
             "claim_kind": c["claim_kind"], "start_seconds": c["start_seconds"], "end_seconds": c["end_seconds"],
             "search_trail": [{"query": q["query"]} for q in (c.get("search_trail") or {}).get("pubmed_queries", [])]}
            for c in job["claims"]]
