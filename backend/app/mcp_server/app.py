"""Composition root: wires the service from the environment.

- ``REDIS_URL``: the shared NCBI token bucket and the shared query cache. Required for
  the deployed server (``MCP_REQUIRE_REDIS`` defaults to on in ``__main__``), because
  without it each replica would keep its own quota and NCBI's limit can't be held.
- ``NCBI_API_KEY`` / ``NCBI_EMAIL``: raise NCBI's limit from 3 to 10 requests/s.
- ``MCP_CLIENTS`` / ``MCP_CLIENTS_FILE``: the client registry (hashed tokens, scopes,
  NCBI shares). See ``config.load_clients``.
- ``MCP_PUBLIC_URL``: the server's public base URL; turns on bearer auth.
- ``DATABASE_URL_SYNC``: the library store (Postgres + pgvector), when
  ``library.mode`` is ``auto``.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Mapping, Optional

from app.mcp_server.config import McpServerConfig, load_clients, load_config
from app.mcp_server.quota import InMemoryBucketStore, RedisBucketStore
from app.mcp_server.server import build_server, http_app
from app.mcp_server.service import RetrievalToolService

log = logging.getLogger(__name__)


def library_searcher_from_env(config: McpServerConfig, env: Mapping[str, str] = os.environ) -> Optional[Any]:
    if config.library.mode == "off":
        return None
    dsn = env.get("DATABASE_URL_SYNC", "").strip()
    if not dsn:
        log.info("no DATABASE_URL_SYNC: search_library will report the library as unavailable")
        return None
    from sqlalchemy import create_engine

    from app.core.retrieval.library import LibrarySearcher, PgLibraryStore, embedder_from_config, load_library_config

    lib_cfg = load_library_config()
    return LibrarySearcher(PgLibraryStore(create_engine(dsn, pool_pre_ping=True)),
                           embedder_from_config(lib_cfg.embedding), lib_cfg)


def build_default_server(
    *,
    clients_env: Optional[Mapping[str, str]] = None,
    public_url: Optional[str] = None,
    library: bool = True,
    require_redis: bool = False,
    env: Mapping[str, str] = os.environ,
):
    config = load_config()
    registry = load_clients(env if clients_env is None else clients_env)
    registry.check_shares(config.ncbi.pipeline_share)
    redis_url = env.get("REDIS_URL", "").strip()
    quota: Any
    cache: Any = None
    if redis_url:
        import redis

        from app.core.retrieval.cache import RedisQueryCache

        client = redis.Redis.from_url(redis_url)
        quota = RedisBucketStore(client)
        cache = RedisQueryCache(client)  # one query cache for every replica and client (§6)
    elif require_redis:
        raise RuntimeError("REDIS_URL is required: the NCBI quota must be shared across replicas")
    else:
        quota = InMemoryBucketStore()
    service = RetrievalToolService(
        config,
        quota_store=quota,
        cache=cache,
        ncbi_api_key=env.get("NCBI_API_KEY", ""),
        ncbi_email=env.get("NCBI_EMAIL", ""),
        library_searcher=library_searcher_from_env(config, env) if library else None,
    )
    return build_server(service, registry, public_url=public_url)


def create_app(env: Mapping[str, str] = os.environ):
    """The ASGI app for ``uvicorn app.mcp_server.app:create_app --factory``."""
    public_url = env.get("MCP_PUBLIC_URL", "").strip()
    if not public_url:
        raise RuntimeError("MCP_PUBLIC_URL is required (the server's public https base URL)")
    require_redis = env.get("MCP_REQUIRE_REDIS", "1") not in ("0", "false", "no")
    server = build_default_server(public_url=public_url, require_redis=require_redis, env=env)
    return http_app(server, load_config())
