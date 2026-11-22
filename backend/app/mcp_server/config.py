"""Server settings and the client registry (design §6 "Sharing it safely", §15 "MCP clients").

Settings come from ``backend/config/mcp_server.yaml``. Clients come from the
environment, never from the repo: ``MCP_CLIENTS`` (a JSON list) or
``MCP_CLIENTS_FILE`` (a YAML file with a ``clients:`` list). Each client entry holds
the SHA-256 hash of its bearer token, never the token itself::

    {"client_id": "other-team", "token_sha256": "<64 hex>",
     "scopes": ["retrieval:map_to_mesh", "retrieval:search_pubmed"],
     "ncbi_share": 0.3, "calls_per_minute": 60}

A scope names one tool (``retrieval:<tool name>``), so ``search_library`` is a
separate scope by construction: the library may hold copyrighted material another
team has no rights to.
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "mcp_server.yaml"

# The five tools of design §6, in the doc's order. Their names are a contract (see
# app.mcp_server.contract): a breaking change ships under a new name.
TOOL_NAMES: tuple[str, ...] = (
    "map_to_mesh",
    "search_pubmed",
    "fetch_pubmed_records",
    "search_library",
    "rerank_evidence",
)
SCOPE_PREFIX = "retrieval:"


def scope_for(tool: str) -> str:
    return SCOPE_PREFIX + tool


ALL_SCOPES: tuple[str, ...] = tuple(scope_for(t) for t in TOOL_NAMES)


class ConfigError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServerSection(_Strict):
    name: str
    path: str = "/mcp"
    allowed_hosts: list[str] = Field(default_factory=list)


class LimitsSection(_Strict):
    timeout_seconds: PositiveFloat
    max_request_bytes: PositiveInt
    max_response_bytes: PositiveInt
    calls_per_minute: PositiveInt
    ncbi_max_wait_seconds: float = Field(ge=0)


class NcbiSection(_Strict):
    rate_with_key: PositiveFloat
    rate_without_key: PositiveFloat
    burst: PositiveInt = 3
    pipeline_share: float = Field(ge=0, le=1)

    def rate(self, has_api_key: bool) -> float:
        return self.rate_with_key if has_api_key else self.rate_without_key


class LibrarySection(_Strict):
    mode: str = "auto"

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in ("auto", "off"):
            raise ValueError("library.mode must be 'auto' or 'off'")
        return v


class McpServerConfig(_Strict):
    version: str
    server: ServerSection
    limits: LimitsSection
    ncbi: NcbiSection
    library: LibrarySection = LibrarySection()


@lru_cache(maxsize=4)
def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> McpServerConfig:
    return McpServerConfig.model_validate(yaml.safe_load(Path(path).read_text()))


# ---------------------------------------------------------------- clients


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ClientConfig(_Strict):
    client_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scopes: tuple[str, ...]
    # Share of the NCBI rate this client may use (0-1). 0 means no PubMed calls
    # beyond cache hits.
    ncbi_share: float = Field(default=0.1, ge=0, le=1)
    calls_per_minute: Optional[PositiveInt] = None  # None: the server default

    @field_validator("scopes")
    @classmethod
    def _known_scopes(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [s for s in v if s not in ALL_SCOPES]
        if unknown:
            raise ValueError(f"unknown scopes {unknown}; valid: {list(ALL_SCOPES)}")
        return tuple(dict.fromkeys(v))


class ClientRegistry(_Strict):
    clients: tuple[ClientConfig, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> "ClientRegistry":
        ids = [c.client_id for c in self.clients]
        if len(ids) != len(set(ids)):
            raise ValueError("client_id values must be unique")
        hashes = [c.token_sha256 for c in self.clients]
        if len(hashes) != len(set(hashes)):
            raise ValueError("two clients share a token")
        return self

    def check_shares(self, pipeline_share: float) -> None:
        """Client shares plus the pipeline's reserved share may not exceed the NCBI
        rate, or a busy client could starve the pipeline."""
        total = pipeline_share + sum(c.ncbi_share for c in self.clients)
        if total > 1.0 + 1e-9:
            raise ConfigError(
                f"NCBI shares add up to {total:.2f} (pipeline {pipeline_share:.2f} + clients); must be <= 1.0"
            )

    def by_token(self, token: str) -> Optional[ClientConfig]:
        digest = hash_token(token)
        for c in self.clients:
            if c.token_sha256 == digest:
                return c
        return None

    def get(self, client_id: str) -> Optional[ClientConfig]:
        return next((c for c in self.clients if c.client_id == client_id), None)


def parse_clients(entries: Sequence[Mapping]) -> ClientRegistry:
    return ClientRegistry(clients=tuple(ClientConfig.model_validate(e) for e in entries))


def load_clients(env: Mapping[str, str] = os.environ) -> ClientRegistry:
    """Clients from ``MCP_CLIENTS`` (JSON list) or ``MCP_CLIENTS_FILE`` (YAML).
    Neither set: no clients, so every request is refused."""
    raw = env.get("MCP_CLIENTS", "").strip()
    if raw:
        try:
            entries = json.loads(raw)
        except ValueError as exc:
            raise ConfigError(f"MCP_CLIENTS is not valid JSON: {exc}") from None
        if not isinstance(entries, list):
            raise ConfigError("MCP_CLIENTS must be a JSON list")
        return parse_clients(entries)
    path = env.get("MCP_CLIENTS_FILE", "").strip()
    if path:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return parse_clients(data.get("clients", []))
    return ClientRegistry()
