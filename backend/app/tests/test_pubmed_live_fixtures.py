"""The parser and retriever on real (recorded, trimmed) NCBI responses (T18).

The synthetic fixtures in ``fixtures/pubmed`` were hand-built in NCBI's formats; these
check the code against what NCBI actually sends. No network."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.pubmed import parse_efetch
from app.core.retrieval.retriever import EvidenceRetriever
from app.tests.pubmed_fixtures import RecordedPubMed

LIVE = Path(__file__).parent / "fixtures" / "pubmed_live"
CLAIMS = [
    "Drinking hot water every morning cures the flu.",
    "Garlic stops colds.",
    "Vaccines cause autism in children.",
    "Vitamin C prevents the common cold.",
    "Lemon water cures cancer.",
    "Ivermectin cures COVID-19.",
    "Intermittent fasting reverses type 2 diabetes.",
    "Fluoride in drinking water lowers children's IQ.",
    "5G spreads coronavirus.",
    "Apple cider vinegar burns fat and causes weight loss.",
]


def test_every_recorded_record_parses_with_the_fields_evidence_needs():
    files = sorted((LIVE / "efetch").glob("*.xml"))
    assert len(files) == 30
    for f in files:
        (art,) = parse_efetch(f"<PubmedArticleSet>{f.read_text()}</PubmedArticleSet>")
        assert art.pmid == f.stem and re.fullmatch(r"\d{6,9}", art.pmid)
        assert art.title.strip()
        assert art.publication_year is None or 1950 <= art.publication_year <= 2026
    parsed = [parse_efetch(f"<PubmedArticleSet>{f.read_text()}</PubmedArticleSet>")[0] for f in files]
    assert sum(1 for a in parsed if a.abstract.strip()) >= 25  # a few real records have none


@pytest.mark.parametrize("claim", CLAIMS)
def test_planner_query_finds_recorded_papers_end_to_end(claim):
    server = RecordedPubMed(LIVE)
    retriever = EvidenceRetriever(server.client())
    found = []
    for q in QueryPlanner().ladder(claim):
        res = retriever.retrieve(q)
        if res.records:
            found = res.records
            break
    assert found, f"no recorded papers for {claim!r}; unknown queries: {server.unknown_queries}"
    index = json.loads((LIVE / "esearch" / "index.json").read_text())
    assert all(r.pmid and (LIVE / "efetch" / f"{r.pmid}.xml").exists() for r in found)
    assert all(r.evidence_id == f"ev_{r.pmid}" and r.pmid in r.source_url for r in found)
    assert len(index) == 10
