# PubMed fixtures (live captures, trimmed)

Real E-utilities responses recorded on 2026-11-22 (T18; the fasting / type 2 diabetes claim re-recorded on 2026-11-26 for T50, whose lexicon maps "type 2 diabetes" to its own MeSH heading) by
`scripts/record_pubmed_fixtures.py` against live NCBI, for the ten default claims in
that script (first query of the ladder that found papers). Same layout as
`../pubmed` (`esearch/index.json`, `esearch/*.json`, `efetch/<pmid>.xml`), so
`RecordedPubMed(FIXTURES_LIVE)` serves them. Tests never touch the network.

Trimmed to keep the repo small (the raw capture was 4.2 MB, 199 records):

- each ESearch reply keeps its real header and query translation, but its `idlist`
  is cut to the top 3 PMIDs (and `retmax` to match);
- only those 30 records' `PubmedArticle` XML is kept, with `<ReferenceList>` removed
  (reference lists were most of the size; the parser does not read them).

Everything else is as NCBI returned it. These are real abstracts: their copyright
belongs to the publishers. Keeping them in the repo as test data is a question for a
person (see context/MULTI_AGENT.md, T18). Re-record with
`python scripts/record_pubmed_fixtures.py --out /tmp/pubmed_recorded`.
