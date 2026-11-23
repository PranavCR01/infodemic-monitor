"""Severity for review priority (target design §12 "Severity: which reviews come first"; T22).

Severity ranks how much harm a claim could do if someone acted on it. It orders the
review queue. **It never changes a label or a verdict:** everything here reads the
finished graph state and returns new values; nothing writes back into state, and the
graph does not call it. ``app.services.review_service`` stores the result on the
review case.

Code decides, not a model. Each claim's ``claim_category`` and the topics named in its
text map to HIGH / MEDIUM / LOW through the table in ``backend/config/severity.yaml``
(seeded from the review rule's high-risk category list, T09). The table is a **draft**
until the project lead and Dr. Brooks sign it off and WHO confirms it; the loader
refuses ``status: approved`` without all three sign-offs.

A video's severity is the highest severity among its **MISINFO-relevant** claims:

- endorsed and CONTRADICTED (§9 rule 1);
- endorsed and unsettled: MIXED, INSUFFICIENT_EVIDENCE or NOT_VERIFIABLE (§12; the same
  "uncertain" set as the ``high_risk_uncertain`` review rule);
- refuted and SUPPORTED, i.e. the speaker denies a supported claim (§9 rule 2, which
  makes the video MISINFO). This extends §12's parenthetical; see
  context/MULTI_AGENT.md §7 (T22).

A video with no MISINFO-relevant claim has no severity (``None``); the queue puts those
cases after LOW.
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.core.graph import routing as r
from app.core.graph.routing import Budgets, DEFAULT_BUDGETS
from app.core.graph.state import GraphClaim, PipelineState, Stance, Verdict

DEFAULT_SEVERITY_PATH = Path(__file__).resolve().parents[3] / "config" / "severity.yaml"


class Severity(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def rank(self) -> int:
        """Higher is more severe (for ``max``)."""
        return _RANK[self]


_RANK = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


def highest(levels: Iterable[Optional[Severity | str]]) -> Optional[Severity]:
    got = [Severity(x) for x in levels if x is not None]
    return max(got, key=lambda s: s.rank) if got else None


# ------------------------------------------------------------------ config


class SignOff(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_lead: bool = False
    dr_brooks: bool = False
    who_confirmed: bool = False

    @property
    def complete(self) -> bool:
        return self.project_lead and self.dr_brooks and self.who_confirmed


class Topic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    severity: Severity
    terms: tuple[str, ...] = Field(min_length=1)

    def pattern(self) -> re.Pattern[str]:
        return _compile_terms(self.terms)


def _compile_terms(terms: Iterable[str]) -> re.Pattern[str]:
    """Whole-word, case-insensitive; ``*`` matches the rest of a word."""
    parts = [re.escape(t.strip()).replace(r"\*", r"\w*") for t in terms if t.strip()]
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)


class SeverityConfig(BaseModel):
    """The severity table (``backend/config/severity.yaml``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    status: str = "draft"
    sign_off: SignOff = SignOff()
    default_severity: Severity = Severity.MEDIUM
    categories: dict[str, Severity] = Field(default_factory=dict)
    topics: tuple[Topic, ...] = ()
    _patterns: tuple = PrivateAttr(default=())

    def model_post_init(self, __context: Any) -> None:
        self._patterns = tuple((t, t.pattern()) for t in self.topics)

    @model_validator(mode="after")
    def _approved_needs_sign_off(self) -> "SeverityConfig":
        if self.status not in ("draft", "approved"):
            raise ValueError(f"severity table status must be 'draft' or 'approved', not {self.status!r}")
        if self.status == "approved" and not self.sign_off.complete:
            raise ValueError(
                "severity table can't be 'approved' until the project lead, Dr. Brooks and WHO have signed it off"
            )
        return self

    @property
    def is_draft(self) -> bool:
        return self.status != "approved"


def load_severity_config(path: Path | str = DEFAULT_SEVERITY_PATH) -> SeverityConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return SeverityConfig.model_validate(data)


@lru_cache(maxsize=1)
def default_severity_config() -> SeverityConfig:
    return load_severity_config()


# ------------------------------------------------------------------ claims


@dataclass(frozen=True)
class ClaimSeverity:
    claim_id: str
    severity: Severity
    basis: tuple[str, ...]  # e.g. ("category:treatment_efficacy", "topic:cancer") or ("default",)


def claim_severity(claim: GraphClaim, config: Optional[SeverityConfig] = None) -> ClaimSeverity:
    """Table severity of one claim: the highest of its category's level and every
    matching topic's level. Unlisted categories with no topic get the default."""
    cfg = config or default_severity_config()
    found: list[tuple[Severity, str]] = []
    category = (claim.claim_category or "").strip()
    if category in cfg.categories:
        found.append((cfg.categories[category], f"category:{category}"))
    for topic, pattern in cfg._patterns:
        if pattern.search(claim.claim_text or ""):
            found.append((topic.severity, f"topic:{topic.name}"))
    if not found:
        return ClaimSeverity(claim.claim_id, cfg.default_severity, ("default",))
    top = highest(s for s, _ in found)
    return ClaimSeverity(claim.claim_id, top, tuple(b for s, b in found if s == top))


UNSETTLED_VERDICTS = frozenset({Verdict.MIXED, Verdict.INSUFFICIENT_EVIDENCE, Verdict.NOT_VERIFIABLE})


def misinfo_relevant(stance: Optional[Stance | str], verdict: Optional[Verdict | str]) -> bool:
    """Whether a claim counts towards the video's severity (see module docstring)."""
    if stance is None or verdict is None:
        return False
    stance, verdict = Stance(stance), Verdict(verdict)
    if stance == Stance.ENDORSES:
        return verdict == Verdict.CONTRADICTED or verdict in UNSETTLED_VERDICTS
    return stance == Stance.REFUTES and verdict == Verdict.SUPPORTED


# ------------------------------------------------------------------ video


@dataclass(frozen=True)
class SeverityAssessment:
    """Severity of every claim and of the video, ready to store on a review case."""

    severity: Optional[Severity]
    claims: dict[str, dict[str, Any]] = field(default_factory=dict)
    table_version: str = ""
    table_status: str = "draft"


def video_severity(claims: Mapping[str, Mapping[str, Any]]) -> Optional[Severity]:
    """The highest *effective* severity (a reviewer's override if there is one,
    else the table's) among MISINFO-relevant claims."""
    return highest(effective_claim_severity(c) for c in claims.values() if c.get("misinfo_relevant"))


def effective_claim_severity(entry: Mapping[str, Any]) -> Optional[str]:
    override = entry.get("override")
    if override:
        return override["severity"]
    return entry.get("severity")


def assess(
    state: PipelineState,
    config: Optional[SeverityConfig] = None,
    budgets: Budgets = DEFAULT_BUDGETS,
) -> SeverityAssessment:
    """Severity of a finished run. Pure: reads state, calls no model, writes nothing.

    Verdicts are the ones the judge used (``routing.verdicts_for_judge``), the same view
    the review rule takes, so a claim that abstained after its budget ran out counts as
    unsettled."""
    cfg = config or default_severity_config()
    verdicts = r.verdicts_for_judge(state, budgets)
    stances = state.get("stance_results") or {}
    out: dict[str, dict[str, Any]] = {}
    for claim in state.get("claims") or []:
        cs = claim_severity(claim, cfg)
        s = stances.get(claim.claim_id)
        v = verdicts.get(claim.claim_id)
        out[claim.claim_id] = {
            "severity": cs.severity.value,
            "basis": list(cs.basis),
            "stance": s.stance.value if s else None,
            "verdict": v.verdict.value if v else None,
            "misinfo_relevant": misinfo_relevant(s.stance if s else None, v.verdict if v else None),
        }
    return SeverityAssessment(
        severity=video_severity(out), claims=out, table_version=cfg.version, table_status=cfg.status
    )
