# PubMed fixtures (synthetic)

Recorded-response fixtures for the retrieval tests (T03, issue #31). Tests serve them
through `httpx.MockTransport` (`app/tests/pubmed_fixtures.py`); no test touches the
network.

**These are synthetic, not live captures.** The automated build environment has no
network access to `eutils.ncbi.nlm.nih.gov`, so the files were hand-built in NCBI's
exact response formats (ESearch JSON, EFetch `PubmedArticle` XML) by
`scripts/build_synthetic_pubmed_fixtures.py`. To make that impossible to mistake for
real evidence:

- every PMID is in the `99000xxx` range (no real PMID is that high yet);
- every title says "(synthetic fixture)" and every abstract starts "Synthetic fixture text.";
- DOIs use a made-up `10.9999/synthetic.` prefix.

Layout:

- `esearch/index.json` maps the exact query string to its ESearch response file. The
  queries are the ones `QueryPlanner` produces, so changing the planner or the MeSH
  lexicon means re-running the build script. `RecordedPubMed` answers a query it has
  no fixture for with an empty result and lists it in `unknown_queries`, which the
  tests assert is empty.
- `efetch/<pmid>.xml` holds one `<PubmedArticle>`; the mock assembles a
  `PubmedArticleSet` from the requested IDs, as EFetch does.

Cases covered: structured abstracts with labels, a title with inline markup, a
`MedlineDate` year, a DOI only in `ELocationID`, a missing abstract, two PMIDs sharing
one DOI (case differs), a retracted trial, a published erratum, a paper found by two
queries, an empty search, and an abstract containing a prompt-injection string.

To replace them with real recordings, run `scripts/record_pubmed_fixtures.py` from a
machine that can reach NCBI; it writes the same layout.
