"""Read a video's duration for the §15 duration limit (T20).

MP4/MOV durations come straight from the ``mvhd`` box, so the common case needs
no external tool. Matroska/WebM files go through ``ffprobe`` (installed in the
backend image with ffmpeg). Any failure returns ``None``, which
``limits.check_duration`` turns into ``corrupt_media``: a file whose duration
can't be read is not worth a worker.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Optional

_CONTAINER_BOXES = {b"moov", b"trak", b"mdia"}


def _iter_boxes(buf: bytes, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(buf[pos:pos + 4], "big")
        kind = buf[pos + 4:pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size, header = int.from_bytes(buf[pos + 8:pos + 16], "big"), 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield kind, pos + header, pos + size
        pos += size


def iso_duration(content: bytes) -> Optional[float]:
    """Duration in seconds from ``moov/mvhd``, or ``None`` if absent or unreadable."""
    for kind, body, end in _iter_boxes(content, 0, len(content)):
        if kind != b"moov":
            continue
        for sub, sbody, send in _iter_boxes(content, body, end):
            if sub != b"mvhd" or send - sbody < 20:
                continue
            version = content[sbody]
            if version == 1:
                if send - sbody < 32:
                    return None
                timescale = int.from_bytes(content[sbody + 20:sbody + 24], "big")
                duration = int.from_bytes(content[sbody + 24:sbody + 32], "big")
            else:
                timescale = int.from_bytes(content[sbody + 12:sbody + 16], "big")
                duration = int.from_bytes(content[sbody + 16:sbody + 20], "big")
            if timescale <= 0:
                return None
            return duration / timescale
    return None


def ffprobe_duration(content: bytes, suffix: str = "", timeout: float = 30.0) -> Optional[float]:
    """Duration via ``ffprobe``; ``None`` if ffprobe is missing, fails or times out."""
    exe = shutil.which("ffprobe")
    if exe is None:
        return None
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        proc = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, timeout=timeout, check=False,
        )
        if proc.returncode != 0:
            return None
        value = json.loads(proc.stdout or b"{}").get("format", {}).get("duration")
        return float(value) if value is not None else None
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def probe_duration(content: bytes, container: str) -> Optional[float]:
    if container in ("mp4", "mov"):
        return iso_duration(content)
    return ffprobe_duration(content, suffix=f".{container}")
