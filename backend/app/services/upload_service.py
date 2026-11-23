"""Upload safeguards and signed uploads (T20; design §1 "Upload", §15 "Input limits").

``UploadGuard`` applies T10's input limits (``app.core.guardrails.limits``) to an
upload: per-user rate limit and daily quota, then size, container format,
extension/content agreement, truncated-file detection and the duration limit.

Two paths use it:

- the signed flow (always on): ``POST /v1/videos/uploads`` hands out a signed
  Supabase Storage URL for one object under ``uploads/<user>/<upload_id>/``;
  ``POST /v1/videos`` downloads that object once, validates it, hashes it and
  registers the video (reusing an earlier video with the same SHA-256);
- the legacy ``POST /videos/upload`` route, only when ``UPLOAD_SAFEGUARDS`` is on
  (default off, so existing clients see no change).

The rate limiter and quota are in-process (T10): with several API workers each
keeps its own count, so the effective limit is ``workers x limit`` until they move
to a shared store.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import HTTPException

from app.core.guardrails.config import InputLimits, load_guardrails
from app.core.guardrails.limits import (
    DailyQuota,
    InputRejected,
    MediaCheck,
    RateLimiter,
    check_duration,
    validate_media,
)
from app.core.guardrails.media_probe import probe_duration

# InputRejected.code -> HTTP status. Codes are stable and safe to show a user.
STATUS_BY_CODE = {
    "file_too_large": 413,
    "unsupported_media": 415,
    "media_mismatch": 415,
    "empty_file": 422,
    "corrupt_media": 422,
    "too_short": 422,
    "too_long": 422,
    "rate_limited": 429,
    "quota_exceeded": 429,
}

ALLOWED_EXTENSIONS = {"mp4", "m4v", "mov", "webm", "mkv"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def rejection_to_http(exc: InputRejected) -> HTTPException:
    message = str(exc).split(": ", 1)[-1]
    return HTTPException(status_code=STATUS_BY_CODE.get(exc.code, 422), detail={"code": exc.code, "message": message})


def safe_component(value: str, fallback: str, max_len: int = 100) -> str:
    """A path component with only ``[A-Za-z0-9._-]``, no leading dots, bounded length."""
    cleaned = re.sub(r"\.{2,}", ".", _SAFE.sub("_", value or "")).lstrip(".")[:max_len]
    return cleaned or fallback


def user_prefix(user: dict) -> str:
    return f"uploads/{safe_component(str(user.get('sub') or ''), 'anonymous', 64)}/"


def storage_key_for(user: dict, upload_id: str, filename: str) -> str:
    return f"{user_prefix(user)}{upload_id}/{safe_component(filename, 'upload.mp4')}"


_KEY_RE = re.compile(r"uploads/[A-Za-z0-9._-]+/[0-9a-f]{32}/[A-Za-z0-9_-][A-Za-z0-9._-]*")


def owns_key(user: dict, storage_key: str) -> bool:
    """Whether ``storage_key`` is a well-formed signed-upload key of this user."""
    return bool(_KEY_RE.fullmatch(storage_key or "")) and storage_key.startswith(user_prefix(user)) \
        and ".." not in storage_key


@dataclass(frozen=True)
class CheckedMedia:
    media: MediaCheck
    duration_seconds: float


class UploadGuard:
    def __init__(
        self,
        limits: Optional[InputLimits] = None,
        probe: Callable[[bytes, str], Optional[float]] = probe_duration,
        rate_limiter: Optional[RateLimiter] = None,
        quota: Optional[DailyQuota] = None,
    ):
        self.limits = limits or load_guardrails().input
        self._probe = probe
        self.rate_limiter = rate_limiter or RateLimiter.from_config(self.limits)
        self.quota = quota or DailyQuota.from_config(self.limits)

    # -- per user
    def hit_rate(self, user: dict) -> None:
        self.rate_limiter.hit(str(user.get("sub") or "anonymous"))

    def consume_quota(self, user: dict) -> int:
        return self.quota.consume(str(user.get("sub") or "anonymous"))

    # -- before an upload (signed flow): what the client declares
    def check_declared(self, filename: str, size_bytes: Optional[int]) -> None:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
        if ext and ext not in ALLOWED_EXTENSIONS:
            raise InputRejected("unsupported_media", f".{ext} is not a supported video type")
        if size_bytes is not None:
            if size_bytes <= 0:
                raise InputRejected("empty_file", "the upload is empty")
            if size_bytes > self.limits.max_file_bytes:
                raise InputRejected("file_too_large", f"{size_bytes} bytes > {self.limits.max_file_bytes}")

    # -- on the bytes themselves
    def check_media(self, content: bytes, filename: str = "") -> CheckedMedia:
        media = validate_media(content, filename, self.limits)
        duration = check_duration(self._probe(content, media.container), self.limits)
        return CheckedMedia(media=media, duration_seconds=duration)


_guard: Optional[UploadGuard] = None


def get_upload_guard() -> UploadGuard:
    """FastAPI dependency: one guard per process (so the rate limit and quota count)."""
    global _guard
    if _guard is None:
        _guard = UploadGuard()
    return _guard


def new_upload_id() -> str:
    return uuid.uuid4().hex
