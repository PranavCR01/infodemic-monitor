"""Optional learned relevance scorer for the reranker (T60, design §6 "Reranking").

``CrossEncoderRelevance`` implements ``rerank.RelevanceModel`` with a biomedical
cross-encoder run locally on CPU: by default ``ncbi/MedCPT-Cross-Encoder`` (PubMed
query-article relevance). It is **not** the default scorer: T60 measured it against the
lexical scorer and kept lexical (``evals/reports/T60/README.md``). It exists so the
comparison can be rerun and so a deployment can opt in.

- ``torch`` and ``transformers`` are imported lazily and are not in ``requirements.txt``;
  the API and worker images don't change unless someone opts in.
- Weights are downloaded from Hugging Face on first use (or at image build time with
  ``CrossEncoderRelevance.download()``) into the normal Hugging Face cache. They are never
  committed.
- The model returns an unbounded logit per (claim, paper) pair; ``squash`` maps it to
  [0, 1] with a sigmoid, so ``RerankConfig.min_relevance`` reads as a probability-like cut.
"""
from __future__ import annotations

import math
import os
from typing import Optional, Sequence

from app.core.retrieval.schemas import EvidenceRecord

DEFAULT_MODEL = "ncbi/MedCPT-Cross-Encoder"
MAX_LENGTH = 512
BATCH = 16


class CrossEncoderRelevance:
    """``RelevanceModel``: one score in [0, 1] per record, in order."""

    squash_doc = "sigmoid(logit)"

    def __init__(self, model_name: Optional[str] = None, *, threads: Optional[int] = None,
                 max_length: int = MAX_LENGTH, batch_size: int = BATCH) -> None:
        self.model_name = model_name or os.environ.get("RERANK_CROSS_ENCODER_MODEL", DEFAULT_MODEL)
        self.threads = threads
        self.max_length = max_length
        self.batch_size = batch_size
        self._tok = None
        self._model = None

    @classmethod
    def download(cls, model_name: Optional[str] = None) -> None:
        """Fetch the weights into the Hugging Face cache (for a build step)."""
        cls(model_name)._load()

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            if self.threads:
                torch.set_num_threads(self.threads)
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self._model.eval()
        return self._tok, self._model

    @staticmethod
    def passage(record: EvidenceRecord) -> str:
        return f"{record.title} {record.abstract}".strip()

    def logits(self, claim_text: str, records: Sequence[EvidenceRecord]) -> list[float]:
        if not records:
            return []
        import torch

        tok, model = self._load()
        out: list[float] = []
        for i in range(0, len(records), self.batch_size):
            batch = records[i : i + self.batch_size]
            enc = tok([[claim_text, self.passage(r)] for r in batch], truncation=True, padding=True,
                      max_length=self.max_length, return_tensors="pt")
            with torch.inference_mode():
                out.extend(float(x) for x in model(**enc).logits.squeeze(dim=1).tolist())
        return out

    @staticmethod
    def squash(logit: float) -> float:
        return 1.0 / (1.0 + math.exp(-logit))

    def __call__(self, claim_text: str, records: Sequence[EvidenceRecord]) -> list[float]:
        return [self.squash(x) for x in self.logits(claim_text, records)]


__all__ = ["CrossEncoderRelevance", "DEFAULT_MODEL"]
