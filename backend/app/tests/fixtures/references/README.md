# Reference-source fixtures (T17, T19)

**Synthetic** (T17): pages in the publishers' HTML structure, written for the tests. The
wording is NOT the publishers' text and must not be cited.

- `cdc_child_schedule.html`, `cdc_measles_vaccine.html`: CDC pages. Since T19 CDC pages
  are `retrieval: stored`, so the tests load these into a temporary stored-snapshot
  archive (`app/tests/reference_fixtures.py`); the fake www.cdc.gov answers 403, as the
  real one does to cloud hosts, and a test fails if it is ever requested.
- `fda_caffeine.html`: a live catalogue page.

**Recorded** (T19, 2026-11-23, NCBI E-utilities, 2 requests): an NCBI Bookshelf search
the way production runs it.

- `bookshelf_esearch.json`: ESearch `db=pubmed`,
  `term=(normal body temperature degrees celsius) AND booksdocs[filter]`, `sort=relevance`.
- `bookshelf_efetch.xml`: EFetch `db=pubmed&id=32966005,29262037&retmode=xml`
  (two StatPearls chapters as `PubmedBookArticle`), with `<ReferenceList>` removed to keep
  it small. StatPearls text is © StatPearls Publishing (CC BY-NC-ND 4.0); see the
  copyright question already open in context/MULTI_AGENT.md §7o.

The real CDC snapshots used in production are not fixtures: they live in
`backend/data/reference_snapshots/` (see `scripts/refresh_reference_snapshots.py`).
