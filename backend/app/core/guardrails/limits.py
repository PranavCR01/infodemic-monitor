"""Input limits (§15 "Input and tool limits").

File size and duration limits, media validation by content (not by file name),
corrupt-file handling, duplicate detection, per-user quotas and rate limits, and
caps on what a video can make the graph do (segments, block size, claims).

Nothing here is wired into the live upload path yet: that would change today's
behaviour, so it belongs to the integration task (T11), behind its flag.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence, TypeVar

from app.core.guardrails.config import InputLimits, load_guardrails

T = TypeVar("T")


class InputRejected(ValueError):
    """An input broke a limit. ``code`` is stable and safe to show a user."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _limits(limits: Optional[InputLimits]) -> InputLimits:
    return limits or load_guardrails().input


# ------------------------------------------------------------ media checks

_ISO_BRANDS_MOV = {b"qt  "}


def sniff_container(head: bytes) -> Optional[str]:
    """The container format from the first bytes, or ``None`` if unrecognised."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mov" if head[8:12] in _ISO_BRANDS_MOV else "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":  # EBML: Matroska or WebM
        return "webm" if b"webm" in head[:64] else "mkv"
    return None


@dataclass(frozen=True)
class MediaCheck:
    container: str
    size_bytes: int
    sha256: str


def validate_media(content: bytes, filename: str = "", limits: Optional[InputLimits] = None) -> MediaCheck:
    """Reject empty, oversized, unrecognised or truncated uploads.

    The format comes from the bytes; the file name is only used to catch an
    extension that disagrees with the content.
    """
    lim = _limits(limits)
    if not content:
        raise InputRejected("empty_file", "the upload is empty")
    if len(content) > lim.max_file_bytes:
        raise InputRejected("file_too_large", f"{len(content)} bytes > {lim.max_file_bytes}")
    container = sniff_container(content[:64])
    if container is None:
        raise InputRejected("unsupported_media", "not a recognised video container")
    if container not in lim.allowed_containers:
        raise InputRejected("unsupported_media", f"{container} is not an allowed format")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    compatible = {"mp4": {"mp4", "m4v"}, "mov": {"mov", "mp4"}, "webm": {"webm", "mkv"}, "mkv": {"mkv", "webm"}}
    if ext and ext not in compatible[container]:
        raise InputRejected("media_mismatch", f".{ext} file contains {container} data")
    if container in ("mp4", "mov") and not _iso_boxes_ok(content):
        raise InputRejected("corrupt_media", "the file's box structure is truncated or invalid")
    return MediaCheck(container=container, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())


def _iso_boxes_ok(content: bytes) -> bool:
    """Walk top-level ISO-BMFF boxes; the sizes must tile the file and include moov.

    Catches the usual corrupt upload (a file cut off mid-transfer) before ffmpeg
    spends a worker on it.
    """
    pos, seen = 0, set()
    n = len(content)
    while pos < n:
        if pos + 8 > n:
            return False
        size = int.from_bytes(content[pos:pos + 4], "big")
        kind = content[pos + 4:pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > n:
                return False
            size, header = int.from_bytes(content[pos + 8:pos + 16], "big"), 16
        elif size == 0:
            size = n - pos
        if size < header or pos + size > n:
            return False
        seen.add(kind)
        pos += size
    return b"ftyp" in seen and b"moov" in seen


def check_duration(seconds: Optional[float], limits: Optional[InputLimits] = None) -> float:
    """Duration comes from the media probe (extraction layer); this applies the limit."""
    lim = _limits(limits)
    if seconds is None or seconds != seconds or seconds <= 0:  # None, NaN, 0
        raise InputRejected("corrupt_media", "duration could not be read")
    if seconds < lim.min_duration_seconds:
        raise InputRejected("too_short", f"{seconds:.1f}s < {lim.min_duration_seconds}s")
    if seconds > lim.max_duration_seconds:
        raise InputRejected("too_long", f"{seconds:.0f}s > {lim.max_duration_seconds}s")
    return seconds


# -------------------------------------------------------------- duplicates


class DuplicateDetector:
    """Exact-duplicate detection by SHA-256. ``lookup`` lets production ask the
    database (``videos.file_hash``); the in-memory map covers one process."""

    def __init__(self, lookup: Optional[Callable[[str], Optional[str]]] = None):
        self._lookup = lookup
        self._seen: dict[str, str] = {}
        self._lock = threading.Lock()

    def check(self, sha256: str, video_id: str) -> Optional[str]:
        """The existing video's ID if ``sha256`` was seen before, else record it."""
        with self._lock:
            if sha256 in self._seen:
                return self._seen[sha256]
            existing = self._lookup(sha256) if self._lookup else None
            if existing:
                self._seen[sha256] = existing
                return existing
            self._seen[sha256] = video_id
            return None


# ------------------------------------------------------- quotas and rates


class RateLimiter:
    """Sliding-window limit per key (user). In-process; a multi-worker deployment
    needs a shared store (Redis) behind the same interface."""

    def __init__(self, requests: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.requests, self.window, self._clock = requests, window_seconds, clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, limits: Optional[InputLimits] = None, **kw) -> "RateLimiter":
        lim = _limits(limits)
        return cls(lim.rate_limit.requests, lim.rate_limit.window_seconds, **kw)

    def hit(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.requests:
                retry = self.window - (now - q[0])
                raise InputRejected("rate_limited", f"try again in {retry:.0f}s")
            q.append(now)


class DailyQuota:
    """Uploads per user per UTC day."""

    def __init__(self, per_day: int, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.per_day, self._clock = per_day, clock
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, limits: Optional[InputLimits] = None, **kw) -> "DailyQuota":
        return cls(_limits(limits).uploads_per_user_per_day, **kw)

    def consume(self, user_id: str) -> int:
        day = self._clock().astimezone(timezone.utc).date().isoformat()
        with self._lock:
            if self._counts[(user_id, day)] >= self.per_day:
                raise InputRejected("quota_exceeded", f"{self.per_day} uploads per day")
            self._counts[(user_id, day)] += 1
            return self.per_day - self._counts[(user_id, day)]


# ----------------------------------------------------- caps on graph work


def check_transcript(text: str, limits: Optional[InputLimits] = None) -> None:
    lim = _limits(limits)
    if len(text) > lim.max_transcript_chars:
        raise InputRejected("content_too_long", f"{len(text)} chars > {lim.max_transcript_chars}")


def check_segments(segments: Sequence, limits: Optional[InputLimits] = None) -> None:
    lim = _limits(limits)
    if len(segments) > lim.max_segments:
        raise InputRejected("too_many_segments", f"{len(segments)} > {lim.max_segments}")


def cap_claims(claims: Sequence[T], limits: Optional[InputLimits] = None) -> tuple[list[T], int]:
    """Keep the first ``max_claims_per_video`` claims; return how many were dropped.

    The cap bounds the loop budget (T02's recursion limit assumes 50). Dropping
    claims silently would hide them, so callers must record the count and send the
    run to review when it's non-zero.
    """
    cap = _limits(limits).max_claims_per_video
    kept = list(claims[:cap])
    return kept, max(0, len(claims) - cap)
