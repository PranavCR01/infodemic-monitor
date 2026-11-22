"""Authoritative reference sources for facts of record (§6 "Trusted sources beyond
PubMed", T17). Plain Python, no LangGraph or MCP code, like the rest of
``app.core.retrieval``."""
from app.core.retrieval.references.config import (
    CataloguePage,
    ReferenceConfig,
    ReferenceSource,
    load_reference_config,
    url_allowed,
)
from app.core.retrieval.references.fetcher import (
    FetchedPage,
    ReferenceFetcher,
    ReferenceFetchError,
    html_to_text,
    text_sha256,
)
from app.core.retrieval.references.passages import Passage, best_passage, split_passages
from app.core.retrieval.references.search import (
    REFERENCE_PUBLICATION_TYPE,
    ReferenceResult,
    ReferenceSearcher,
    bookshelf_query,
    is_reference_evidence_id,
    match_catalogue,
    reference_evidence_id,
)
from app.core.retrieval.references.snapshots import (
    InMemorySnapshotStore,
    Snapshot,
    SnapshotMismatch,
    SnapshotStore,
    SqlSnapshotStore,
)

__all__ = [
    "CataloguePage", "FetchedPage", "InMemorySnapshotStore", "Passage", "REFERENCE_PUBLICATION_TYPE",
    "ReferenceConfig", "ReferenceFetchError", "ReferenceFetcher", "ReferenceResult", "ReferenceSearcher",
    "ReferenceSource", "Snapshot", "SnapshotMismatch", "SnapshotStore", "SqlSnapshotStore",
    "best_passage", "bookshelf_query", "html_to_text", "is_reference_evidence_id", "load_reference_config",
    "match_catalogue", "reference_evidence_id", "split_passages", "text_sha256", "url_allowed",
]
