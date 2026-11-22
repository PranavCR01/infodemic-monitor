"""The reference allow-list (§6 "Trusted sources beyond PubMed": "A fixed allow-list in
config"). Loaded from ``config/reference_sources.yaml``.

Loading validates the allow-list itself: every catalogue page must be HTTPS, on one of
its source's allowed hosts and under one of its allowed path prefixes. A model never
sees or edits any of this; the fetcher refuses any URL the config doesn't allow.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).resolve().parents[4] / "config" / "reference_sources.yaml"


class _Cfg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReferenceSource(_Cfg):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    publisher: str
    covers: tuple[str, ...] = ()
    backend: Literal["catalogue", "bookshelf"]
    allowed_hosts: tuple[str, ...] = Field(min_length=1)
    allowed_path_prefixes: tuple[str, ...] = ("/",)
    max_results: int = Field(default=3, ge=1, le=10)  # bookshelf only

    @model_validator(mode="after")
    def _plain_hosts(self) -> "ReferenceSource":
        for h in self.allowed_hosts:
            if h != h.lower() or "*" in h or "/" in h or ":" in h or not h:
                raise ValueError(f"source {self.id}: host {h!r} must be an exact lower-case hostname")
        for p in self.allowed_path_prefixes:
            if not p.startswith("/") or ".." in p:
                raise ValueError(f"source {self.id}: path prefix {p!r} must start with / and not contain ..")
        return self


class CataloguePage(_Cfg):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    source: str
    title: str
    url: str
    keywords: tuple[str, ...] = Field(min_length=1)


class ReferenceConfig(_Cfg):
    version: str
    max_records_per_claim: int = Field(default=5, ge=1, le=10)
    max_pages_per_claim: int = Field(default=3, ge=1, le=10)
    min_keyword_hits: int = Field(default=1, ge=1)
    max_passage_chars: int = Field(default=1200, ge=200, le=5000)
    min_passage_overlap: float = Field(default=0.3, ge=0.0, le=1.0)
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    max_response_bytes: int = Field(default=3_000_000, gt=0, le=10_000_000)
    cache_ttl_seconds: int = Field(default=86_400, ge=0)
    sources: tuple[ReferenceSource, ...] = ()
    catalogue: tuple[CataloguePage, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> "ReferenceConfig":
        ids = [s.id for s in self.sources]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate source id")
        page_ids = [p.id for p in self.catalogue]
        if len(set(page_ids)) != len(page_ids):
            raise ValueError("duplicate catalogue page id")
        by_id = {s.id: s for s in self.sources}
        for page in self.catalogue:
            src = by_id.get(page.source)
            if src is None:
                raise ValueError(f"catalogue page {page.id}: unknown source {page.source!r}")
            if src.backend != "catalogue":
                raise ValueError(f"catalogue page {page.id}: source {src.id} is not a catalogue source")
            if not url_allowed(page.url, src):
                raise ValueError(f"catalogue page {page.id}: {page.url} is outside source {src.id}'s allow-list")
        return self

    def source(self, source_id: str) -> Optional[ReferenceSource]:
        return next((s for s in self.sources if s.id == source_id), None)

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset(h for s in self.sources for h in s.allowed_hosts)


def url_allowed(url: str, source: ReferenceSource) -> bool:
    """True when ``url`` is HTTPS on one of the source's exact hosts, default port, no
    credentials, and under one of its path prefixes."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    if (parts.hostname or "").lower() not in source.allowed_hosts or port not in (None, 443):
        return False
    path = parts.path or "/"
    if ".." in path or "\\" in path:
        return False
    return any(path.startswith(p) for p in source.allowed_path_prefixes)


def load_reference_config(path: Optional[Path | str] = None) -> ReferenceConfig:
    return _load(str(path or DEFAULT_PATH))


@lru_cache(maxsize=8)
def _load(path: str) -> ReferenceConfig:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return ReferenceConfig.model_validate(data)
