from __future__ import annotations

from typing import Any, Optional

from app.core.extraction.multimodal import MultimodalFusion
from app.core.inference import get_provider
from app.core.progress import SEARCHING_EVIDENCE, TRANSCRIBING, VERIFYING, report_step
from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel


async def _ground(fusion: FusionResult, classification: ClassificationResult) -> ClassificationResult:
    """Today's post-hoc PubMed grounding, for MISINFO and DEBUNKING only."""
    if classification.label in (MisinfoLabel.MISINFO, MisinfoLabel.DEBUNKING):
        from app.core.grounding.pubmed import ground_transcript
        report_step(SEARCHING_EVIDENCE)
        citations = await ground_transcript(fusion.transcript)
        classification = classification.model_copy(update={"citations": citations})
    return classification


async def run_pipeline(video_path: str) -> tuple[FusionResult, ClassificationResult]:
    """Full pipeline: video file → (FusionResult, ClassificationResult).

    The single-call path (the live path while ``USE_GRAPH_PIPELINE`` is off).
    Sync steps (transcription, inference) run in the calling thread.
    Grounding is async and runs only for MISINFO and DEBUNKING.
    """
    report_step(TRANSCRIBING)
    fusion = MultimodalFusion().fuse(video_path)
    provider = get_provider()
    report_step(VERIFYING)
    classification = provider.classify(fusion)
    classification = await _ground(fusion, classification)
    return fusion, classification


async def run_graph_pipeline(
    video_path: str,
    *,
    job_id: str,
    video_id: Optional[str] = None,
    provider: Any = None,
):
    """Graph path (T11, ``USE_GRAPH_PIPELINE=true``): video file → (FusionResult,
    GraphOutcome).

    Transcription is the same as the single-call path, but keeps Whisper's timed
    segments for the graph. When the graph falls back, the single call's answer gets
    the single call's own PubMed grounding, so a fallback result looks exactly like a
    single-call result (plus the recorded fallback).
    """
    from app.core.inference.providers.graph_provider import build_graph_provider

    report_step(TRANSCRIBING)
    fusion = MultimodalFusion().fuse(video_path, keep_segments=True)
    provider = provider or build_graph_provider()
    outcome = provider.run(fusion, job_id=job_id, video_id=video_id, media_uri=video_path)
    if outcome.fallback_used:
        outcome.classification = await _ground(fusion, outcome.classification)
    return fusion, outcome
