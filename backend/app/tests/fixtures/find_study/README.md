# Find-the-study fixtures (T50 item i)

**NCBI E-utilities: real responses**, recorded from this build environment on
2026-11-26 (curl, no API key):

- `esearch/doi_jama_2026_21764.json`: ESearch `"10.1001/jama.2026.21764"[doi]` →
  PMID 42986716 (the JAMA 2026 paper "Nonreceipt of Newborn Vitamin K and Risk of
  Bleeding"; Google had reported this PMID unverified, this lookup verifies it);
- `efetch/42986716.xml`: that record's `PubmedArticle` (`<ReferenceList>` removed),
  whose DOI is 10.1001/jama.2026.21764, journal JAMA, year 2026;
- `esearch/doi_unknown.json`: ESearch for a DOI PubMed doesn't have (no items found).

A PMID with no record (`999999999`) needs no file: EFetch returns an empty
`PubmedArticleSet`, which `RecordedPubMed` reproduces for any PMID without a file.

**Crossref: synthetic.** `api.crossref.org` is blocked by the build environment's
network policy (CONNECT 403), so `crossref/10.9999_synthetic.vitk.2026.json` was written
by hand in the `/works/{doi}` response shape documented by Crossref. Its DOI uses the
made-up `10.9999/synthetic.` prefix, its title says "(synthetic fixture)", and its
abstract carries a prompt-injection sentence on purpose. Re-record from a machine that
can reach Crossref with `curl -A "infodemic-monitor-retrieval/1.0" https://api.crossref.org/works/<doi>`.
