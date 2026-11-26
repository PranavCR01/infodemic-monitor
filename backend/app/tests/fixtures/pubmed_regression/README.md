# Search regression set: real production misses (D8, T50)

One directory per production job whose search missed, in the `RecordedPubMed` layout
(`esearch/index.json`, `esearch/*.json`, `efetch/<pmid>.xml`). Served offline by
`app/tests/test_search_regression_set.py`; CI fails if a rewrite of the planner, the
lexicon or the reranker loses what these searches find.

- `vitamin_k_5cc07f48/`: production job 5cc07f48 ("Download (4).mp4", 2026-11-26), where
  every query searched `vitamin` instead of `vitamin K` and an accurate video was labelled
  MISINFO (unproven). **Real E-utilities responses**, recorded 2026-11-26 from the build
  environment by `scripts/t50_vitamin_k_regression.py --record-fixture` for every query
  the T50 planner runs on the job's 13 claims (first three rungs), trimmed to the top 5
  PMIDs per search with `<ReferenceList>` removed. The claim texts are the T49 fixture's
  (`fixtures/prod_5cc07f48`), which are RECONSTRUCTED (no production DB access): replace
  them with the real rows and re-record when they are available.

Re-record after a planner change makes a query miss its fixture (the test lists unknown
queries). Add a job here when a reviewer marks a source as missing (queued after T50).
