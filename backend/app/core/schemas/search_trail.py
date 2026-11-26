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

MAX_SCREENED_OUT = 100
SEARCH_TRAIL_VERSION = 3  # 2 (T50): kind, planning, ladder_exhausted, screened_out, find_study; 3 (T57): shared_studies

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
    # T50: which rung of the plan this query was (citation, pico, intervention_outcome,
    # broader_outcome, intervention_only, assistant, keywords, critic ...).
    kind: Optional[str] = None


class PlanningView(BaseModel):
    """What planning decided before searching (T50, §6 "Planning the search")."""

    language: str = "en"
    # A non-English claim translated before planning: the English text searched.
    translated: bool = False
    search_text: Optional[str] = None
    translation_error: Optional[str] = None
    # The video's main intervention, carried over to a claim that refers to it without
    # naming it ("babies who don't get the shot").
    context_concept: Optional[str] = None
    # What the claim says about a study it cites (journal [ta], year, sample size,
    # institution); such a claim gets a citation lookup first.
    citation: Optional[dict] = None
    assistant_used: bool = False
    assistant_error: Optional[str] = None
    # No query at all, and why: "needs_translation" (a script the rules can't read and no
    # translator configured) or "no_terms".
    no_query_reason: Optional[str] = None


class ScreenedOutView(BaseModel):
    """A paper the searches returned that the reranker did not keep (T50 g): listed so
    the result page can show what was screened out when nothing was kept."""

    evidence_id: str
    pmid: Optional[str] = None
    title: str
    year: Optional[int] = None
    source: str = "pubmed"


class StudyCandidateView(BaseModel):
    pmid: Optional[str] = None
    doi: Optional[str] = None
    outcome: str
    reason: str = ""
    evidence_id: Optional[str] = None
    via: Optional[str] = None


class FindStudyView(BaseModel):
    """The find-the-study step (T50 i): the web searches the model ran, the ids it
    proposed and how each was verified. Web text never appears here."""

    reason: str
    round: int = 0
    web_queries: list[str] = Field(default_factory=list)
    web_searches: int = 0
    candidates: list[StudyCandidateView] = Field(default_factory=list)
    verified: int = 0
    model: Optional[str] = None
    cost_usd: Optional[float] = None
    latency_ms: int = 0
    error: Optional[str] = None


class SharedStudyView(BaseModel):
    """A cited-study record another claim of the same video holds, offered to this
    claim (T57). ``shared_from`` is the claim it came from; ``outcome`` is kept,
    not_kept_by_reranker, off_topic or citation_mismatch."""

    evidence_id: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    shared_from: str
    outcome: str
    reason: str = ""
    relevance_score: Optional[float] = None


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
    # T50 d: the plan had no new query left, so the search stopped early.
    ladder_exhausted: bool = False
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
    planning: Optional[PlanningView] = None
    find_study: Optional[FindStudyView] = None
    # T57: cited-study records shared from the video's other claims (additive).
    shared_studies: list[SharedStudyView] = Field(default_factory=list)
    # Up to MAX_SCREENED_OUT papers retrieved but not kept, in retrieval order.
    screened_out: list[ScreenedOutView] = Field(default_factory=list)
    screened_out_truncated: bool = False
