""""How we searched" for one claim (T31; target design §6, §8, §12).

Stored as JSON on ``claims.search_trail`` and returned by the result API on every
claim (``ClaimView.search_trail``). Built by code from the graph state after the run
(``app.services.search_trail.build_search_trail``); a model never writes any of it.

What it holds, and what it never holds:

- the PubMed queries actually run, in order, with what each returned;
- the allow-listed reference sources and pages consulted (names, publishers and hosts
  come from ``config/reference_sources.yaml``) and whether the offline library ran;
- counts: ``retrieved`` (results the searches returned), ``screened`` (distinct
  records the reranker scored, after filters and PMID/DOI dedup) and ``kept`` (what
  went to the verifier, at most 10, §6 "Cap");
- the search budget used (§6 "When nothing comes back", §8 "Budgets").

No API keys, no request URLs (E-utilities URLs can carry the key), no prompts and no
exception messages: a failed search records the exception type only.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SEARCH_TRAIL_VERSION = 1

ReferenceOutcome = Literal["passage", "no_passage", "no_results", "skipped", "error"]


class PubMedQueryView(BaseModel):
    round: int
    query: str
    # PMIDs ESearch returned; None when the search failed or (for results stored
    # before the trail existed) is unknown.
    results: Optional[int] = None
    # Left after the publication-type and year filters (retractions, errata).
    after_filters: Optional[int] = None
    # Added to the claim's set by this round after PMID/DOI dedup (references included).
    new_records: Optional[int] = None
    from_cache: Optional[bool] = None
    # True when PubMed failed for this query; error_type is the exception class only.
    failed: bool = False
    error_type: Optional[str] = None
    # True when the same query already ran for this claim (the planner's ladder ran
    # out and the broadest query was repeated, served from the cache). Its results
    # are not counted twice in ``counts.retrieved``.
    repeat: bool = False


class ReferenceItemView(BaseModel):
    item: str  # catalogue page id, NBK accession, or "search"
    url: Optional[str] = None  # the allow-listed page, never an API request URL
    mode: str  # live | stored | search
    outcome: ReferenceOutcome


class ReferenceSourceView(BaseModel):
    source_id: str
    name: str
    publisher: str = ""
    sites: list[str] = Field(default_factory=list)
    items: list[ReferenceItemView] = Field(default_factory=list)
    passages: int = 0  # items that gave a quotable passage


class LibrarySearchView(BaseModel):
    """The offline-library fallback (§6): it runs only when PubMed came up short."""

    fired: bool
    passages: int = 0


class SearchCountsView(BaseModel):
    # None only when the trail was rebuilt from queries alone (no per-round record).
    retrieved: Optional[int] = None
    screened: int = 0
    kept: int = 0


class SearchBudgetView(BaseModel):
    rounds_used: int
    rounds_max: int
    exhausted: bool
    evidence_cap: int
    # Rounds asked for by the critic (§8 RETRIEVE_MORE) are part of the same budget.


class SearchTrailView(BaseModel):
    version: int = SEARCH_TRAIL_VERSION
    # "graph": recorded round by round during the run. "queries_only": the run kept no
    # per-round record (an older checkpoint), so only the planned queries are known.
    recorded: Literal["graph", "queries_only"] = "graph"
    pubmed_queries: list[PubMedQueryView] = Field(default_factory=list)
    references: list[ReferenceSourceView] = Field(default_factory=list)
    library: Optional[LibrarySearchView] = None
    counts: SearchCountsView
    budget: SearchBudgetView
