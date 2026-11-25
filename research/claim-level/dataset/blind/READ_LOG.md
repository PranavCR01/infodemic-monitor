# Blind pass read log (blind_model_pass_v1)

Every repository file opened before the labels were committed.

- research/claim-level/dataset/REVIEW.md
- research/claim-level/dataset/README.md
- docs/target-system-design.md (via `git show origin/langgraph-build:...`, sections 4, 5, 7 read in full; 6, 9 skimmed)
- research/claim-level/dataset/scripts/judge.py (to derive video labels)
- directory listings of research/claim-level/dataset/ and scripts/ (names only)
- research/claim-level/dataset/transcripts/<id>.json for the 41 blind videos,
  read through a small viewer that printed only `transcript.segments` and
  `on_screen.captions`. The JSON also carries `collector`, `collector_label`,
  `relative_path` and `creator_handle`; the viewer did not print them, and one
  early raw dump of v01 showed `collector_label` and `relative_path` for v01
  only (v01 has no health content, labelled out_of_scope on that basis).

Not opened before the labels were committed: claims.csv, videos.csv,
video_index.csv, external_agreement.md, collector_agreement.md, sources/,
labels_*.py / labels.py, PLAN.md, evidence_cache/, scripts/evidence.py, and
the git history or diffs of any of them.

Evidence: live PubMed E-utilities (esearch sort=relevance, esummary, efetch),
throttled to under 3 requests/second, cached in a scratch directory outside the
repo. Queries are in `model_relabel_queries.txt` (plus a few ad hoc retries).
No §6 reference URLs were fetched in this pass. Every PMID cited in
`model_relabel_claims.csv` (117 unique) was returned by one of these searches.
