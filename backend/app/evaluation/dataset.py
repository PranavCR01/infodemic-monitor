"""The shared, versioned evaluation dataset (design doc section 14).

Reads the claim-level dataset layout already used by the claim-level track
(``research/claim-level/dataset``: ``videos.csv`` + ``claims.csv``, see its
README), so every track scores against the same set. Optional extra columns:

- ``videos.csv``: ``categories`` (``;``-separated hard-case tags, see
  ``HARD_CASE_CATEGORIES``), ``split`` (``tune`` / ``test``).
- ``claims.csv``: ``source`` (``speech`` / ``screen`` / ``both``),
  ``relevant_pmids`` (``;``-separated, for retrieval metrics).
- ``inputs.jsonl``: one ``{"video_id", "transcript", "visual_text"}`` object per
  video, the text the systems under test are given.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from app.core.schemas.pipeline import FusionResult, MisinfoLabel
from app.evaluation import metrics

# Claim truth (section 14: "supported, contradicted, insufficient"). The
# claim-level dataset README uses the video label names at claim level; they are
# mapped here so both vocabularies load.
CLAIM_TRUTHS = ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "MIXED", "NOT_VERIFIABLE")
_TRUTH_ALIASES = {
    "MISINFO": "CONTRADICTED",
    "NO_MISINFO": "SUPPORTED",
    "CANNOT_RECOGNIZE": "INSUFFICIENT_EVIDENCE",
    "INSUFFICIENT": "INSUFFICIENT_EVIDENCE",
}
STANCES = ("ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR")
SOURCES = ("speech", "screen", "both")
SPLITS = ("tune", "test")

# Section 14, "Covers the hard cases on purpose".
HARD_CASE_CATEGORIES = (
    "clearly_false",
    "accurate",
    "debunking",
    "neutral_discussion",
    "satire_sarcasm",
    "mixed_claims",
    "screen_only_claim",
    "speech_screen_disagree",
    "noisy_audio",
    "other_language",
    "scientific_uncertainty",
    "missing_evidence",
    "prompt_injection",
    "multi_claim",
)

DATASET_FILES = ("videos.csv", "claims.csv", "inputs.jsonl")


class DatasetError(ValueError):
    pass


class GoldClaim(BaseModel):
    video_id: str
    claim_id: str
    claim_text: str
    truth: str
    stance: str
    evidence_source: str = ""
    source: Optional[str] = None
    relevant_pmids: list[str] = Field(default_factory=list)
    notes: str = ""


class GoldVideo(BaseModel):
    video_id: str
    label: MisinfoLabel
    platform: str = ""
    topic: str = ""
    source_url: str = ""
    categories: list[str] = Field(default_factory=list)
    split: Optional[str] = None
    notes: str = ""
    claims: list[GoldClaim] = Field(default_factory=list)


class VideoInput(BaseModel):
    """What a system under test receives for one video."""

    video_id: str
    fusion: FusionResult


class Dataset(BaseModel):
    name: str
    version: str
    hash: str
    videos: list[GoldVideo]
    inputs: dict[str, VideoInput] = Field(default_factory=dict)

    def video(self, video_id: str) -> GoldVideo:
        for v in self.videos:
            if v.video_id == video_id:
                return v
        raise KeyError(video_id)

    def split(self, name: Optional[str]) -> list[GoldVideo]:
        """Videos in one split. ``None`` or ``"all"`` returns every video."""
        if name in (None, "all"):
            return list(self.videos)
        if name not in SPLITS:
            raise DatasetError(f"unknown split {name!r}; use one of {SPLITS} or 'all'")
        return [v for v in self.videos if v.split == name]

    def coverage(self) -> dict[str, int]:
        """Videos per hard-case category; zero means the category is missing."""
        counts = {c: 0 for c in HARD_CASE_CATEGORIES}
        for v in self.videos:
            for c in v.categories:
                counts[c] = counts.get(c, 0) + 1
        return counts

    def label_inconsistencies(self) -> list[str]:
        """Videos whose label doesn't follow from their claims under the judge rules (section 9)."""
        problems = []
        for v in self.videos:
            if not v.claims:
                continue
            expected = metrics.judge_label([(c.stance, c.truth) for c in v.claims])
            if expected != v.label.value:
                problems.append(
                    f"{v.video_id}: labelled {v.label.value}, claims imply {expected}"
                )
        return problems


# --- Loading ----------------------------------------------------------------

def normalize_truth(raw: str) -> str:
    value = (raw or "").strip().upper()
    value = _TRUTH_ALIASES.get(value, value)
    if value not in CLAIM_TRUTHS:
        raise DatasetError(f"unknown claim truth label {raw!r}")
    return value


def _split_list(raw: Optional[str]) -> list[str]:
    return [p.strip() for p in (raw or "").split(";") if p.strip()]


def assign_split(video_id: str, test_fraction: float = 0.5, seed: str = "infodemic") -> str:
    """Deterministic split by video id, so a video never lands in both splits."""
    digest = hashlib.sha256(f"{seed}:{video_id}".encode()).hexdigest()
    return "test" if int(digest[:8], 16) / 0xFFFFFFFF < test_fraction else "tune"


def dataset_hash(directory: str | Path) -> str:
    """sha256 over the dataset files' names and bytes, recorded on every run."""
    directory = Path(directory)
    h = hashlib.sha256()
    for name in DATASET_FILES:
        path = directory / name
        if path.exists():
            h.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise DatasetError(f"missing dataset file: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            {k.strip(): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(fh)
        ]


def load_dataset(
    directory: str | Path,
    *,
    version: str = "unversioned",
    name: Optional[str] = None,
    test_fraction: float = 0.5,
    expected_hash: Optional[str] = None,
) -> Dataset:
    directory = Path(directory)
    digest = dataset_hash(directory)
    if expected_hash and expected_hash != digest:
        raise DatasetError(
            f"dataset hash mismatch: config pins {expected_hash}, files hash to {digest}"
        )

    videos: dict[str, GoldVideo] = {}
    for row in _read_csv(directory / "videos.csv"):
        vid = row.get("video_id", "")
        if not vid:
            raise DatasetError("videos.csv row without video_id")
        if vid in videos:
            raise DatasetError(f"duplicate video_id {vid!r}")
        try:
            label = MisinfoLabel(row.get("video_level_label", "").upper())
        except ValueError:
            raise DatasetError(f"{vid}: unknown video label {row.get('video_level_label')!r}") from None
        categories = _split_list(row.get("categories"))
        unknown = [c for c in categories if c not in HARD_CASE_CATEGORIES]
        if unknown:
            raise DatasetError(f"{vid}: unknown categories {unknown}")
        split = row.get("split") or assign_split(vid, test_fraction)
        if split not in SPLITS:
            raise DatasetError(f"{vid}: unknown split {split!r}")
        videos[vid] = GoldVideo(
            video_id=vid, label=label, platform=row.get("platform", ""),
            topic=row.get("topic", ""), source_url=row.get("source_url", ""),
            categories=categories, split=split, notes=row.get("notes", ""),
        )

    seen: set[tuple[str, str]] = set()
    for row in _read_csv(directory / "claims.csv"):
        vid, cid = row.get("video_id", ""), row.get("claim_id", "")
        if vid not in videos:
            raise DatasetError(f"claims.csv refers to unknown video {vid!r}")
        if (vid, cid) in seen:
            raise DatasetError(f"duplicate claim {vid}/{cid}")
        seen.add((vid, cid))
        stance = row.get("speaker_stance", "").upper()
        if stance not in STANCES:
            raise DatasetError(f"{vid}/{cid}: unknown stance {stance!r}")
        source = (row.get("source") or "").lower() or None
        if source is not None and source not in SOURCES:
            raise DatasetError(f"{vid}/{cid}: unknown source {source!r}")
        try:
            truth = normalize_truth(row.get("ground_truth_label", ""))
        except DatasetError as exc:
            raise DatasetError(f"{vid}/{cid}: {exc}") from None
        videos[vid].claims.append(GoldClaim(
            video_id=vid, claim_id=cid, claim_text=row.get("claim_text", ""),
            truth=truth, stance=stance, evidence_source=row.get("evidence_source", ""),
            source=source, relevant_pmids=_split_list(row.get("relevant_pmids")),
            notes=row.get("notes", ""),
        ))

    inputs = load_inputs(directory / "inputs.jsonl", known=set(videos))
    return Dataset(
        name=name or directory.name, version=version, hash=digest,
        videos=list(videos.values()), inputs=inputs,
    )


def load_inputs(path: Path, known: Iterable[str] = ()) -> dict[str, VideoInput]:
    if not path.exists():
        return {}
    known = set(known)
    out: dict[str, VideoInput] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{path.name}:{n}: invalid JSON ({exc})") from None
        vid = obj.get("video_id")
        if known and vid not in known:
            raise DatasetError(f"{path.name}:{n}: unknown video {vid!r}")
        transcript = obj.get("transcript", "")
        visual = obj.get("visual_text", "")
        combined = obj.get("combined_content") or "\n".join(
            p for p in (f"[SPEECH]\n{transcript}" if transcript else "",
                        f"[ON-SCREEN TEXT]\n{visual}" if visual else "") if p
        )
        out[vid] = VideoInput(video_id=vid, fusion=FusionResult(
            transcript=transcript, visual_text=visual, combined_content=combined,
            metadata=obj.get("metadata", {}),
        ))
    return out


# --- Labeller agreement -----------------------------------------------------

class AgreementReport(BaseModel):
    videos_compared: int
    claims_compared: int
    video_label_kappa: Optional[float]
    claim_truth_kappa: Optional[float]
    stance_kappa: Optional[float]
    disagreements: list[str]


def labeller_agreement(first: Dataset, second: Dataset) -> AgreementReport:
    """Cohen's kappa between two independent labellers on their overlapping items."""
    shared = [v.video_id for v in first.videos if any(s.video_id == v.video_id for s in second.videos)]
    va, vb, ta, tb, sa, sb = [], [], [], [], [], []
    disagreements: list[str] = []
    for vid in shared:
        a, b = first.video(vid), second.video(vid)
        va.append(a.label.value)
        vb.append(b.label.value)
        if a.label != b.label:
            disagreements.append(f"{vid}: video label {a.label.value} vs {b.label.value}")
        b_claims = {c.claim_id: c for c in b.claims}
        for ca in a.claims:
            cb = b_claims.get(ca.claim_id)
            if cb is None:
                disagreements.append(f"{vid}/{ca.claim_id}: only in first labeller's set")
                continue
            ta.append(ca.truth)
            tb.append(cb.truth)
            sa.append(ca.stance)
            sb.append(cb.stance)
            if ca.truth != cb.truth:
                disagreements.append(f"{vid}/{ca.claim_id}: truth {ca.truth} vs {cb.truth}")
            if ca.stance != cb.stance:
                disagreements.append(f"{vid}/{ca.claim_id}: stance {ca.stance} vs {cb.stance}")
        for cid in set(b_claims) - {c.claim_id for c in a.claims}:
            disagreements.append(f"{vid}/{cid}: only in second labeller's set")
    return AgreementReport(
        videos_compared=len(shared), claims_compared=len(ta),
        video_label_kappa=metrics.cohens_kappa(va, vb),
        claim_truth_kappa=metrics.cohens_kappa(ta, tb),
        stance_kappa=metrics.cohens_kappa(sa, sb),
        disagreements=disagreements,
    )
