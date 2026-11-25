"""The adversarial case set (§15 "Tested"): schema and loader."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.graph.state import OcrSegment, Stance, TranscriptSegment, Verdict
from app.core.schemas.pipeline import FusionResult, MisinfoLabel

REPO_DIR = Path(__file__).resolve().parents[4]
DEFAULT_CASES_PATH = REPO_DIR / "research" / "adversarial" / "adversarial_v1.yaml"

CATEGORIES = (
    "speech_injection", "screen_injection", "abstract_injection", "jailbreak_roleplay",
    "out_of_domain", "format_attack", "control",
)
STEPS = ("classify", "extract_claims", "analyze_stance", "verify_claims", "critique")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseEvidence(_M):
    pmid: str
    title: str
    abstract: str = ""
    year: Optional[int] = None

    @property
    def evidence_id(self) -> str:
        return f"pmid:{self.pmid}"


class CaseClaim(_M):
    text: str
    segments: list[str]
    stance: Stance
    truth: Verdict
    evidence: list[CaseEvidence] = Field(default_factory=list)


class OnScreen(_M):
    text: str
    with_: Optional[str] = Field(default=None, alias="with")


class Attack(_M):
    trigger: str
    target_labels: list[MisinfoLabel]
    effects: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _known_steps(self) -> "Attack":
        unknown = set(self.effects) - set(STEPS)
        if unknown:
            raise ValueError(f"unknown attack steps {sorted(unknown)}; use {STEPS}")
        return self


class Expected(_M):
    labels: list[MisinfoLabel]
    review: Optional[bool] = None


class AdversarialCase(_M):
    id: str
    category: str
    description: str
    in_domain: bool = True
    transcript: list[str]
    on_screen: list[OnScreen] = Field(default_factory=list)
    claims: list[CaseClaim] = Field(default_factory=list)
    honest_label: MisinfoLabel
    attack: Optional[Attack] = None
    expected: Expected
    known_gap: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "AdversarialCase":
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.id}: unknown category {self.category!r}")
        ids = {s.segment_id for s in self.transcript_segments()} | {o.segment_id for o in self.ocr_segments()}
        for c in self.claims:
            missing = set(c.segments) - ids
            if missing:
                raise ValueError(f"{self.id}: claim cites unknown segments {sorted(missing)}")
        for o in self.on_screen:
            if o.with_ and o.with_ not in ids:
                raise ValueError(f"{self.id}: on-screen text attached to unknown segment {o.with_}")
        return self

    # -- the case as pipeline input --

    def transcript_segments(self) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(segment_id=f"t{i}", start=5.0 * (i - 1), end=5.0 * (i - 1) + 4.5, text=t)
            for i, t in enumerate(self.transcript, start=1)
        ]

    def ocr_segments(self) -> list[OcrSegment]:
        timing = {s.segment_id: (s.start, s.end) for s in self.transcript_segments()}
        out, orphan_start = [], 5.0 * len(self.transcript) + 0.5
        for j, o in enumerate(self.on_screen, start=1):
            if o.with_:
                start, end = timing[o.with_]
                start, end = start + 0.5, end - 0.5
            else:
                start, end = orphan_start, orphan_start + 3.0
                orphan_start += 5.0
            out.append(OcrSegment(segment_id=f"o{j}", start=start, end=end, text=o.text, confidence=0.95))
        return out

    def fusion(self) -> FusionResult:
        """The single-call baseline's input. Built as the live fusion does
        (``[AUDIO TRANSCRIPT]``), plus the on-screen text, which the live path will
        include once OCR is re-enabled; giving the baseline the same material as the
        graph keeps the comparison fair."""
        transcript = " ".join(self.transcript)
        visual = "\n".join(o.text for o in self.on_screen)
        combined = f"[AUDIO TRANSCRIPT]\n{transcript}"
        if visual:
            combined += f"\n\n[ON-SCREEN TEXT]\n{visual}"
        return FusionResult(transcript=transcript, visual_text=visual, combined_content=combined, metadata={})


class CaseSet(_M):
    version: str
    hash: str
    cases: list[AdversarialCase]

    def by_id(self, case_id: str) -> AdversarialCase:
        return next(c for c in self.cases if c.id == case_id)


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> CaseSet:
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw)
    cases = [AdversarialCase.model_validate(c) for c in data["cases"]]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    return CaseSet(version=data["version"], hash=hashlib.sha256(raw).hexdigest(), cases=cases)
