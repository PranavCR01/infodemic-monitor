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

    if classification.label in (MisinfoLabel.MISINFO, MisinfoLabel.DEBUNKING) and classification.claims:
        from app.core.grounding.pubmed import ground_transcript
        citations = await ground_transcript(classification.claims)

        by_claim: dict[str, list] = {}
        for c in citations:
            by_claim.setdefault(c.claim_id, []).append(c)

        updated_claims = [
            claim.model_copy(update={"citations": by_claim.get(claim.claim_id, [])})
            for claim in classification.claims
        ]
        classification = classification.model_copy(
            update={"claims": updated_claims, "citations": citations}
        )

    return fusion, classification
