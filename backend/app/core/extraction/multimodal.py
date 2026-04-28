"""Multimodal fusion — builds FusionResult from transcript only.

OCR is disabled; the pipeline runs on transcript alone.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.extraction.transcription import transcribe
from app.core.schemas.pipeline import FusionResult


class ContentTooLongError(Exception):
    """Raised when content exceeds the provider limit."""


class MultimodalFusion:
    """Fuse audio transcript into a FusionResult (OCR disabled)."""

    def fuse(self, video_path: str) -> FusionResult:
        """Run transcription and return a FusionResult."""
        transcript = transcribe(video_path)

        combined = f"[AUDIO TRANSCRIPT]\n{transcript}" if transcript else ""

        if len(combined) > settings.MAX_INPUT_CHARS:
            raise ContentTooLongError(
                f"Transcript is {len(combined):,} chars — "
                f"exceeds limit of {settings.MAX_INPUT_CHARS:,} chars."
            )

        return FusionResult(
            transcript=transcript,
            visual_text="",
            combined_content=combined,
            metadata={
                "audio_length_chars": len(transcript),
                "visual_length_chars": 0,
                "frames_processed": 0,
                "ocr_detection_count": 0,
                "ocr_disabled": True,
            },
        )
