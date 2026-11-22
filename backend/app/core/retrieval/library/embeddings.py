"""Embeddings (§6 "Building the library" step 5).

MedCPT, NCBI's biomedical retrieval model, with separate encoders for documents and
queries (768 dimensions). It runs in our own process, so document text is never sent to
an outside API. The model names and version come from ``config/library.yaml``; every chunk
records the embedding model and version it was embedded with.

``HashingEmbedder`` is a deterministic stand-in with no model behind it (feature hashing
of words and word pairs). It exists for tests and for running the pipeline without the
model weights; it matches words, not meaning, and must not be used for the real library.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Callable, Optional, Protocol, Sequence

from app.core.retrieval.library.config import EmbeddingConfig

Vector = list[float]


class Embedder(Protocol):
    model_name: str  # recorded on every chunk, e.g. "<document_model>|<query_model>"
    model_version: str
    dimensions: int

    def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[Vector]:
        """Embed ``(title, chunk_text)`` pairs."""
        ...

    def embed_query(self, text: str) -> Vector: ...


def _normalise(v: Sequence[float]) -> Vector:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class MedCptEmbedder:
    """MedCPT article and query encoders via Hugging Face ``transformers`` (CLS pooling,
    as the model card describes). ``transformers`` and ``torch`` are imported lazily; tests
    inject ``loader`` instead of downloading weights.

    ``loader(model_id) -> (tokenizer, model)``.
    """

    def __init__(self, cfg: EmbeddingConfig, loader: Optional[Callable[[str], tuple[Any, Any]]] = None,
                 device: str = "cpu") -> None:
        if not (cfg.document_model and cfg.query_model):
            raise ValueError("MedCPT needs embedding.document_model and embedding.query_model in config")
        self.cfg = cfg
        self.model_name = f"{cfg.document_model}|{cfg.query_model}"
        self.model_version = cfg.version
        self.dimensions = cfg.dimensions
        self._loader = loader or self._hf_loader
        self._device = device
        self._doc: Optional[tuple[Any, Any]] = None
        self._query: Optional[tuple[Any, Any]] = None

    def _hf_loader(self, model_id: str):
        from transformers import AutoModel, AutoTokenizer  # type: ignore

        tok = AutoTokenizer.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id).to(self._device)
        model.eval()
        return tok, model

    def _encode(self, which: str, inputs: Any, max_length: int) -> list[Vector]:
        if which == "doc":
            self._doc = self._doc or self._loader(self.cfg.document_model)
            tok, model = self._doc
        else:
            self._query = self._query or self._loader(self.cfg.query_model)
            tok, model = self._query
        try:
            import torch  # type: ignore

            ctx = torch.no_grad()
        except ImportError:  # injected test doubles
            import contextlib

            ctx = contextlib.nullcontext()
        with ctx:
            enc = tok(inputs, truncation=True, padding=True, return_tensors="pt", max_length=max_length)
            if hasattr(enc, "to"):
                enc = enc.to(self._device)
            out = model(**enc).last_hidden_state[:, 0, :]
        rows = out.tolist() if hasattr(out, "tolist") else list(out)
        for r in rows:
            if len(r) != self.dimensions:
                raise ValueError(f"encoder returned {len(r)} dimensions, config says {self.dimensions}")
        return [list(map(float, r)) for r in rows]

    def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[Vector]:
        out: list[Vector] = []
        bs = max(1, self.cfg.batch_size)
        for i in range(0, len(items), bs):
            batch = [[title, text] for title, text in items[i : i + bs]]
            out.extend(self._encode("doc", batch, self.cfg.max_document_tokens))
        return out

    def embed_query(self, text: str) -> Vector:
        return self._encode("query", [text], self.cfg.max_query_tokens)[0]


_WORD = re.compile(r"[a-z0-9]+")


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ing", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


class HashingEmbedder:
    """Deterministic word-hashing embedder for tests and model-free runs. Not MedCPT."""

    model_name = "hashing-dev"
    model_version = "1"

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions

    def _vec(self, text: str) -> Vector:
        v = [0.0] * self.dimensions
        words = [_stem(w) for w in _WORD.findall(text.lower()) if len(w) > 2]
        feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
        for f in feats:
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dimensions
            v[idx] += 1.0 if h[4] & 1 else -1.0
        return _normalise(v)

    def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[Vector]:
        return [self._vec(f"{title} {text}") for title, text in items]

    def embed_query(self, text: str) -> Vector:
        return self._vec(text)


def embedder_from_config(cfg: EmbeddingConfig) -> Embedder:
    if cfg.provider == "medcpt":
        return MedCptEmbedder(cfg)
    if cfg.provider == "hashing":
        return HashingEmbedder(cfg.dimensions)
    raise ValueError(f"unknown embedding provider {cfg.provider!r}")
