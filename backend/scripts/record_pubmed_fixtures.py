"""Record live PubMed responses for a set of claims, and print the evidence they find.

Needs network access to eutils.ncbi.nlm.nih.gov (the automated build environment has
none, which is why the committed fixtures are synthetic). Run from backend/:

    python scripts/record_pubmed_fixtures.py --out /tmp/pubmed_recorded
    python scripts/record_pubmed_fixtures.py --claims my_claims.txt --rounds 3

For every claim it plans queries with ``QueryPlanner``, runs up to ``--rounds`` rungs
of the ladder (stopping at the first that finds papers, like the graph), saves each raw
ESearch JSON and each EFetch article in the fixture layout (``esearch/index.json``,
``esearch/*.json``, ``efetch/<pmid>.xml``), and prints a Markdown table: the sample
the issue #31 acceptance criteria ask for in context/MULTI_AGENT.md.

Set NCBI_API_KEY / NCBI_EMAIL in the environment to use them. Recorded fixtures hold
real abstracts: keep them out of the repo unless their size and licence are fine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402

from app.core.retrieval.planning import QueryPlanner  # noqa: E402
from app.core.retrieval.pubmed import ESEARCH_URL, PubMedClient  # noqa: E402
from app.core.retrieval.retriever import EvidenceRetriever  # noqa: E402

DEFAULT_CLAIMS = [
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", help="file with one claim per line")
    ap.add_argument("--out", default="recorded_pubmed")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--show", type=int, default=3, help="papers per claim in the table")
    args = ap.parse_args()

    claims = DEFAULT_CLAIMS
    if args.claims:
        claims = [line.strip() for line in open(args.claims) if line.strip()]

    os.makedirs(f"{args.out}/esearch", exist_ok=True)
    os.makedirs(f"{args.out}/efetch", exist_ok=True)
    index: dict[str, str] = {}

    def save(resp: httpx.Response) -> None:
        resp.read()
        if str(resp.url).startswith(ESEARCH_URL):
            term = resp.request.url.params.get("term", "")
            name = f"search_{len(index) + 1:02d}.json"
            with open(f"{args.out}/esearch/{name}", "w") as f:
                json.dump(resp.json(), f, indent=1)
            index[term] = name
        else:
            root = ET.fromstring(resp.text)
            for art in root.findall("PubmedArticle"):
                pmid = art.findtext("MedlineCitation/PMID")
                with open(f"{args.out}/efetch/{pmid}.xml", "wb") as f:
                    f.write(ET.tostring(art))

    http = httpx.Client(timeout=20, event_hooks={"response": [save]})
    client = PubMedClient(http, api_key=os.environ.get("NCBI_API_KEY", ""),
                          email=os.environ.get("NCBI_EMAIL", ""))
    retriever = EvidenceRetriever(client)
    planner = QueryPlanner()

    print("| # | Claim | Query that found papers | Papers (PMID, year, type, title) |")
    print("|---|---|---|---|")
    for n, claim in enumerate(claims, 1):
        found, used = [], ""
        for q in planner.ladder(claim)[: args.rounds]:
            res = retriever.retrieve(q)
            if res.records:
                found, used = res.records, q
                break
        papers = "<br>".join(
            f"{r.pmid} ({r.publication_year}, {', '.join(r.publication_type[:2])}): {r.title[:90]}"
            for r in found[: args.show]
        ) or "none after the budget"
        print(f"| {n} | {claim} | `{used}` | {papers} |")

    with open(f"{args.out}/esearch/index.json", "w") as f:
        json.dump(index, f, indent=1)
    print(f"\nRecorded {len(index)} searches and {len(os.listdir(args.out + '/efetch'))} articles "
          f"to {args.out}; {client.request_count} requests.", file=sys.stderr)


if __name__ == "__main__":
    main()
