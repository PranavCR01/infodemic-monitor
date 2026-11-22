"""The five retrieval tools, with access control and limits, and no MCP code.

``RetrievalToolService.run(tool, client, arguments)`` is the one entry point the MCP
layer (``app.mcp_server.server``) calls. In order, it:

1. checks the client holds the tool's scope (``retrieval:<tool>``);
2. takes a token from the client's call bucket (per-client calls per minute);
3. validates the arguments against the tool's input model (hard caps);
4. calls the shared retrieval package (``app.core.retrieval``) — the same functions
   our LangGraph nodes import in process, so both teams get identical behaviour;
5. checks the serialized result against the response size cap.

PubMed requests go through ``BucketLimiter``: the shared NCBI bucket plus the
client's own share. Searches and records are cached in the shared query cache
(``RedisQueryCache`` in production), so a cache hit costs no NCBI quota.

Errors are ``ToolCallError`` with a fixed ``kind`` (``schemas.ErrorKind``); messages
never include stack traces, tokens or other clients' details.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Mapping, Optional

import httpx
from pydantic import BaseModel, ValidationError

from app.core.retrieval.cache import InMemoryQueryCache, QueryCache, search_key
from app.core.retrieval.mesh import map_to_mesh
from app.core.retrieval.pubmed import PubMedClient, PubMedError
from app.core.retrieval.rerank import Reranker, RerankConfig
from app.core.retrieval.retriever import EvidenceRetriever, to_evidence
from app.core.retrieval.schemas import SearchFilters
from app.mcp_server import schemas as S
from app.mcp_server.config import ClientConfig, McpServerConfig, scope_for
from app.mcp_server.quota import (
    Bucket,
    BucketLimiter,
    BucketStore,
    DeniedLimiter,
    InMemoryBucketStore,
    QuotaExceeded,
    ncbi_client_bucket,
    ncbi_global_bucket,
)

log = logging.getLogger(__name__)

INPUT_MODELS: dict[str, type[BaseModel]] = {
    "map_to_mesh": S.MapToMeshInput,
    "search_pubmed": S.SearchPubMedInput,
    "fetch_pubmed_records": S.FetchPubMedRecordsInput,
    "search_library": S.SearchLibraryInput,
    "rerank_evidence": S.RerankEvidenceInput,
}
OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "map_to_mesh": S.MeshMapping,
    "search_pubmed": S.PubMedSearchResult,
    "fetch_pubmed_records": S.PubMedRecords,
    "search_library": S.LibrarySearchResult,
    "rerank_evidence": S.RerankResult,
}


class ToolCallError(RuntimeError):
    def __init__(self, kind: str, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.retry_after = retry_after


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err.get("loc", ())) or "arguments"
    return f"{loc}: {err['msg']}"


class RetrievalToolService:
    def __init__(
        self,
        config: McpServerConfig,
        *,
        quota_store: Optional[BucketStore] = None,
        cache: Optional[QueryCache] = None,
        http: Any = None,
        ncbi_api_key: str = "",
        ncbi_email: str = "",
        library_searcher: Any = None,
        reranker: Optional[Reranker] = None,
        sleep: Callable[[float], None] = time.sleep,
        pubmed_retry: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.config = config
        self.quota = quota_store or InMemoryBucketStore()
        self.cache: QueryCache = cache if cache is not None else InMemoryQueryCache()
        self._http = http
        self._api_key = ncbi_api_key
        self._email = ncbi_email
        self.library = library_searcher
        self.reranker = reranker or Reranker()
        self._sleep = sleep
        # The PubMed client's own retries must fit inside the tool timeout.
        self._retry = dict(pubmed_retry or {"max_attempts": 3, "backoff_min": 0.5, "backoff_max": 4.0})

    # ------------------------------------------------------------- plumbing

    @property
    def ncbi_rate(self) -> float:
        return self.config.ncbi.rate(bool(self._api_key))

    def _http_client(self):
        if self._http is None:
            from app.core.guardrails.config import load_guardrails
            from app.core.guardrails.tools import GuardedHttpClient
            from app.core.retrieval.pubmed import MAX_RESPONSE_BYTES, USER_AGENT

            limits = load_guardrails().tools.model_copy(
                update={"timeout_seconds": min(15.0, self.config.limits.timeout_seconds),
                        "max_response_bytes": MAX_RESPONSE_BYTES}
            )
            self._http = GuardedHttpClient(limits, headers={"User-Agent": USER_AGENT})
        return self._http

    def ncbi_limiter(self, client: ClientConfig):
        own = ncbi_client_bucket(client.client_id, self.ncbi_rate, client.ncbi_share, self.config.ncbi.burst)
        if own is None:
            return DeniedLimiter()
        buckets = [own, ncbi_global_bucket(self.ncbi_rate, self.config.ncbi.burst)]
        return BucketLimiter(self.quota, buckets, max_wait=self.config.limits.ncbi_max_wait_seconds,
                             sleep=self._sleep)

    def _retriever(self, client: ClientConfig, max_results: int = 20,
                   filters: SearchFilters = SearchFilters()) -> EvidenceRetriever:
        pubmed = PubMedClient(
            self._http_client(), api_key=self._api_key, email=self._email,
            rate_limiter=self.ncbi_limiter(client), sleep=self._sleep, **self._retry,
        )
        return EvidenceRetriever(pubmed, self.cache, max_results=max_results, filters=filters)

    def _call_bucket(self, client: ClientConfig) -> Bucket:
        per_min = client.calls_per_minute or self.config.limits.calls_per_minute
        return Bucket(f"calls:{client.client_id}", per_min / 60.0, float(max(1, per_min // 6)))

    # ---------------------------------------------------------------- entry

    def run(self, tool: str, client: Optional[ClientConfig], arguments: Mapping[str, Any]) -> BaseModel:
        if tool not in INPUT_MODELS:
            raise ToolCallError("bad_arguments", f"unknown tool {tool!r}")
        if client is None:
            raise ToolCallError("forbidden", "no authenticated client")
        if scope_for(tool) not in client.scopes:
            raise ToolCallError("forbidden", f"client lacks scope {scope_for(tool)}")
        wait = self.quota.try_acquire([self._call_bucket(client)])
        if wait > 0:
            raise ToolCallError("rate_limited", f"call limit reached; retry in {wait:.1f}s", retry_after=wait)
        try:
            args = INPUT_MODELS[tool].model_validate(dict(arguments))
        except ValidationError as exc:
            raise ToolCallError("bad_arguments", _first_error(exc)) from None

        started = time.monotonic()
        try:
            result = getattr(self, f"_{tool}")(client, args)
        except ToolCallError:
            raise
        except QuotaExceeded as exc:
            raise ToolCallError("ncbi_quota", str(exc), retry_after=exc.retry_after) from None
        except PubMedError as exc:
            raise ToolCallError("upstream_error", f"PubMed: {str(exc)[:200]}") from None
        except httpx.HTTPError as exc:  # retries used up (HTTP 429/5xx or transport failure)
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else type(exc).__name__
            raise ToolCallError("upstream_error", f"PubMed unavailable ({detail})") from None
        size = len(json.dumps(result.model_dump(mode="json")).encode())
        if size > self.config.limits.max_response_bytes:
            raise ToolCallError("response_too_large",
                                f"{size} bytes > {self.config.limits.max_response_bytes}; ask for fewer results")
        # No query text or abstracts in logs (§15 "Logs").
        log.info("mcp tool=%s client=%s bytes=%d ms=%d", tool, client.client_id, size,
                 int((time.monotonic() - started) * 1000))
        return result

    # ---------------------------------------------------------------- tools

    def _map_to_mesh(self, client: ClientConfig, args: S.MapToMeshInput) -> S.MeshMapping:
        return S.MeshMapping(concepts=map_to_mesh(args.text))

    def _search_pubmed(self, client: ClientConfig, args: S.SearchPubMedInput) -> S.PubMedSearchResult:
        from app.core.guardrails.tools import _CTRL, _URLISH

        if _URLISH.search(args.query) or _CTRL.search(args.query):
            raise ToolCallError("bad_arguments", "query may not contain a URL, path or control characters")
        filters = args.filters.to_search_filters() if args.filters else SearchFilters()
        retriever = self._retriever(client, args.max_results, filters)
        cached = self.cache.get(search_key(args.query, args.max_results, filters.cache_key())) is not None
        return S.PubMedSearchResult(query=args.query, pmids=retriever.search(args.query), cached=cached)

    def _fetch_pubmed_records(self, client: ClientConfig, args: S.FetchPubMedRecordsInput) -> S.PubMedRecords:
        articles = self._retriever(client).articles(args.pmids)
        excluded = {t.lower() for t in SearchFilters().exclude_types}
        records = [
            to_evidence(a, "").model_copy(update={"query": None})
            for a in articles
            if not excluded & {t.lower() for t in a.publication_types}
        ]
        found = {a.pmid for a in articles}
        return S.PubMedRecords(records=records, missing=[p for p in args.pmids if p not in found])

    def _search_library(self, client: ClientConfig, args: S.SearchLibraryInput) -> S.LibrarySearchResult:
        if self.library is None:
            raise ToolCallError("unavailable", "the offline library is not available on this server")
        try:
            found = self.library.search(args.query, args.k)
        except Exception as exc:  # noqa: BLE001 - store outage; details stay in our logs
            log.warning("library search failed: %s", type(exc).__name__)
            raise ToolCallError("unavailable", "library search failed") from None
        return S.LibrarySearchResult(query=found.query, records=found.records, methods=list(found.methods))

    def _rerank_evidence(self, client: ClientConfig, args: S.RerankEvidenceInput) -> S.RerankResult:
        base = self.reranker.config
        cfg = RerankConfig(max_results=min(args.k, S.MAX_RERANK_K), min_relevance=base.min_relevance,
                           relevance_weight=base.relevance_weight, quality_weight=base.quality_weight)
        res = Reranker(cfg, self.reranker.relevance_model).rerank(args.claim, args.records)
        return S.RerankResult(
            claim=args.claim, kept=res.kept, cleared_threshold=res.cleared_threshold,
            dropped_below_threshold=res.dropped_below_threshold, dropped_over_cap=res.dropped_over_cap,
        )
