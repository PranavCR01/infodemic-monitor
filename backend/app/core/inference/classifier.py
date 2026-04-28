"""InferenceProvider Protocol — defines the interface all providers must satisfy.

Usage:
    from app.core.inference.classifier import InferenceProvider

    def my_func(provider: InferenceProvider) -> ClassificationResult:
        return provider.classify(fusion_result)
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.schemas.pipeline import ClassificationResult, FusionResult


@runtime_checkable
class InferenceProvider(Protocol):
    """Interface that every LLM inference provider must implement."""

    def classify(self, fusion: FusionResult) -> ClassificationResult:
        """Classify video content and return a structured verdict."""
        ...
