# backend/scripts

Run from `backend/` (for example `python scripts/ingest_library.py --help`).

## Operational

| Script | What it does |
|---|---|
| `assign_owners.py` | Assign owners to legacy jobs and videos (admin only) |
| `ingest_library.py` | Offline library batch ingest (design §6, "Building the library") |
| `refresh_reference_snapshots.py` | Refresh the stored reference-source snapshots |
| `mcp_client_token.py` | Make a bearer token for a retrieval MCP server client |
| `export_prod_job_fixture.py` | Export one production job as a test fixture, without personal data |
| `record_pubmed_fixtures.py` | Record live PubMed responses for a set of claims |
| `build_synthetic_pubmed_fixtures.py` | Build the synthetic PubMed fixtures in `app/tests/fixtures/pubmed` |
| `build_rerank_relevance_set.py` | Build the reranker relevance set fixture |
| `judge_crosscheck.py` | Check the judge rules against the golden set's labels |
| `smoke_run.py` | Real-model smoke run on a few videos (paid; needs approval) |
| `compare_library_ocr.py` | Tesseract vs EasyOCR on scanned library pages |

## One-off evaluation replays (`tNN_*`)

Each `tNN_*` script reproduces the numbers in `evals/reports/TNN/` for build-queue task TNN.
They are kept so the reports can be regenerated, and are not part of the running system. Some
import each other, and tests import `t50_paid_runs.py` and `t50_vitamin_k_regression.py`,
so they stay in this folder.

Scripts that make paid model calls refuse to run without `--live` and a `--max-usd` cap, and
need the project lead's approval.
