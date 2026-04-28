"""Transcription module — faster-whisper (local CPU) or OpenAI Whisper-1.

Provider selected via settings.WHISPER_PROVIDER.
"""
from __future__ import annotations

import logging
import os

from app.core.config import settings
from app.core.exceptions import TranscriptionError

logger = logging.getLogger(__name__)

_OPENAI_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

_whisper_model = None


def _cuda_available() -> bool:
    """Return True only when a CUDA device exists AND libcublas is loadable.

    ctranslate2 on Linux (PyPI) does not bundle CUDA libs — they must be
    present on the host / in the container image. Checking get_cuda_device_count()
    alone is insufficient because the GPU may be visible via the NVIDIA runtime
    while libcublas.so.12 is absent, causing a RuntimeError on first inference.
    """
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0:
            return False
        import ctypes
        ctypes.CDLL("libcublas.so.12")
        return True
    except Exception:
        return False


def get_whisper_model():
    """Return the module-level faster-whisper singleton, initializing on first call."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        device, compute_type = ("cuda", "float16") if _cuda_available() else ("cpu", "int8")
        logger.info(
            "Loading faster-whisper model '%s' on %s (%s)",
            settings.WHISPER_MODEL_SIZE, device, compute_type,
        )
        _whisper_model = WhisperModel(
            settings.WHISPER_MODEL_SIZE,
            device=device,
            compute_type=compute_type,
        )
        logger.info("faster-whisper model loaded")
    return _whisper_model


def transcribe(video_path: str) -> str:
    """Transcribe audio from a video file. Returns the transcript string.

    Raises TranscriptionError on failure.
    """
    provider = settings.WHISPER_PROVIDER
    if provider == "openai":
        return _transcribe_openai(video_path)
    return _transcribe_faster_whisper(video_path)


def _transcribe_faster_whisper(video_path: str) -> str:
    try:
        model = get_whisper_model()
        segments, _ = model.transcribe(video_path, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as exc:
        raise TranscriptionError(provider="faster_whisper", cause=exc) from exc


def _transcribe_openai(video_path: str) -> str:
    file_size = os.path.getsize(video_path)
    if file_size > _OPENAI_MAX_BYTES:
        raise TranscriptionError(
            provider="openai",
            cause=ValueError(
                f"File is {file_size / 1024 / 1024:.1f} MB — "
                f"OpenAI Whisper-1 limit is 25 MB."
            ),
        )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        with open(video_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        return resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError(provider="openai", cause=exc) from exc
