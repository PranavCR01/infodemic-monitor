"""The MCP front end: a thin wrapper around ``RetrievalToolService`` (design §6
"Retrieval as a shared service").

Built with the official MCP Python SDK. The doc names FastMCP; in the SDK's 2.x line
FastMCP was renamed ``MCPServer`` with the same decorator API, so that is what this
uses. Served over Streamable HTTP (stateless, JSON responses, so replicas need no
sticky sessions) behind bearer-token auth.

Every tool's parameters reuse the ``FieldInfo`` of its input model in
``app.mcp_server.schemas``, so the published JSON Schema carries the same caps the
service enforces. Results are Pydantic models, returned as structured content with
an output schema.

Tool code runs in a worker thread under a hard timeout (``limits.timeout_seconds``).
"""
from __future__ import annotations

import os
from typing import Annotated, Any, Optional

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.core.retrieval.schemas import EvidenceRecord
from app.mcp_server import schemas as S
from app.mcp_server.config import ClientConfig, ClientRegistry, McpServerConfig
from app.mcp_server.service import RetrievalToolService, ToolCallError

INSTRUCTIONS = (
    "Evidence retrieval tools of the WHO Infodemic Monitor: MeSH mapping, PubMed search "
    "and fetch, the lab's offline library, and relevance/study-type reranking. Every "
    "paper ID, title and link comes from PubMed's or the library's own records. "
    + S.UNTRUSTED_NOTICE
    + " Tool names and schemas are a versioned contract: a breaking change ships under "
    "a new tool name and the old one stays until callers migrate."
)


def _f(model: type, name: str):
    return model.model_fields[name]


class RegistryTokenVerifier:
    """Bearer tokens checked against the registry's SHA-256 hashes."""

    def __init__(self, registry: ClientRegistry) -> None:
        self.registry = registry

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        client = self.registry.by_token(token)
        if client is None:
            return None
        return AccessToken(token="", client_id=client.client_id, scopes=list(client.scopes))


def build_server(
    service: RetrievalToolService,
    registry: ClientRegistry,
    *,
    public_url: Optional[str] = None,
    local_client: Optional[ClientConfig] = None,
) -> MCPServer:
    """``public_url`` (e.g. ``https://retrieval.example.org``) turns on bearer auth,
    which the HTTP app requires. ``local_client`` is the identity used when a call
    carries no token: only for in-process use and tests, never for HTTP."""
    cfg = service.config
    kwargs: dict[str, Any] = {}
    if public_url:
        base = public_url.rstrip("/")
        kwargs = dict(
            token_verifier=RegistryTokenVerifier(registry),
            auth=AuthSettings(issuer_url=base, resource_server_url=base + cfg.server.path,
                              validate_token_resource=False),
        )
    server: MCPServer = MCPServer(cfg.server.name, instructions=INSTRUCTIONS, version=cfg.version, **kwargs)
    timeout = cfg.limits.timeout_seconds

    def caller() -> Optional[ClientConfig]:
        token = get_access_token()
        if token is not None:
            return registry.get(token.client_id)
        return local_client if not public_url else None

    async def dispatch(tool: str, arguments: dict) -> Any:
        client = caller()
        try:
            with anyio.fail_after(timeout):
                return await anyio.to_thread.run_sync(
                    lambda: service.run(tool, client, arguments), abandon_on_cancel=True
                )
        except TimeoutError:
            raise ToolError(f"timeout: {tool} took longer than {timeout:g}s") from None
        except ToolCallError as exc:
            hint = f" (retry_after={exc.retry_after:.1f}s)" if exc.retry_after else ""
            raise ToolError(f"{exc.kind}: {exc.message}{hint}") from None

    read_only = dict(read_only_hint=True, destructive_hint=False, idempotent_hint=True)

    @server.tool(
        name="map_to_mesh",
        description="Turns plain health terms into MeSH headings, with [tiab] synonyms and a broader heading.",
        annotations=ToolAnnotations(title="Map to MeSH", open_world_hint=False, **read_only),
    )
    async def map_to_mesh(text: Annotated[str, _f(S.MapToMeshInput, "text")]) -> S.MeshMapping:
        return await dispatch("map_to_mesh", {"text": text})

    @server.tool(
        name="search_pubmed",
        description="PubMed ESearch with sort=relevance. Returns PMIDs in relevance order. Results are cached.",
        annotations=ToolAnnotations(title="Search PubMed", open_world_hint=True, **read_only),
    )
    async def search_pubmed(
        query: Annotated[str, _f(S.SearchPubMedInput, "query")],
        max_results: Annotated[int, _f(S.SearchPubMedInput, "max_results")] = 20,
        filters: Annotated[Optional[S.PubMedFilters], _f(S.SearchPubMedInput, "filters")] = None,
    ) -> S.PubMedSearchResult:
        args: dict[str, Any] = {"query": query, "max_results": max_results}
        if filters is not None:
            args["filters"] = filters.model_dump()
        return await dispatch("search_pubmed", args)

    @server.tool(
        name="fetch_pubmed_records",
        description="PubMed EFetch: title, abstract, year, publication type and DOI per PMID. "
        + S.UNTRUSTED_NOTICE,
        annotations=ToolAnnotations(title="Fetch PubMed records", open_world_hint=True, **read_only),
    )
    async def fetch_pubmed_records(
        pmids: Annotated[list[str], _f(S.FetchPubMedRecordsInput, "pmids")],
    ) -> S.PubMedRecords:
        return await dispatch("fetch_pubmed_records", {"pmids": pmids})

    @server.tool(
        name="search_library",
        description="Hybrid vector + full-text search over the lab's offline library of scanned papers. "
        "Needs its own scope: the library may hold copyrighted material. " + S.UNTRUSTED_NOTICE,
        annotations=ToolAnnotations(title="Search the offline library", open_world_hint=False, **read_only),
    )
    async def search_library(
        query: Annotated[str, _f(S.SearchLibraryInput, "query")],
        k: Annotated[int, _f(S.SearchLibraryInput, "k")] = 10,
    ) -> S.LibrarySearchResult:
        return await dispatch("search_library", {"query": query, "k": k})

    @server.tool(
        name="rerank_evidence",
        description="Keeps the records that test the claim: relevance and study-type scoring, a relevance "
        "threshold, capped at k (at most 10). " + S.UNTRUSTED_NOTICE,
        annotations=ToolAnnotations(title="Rerank evidence", open_world_hint=False, **read_only),
    )
    async def rerank_evidence(
        claim: Annotated[str, _f(S.RerankEvidenceInput, "claim")],
        records: Annotated[list[EvidenceRecord], _f(S.RerankEvidenceInput, "records")],
        k: Annotated[int, _f(S.RerankEvidenceInput, "k")] = S.MAX_RERANK_K,
    ) -> S.RerankResult:
        return await dispatch(
            "rerank_evidence", {"claim": claim, "records": [r.model_dump() for r in records], "k": k}
        )

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(request):  # noqa: ARG001
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ok", "contract": cfg.version})

    return server


def allowed_hosts(config: McpServerConfig, env=os.environ) -> list[str]:
    extra = [h.strip() for h in env.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return list(dict.fromkeys([*config.server.allowed_hosts, *extra]))


def http_app(server: MCPServer, config: McpServerConfig, *, hosts: Optional[list[str]] = None):
    """The Starlette app for Streamable HTTP. Refuses to build without auth."""
    if server.settings.auth is None:
        raise ValueError("the HTTP app needs bearer auth: build the server with public_url")
    return server.streamable_http_app(
        streamable_http_path=config.server.path,
        stateless_http=True,
        json_response=True,
        max_request_body_size=config.limits.max_request_bytes,
        transport_security=TransportSecuritySettings(
            allowed_hosts=hosts if hosts is not None else allowed_hosts(config)
        ),
    )
