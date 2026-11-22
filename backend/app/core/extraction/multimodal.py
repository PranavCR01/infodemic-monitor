"""Multimodal fusion — builds FusionResult from transcript only.

OCR is disabled; the pipeline runs on transcript alone.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.extraction import transcription
from app.core.extraction.transcription import transcribe
from app.core.schemas.pipeline import FusionResult


class ContentTooLongError(Exception):
    """Raised when content exceeds the provider limit."""


class MultimodalFusion:
    """Fuse audio transcript into a FusionResult (OCR disabled)."""

    def fuse(self, video_path: str, *, keep_segments: bool = False) -> FusionResult:
        """Run transcription and return a FusionResult.

        ``keep_segments=True`` (graph pipeline only, T11) also keeps Whisper's timed
        segments in ``metadata["transcript_segments"]``; the default is unchanged.
        """
        segments: list[dict] | None = None
        if keep_segments:
            transcript, segments = transcription.transcribe_segments(video_path)
        else:
            transcript = transcribe(video_path)

        combined = f"[AUDIO TRANSCRIPT]\n{transcript}" if transcript else ""

        if len(combined) > settings.MAX_INPUT_CHARS:
            raise ContentTooLongError(
                f"Transcript is {len(combined):,} chars — "
                f"exceeds limit of {settings.MAX_INPUT_CHARS:,} chars."
            )

        metadata = {
            "audio_length_chars": len(transcript),
            "visual_length_chars": 0,
            "frames_processed": 0,
            "ocr_detection_count": 0,
            "ocr_disabled": True,
        }
        if segments is not None:
            metadata["transcript_segments"] = segments
        return FusionResult(
            transcript=transcript,
            visual_text="",
            combined_content=combined,
            metadata=metadata,
        )
