"""Library settings, loaded from ``backend/config/library.yaml`` (target design §6).

The embedding model is named here, never in code: changing it is a config change that
also means re-embedding the library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import yaml

DEFAULT_LIBRARY_CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "library.yaml"


class LibraryConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "medcpt"
    document_model: str = ""
    query_model: str = ""
    version: str = ""
    dimensions: int = 768
    max_document_tokens: int = 512
    max_query_tokens: int = 64
    batch_size: int = 16


@dataclass(frozen=True)
class OcrConfig:
    engine: str = "ocrmypdf"
    language: str = "eng"
    deskew: bool = True
    rotate_pages: bool = True
    min_page_confidence: float = 70.0
    min_word_ratio: float = 0.6
    min_page_chars: int = 20
    confidence_dpi: int = 300


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 400
    overlap_tokens: int = 50


@dataclass(frozen=True)
class SearchConfig:
    candidates_per_method: int = 50
    rrf_k: int = 60
    default_k: int = 10
    max_k: int = 10


@dataclass(frozen=True)
class LibraryConfig:
    version: str = "library_v1"
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    viewer_url: str = "/library/documents/{document_id}?page={page}&chunk={chunk_id}"


def _section(cls, data: Any, name: str):
    if data is None:
        return cls()
    if not isinstance(data, dict):
        raise LibraryConfigError(f"{name}: expected a mapping")
    known = set(cls.__dataclass_fields__)
    unknown = set(data) - known
    if unknown:
        raise LibraryConfigError(f"{name}: unknown keys {sorted(unknown)}")
    return cls(**data)


def parse_library_config(data: dict) -> LibraryConfig:
    if not isinstance(data, dict):
        raise LibraryConfigError("library config must be a mapping")
    unknown = set(data) - {"version", "embedding", "ocr", "chunking", "search", "viewer_url"}
    if unknown:
        raise LibraryConfigError(f"unknown keys {sorted(unknown)}")
    cfg = LibraryConfig(
        version=str(data.get("version", "library_v1")),
        embedding=_section(EmbeddingConfig, data.get("embedding"), "embedding"),
        ocr=_section(OcrConfig, data.get("ocr"), "ocr"),
        chunking=_section(ChunkingConfig, data.get("chunking"), "chunking"),
        search=_section(SearchConfig, data.get("search"), "search"),
        viewer_url=str(data.get("viewer_url", LibraryConfig.viewer_url)),
    )
    _validate(cfg)
    return cfg


def _validate(cfg: LibraryConfig) -> None:
    e, c, s = cfg.embedding, cfg.chunking, cfg.search
    if e.dimensions != 768:
        # The library_chunks.embedding column is vector(768) (§17); another size needs a migration.
        raise LibraryConfigError("embedding.dimensions must be 768 (library_chunks.embedding is vector(768))")
    if e.provider == "medcpt" and not (e.document_model and e.query_model and e.version):
        raise LibraryConfigError("embedding: document_model, query_model and version are required")
    if not 0 <= c.overlap_tokens < c.target_tokens:
        raise LibraryConfigError("chunking: need 0 <= overlap_tokens < target_tokens")
    if not 1 <= s.default_k <= s.max_k <= 10:
        raise LibraryConfigError("search: need 1 <= default_k <= max_k <= 10 (§6 cap)")
    for key in ("{document_id}", "{page}"):
        if key not in cfg.viewer_url:
            raise LibraryConfigError(f"viewer_url must contain {key}")


def load_library_config(path: Optional[Union[str, Path]] = None) -> LibraryConfig:
    path = Path(path) if path else DEFAULT_LIBRARY_CONFIG_PATH
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise LibraryConfigError(f"{path}: invalid YAML: {exc}") from exc
    return parse_library_config(data)
