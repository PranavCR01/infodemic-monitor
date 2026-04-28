from __future__ import annotations

from app.core.extraction.multimodal import MultimodalFusion
from app.core.inference import get_provider
from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel


async def run_pipeline(video_path: str) -> tuple[FusionResult, ClassificationResult]:
    """Full pipeline: video file → (FusionResult, ClassificationResult).

    Sync steps (transcription, inference) run in the calling thread.
    Grounding is async and runs only for MISINFO and DEBUNKING.
    """
    fusion = MultimodalFusion().fuse(video_path)
    provider = get_provider()
    classification = provider.classify(fusion)

    if classification.label in (MisinfoLabel.MISINFO, MisinfoLabel.DEBUNKING):
        from app.core.grounding.pubmed import ground_transcript
        citations = await ground_transcript(fusion.transcript)
        classification = classification.model_copy(update={"citations": citations})

    return fusion, classification
