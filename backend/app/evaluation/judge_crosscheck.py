"""Judge cross-check (T24, target design §9 and §14).

Runs two independently written implementations of the §9 judge on the same claims and
reports where they differ:

- the **backend judge**: ``app.core.graph.judge.decide`` (label, deciding claims, the
  rules' own review reasons and the §9 pattern flags), followed by the review rule
  ``app.core.graph.review_policy.evaluate`` (§11), on a ``PipelineState`` built from the
  claims;
- the **golden-set judge**: ``research/claim-level/dataset/scripts/judge.py`` on the
  ``data/golden-label-set`` branch (``judge`` and ``review_reasons``), which derives the
  golden set's ``video_level_label`` and ``review_reasons`` columns.

The input is claim-level only: each claim's recorded ``speaker_stance``,
``claim_verdict`` and cited evidence IDs. No transcript, no retrieval, no model call.

**Comparing review reasons.** The two sides word their reasons differently, so both are
mapped to one vocabulary (``<kind>[:<claim_id>]``):

| kind | backend | golden |
|---|---|---|
| ``denies_supported`` | ``judge:denies_supported:<cid>`` | "speaker denies a supported claim" (one per deciding claim) |
| ``possible_debunk`` | ``judge:possible_debunk:<cid>`` | "possible debunk of an unsettled claim" (one per deciding claim) |
| ``mixed_video`` | ``judge:mixed_video`` | — (``is_mixed`` exists but adds no reason) |
| ``weak_evidence`` | ``weak_evidence:<cid>`` | "deciding claim <cid> is INSUFFICIENT_EVIDENCE/MIXED" |
| ``conflicting_evidence`` | ``conflicting_evidence:<cid>`` | "claim <cid> has both supporting and contradicting evidence" |
| ``unclear_stance`` | ``unclear_stance:<cid>`` | "claim <cid> stance is UNCLEAR" |
| ``mixed_evidence`` etc. | the judge's other §9 pattern flags | — |
| ``nothing_judged`` | ``judge:nothing_judged`` | ``nothing_judged`` (once the golden judge has the T37 rule) |
| ``main_claims_unchecked`` | ``judge:main_claims_unchecked`` (T64 f) | — (not in the golden judge) |

Backend reasons from signals the golden set cannot carry (critic, validation, budget,
calibrated confidence, study type, high-risk category, guardrails) are left out: the
state built here has none of them, and :data:`PIPELINE_ONLY_RULES` names them.

**T64 (f) note.** ``main_claims_unchecked`` (NO_MISINFO with at least half of the endorsed
treatment / prevention claims INSUFFICIENT_EVIDENCE; label unchanged) needs claim
categories. The golden set's claims.csv has none, so :func:`build_state` gives only
UNSUPPORTED claims an efficacy category, and an INSUFFICIENT_EVIDENCE claim is never a
"main" claim here: the reason cannot fire on the golden set and the cross-check is
unchanged (T64: identical report on 92a731e). If categories are added later it would show
as the backend-only kind ``main_claims_unchecked_not_in_golden_judge``. T64's other rules
(a, b, c, e) live in the verify step and the reranker, not the judge, so they don't reach
this cross-check either (as T49's guard).

Every difference is classified (:func:`classify_difference`) with the side that matches
§9, so a new kind of difference shows up as ``unclassified``.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from app.core.graph import judge as jg
from app.core.graph import review_policy as rp
from app.core.graph.routing import DEFAULT_BUDGETS
from app.core.graph.state import (
    EvidenceRecord,
    GraphClaim,
    PipelineState,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)

# Review rules whose inputs only exist in a running pipeline (§11 "the rest of the rule
# belongs to the running pipeline, not to a hand-labelled set").
PIPELINE_ONLY_RULES = frozenset({
    "validation_failed", "weak_study_types", "critic_escalated", "budget_exhausted",
    "low_confidence", "high_risk_uncertain", "guardrails",
})

# Golden judge reason strings (scripts/judge.py) → vocabulary kind. Before the D1
# re-derivation (golden set @ 45244b0) the golden judge wrote sentences; from 022ac44 it
# writes ``<kind>:<claim_id>`` (or ``mixed_video``). Both are understood.
GOLDEN_RULE_REASONS = {
    "speaker denies a supported claim": "denies_supported",
    "possible debunk of an unsettled claim": "possible_debunk",
}
_GOLDEN_TRIGGERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^deciding claim (\S+) is (?:INSUFFICIENT_EVIDENCE|MIXED)$"), "weak_evidence"),
    (re.compile(r"^claim (\S+) has both supporting and contradicting evidence$"), "conflicting_evidence"),
    (re.compile(r"^claim (\S+) stance is UNCLEAR$"), "unclear_stance"),
)
# ``<kind>:<cid>`` reasons of the 022ac44 golden judge → vocabulary kind.
GOLDEN_KIND_REASONS = {
    "denies_supported": "denies_supported",
    "unproven_claim": "unproven_claim",
    "possible_debunk": "possible_debunk",
    "mixed_evidence": "mixed_evidence",
    "deciding_insufficient": "weak_evidence",
    "evidence_both_sides": "conflicting_evidence",
    "unclear_stance": "unclear_stance",
}
# Video-level golden reasons (no claim id) → vocabulary kind.
GOLDEN_VIDEO_REASONS = {"mixed_video": "mixed_video", "nothing_judged": "nothing_judged"}


class UnknownReason(ValueError):
    """A golden reason string this module does not know how to map."""


# ------------------------------------------------------------------ input


@dataclass(frozen=True)
class GoldenClaim:
    claim_id: str
    speaker_stance: str
    claim_verdict: str
    evidence_supporting: tuple[str, ...] = ()
    evidence_contradicting: tuple[str, ...] = ()
    claim_category: str = ""  # T30: UNSUPPORTED is only for efficacy categories

    def as_row(self) -> dict[str, str]:
        """The claims.csv row shape the golden judge reads."""
        return {
            "claim_id": self.claim_id,
            "speaker_stance": self.speaker_stance,
            "claim_verdict": self.claim_verdict,
            "evidence_supporting": ";".join(self.evidence_supporting),
            "evidence_contradicting": ";".join(self.evidence_contradicting),
        }


@dataclass(frozen=True)
class GoldenVideo:
    video_id: str
    out_of_scope: bool
    recorded_label: str
    recorded_review_reasons: tuple[str, ...]
    claims: tuple[GoldenClaim, ...]
    recorded_basis: str = ""  # videos.csv misinfo_basis (T30; empty unless MISINFO)


def _split_ids(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in (s or "").split(";") if x.strip())


def load_golden_csvs(videos_csv: str, claims_csv: str) -> list[GoldenVideo]:
    """Parse the golden set's ``videos.csv`` and ``claims.csv`` (as text), keeping only
    the claim-level fields the judges read."""
    by_video: dict[str, list[GoldenClaim]] = {}
    for row in csv.DictReader(io.StringIO(claims_csv)):
        by_video.setdefault(row["video_id"], []).append(GoldenClaim(
            claim_id=row["claim_id"],
            speaker_stance=row["speaker_stance"],
            claim_verdict=row["claim_verdict"],
            evidence_supporting=_split_ids(row.get("evidence_supporting", "")),
            evidence_contradicting=_split_ids(row.get("evidence_contradicting", "")),
            claim_category=(row.get("claim_category") or "").strip(),
        ))
    out = []
    for row in csv.DictReader(io.StringIO(videos_csv)):
        vid = row["video_id"]
        out.append(GoldenVideo(
            video_id=vid,
            out_of_scope="out_of_scope" in _split_ids(row.get("case_tags", "")),
            recorded_label=row["video_level_label"],
            recorded_review_reasons=_split_ids(row.get("review_reasons", "")),
            claims=tuple(by_video.get(vid, [])),
            recorded_basis=(row.get("misinfo_basis") or "").strip(),
        ))
    return out


def to_fixture(videos: Sequence[GoldenVideo]) -> list[dict[str, Any]]:
    return [
        {
            "video_id": v.video_id,
            "out_of_scope": v.out_of_scope,
            "recorded_label": v.recorded_label,
            "recorded_review_reasons": list(v.recorded_review_reasons),
            "recorded_basis": v.recorded_basis,
            "claims": [
                {"claim_id": c.claim_id, "speaker_stance": c.speaker_stance,
                 "claim_verdict": c.claim_verdict,
                 "evidence_supporting": list(c.evidence_supporting),
                 "evidence_contradicting": list(c.evidence_contradicting),
                 **({"claim_category": c.claim_category} if c.claim_category else {})}
                for c in v.claims
            ],
        }
        for v in videos
    ]


def from_fixture(rows: Iterable[Mapping[str, Any]]) -> list[GoldenVideo]:
    return [
        GoldenVideo(
            video_id=r["video_id"], out_of_scope=bool(r["out_of_scope"]),
            recorded_label=r["recorded_label"],
            recorded_review_reasons=tuple(r["recorded_review_reasons"]),
            recorded_basis=r.get("recorded_basis", ""),
            claims=tuple(
                GoldenClaim(
                    claim_id=c["claim_id"], speaker_stance=c["speaker_stance"],
                    claim_verdict=c["claim_verdict"],
                    evidence_supporting=tuple(c["evidence_supporting"]),
                    evidence_contradicting=tuple(c["evidence_contradicting"]),
                    claim_category=c.get("claim_category", ""),
                )
                for c in r["claims"]
            ),
        )
        for r in rows
    ]


# ------------------------------------------------------------------ backend side


def _evidence_record(eid: str) -> EvidenceRecord:
    pmid = eid.split(":", 1)[1] if eid.upper().startswith("PMID:") else None
    return EvidenceRecord(
        evidence_id=eid, source="pubmed" if pmid else "reference", title=eid, pmid=pmid,
        # No study-type signal in the golden set; "unknown" keeps the weak-study-type
        # rule (pipeline-only) from firing on guessed types.
        study_type="unknown",
    )


def build_state(video: GoldenVideo) -> PipelineState:
    """A ``PipelineState`` holding only the judge's inputs: claims, stances, verdicts and
    the cited evidence (as retrieved for that claim, so citations are in scope)."""
    s = initial_state(job_id=f"crosscheck-{video.video_id}", video_id=video.video_id,
                      media_uri=f"golden://{video.video_id}", pipeline_version="t24-crosscheck")
    claims, stances, verdicts, evidence = [], {}, {}, {}
    for i, c in enumerate(video.claims):
        # T30: a golden UNSUPPORTED verdict already says the full search found nothing
        # for an efficacy claim. Without a category column, assume the labeller applied
        # that rule; with one, the backend's gate checks it.
        category = c.claim_category or (
            "treatment_efficacy" if c.claim_verdict == Verdict.UNSUPPORTED.value else "unknown")
        claims.append(GraphClaim(
            claim_id=c.claim_id, claim_text=c.claim_id, claim_category=category,
            source_segment_ids=[], start_seconds=float(i), end_seconds=float(i) + 1,
        ))
        stances[c.claim_id] = StanceResult(claim_id=c.claim_id, stance=Stance(c.speaker_stance),
                                           stance_segment_ids=[])
        verdicts[c.claim_id] = VerificationResult(
            claim_id=c.claim_id, verdict=Verdict(c.claim_verdict),
            supporting_evidence_ids=list(c.evidence_supporting),
            contradicting_evidence_ids=list(c.evidence_contradicting),
        )
        ids = dict.fromkeys([*c.evidence_supporting, *c.evidence_contradicting])
        if ids:
            evidence[c.claim_id] = [_evidence_record(e) for e in ids]
    # Golden verdicts are final: every claim's search counts as complete (T30's gate).
    attempts = {c.claim_id: DEFAULT_BUDGETS.max_retrieval_attempts for c in video.claims}
    s.update(claims=claims, stance_results=stances, verification_results=verdicts,
             retrieved_evidence=evidence, retrieval_attempts=attempts)
    return s


@dataclass(frozen=True)
class JudgeOutput:
    label: str
    deciding: tuple[str, ...]
    reasons: frozenset[str]  # normalised vocabulary
    raw: tuple[str, ...] = ()  # the side's own wording, for the report
    extra: tuple[str, ...] = ()  # backend reasons outside the shared signals
    basis: str = ""  # misinfo_basis (T30); empty unless MISINFO


def run_backend(video: GoldenVideo) -> JudgeOutput:
    state = build_state(video)
    final, errors = jg.judge(state)
    if errors:  # the inputs are built to be clean; an error here is a harness bug
        raise AssertionError(f"{video.video_id}: backend judge errors {errors}")
    state["final_result"] = final
    state["validation_errors"] = []  # validation is pipeline-only; treated as passed
    decision = rp.evaluate(state)
    reasons, extra = set(), []
    for name, got in decision.fired.items():
        for reason in got:
            if name in PIPELINE_ONLY_RULES:
                extra.append(reason)
            elif name == "judge_flags":
                reasons.add(reason.removeprefix("judge:"))
            else:
                reasons.add(reason)
    return JudgeOutput(
        label=final.classification.value, deciding=tuple(final.claim_ids),
        reasons=frozenset(reasons), raw=decision.reasons, extra=tuple(extra),
        basis=final.misinfo_basis or "",
    )


# ------------------------------------------------------------------ golden side


# ``(label, deciding, reasons)`` before 022ac44; ``(label, basis, deciding, reasons)`` after.
GoldenJudge = Callable[[list[dict]], tuple]
GoldenReasons = Callable[[list[dict]], list[str]]


def normalise_golden_reasons(reasons: Sequence[str], deciding: Sequence[str]) -> frozenset[str]:
    out: set[str] = set()
    for r in reasons:
        if r in GOLDEN_RULE_REASONS:
            out.update(f"{GOLDEN_RULE_REASONS[r]}:{cid}" for cid in deciding)
            continue
        if r in GOLDEN_VIDEO_REASONS:
            out.add(GOLDEN_VIDEO_REASONS[r])
            continue
        kind, sep, cid = r.partition(":")
        if sep and kind in GOLDEN_KIND_REASONS:
            out.add(f"{GOLDEN_KIND_REASONS[kind]}:{cid}")
            continue
        for pattern, kind in _GOLDEN_TRIGGERS:
            m = pattern.match(r)
            if m:
                out.add(f"{kind}:{m.group(1)}")
                break
        else:
            raise UnknownReason(r)
    return frozenset(out)


def run_golden(video: GoldenVideo, judge: GoldenJudge, review_reasons: GoldenReasons) -> JudgeOutput:
    rows = [c.as_row() for c in video.claims]
    out = judge(rows)
    if len(out) == 4:
        label, basis, deciding, _ = out
    else:  # golden judge before the D1 re-derivation
        (label, deciding, _), basis = out, None
    raw = review_reasons(rows)
    ids = tuple(c["claim_id"] for c in deciding)
    return JudgeOutput(label=label, deciding=ids, reasons=normalise_golden_reasons(raw, ids), raw=tuple(raw),
                       basis=basis or "")


# ------------------------------------------------------------------ comparison


# Every known kind of difference, with the side that matches §9/§11 and why. The keys
# are what :func:`classify_difference` returns.
DIFFERENCE_KINDS: dict[str, dict[str, str]] = {
    "rule_reason_from_non_deciding_claim": {
        "matches": "backend",
        "why": "§9: 'Review reasons are collected from every claim, whichever rule decides "
               "the label: a refuted claim the evidence can't settle raises \"possible "
               "debunk\" even when another claim makes the video NO-MISINFO.' The golden "
               "judge returns the reason only when its own rule decides the label (the "
               "pseudocode's third value read literally).",
    },
    "mixed_video": {
        "matches": "backend",
        "why": "§9: 'Mixed videos (one false claim endorsed, another refuted) are labelled "
               "MISINFO and always sent to review.' The golden judge detects the pattern "
               "(is_mixed) but adds no review reason.",
    },
    "mixed_evidence": {
        "matches": "backend",
        "why": "§9 probe: 'A claim with MIXED evidence doesn't make a video MISINFO by "
               "itself, but it's a review trigger.' The backend judge flags every MIXED claim "
               "(judge:mixed_evidence:<cid>); the golden judge only flags MIXED on deciding "
               "claims (§11 bullet), so a non-deciding MIXED claim sends nothing to review. "
               "On a deciding MIXED claim both sides send it to review and the backend "
               "records the flag in addition to weak_evidence.",
    },
    "unclear_stance_contradicted": {
        "matches": "backend",
        "why": "§9 'Where an LLM still helps': 'Unclear stance on a deciding claim' is a "
               "pattern code detects and sends to a person. The backend also flags a "
               "contradicted claim with UNCLEAR stance when the label isn't MISINFO (the "
               "label would have been MISINFO had the stance been ENDORSES). Not modelled "
               "by the golden judge.",
    },
    "false_claim_not_refuted": {
        "matches": "backend",
        "why": "Backend-only safety flag (T10): a contradicted claim that is QUOTES or "
               "NEUTRAL in a NO_MISINFO video. Not in §9's text; §9 does not forbid it. "
               "Not modelled by the golden judge.",
    },
    "trigger_on_non_deciding_claim_when_nothing_decides": {
        "matches": "backend",
        "why": "§11 limits the conflict and UNCLEAR-stance triggers to a *deciding* claim. "
               "When no claim decides (nothing judged), the golden review_triggers falls "
               "back to every claim (`pool = deciding or claims`); §11 has no such "
               "fallback.",
    },
    "weak_evidence_covered_by_judge_reason": {
        "matches": "both (same review outcome)",
        "why": "§11 lists a deciding claim that is MIXED or UNSUPPORTED as a weak-evidence "
               "trigger, and the backend raises weak_evidence:<cid> for it. The golden "
               "judge (022ac44) leaves that trigger out because its own mixed_evidence / "
               "unproven_claim reason for the same claim already sends the video to "
               "review. Same claim, same outcome, one extra reason on the backend side.",
    },
    "nothing_judged_not_in_pinned_golden_judge": {
        "matches": "backend (expected; golden judge not yet re-pinned)",
        "why": "§9 pseudocode and §11 (commit 93068e6, T37): when no claim could be judged "
               "and any claim is INSUFFICIENT_EVIDENCE, the judge adds the review reason "
               "nothing_judged. The golden set's judge.py gets the same rule "
               "separately; the vendored copy pinned in the fixture predates it, so the "
               "backend raises the reason alone. Expected until the fixture is re-pinned "
               "(data/golden-label-set 0fbc68a has the rule; there the reason matches on "
               "all 28 videos).",
    },
    "main_claims_unchecked_not_in_golden_judge": {
        "matches": "backend (expected; review coverage rule the golden judge does not model)",
        "why": "T64 (f), lead decision 2026-11-26: when the label is NO_MISINFO and at least "
               "half of the endorsed treatment_efficacy / prevention claims are "
               "INSUFFICIENT_EVIDENCE, the backend judge adds the video-level review reason "
               "main_claims_unchecked (label unchanged, severity unchanged). The golden "
               "judge has no such rule and the golden set has no claim categories.",
    },
}


@dataclass
class VideoComparison:
    video_id: str
    out_of_scope: bool
    backend: JudgeOutput
    golden: JudgeOutput
    recorded_label: str
    recorded_reasons_match_golden: bool
    backend_only: frozenset[str] = field(default_factory=frozenset)
    golden_only: frozenset[str] = field(default_factory=frozenset)
    differences: dict[str, str] = field(default_factory=dict)  # reason → kind

    @property
    def label_agrees(self) -> bool:
        return self.backend.label == self.golden.label

    @property
    def basis_agrees(self) -> bool:
        return self.backend.basis == self.golden.basis

    @property
    def deciding_agrees(self) -> bool:
        return self.backend.deciding == self.golden.deciding

    @property
    def reasons_agree(self) -> bool:
        return self.backend.reasons == self.golden.reasons

    @property
    def review_agrees(self) -> bool:
        """Both send the video to review, or neither does (on the shared signals)."""
        return bool(self.backend.reasons) == bool(self.golden.reasons)


def classify_difference(reason: str, side: str, video: GoldenVideo, golden: JudgeOutput) -> str:
    """Which known kind a one-sided reason belongs to, or ``unclassified``."""
    kind, _, cid = reason.partition(":")
    deciding = set(golden.deciding)
    if side == "backend":
        if kind in ("denies_supported", "possible_debunk") and cid not in deciding:
            return "rule_reason_from_non_deciding_claim"
        if kind == "mixed_video":
            return "mixed_video"
        if kind == "mixed_evidence":
            return "mixed_evidence"
        if kind == "nothing_judged" and not golden.deciding:
            return "nothing_judged_not_in_pinned_golden_judge"
        if kind in ("unclear_stance_contradicted", "false_claim_not_refuted"):
            return kind
        if kind == "main_claims_unchecked" and golden.label == "NO_MISINFO":
            return "main_claims_unchecked_not_in_golden_judge"
        if kind == "weak_evidence" and (
            f"unproven_claim:{cid}" in golden.reasons or f"mixed_evidence:{cid}" in golden.reasons
        ):
            return "weak_evidence_covered_by_judge_reason"
    if side == "golden" and not golden.deciding and kind in ("conflicting_evidence", "unclear_stance"):
        return "trigger_on_non_deciding_claim_when_nothing_decides"
    return "unclassified"


def compare(video: GoldenVideo, judge: GoldenJudge, review_reasons: GoldenReasons) -> VideoComparison:
    backend = run_backend(video)
    golden = run_golden(video, judge, review_reasons)
    recorded_ok = (
        video.recorded_label == golden.label
        and video.recorded_basis == golden.basis
        and list(video.recorded_review_reasons) == list(golden.raw)
    )
    b_only = backend.reasons - golden.reasons
    g_only = golden.reasons - backend.reasons
    diffs = {r: classify_difference(r, "backend", video, golden) for r in sorted(b_only)}
    diffs.update({r: classify_difference(r, "golden", video, golden) for r in sorted(g_only)})
    return VideoComparison(
        video_id=video.video_id, out_of_scope=video.out_of_scope, backend=backend, golden=golden,
        recorded_label=video.recorded_label, recorded_reasons_match_golden=recorded_ok,
        backend_only=frozenset(b_only), golden_only=frozenset(g_only), differences=diffs,
    )


def compare_all(
    videos: Sequence[GoldenVideo], judge: GoldenJudge, review_reasons: GoldenReasons
) -> list[VideoComparison]:
    return [compare(v, judge, review_reasons) for v in videos]


# ------------------------------------------------------------------ report


def agreement_table(results: Sequence[VideoComparison]) -> list[tuple[str, int, int]]:
    """``(check, agree, total)`` rows; counts only, no accuracy (labels are data)."""
    in_scope = [r for r in results if not r.out_of_scope]

    def row(name: str, pred: Callable[[VideoComparison], bool], pool=in_scope):
        return (name, sum(1 for r in pool if pred(r)), len(pool))

    return [
        row("video label (in scope)", lambda r: r.label_agrees),
        row("video label (out_of_scope, no claims)", lambda r: r.label_agrees,
            [r for r in results if r.out_of_scope]),
        row("misinfo_basis (in scope)", lambda r: r.basis_agrees),
        row("deciding claims", lambda r: r.deciding_agrees),
        row("sent to review (shared signals)", lambda r: r.review_agrees),
        row("review reasons, exact (shared vocabulary)", lambda r: r.reasons_agree),
        row("golden judge reproduces videos.csv label + basis + review_reasons",
            lambda r: r.recorded_reasons_match_golden, list(results)),
    ]


def difference_counts(results: Sequence[VideoComparison]) -> dict[str, tuple[int, int, list[str]]]:
    """kind → (reasons, videos, video ids)."""
    out: dict[str, tuple[int, int, list[str]]] = {}
    for r in results:
        for kind in r.differences.values():
            n, _, vids = out.get(kind, (0, 0, []))
            if r.video_id not in vids:
                vids = [*vids, r.video_id]
            out[kind] = (n + 1, len(vids), vids)
    return out


def render_markdown(results: Sequence[VideoComparison], source: Optional[str] = None) -> str:
    lines = ["# Judge cross-check (T24)", ""]
    if source:
        lines += [f"Golden set: {source}", ""]
    lines += ["| Check | Agree | Of |", "|---|---:|---:|"]
    lines += [f"| {n} | {a} | {t} |" for n, a, t in agreement_table(results)]
    lines += ["", "## Differences by kind", "",
              "| Kind | Reasons | Videos | Matches §9/§11 | Videos |", "|---|---:|---:|---|---|"]
    for kind, (n, nv, vids) in sorted(difference_counts(results).items()):
        matches = DIFFERENCE_KINDS.get(kind, {}).get("matches", "UNCLASSIFIED")
        lines.append(f"| {kind} | {n} | {nv} | {matches} | {', '.join(vids)} |")
    lines += ["", "## Per video (only videos with a difference)", ""]
    for r in results:
        if r.label_agrees and r.basis_agrees and r.reasons_agree and r.deciding_agrees:
            continue
        lines.append(f"- **{r.video_id}** label backend={r.backend.label} golden={r.golden.label}; "
                     f"basis backend={r.backend.basis or '-'} golden={r.golden.basis or '-'}; "
                     f"deciding backend={list(r.backend.deciding)} golden={list(r.golden.deciding)}")
        for reason, kind in r.differences.items():
            side = "backend only" if reason in r.backend_only else "golden only"
            lines.append(f"  - {side}: `{reason}` ({kind})")
    lines += ["", "## Why each kind matches the side it does", ""]
    for kind, d in DIFFERENCE_KINDS.items():
        lines.append(f"- **{kind}** → {d['matches']}. {d['why']}")
    return "\n".join(lines) + "\n"
