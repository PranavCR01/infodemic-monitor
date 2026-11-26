# T50: search planning rewrite and find-the-study step: measurements

All numbers here were produced **without any model call** (rules only). The parts that
need a model (search assistant, translation, find-the-study web search) have a dry-run
cost estimate only; the paid run waits for the lead's approval and cap.

| File | What |
| --- | --- |
| `recall.md`, `recall_rows.json` | Tune split (187 claims): share with at least one on-topic record retrieved, before vs after, English and non-English separately |
| `vitamin_k.md`, `vitamin_k.json` | The 13-claim vitamin K job (5cc07f48) as a search regression |
| `t49_replay/` | T49's unproven-guard replay on the evidence the rewritten search retrieves |
| `cost_estimate.md`, `cost_estimate.json` | Dry-run cost of the paid runs (vitamin K fixture; tune recall) |

The D8 CI regression set (real production misses, offline) is `backend/app/tests/fixtures/pubmed_regression/` with `backend/app/tests/test_search_regression_set.py`.

**How they were made** (from `backend/`, live NCBI E-utilities at <= 2.5 requests/s, no key):

    # before: on origin/langgraph-build b52e952 (a checkout of the old code)
    python scripts/t50_search_recall.py record --out before.json
    # after: on this branch
    python scripts/t50_search_recall.py record --out after.json
    python scripts/t50_search_recall.py score before.json after.json --out ../evals/reports/T50/recall.md
    python scripts/t49_unproven_guard_replay.py --t50-evidence after.json --out ../evals/reports/T50/t49_replay
    python scripts/t50_vitamin_k_regression.py --out ../evals/reports/T50/vitamin_k.md
    python scripts/t50_paid_runs.py estimate --record after.json --vitamin-k ../evals/reports/T50/vitamin_k.json \
        --out ../evals/reports/T50/cost_estimate.md

The raw `before.json` / `after.json` records (5-8 MB, PubMed abstracts) are not committed;
the commands above rebuild them.

**Caveats.**

- *On topic* is the T49 deterministic check (`unproven_guard.on_topic`) from the new code,
  applied to both runs. It uses the same MeSH lexicon the new planner searches with, so it
  is partly circular for claims whose concept T50 added; the golden-cited-PMID numbers are the
  independent check (D8 strict, golden PMID kept: 3.4% → 13.6%; retrieved at all: 5.9% → 16.9%).
- D8 target (lenient >= 80%) is **not met** rules-only: 60.4% on the T49 intervention yardstick,
  79.7% on the claim-concept yardstick. The model helpers would add to it; that needs the paid run.
- The lexicon additions were chosen from the **tune** split's claims (the design says to grow
  the lexicon from the evaluation set). Expect a smaller gain on the test split, which was not read.
- The recall run uses the full budget (3 rounds) for every claim; in the graph a claim gets
  rounds 2-3 only when its search was empty or the critic asks for more.
- The vitamin K fixture's claim texts are RECONSTRUCTED (T49: no production DB access).
