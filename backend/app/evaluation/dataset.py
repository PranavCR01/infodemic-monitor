"""The shared, versioned evaluation dataset (design doc section 14).

Reads the golden label set (``research/claim-level/dataset``; its README is the
schema authority) so every track scores against the same set:

- ``videos.csv``: ``video_id``, ``video_level_label`` (derived by the §9 rules),
  ``misinfo_basis`` (``contradicted`` / ``denies_supported`` / ``unproven``, set only
  for ``MISINFO``), ``review_reasons`` (``;``-separated), ``text_type``, ``case_tags``
  (``;``-separated, see ``HARD_CASE_CATEGORIES`` and ``OTHER_TAGS``), ``split``
  (``tune`` / ``test``), the review fields (``annotator``, ``confidence``,
  ``review_status``, ``reviewer``, ``reviewer_notes``) and the source fields
  (``source``, ``external_label``, ``external_source``, ``external_url``).
- ``claims.csv``: ``video_id``, ``claim_id``, ``claim_text``, ``claim_source``
  (``speech`` / ``screen`` / ``both``), ``claim_kind`` (``research_question`` /
  ``fact_of_record``), ``start_seconds``, ``end_seconds``, ``speaker_stance``,
  ``claim_verdict`` (incl. ``UNSUPPORTED``), ``evidence_supporting`` /
  ``evidence_contradicting`` (``;``-separated ``PMID:<id>`` or §6 reference URLs) and
  the review fields.
- Inputs, the text the systems under test are given: ``inputs.jsonl`` (one
  ``{"video_id", "transcript", "visual_text"}`` object per video; the small test
  fixtures) or, when that file is absent, ``transcripts/<video_id>.json`` (the golden
  set's Whisper segments and raw OCR detections; see :func:`transcript_input`).

**Out of scope.** A video tagged ``out_of_scope`` (no health content; it must be the
only tag and the video has no claims) is not part of the set: it is kept on
``Dataset.excluded`` and left out of ``videos``, every split, count and metric, so it
cannot inflate ``CANNOT_RECOGNIZE`` (README "Out of scope (§14)").

**Old schema.** ``ground_truth_label`` (video-label vocabulary on claim rows) was
replaced by ``claim_verdict``; a file that still uses it is refused with that message
rather than silently mapped.

**The test split is for T14.** Loading reads and counts every split; nothing here
predicts or scores anything.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from app.core.schemas.pipeline import FusionResult, MisinfoLabel
from app.evaluation import metrics

# §7 claim verdicts, exactly the golden set's vocabulary.
CLAIM_VERDICTS = metrics.VERDICTS
CLAIM_TRUTHS = CLAIM_VERDICTS  # older name, kept for callers
STANCES = ("ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR")
SOURCES = ("speech", "screen", "both")
CLAIM_KINDS = ("research_question", "fact_of_record")
SPLITS = ("tune", "test")
MISINFO_BASES = metrics.MISINFO_BASES
REVIEW_STATUSES = ("pending", "verified", "corrected")
CONFIDENCES = ("low", "medium", "high")
TEXT_TYPES = ("high_text", "low_text")
OUT_OF_SCOPE = "out_of_scope"

# Section 14, "Covers the hard cases on purpose", in the golden set's tag names.
HARD_CASE_CATEGORIES = (
    "clearly_false",
    "accurate",
    "debunking",
    "neutral_discussion",
    "satire",
    "mixed",              # §9: endorses one falsehood and refutes another
    "true_and_false",     # §14: "mixed videos (true and false claims)"
    "screen_only",
    "speech_screen_disagree",
    "noisy_audio",
    "other_language",
    "uncertain_science",
    "missing_evidence",
    "prompt_injection",
    "multi_claim",
)
# Tags the golden set also uses that are not hard-case categories.
OTHER_TAGS = ("single_claim", "no_claims", "fact_checker_produced", OUT_OF_SCOPE)
# Category names used before the golden set existed.
_TAG_ALIASES = {
    "satire_sarcasm": "satire",
    "mixed_claims": "true_and_false",
    "screen_only_claim": "screen_only",
    "scientific_uncertainty": "uncertain_science",
}

DATASET_FILES = ("videos.csv", "claims.csv", "inputs.jsonl", "reference_citations.csv")
TRANSCRIPTS_DIR = "transcripts"


class DatasetError(ValueError):
    pass


class GoldClaim(BaseModel):
    video_id: str
    claim_id: str
    claim_text: str
    verdict: str                       # claim_verdict (§7)
    stance: str                        # speaker_stance (§5)
    kind: Optional[str] = None         # claim_kind (§4)
    source: Optional[str] = None       # claim_source: speech / screen / both
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    evidence_supporting: list[str] = Field(default_factory=list)
    evidence_contradicting: list[str] = Field(default_factory=list)
    annotator: str = ""
    confidence: str = ""
    review_status: str = "pending"
    reviewer: str = ""
    reviewer_notes: str = ""
    notes: str = ""

    @property
    def truth(self) -> str:
        """Older name for ``verdict``."""
        return self.verdict

    @property
    def evidence(self) -> list[str]:
        return [*self.evidence_supporting, *self.evidence_contradicting]

    @property
    def relevant_pmids(self) -> list[str]:
        """PMIDs (digits only) the labeller retrieved and cited, either side: the
        relevance set for retrieval recall/nDCG and the citation-support check."""
        out: list[str] = []
        for e in self.evidence:
            pmid = e[5:] if e.upper().startswith("PMID:") else (e if e.isdigit() else "")
            if pmid and pmid not in out:
                out.append(pmid)
        return out

    @property
    def key(self) -> str:
        return f"{self.video_id}/{self.claim_id}"


class GoldVideo(BaseModel):
    video_id: str
    label: MisinfoLabel
    misinfo_basis: Optional[str] = None
    review_reasons: list[str] = Field(default_factory=list)
    platform: str = ""
    topic: str = ""
    source_url: str = ""
    text_type: Optional[str] = None
    categories: list[str] = Field(default_factory=list)   # case_tags
    split: Optional[str] = None
    annotator: str = ""
    confidence: str = ""
    review_status: str = "pending"
    reviewer: str = ""
    reviewer_notes: str = ""
    source: str = ""
    external_label: str = ""
    external_source: str = ""
    external_url: str = ""
    notes: str = ""
    claims: list[GoldClaim] = Field(default_factory=list)

    @property
    def case_tags(self) -> list[str]:
        return self.categories

    @property
    def out_of_scope(self) -> bool:
        return OUT_OF_SCOPE in self.categories

    @property
    def review_reason_kinds(self) -> list[str]:
        """``possible_debunk:c3`` -> ``possible_debunk``, in order, without repeats."""
        return list(dict.fromkeys(r.split(":", 1)[0] for r in self.review_reasons))


class VideoInput(BaseModel):
    """What a system under test receives for one video."""

    video_id: str
    fusion: FusionResult


class Dataset(BaseModel):
    name: str
    version: str
    hash: str
    videos: list[GoldVideo]                                  # in scope only
    excluded: list[GoldVideo] = Field(default_factory=list)  # out_of_scope (§14)
    inputs: dict[str, VideoInput] = Field(default_factory=dict)
    directory: Optional[str] = None

    def video(self, video_id: str) -> GoldVideo:
        for v in self.videos:
            if v.video_id == video_id:
                return v
        raise KeyError(video_id)

    def split(self, name: Optional[str]) -> list[GoldVideo]:
        """In-scope videos in one split. ``None`` or ``"all"`` returns every one."""
        if name in (None, "all"):
            return list(self.videos)
        if name not in SPLITS:
            raise DatasetError(f"unknown split {name!r}; use one of {SPLITS} or 'all'")
        return [v for v in self.videos if v.split == name]

    def claims(self, split: Optional[str] = None) -> list[GoldClaim]:
        return [c for v in self.split(split) for c in v.claims]

    def label_counts(self, split: Optional[str] = None) -> dict[str, int]:
        counts = Counter(v.label.value for v in self.split(split))
        return {label.value: counts.get(label.value, 0) for label in MisinfoLabel}

    def basis_counts(self, split: Optional[str] = None) -> dict[str, int]:
        counts = Counter(v.misinfo_basis for v in self.split(split) if v.misinfo_basis)
        return {b: counts.get(b, 0) for b in MISINFO_BASES}

    def verdict_counts(self, split: Optional[str] = None) -> dict[str, int]:
        counts = Counter(c.verdict for c in self.claims(split))
        return {v: counts.get(v, 0) for v in CLAIM_VERDICTS}

    def stance_counts(self, split: Optional[str] = None) -> dict[str, int]:
        counts = Counter(c.stance for c in self.claims(split))
        return {s: counts.get(s, 0) for s in STANCES}

    def coverage(self, split: Optional[str] = None) -> dict[str, int]:
        """In-scope videos per hard-case category; zero means the category is missing."""
        counts = {c: 0 for c in HARD_CASE_CATEGORIES}
        for v in self.split(split):
            for c in v.categories:
                if c in counts:
                    counts[c] += 1
        return counts

    def summary(self) -> dict:
        """Aggregate counts only (no claim text, no per-item labels)."""
        return {
            "videos": len(self.videos),
            "excluded_out_of_scope": len(self.excluded),
            "claims": len(self.claims()),
            "splits": {s: len(self.split(s)) for s in SPLITS},
            "labels": self.label_counts(),
            "misinfo_basis": self.basis_counts(),
            "verdicts": self.verdict_counts(),
            "stances": self.stance_counts(),
        }

    def label_inconsistencies(self) -> list[str]:
        """Videos whose label or ``misinfo_basis`` doesn't follow from their claims
        under the §9 judge rules. Videos with no claims are skipped (the fixtures use
        that for "no checkable claims"); in the golden set they are CANNOT_RECOGNIZE."""
        problems = []
        for v in self.videos:
            if not v.claims:
                continue
            claims = [(c.stance, c.verdict) for c in v.claims]
            expected = metrics.judge_label(claims)
            if expected != v.label.value:
                problems.append(f"{v.video_id}: labelled {v.label.value}, claims imply {expected}")
                continue
            basis = metrics.misinfo_basis(claims)
            if v.misinfo_basis is not None and v.misinfo_basis != basis:
                problems.append(f"{v.video_id}: misinfo_basis {v.misinfo_basis}, claims imply {basis}")
        return problems

    def input(self, video_id: str) -> VideoInput:
        """The input for one in-scope video, from ``inputs`` or its transcript file."""
        if video_id in self.inputs:
            return self.inputs[video_id]
        self.video(video_id)  # KeyError for unknown or out-of-scope videos
        if not self.directory:
            raise KeyError(video_id)
        return transcript_input(Path(self.directory), video_id)


# --- Loading ----------------------------------------------------------------

def normalize_verdict(raw: str) -> str:
    value = (raw or "").strip().upper()
    if value not in CLAIM_VERDICTS:
        raise DatasetError(f"unknown claim_verdict {raw!r}; use one of {CLAIM_VERDICTS}")
    return value


normalize_truth = normalize_verdict  # older name


def _split_list(raw: Optional[str]) -> list[str]:
    return [p.strip() for p in (raw or "").split(";") if p.strip()]


def _float(raw: str, where: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise DatasetError(f"{where}: not a number: {raw!r}") from None


def _choice(raw: str, allowed: tuple[str, ...], what: str, where: str, *, default: Optional[str] = None):
    if not raw:
        return default
    if raw not in allowed:
        raise DatasetError(f"{where}: unknown {what} {raw!r}; use one of {allowed}")
    return raw


def assign_split(video_id: str, test_fraction: float = 0.5, seed: str = "infodemic") -> str:
    """Deterministic split by video id, for files without a ``split`` column."""
    digest = hashlib.sha256(f"{seed}:{video_id}".encode()).hexdigest()
    return "test" if int(digest[:8], 16) / 0xFFFFFFFF < test_fraction else "tune"


def dataset_hash(directory: str | Path) -> str:
    """sha256 over the dataset files' names and bytes (the label files, the inputs and
    every transcript), recorded on every run."""
    directory = Path(directory)
    h = hashlib.sha256()
    paths = [directory / name for name in DATASET_FILES]
    tdir = directory / TRANSCRIPTS_DIR
    if tdir.is_dir():
        paths += sorted(tdir.glob("*.json"))
    for path in paths:
        if path.is_file():
            rel = path.relative_to(directory).as_posix()
            h.update(rel.encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise DatasetError(f"missing dataset file: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            {k.strip(): (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(fh)
        ]


def _tags(raw: str, where: str) -> list[str]:
    tags = [_TAG_ALIASES.get(t, t) for t in _split_list(raw.replace(",", ";"))]
    unknown = [t for t in tags if t not in HARD_CASE_CATEGORIES and t not in OTHER_TAGS]
    if unknown:
        raise DatasetError(f"{where}: unknown categories {unknown}")
    if OUT_OF_SCOPE in tags and tags != [OUT_OF_SCOPE]:
        raise DatasetError(f"{where}: out_of_scope must be the only tag, got {tags}")
    return tags


def _video(row: dict[str, str], test_fraction: float) -> GoldVideo:
    vid = row.get("video_id", "")
    try:
        label = MisinfoLabel(row.get("video_level_label", "").upper())
    except ValueError:
        raise DatasetError(f"{vid}: unknown video label {row.get('video_level_label')!r}") from None
    basis = _choice(row.get("misinfo_basis", ""), MISINFO_BASES, "misinfo_basis", vid)
    if "misinfo_basis" in row and (basis is None) != (label != MisinfoLabel.MISINFO):
        raise DatasetError(f"{vid}: misinfo_basis is set only (and always) for MISINFO; "
                           f"got label {label.value}, basis {basis!r}")
    split = _choice(row.get("split", ""), SPLITS, "split", vid) or assign_split(vid, test_fraction)
    return GoldVideo(
        video_id=vid, label=label, misinfo_basis=basis,
        review_reasons=_split_list(row.get("review_reasons")),
        platform=row.get("platform", ""), topic=row.get("topic", ""),
        source_url=row.get("source_url", ""),
        text_type=_choice(row.get("text_type", ""), TEXT_TYPES, "text_type", vid),
        categories=_tags(row.get("case_tags") or row.get("categories") or "", vid),
        split=split,
        annotator=row.get("annotator", ""),
        confidence=_choice(row.get("confidence", ""), CONFIDENCES, "confidence", vid, default=""),
        review_status=_choice(row.get("review_status", ""), REVIEW_STATUSES, "review_status", vid,
                              default="pending"),
        reviewer=row.get("reviewer", ""), reviewer_notes=row.get("reviewer_notes", ""),
        source=row.get("source", ""), external_label=row.get("external_label", ""),
        external_source=row.get("external_source", ""), external_url=row.get("external_url", ""),
        notes=row.get("notes", ""),
    )


def _claim(row: dict[str, str]) -> GoldClaim:
    vid, cid = row.get("video_id", ""), row.get("claim_id", "")
    where = f"{vid}/{cid}"
    stance = row.get("speaker_stance", "").upper()
    if stance not in STANCES:
        raise DatasetError(f"{where}: unknown stance {stance!r}")
    try:
        verdict = normalize_verdict(row.get("claim_verdict", ""))
    except DatasetError as exc:
        raise DatasetError(f"{where}: {exc}") from None
    supporting = _split_list(row.get("evidence_supporting"))
    contradicting = _split_list(row.get("evidence_contradicting"))
    if verdict == "UNSUPPORTED" and (supporting or contradicting):
        raise DatasetError(f"{where}: an UNSUPPORTED claim cites no evidence (§7)")
    start = _float(row.get("start_seconds", ""), where)
    end = _float(row.get("end_seconds", ""), where)
    if start is not None and end is not None and end < start:
        raise DatasetError(f"{where}: end_seconds {end} before start_seconds {start}")
    return GoldClaim(
        video_id=vid, claim_id=cid, claim_text=row.get("claim_text", ""),
        verdict=verdict, stance=stance,
        kind=_choice(row.get("claim_kind", ""), CLAIM_KINDS, "claim_kind", where),
        source=_choice((row.get("claim_source") or "").lower(), SOURCES, "claim_source", where),
        start_seconds=start, end_seconds=end,
        evidence_supporting=supporting, evidence_contradicting=contradicting,
        annotator=row.get("annotator", ""),
        confidence=_choice(row.get("confidence", ""), CONFIDENCES, "confidence", where, default=""),
        review_status=_choice(row.get("review_status", ""), REVIEW_STATUSES, "review_status", where,
                              default="pending"),
        reviewer=row.get("reviewer", ""), reviewer_notes=row.get("reviewer_notes", ""),
        notes=row.get("notes", ""),
    )


def load_dataset(
    directory: str | Path,
    *,
    version: str = "unversioned",
    name: Optional[str] = None,
    test_fraction: float = 0.5,
    expected_hash: Optional[str] = None,
    with_inputs: bool = True,
) -> Dataset:
    """Load and validate the set. ``with_inputs=False`` skips building inputs from
    ``transcripts/`` (labels and counts only); ``Dataset.input`` still builds one on
    demand."""
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
        videos[vid] = _video(row, test_fraction)

    claim_rows = _read_csv(directory / "claims.csv")
    if claim_rows and "claim_verdict" not in claim_rows[0]:
        if "ground_truth_label" in claim_rows[0]:
            raise DatasetError("claims.csv uses the old ground_truth_label column; "
                               "the golden schema calls it claim_verdict (§7 verdicts)")
        raise DatasetError("claims.csv has no claim_verdict column")
    seen: set[tuple[str, str]] = set()
    for row in claim_rows:
        vid, cid = row.get("video_id", ""), row.get("claim_id", "")
        if vid not in videos:
            raise DatasetError(f"claims.csv refers to unknown video {vid!r}")
        if (vid, cid) in seen:
            raise DatasetError(f"duplicate claim {vid}/{cid}")
        seen.add((vid, cid))
        videos[vid].claims.append(_claim(row))

    in_scope, excluded = [], []
    for v in videos.values():
        if v.out_of_scope:
            if v.claims:
                raise DatasetError(f"{v.video_id}: an out_of_scope video has no claims")
            excluded.append(v)
        else:
            in_scope.append(v)
    keep = {v.video_id for v in in_scope}

    inputs_path = directory / "inputs.jsonl"
    if inputs_path.exists():
        inputs = {k: x for k, x in load_inputs(inputs_path, known=set(videos)).items() if k in keep}
    elif with_inputs and (directory / TRANSCRIPTS_DIR).is_dir():
        inputs = {vid: transcript_input(directory, vid) for vid in keep
                  if (directory / TRANSCRIPTS_DIR / f"{vid}.json").is_file()}
    else:
        inputs = {}
    return Dataset(
        name=name or directory.name, version=version, hash=digest,
        videos=in_scope, excluded=excluded, inputs=inputs, directory=str(directory),
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
        out[vid] = VideoInput(video_id=vid, fusion=FusionResult(
            transcript=transcript, visual_text=visual,
            combined_content=obj.get("combined_content") or _combined(transcript, visual),
            metadata=obj.get("metadata", {}),
        ))
    return out


def _combined(transcript: str, visual: str) -> str:
    return "\n".join(
        p for p in (f"[SPEECH]\n{transcript}" if transcript else "",
                    f"[ON-SCREEN TEXT]\n{visual}" if visual else "") if p
    )


def transcript_input(directory: str | Path, video_id: str) -> VideoInput:
    """A video's input from the golden set's ``transcripts/<video_id>.json``.

    Speech: Whisper's timed segments, joined for ``transcript`` and kept in
    ``metadata["transcript_segments"]`` (what the graph provider reads, as with
    ``fuse(keep_segments=True)``). Screen: the raw OCR detections collapsed into
    captions by the routing experiment's deterministic rule (watermarks and noise
    dropped, repeated frames merged), one caption per line in ``visual_text``; their
    timings are kept in ``metadata["ocr_segments"]``.
    """
    # Imported here: the routing-experiment helpers pull in the graph modules.
    from app.evaluation.routing_experiment.items import ocr_segments, transcript_segments

    path = Path(directory) / TRANSCRIPTS_DIR / f"{video_id}.json"
    if not path.is_file():
        raise DatasetError(f"missing transcript file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{path.name}: invalid JSON ({exc})") from None
    speech = transcript_segments(data)
    captions = ocr_segments(data)
    transcript = " ".join(s.text for s in speech)
    visual = "\n".join(c.text for c in captions)
    return VideoInput(video_id=video_id, fusion=FusionResult(
        transcript=transcript, visual_text=visual,
        combined_content=_combined(transcript, visual),
        metadata={
            "source": f"golden:{TRANSCRIPTS_DIR}/{video_id}.json",
            "audio_length_chars": len(transcript),
            "visual_length_chars": len(visual),
            "transcript_segments": [s.model_dump(include={"start", "end", "text"}) for s in speech],
            "ocr_segments": [c.model_dump(include={"start", "end", "text"}) for c in captions],
        },
    ))


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
            ta.append(ca.verdict)
            tb.append(cb.verdict)
            sa.append(ca.stance)
            sb.append(cb.stance)
            if ca.verdict != cb.verdict:
                disagreements.append(f"{vid}/{ca.claim_id}: truth {ca.verdict} vs {cb.verdict}")
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
