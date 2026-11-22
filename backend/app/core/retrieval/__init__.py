"""Evidence retrieval (target design §6): planning, PubMed client, cache, dedup.

Plain Python with no LangGraph or MCP code, so the graph nodes
(``app.core.graph.retrieval_nodes``) and the future MCP server (T13) share one
implementation. Replaces ``app.core.grounding.pubmed`` for the graph; the live
single-call pipeline still uses the old module until the integration task (T11).
"""
from app.core.retrieval.cache import InMemoryQueryCache, QueryCache, RedisQueryCache
from app.core.retrieval.mesh import map_to_mesh
from app.core.retrieval.planning import QueryPlanner, frame_claim, normalize_claim, sanitize_query
from app.core.retrieval.pubmed import PubMedArticle, PubMedClient, PubMedError, RateLimiter
from app.core.retrieval.retriever import EvidenceRetriever, RetrievalResult, merge_evidence
from app.core.retrieval.schemas import ClaimFrame, Concept, EvidenceRecord, SearchFilters

__all__ = [
    "ClaimFrame",
    "Concept",
    "EvidenceRecord",
    "EvidenceRetriever",
    "InMemoryQueryCache",
    "PubMedArticle",
    "PubMedClient",
    "PubMedError",
    "QueryCache",
    "QueryPlanner",
    "RateLimiter",
    "RedisQueryCache",
    "RetrievalResult",
    "SearchFilters",
    "frame_claim",
    "map_to_mesh",
    "merge_evidence",
    "normalize_claim",
    "sanitize_query",
]
