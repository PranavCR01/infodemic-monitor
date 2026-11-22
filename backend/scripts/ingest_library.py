"""Offline library batch job (target design §6 "Building the library"). Run from backend/:

    # Ingest a folder of scanned PDFs listed in a manifest CSV
    python scripts/ingest_library.py ingest --manifest uploads/manifest.csv --pdf-dir uploads/ \
        --uploaded-by alice@lab

    # A reviewer checked flagged pages 3 and 4 of a document: index them
    python scripts/ingest_library.py approve --document 1a2b3c4d5e6f7a8b --pages 3 4 --reviewer bob@lab

    # Try a search
    python scripts/ingest_library.py search "zinc lozenges common cold"

Uses DATABASE_URL_SYNC (Postgres with pgvector, migrated to 0006). Needs the ``library``
extra (pip install -e ".[library]") plus the tesseract-ocr and ghostscript packages.
``--embedder hashing`` uses the model-free stand-in, for trying the pipeline without the
MedCPT weights; never use it for the real library (search only matches chunks embedded
with the model the searcher uses).
``--pubmed-check`` asks PubMed whether it already holds each DOI (needs network).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.retrieval.library import (  # noqa: E402
    HashingEmbedder,
    LibraryIngestor,
    LibrarySearcher,
    PgLibraryStore,
    PubMedDoiLookup,
    embedder_from_config,
    load_library_config,
)
from app.core.retrieval.library.ocr import default_engine  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="library config YAML (default config/library.yaml)")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL_SYNC"), help="Postgres URL (DATABASE_URL_SYNC)")
    ap.add_argument("--embedder", choices=["config", "hashing"], default="config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--manifest", required=True, type=Path)
    ing.add_argument("--pdf-dir", required=True, type=Path)
    ing.add_argument("--uploaded-by")
    ing.add_argument("--pubmed-check", action="store_true")
    ing.add_argument("--ocr-engine", choices=["ocrmypdf", "text_layer"])
    apr = sub.add_parser("approve")
    apr.add_argument("--document", required=True)
    apr.add_argument("--pages", required=True, type=int, nargs="+")
    apr.add_argument("--reviewer", required=True)
    se = sub.add_parser("search")
    se.add_argument("query")
    se.add_argument("-k", type=int, default=10)
    args = ap.parse_args(argv)

    if not args.dsn:
        ap.error("set DATABASE_URL_SYNC or pass --dsn")
    from sqlalchemy import create_engine

    cfg = load_library_config(args.config)
    store = PgLibraryStore(create_engine(args.dsn))
    embedder = HashingEmbedder() if args.embedder == "hashing" else embedder_from_config(cfg.embedding)

    if args.cmd == "search":
        res = LibrarySearcher(store, embedder, cfg).search(args.query, args.k)
        for h in res.hits:
            print(f"{h.record.evidence_id}\t{h.rrf_score:.4f}\tv={h.vector_rank}\tt={h.text_rank}\t{h.record.title}")
        return 0

    ocr_cfg = replace(cfg.ocr, engine=args.ocr_engine) if getattr(args, "ocr_engine", None) else cfg.ocr
    pubmed = None
    if getattr(args, "pubmed_check", False):
        from app.core.graph.retrieval_nodes import retriever_from_settings

        pubmed = PubMedDoiLookup(retriever_from_settings().client)
    ingestor = LibraryIngestor(store, default_engine(ocr_cfg), embedder, cfg, pubmed=pubmed)

    if args.cmd == "approve":
        print(json.dumps(asdict(ingestor.approve_pages(args.document, args.pages, reviewer=args.reviewer))))
        return 0

    report = ingestor.ingest_batch(args.manifest, args.pdf_dir, uploaded_by=args.uploaded_by)
    for e in report.manifest_errors:
        print(f"manifest row {e.row}: {e.message}", file=sys.stderr)
    for o in report.outcomes:
        print(json.dumps(asdict(o)))
    print(json.dumps(report.summary()), file=sys.stderr)
    return 0 if not report.count("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
