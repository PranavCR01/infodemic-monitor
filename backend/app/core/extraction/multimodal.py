"""Multimodal fusion — builds FusionResult from the transcript and, when
``OCR_PROVIDER=vision``, the on-screen text read by ``vision_ocr`` (off by default).

With OCR on, the on-screen text is routed by kind (T68, ``screen_text``): title and
claim cards (and subtitles that match nothing said) reach extraction; subtitles that
repeat the speech are dropped; documents and charts become one-line notes in
``metadata["ocr_documents"]``, never extraction input. With OCR off nothing here runs
and the result is byte-identical to before.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.extraction import screen_text, transcription, vision_ocr
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

        ocr_segs = vision_ocr.extract_on_screen_text(video_path) if vision_ocr.enabled() else []
        routed = None
        if ocr_segs:
            routed = screen_text.route(ocr_segs, screen_text.spoken_from(segments, transcript))
            ocr_segs = routed.to_extraction
        visual_text = "\n".join(dict.fromkeys(s.text for s in ocr_segs))

        parts = []
        if transcript:
            parts.append(f"[AUDIO TRANSCRIPT]\n{transcript}")
        if visual_text:
            parts.append(f"[ON-SCREEN TEXT]\n{visual_text}")
        combined = "\n\n".join(parts)

        if len(combined) > settings.MAX_INPUT_CHARS:
            raise ContentTooLongError(
                f"Transcript is {len(combined):,} chars — "
                f"exceeds limit of {settings.MAX_INPUT_CHARS:,} chars."
            )

        metadata = {
            "audio_length_chars": len(transcript),
            "visual_length_chars": len(visual_text),
            "frames_processed": 0,
            "ocr_detection_count": len(ocr_segs),
            "ocr_disabled": not vision_ocr.enabled(),
            "ocr_provider": "vision" if vision_ocr.enabled() else "none",
        }
        if ocr_segs:
            metadata["ocr_segments"] = [{"start": s.start, "end": s.end, "text": s.text, "kind": s.kind}
                                        for s in ocr_segs]
        if routed is not None:
            metadata["ocr_routing"] = routed.counts()
            if routed.documents:
                metadata["ocr_documents"] = [{"start": d.start, "end": d.end, "note": d.text}
                                             for d in routed.documents]
        if segments is not None:
            metadata["transcript_segments"] = segments
        return FusionResult(
            transcript=transcript,
            visual_text=visual_text,
            combined_content=combined,
            metadata=metadata,
        )
