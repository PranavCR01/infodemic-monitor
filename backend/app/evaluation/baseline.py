"""The baseline: today's single-call classifier, wrapped as an EvaluationSystem.

Any ``InferenceProvider`` works, so tests pass a fake and paid runs pass the
real provider. The model id comes from the provider's own result, not from here.
"""
from __future__ import annotations

from typing import Any

from app.core.inference.classifier import InferenceProvider
from app.evaluation.dataset import VideoInput
from app.evaluation.records import VideoPrediction


class SingleCallBaseline:
    def __init__(self, provider: InferenceProvider, name: str = "baseline"):
        self.provider = provider
        self.name = name
        self._seen: dict[str, str] = {}

    def predict(self, video: VideoInput) -> VideoPrediction:
        result = self.provider.classify(video.fusion)
        self._seen = {"provider": result.provider, "model": result.model_used}
        return VideoPrediction(
            video_id=video.video_id,
            label=result.label,
            confidence=result.confidence,
            explanation=result.explanation,
            claims=None,  # the baseline produces no claims; claim metrics are not applicable
            latency_ms=result.latency_ms,
            trace=[{"step": "classify", "provider": result.provider, "model": result.model_used}],
        )

    def versions(self) -> dict[str, Any]:
        return {"classify": dict(self._seen)} if self._seen else {}
