"""Read the golden label set for the routing experiment: tune split only.

The set lives on the branch ``data/golden-label-set`` under
``research/claim-level/dataset`` and is read with ``git show``, so nothing is checked
out or merged. A directory with the same layout works too (tests use a tiny fixture).

**Test-split guard.** ``videos.csv`` and ``claims.csv`` are one file each for both
splits, so their rows are read and every row whose video is not in the tune split is
dropped before anything else sees it. A transcript is fetched only for a tune video:
``transcript()`` raises ``TestSplitError`` for any other video id, before any read.
The test split stays untouched for the final evaluation (T14).
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

DEFAULT_REF = "origin/data/golden-label-set"
DEFAULT_BASE = "research/claim-level/dataset"
TUNE = "tune"


class GoldenSetError(ValueError):
    """The golden set could not be read or is malformed."""


class TestSplitError(GoldenSetError):
    """Something asked for a video outside the tune split."""

    __test__ = False  # not a pytest class


class Source(Protocol):
    def read(self, relpath: str) -> str: ...

    def describe(self) -> str: ...


@dataclass(frozen=True)
class GitSource:
    """Files read with ``git show <ref>:<base>/<relpath>``; no checkout, no merge."""

    ref: str = DEFAULT_REF
    base: str = DEFAULT_BASE
    repo: Optional[Path] = None

    def read(self, relpath: str) -> str:
        spec = f"{self.ref}:{self.base.rstrip('/')}/{relpath}"
        try:
            out = subprocess.run(
                ["git", "show", spec], cwd=self.repo, capture_output=True, check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise GoldenSetError(f"git show {spec} failed: {exc.stderr.decode(errors='replace').strip()}") from None
        return out.stdout.decode("utf-8")

    def commit(self) -> str:
        try:
            out = subprocess.run(["git", "rev-parse", self.ref], cwd=self.repo, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            return "unknown"
        return out.stdout.decode().strip()

    def describe(self) -> str:
        return f"git:{self.ref}@{self.commit()[:12]}:{self.base}"


@dataclass(frozen=True)
class DirSource:
    path: Path

    def read(self, relpath: str) -> str:
        p = Path(self.path) / relpath
        if not p.is_file():
            raise GoldenSetError(f"missing golden-set file: {p}")
        return p.read_text(encoding="utf-8")

    def describe(self) -> str:
        return f"dir:{self.path}"


@dataclass(frozen=True)
class GoldClaimRow:
    video_id: str
    claim_id: str
    text: str
    source: str            # speech | screen | both
    kind: str              # research_question | fact_of_record
    start: float
    end: float
    stance: str
    verdict: str
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    notes: str = ""

    @property
    def key(self) -> str:
        return f"{self.video_id}:{self.claim_id}"


@dataclass(frozen=True)
class GoldVideoRow:
    video_id: str
    split: str
    case_tags: tuple[str, ...]
    out_of_scope: bool
    claims: tuple[GoldClaimRow, ...] = field(default_factory=tuple)


def _float(raw: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _list(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in (raw or "").split(";") if p.strip())


class TuneSet:
    """The tune split of the golden set, and nothing else."""

    def __init__(self, source: Source):
        self.source = source
        videos = list(csv.DictReader(io.StringIO(source.read("videos.csv"))))
        if not videos or "split" not in videos[0]:
            raise GoldenSetError("videos.csv has no 'split' column")
        # Drop every non-tune row immediately; nothing below sees them.
        tune_rows = [v for v in videos if (v.get("split") or "").strip() == TUNE]
        self._tune_ids = frozenset(v["video_id"] for v in tune_rows)
        del videos
        claims: dict[str, list[GoldClaimRow]] = {vid: [] for vid in self._tune_ids}
        for row in csv.DictReader(io.StringIO(source.read("claims.csv"))):
            vid = row.get("video_id", "")
            if vid not in self._tune_ids:
                continue
            claims[vid].append(GoldClaimRow(
                video_id=vid, claim_id=row["claim_id"], text=row["claim_text"].strip(),
                source=(row.get("claim_source") or "speech").strip(),
                kind=(row.get("claim_kind") or "research_question").strip() or "research_question",
                start=_float(row.get("start_seconds", "")), end=_float(row.get("end_seconds", "")),
                stance=row["speaker_stance"].strip().upper(), verdict=row["claim_verdict"].strip().upper(),
                supporting=_list(row.get("evidence_supporting", "")),
                contradicting=_list(row.get("evidence_contradicting", "")),
                notes=row.get("notes", "") or "",
            ))
        self.videos: dict[str, GoldVideoRow] = {}
        for v in tune_rows:
            tags = _list((v.get("case_tags") or "").replace(",", ";"))
            self.videos[v["video_id"]] = GoldVideoRow(
                video_id=v["video_id"], split=TUNE, case_tags=tags,
                out_of_scope="out_of_scope" in tags,
                claims=tuple(claims.get(v["video_id"], [])),
            )

    @property
    def video_ids(self) -> list[str]:
        return sorted(self.videos, key=_natural)

    def check_tune(self, video_id: str) -> None:
        if video_id not in self._tune_ids:
            raise TestSplitError(
                f"video {video_id!r} is not in the tune split; the routing experiment reads "
                "tune-split videos only (the test split is reserved for T14)"
            )

    def transcript(self, video_id: str) -> dict:
        """The transcript JSON of a tune video. Refuses any other video before reading."""
        self.check_tune(video_id)
        try:
            return json.loads(self.source.read(f"transcripts/{video_id}.json"))
        except json.JSONDecodeError as exc:
            raise GoldenSetError(f"transcripts/{video_id}.json is not JSON: {exc}") from None

    def reference_passages(self) -> dict[str, list[dict]]:
        """Quoted §6 reference passages per ``video:claim`` (tune claims only)."""
        try:
            text = self.source.read("reference_citations.csv")
        except GoldenSetError:
            return {}
        out: dict[str, list[dict]] = {}
        for row in csv.DictReader(io.StringIO(text)):
            if row.get("video_id") not in self._tune_ids:
                continue
            out.setdefault(f"{row['video_id']}:{row['claim_id']}", []).append(dict(row))
        return out


def _natural(video_id: str) -> tuple:
    digits = "".join(ch for ch in video_id if ch.isdigit())
    return (int(digits) if digits else 0, video_id)
