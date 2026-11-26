"""Per-step labelled items from the tune split (design §13 "does routing need its own
data?", §14 "Metrics for each step").

- ``extract_claims``: one item per in-scope tune video. Input: the video's Whisper
  segments and its collapsed on-screen captions (fused by overlap, as the graph's
  ``fuse_modalities`` does). Gold: the video's labelled claim texts.
- ``analyze_stance``: one item per gold claim. Input: the claim (with the transcript
  and caption segments its time range covers) plus the video's segments, from which
  the node picks the claim's context. Gold: ``speaker_stance``.
- ``verify_claims``: one item per gold claim. Input: the claim plus its **frozen**
  evidence (``frozen.py``), identical for every candidate. Gold: ``claim_verdict``,
  UNSUPPORTED included.

Out-of-scope videos (no health content) are left out of every metric (§14), so they
produce no items. Videos outside the tune split are refused by ``golden.TuneSet``.

``claim_category`` is not labelled for most claims, and the verifier needs it to know
whether UNSUPPORTED is allowed. It comes from ``efficacy_category`` below, a fixed rule
applied to every claim the same way, never from the gold verdict (that would leak the
answer); it is frozen with the evidence so every candidate sees the same category.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from app.core.claim_category import EVIDENCE_META, is_evidence_meta
from app.core.graph.nodes import fuse_by_overlap
from app.core.pipeline_options import PipelineOptions
from app.core.graph.state import (
    EvidenceRecord,
    FusedSegment,
    GraphClaim,
    OcrSegment,
    Stance,
    TranscriptSegment,
    Verdict,
)
from app.evaluation.routing_experiment.golden import GoldClaimRow, TuneSet
from app.evaluation.selection import StepItem

STEPS: tuple[str, ...] = ("extract_claims", "analyze_stance", "verify_claims")
STANCE_LABELS: tuple[str, ...] = tuple(s.value for s in Stance)
VERDICT_LABELS: tuple[str, ...] = tuple(v.value for v in Verdict)


# ------------------------------------------------------------------ inputs


class VideoInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    video_id: str
    transcript: list[TranscriptSegment]
    ocr: list[OcrSegment]
    fused: list[FusedSegment]


class StanceInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim: GraphClaim
    transcript: list[TranscriptSegment]
    ocr: list[OcrSegment]
    fused: list[FusedSegment]


class VerifyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim: GraphClaim
    evidence: list[EvidenceRecord]
    allow_unsupported: bool


# ------------------------------------------------------------------ transcripts


def _field(obj: Any) -> Any:
    """Some golden-set fields are JSON strings; decode those, keep the rest."""
    if isinstance(obj, str):
        import json
        try:
            return json.loads(obj)
        except ValueError:
            return {}
    return obj or {}


def transcript_segments(data: dict) -> list[TranscriptSegment]:
    tr = _field(data.get("transcript"))
    out: list[TranscriptSegment] = []
    for s in tr.get("segments", []) or []:
        text = str(s.get("text", "")).strip()
        if not text:
            continue
        start = max(0.0, float(s.get("start", 0.0)))
        end = max(start, float(s.get("end", start)))
        out.append(TranscriptSegment(segment_id=f"t{len(out) + 1}", start=start, end=end, text=text))
    return out


_NORM = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    return _NORM.sub(" ", text.lower()).strip()


def _tokens(text: str) -> set[str]:
    return set(_norm(text).split())


def _similar(a: str, b: str, threshold: float = 0.6) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def ocr_segments(
    data: dict, *, watermark_share: float = 0.4, min_confidence: float = 0.5, min_chars: int = 3,
) -> list[OcrSegment]:
    """Collapse raw EasyOCR detections into captions (§2 "On-screen text", §3 step 1).

    The golden transcripts keep every detection per sampled frame. Here: drop
    low-confidence and very short detections; drop watermarks (text seen in at least
    ``watermark_share`` of sampled frames: the platform logo, the creator's handle);
    join each frame's remaining detections into one line; merge consecutive frames
    showing the same caption (token Jaccard >= 0.6) into one segment whose end is the
    last frame plus one sampling interval. A simple, deterministic approximation of
    the §2 grouping, identical for every candidate.
    """
    meta = _field(data.get("ocr"))
    on_screen = _field(data.get("on_screen"))
    detections = [d for d in on_screen.get("detections", []) or []
                  if float(d.get("confidence", 0.0)) >= min_confidence
                  and len(_norm(str(d.get("text", ""))).replace(" ", "")) >= min_chars]
    if not detections:
        return []
    fps = float(meta.get("fps") or 0.5)
    interval = 1.0 / fps if fps > 0 else 2.0
    frames: dict[float, list[str]] = {}
    for d in detections:
        frames.setdefault(round(float(d.get("time", 0.0)), 2), []).append(str(d["text"]).strip())
    n_frames = int(on_screen.get("frames_sampled") or 0) or len(frames)
    seen_in: dict[str, int] = {}
    for texts in frames.values():
        for key in {_norm(t) for t in texts}:
            seen_in[key] = seen_in.get(key, 0) + 1
    marks = {k for k, n in seen_in.items() if n_frames >= 5 and n / n_frames >= watermark_share}

    runs: list[list[Any]] = []  # [start, last_time, best_text]
    for t in sorted(frames):
        line = " ".join(x for x in frames[t] if _norm(x) not in marks).strip()
        if len(_norm(line).replace(" ", "")) < min_chars:
            continue
        if runs and _similar(runs[-1][2], line) and t - runs[-1][1] <= interval * 1.5:
            runs[-1][1] = t
            if len(line) > len(runs[-1][2]):
                runs[-1][2] = line
            continue
        runs.append([t, t, line])
    return [
        OcrSegment(segment_id=f"o{i}", start=start, end=last + interval, text=text, confidence=1.0)
        for i, (start, last, text) in enumerate(runs, start=1)
    ]


def extraction_view(video: VideoInput, options: "PipelineOptions") -> VideoInput:
    """What extraction is given for ``video`` under ``options`` (config/pipeline.yaml):
    unchanged with ``use_ocr: true``; transcript only (no captions, re-fused) with false."""
    if options.extraction.use_ocr:
        return video
    return VideoInput(video_id=video.video_id, transcript=video.transcript, ocr=[],
                      fused=fuse_by_overlap(video.transcript, []))


def video_input(tune: TuneSet, video_id: str) -> VideoInput:
    data = tune.transcript(video_id)  # refuses non-tune videos
    transcript = transcript_segments(data)
    ocr = ocr_segments(data)
    return VideoInput(video_id=video_id, transcript=transcript, ocr=ocr, fused=fuse_by_overlap(transcript, ocr))


# ------------------------------------------------------------------ claims


_TREATMENT = re.compile(
    r"\b(cures?|cured|curing|treats?|treated|treating|heals?|healed|healing|reverses?|reversed|"
    r"relieves?|relief|remed(?:y|ies)|gets? rid of|clears? up|eliminates?|fights? off|kills? (?:the )?"
    r"(?:virus|bacteria|cancer|infection|parasites?)|shrinks? (?:the )?tumou?rs?|works? (?:for|against|every time)|"
    # French and Spanish: the golden set has claims in both.
    r"remèdes? contre|guérit|guérir|soigne|traite|traiter|cura|curar|trata|tratar|alivia)\b",
    re.I,
)
_PREVENTION = re.compile(
    r"\b(prevents?|prevented|preventing|prevention|protects? (?:you )?(?:against|from)|wards? off|"
    r"reduces? (?:the |your )?risk of|lowers? (?:the |your )?risk of|stops? you (?:from )?getting|"
    r"keeps? (?:\w+ )?away|immun(?:e|ity) (?:to|against)|"
    r"prévient|prévenir|protège (?:du|de la|des|contre)|previene|prevenir|protege (?:contra|de|del)|"
    r"reduce (?:el|los) riesgos? de)\b",
    re.I,
)


def efficacy_category(text: str) -> str:
    """``treatment_efficacy`` / ``prevention`` / ``evidence_meta`` / ``other`` from fixed
    cue words. Applied the same way to every claim, whatever its gold verdict. T51: an
    evidence-strength statement is ``evidence_meta`` first, as in the extractor."""
    if is_evidence_meta(text):
        return EVIDENCE_META
    if _PREVENTION.search(text):
        return "prevention"
    if _TREATMENT.search(text):
        return "treatment_efficacy"
    return "other"


def _overlapping(segments: Iterable[Any], start: float, end: float, pad: float = 0.05) -> list[str]:
    return [s.segment_id for s in segments if s.end >= start - pad and s.start <= end + pad]


def graph_claim(row: GoldClaimRow, video: Optional[VideoInput] = None, *, category: Optional[str] = None) -> GraphClaim:
    """A gold claim in the graph's claim shape. Source segments are the transcript (and,
    for screen claims, caption) pieces its labelled time range covers."""
    ids: list[str] = []
    if video is not None:
        if row.source in ("speech", "both"):
            ids += _overlapping(video.transcript, row.start, row.end)
        if row.source in ("screen", "both"):
            ids += _overlapping(video.ocr, row.start, row.end)
        if not ids:
            pool = [*video.transcript, *video.ocr]
            if pool:
                mid = (row.start + row.end) / 2
                ids = [min(pool, key=lambda s: abs((s.start + s.end) / 2 - mid)).segment_id]
    kind = row.kind if row.kind in ("research_question", "fact_of_record") else "research_question"
    return GraphClaim(
        claim_id=row.claim_id, claim_text=row.text,
        claim_category=category or efficacy_category(row.text),
        source_segment_ids=list(dict.fromkeys(ids)),
        start_seconds=row.start, end_seconds=max(row.start, row.end), claim_kind=kind,
    )


# ------------------------------------------------------------------ items


def in_scope_video_ids(tune: TuneSet, only: Optional[Sequence[str]] = None) -> list[str]:
    ids = list(only) if only else tune.video_ids
    for vid in ids:
        tune.check_tune(vid)  # refuses test-split ids, even when passed explicitly
    return [vid for vid in ids if not tune.videos[vid].out_of_scope]


def extraction_items(tune: TuneSet, videos: dict[str, VideoInput], only: Optional[Sequence[str]] = None) -> list[StepItem]:
    items = []
    for vid in in_scope_video_ids(tune, only):
        gold = [c.text for c in tune.videos[vid].claims]
        items.append(StepItem(item_id=vid, input=videos[vid], gold=gold))
    return items


def stance_items(tune: TuneSet, videos: dict[str, VideoInput], only: Optional[Sequence[str]] = None) -> list[StepItem]:
    items = []
    for vid in in_scope_video_ids(tune, only):
        v = videos[vid]
        for row in tune.videos[vid].claims:
            if row.stance not in STANCE_LABELS:
                continue
            items.append(StepItem(
                item_id=row.key,
                input=StanceInput(claim=graph_claim(row, v), transcript=v.transcript, ocr=v.ocr, fused=v.fused),
                gold=row.stance,
            ))
    return items


def verify_items(tune: TuneSet, frozen: "FrozenEvidenceLike", only: Optional[Sequence[str]] = None) -> list[StepItem]:
    """One item per gold claim with its frozen evidence. A claim missing from the
    frozen file is an error: every candidate must see identical, recorded evidence."""
    items = []
    for vid in in_scope_video_ids(tune, only):
        for row in tune.videos[vid].claims:
            if row.verdict not in VERDICT_LABELS:
                continue
            entry = frozen.entry(row.key, row.text)
            claim = graph_claim(row, None, category=entry.claim_category)
            items.append(StepItem(
                item_id=row.key,
                input=VerifyInput(claim=claim, evidence=list(entry.evidence),
                                  allow_unsupported=entry.allow_unsupported),
                gold=row.verdict,
            ))
    return items


class FrozenEvidenceLike:  # pragma: no cover - typing aid only
    def entry(self, key: str, claim_text: Optional[str] = None) -> Any: ...
