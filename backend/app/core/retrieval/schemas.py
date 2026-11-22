"""Records the retrieval package returns (target design §6 "Each evidence record").

This module has no LangGraph or MCP imports, so the graph nodes and the future MCP
server (§6 "Retrieval as a shared service") share one definition. ``EvidenceRecord`` is
re-exported by ``app.core.graph.state`` and stored in graph checkpoints.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Record(BaseModel):
    """Immutable, and unknown fields are an error (same rules as graph state records)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceRecord(_Record):
    """One retrieved paper or library passage (§6). IDs, titles and URLs always come
    from the retrieval tool's response, never from a model."""

    evidence_id: str
    source: Literal["pubmed", "library"]
    title: str
    abstract: str = ""
    pmid: Optional[str] = None
    doi: Optional[str] = None
    document_id: Optional[str] = None
    page: Optional[int] = None
    publication_year: Optional[int] = None
    publication_type: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    query: Optional[str] = None
    relevance_score: Optional[float] = None


class Concept(_Record):
    """One term the planner recognised, mapped to PubMed's vocabulary (§6 step 2)."""

    key: str
    label: str
    kind: Literal["condition", "intervention", "population", "outcome"]
    mesh: Optional[str] = None
    synonyms: tuple[str, ...] = ()
    parent_mesh: Optional[str] = None
    matched_text: str = ""


class ClaimFrame(_Record):
    """A claim broken down into population, intervention, comparator and outcome
    (§6 step 1). ``qualifiers`` (doses, frequencies) are kept for the record but are
    the first thing broadening drops."""

    normalized_text: str
    population: tuple[Concept, ...] = ()
    intervention: tuple[Concept, ...] = ()
    comparator: tuple[Concept, ...] = ()
    outcome: tuple[Concept, ...] = ()
    qualifiers: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

    @property
    def has_concepts(self) -> bool:
        return bool(self.intervention or self.outcome)


class SearchFilters(_Record):
    """Filters applied to a PubMed search (§6 issue #31 step 4).

    ``publication_types`` restricts ESearch to those types (``[pt]``); ``exclude_types``
    drops fetched records of those types. ``min_year``/``max_year`` use the publication
    date (``datetype=pdat``).
    """

    publication_types: tuple[str, ...] = ()
    exclude_types: tuple[str, ...] = (
        "Retracted Publication",
        "Retraction of Publication",
        "Published Erratum",
    )
    min_year: Optional[int] = None
    max_year: Optional[int] = None

    def cache_key(self) -> str:
        return self.model_dump_json()
