"""Deterministic validation of the graph's output (target design §10; issue #36).

Nothing reaches a researcher without passing these plain-code checks. They catch
fabricated or broken output; they do not judge meaning (whether a real paper supports
the verdict is the critic's question and the evaluation's measurement).

| Check (``ValidationIssue.check``) | What it catches |
|---|---|
| ``schema``               | malformed records, labels outside the allowed set, missing required fields |
| ``citation_membership``  | an evidence ID cited for a claim that was not retrieved for that claim |
| ``quote_membership``     | a quoted snippet that is not in the transcript, OCR text or claim text |
| ``source_ids``           | claim or stance segment IDs that are not in the video; unknown claim IDs |
| ``merge_plausibility``   | speech and captions merged into one claim that don't overlap in time |
| ``timestamps``           | negative times, start after end, times past the video's length |
| ``consistency``          | a label that is not what the §9 rules give for these claims |
| ``length_limits``        | runaway explanations, rationales, limitations |

Every issue names the step whose output is wrong (``step``). Issues in the judge's own
output (``final_result``) can be repaired by re-running the judge once (§10 "one
repair attempt"); issues in upstream records cannot be repaired here, because those
nodes already ran their own repair (the verifier re-asks once, T06; the stance step
falls back to UNCLEAR, T04), so they go straight to review.

The validator only reads state. ``make_validate_result`` wraps it as the
``validate_result`` node, which writes ``validation_errors`` (one string per issue,
``"<check>:<step>[:<claim_id>]: <message>"``) and ``validation_attempts``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from pydantic import BaseModel, ValidationError

from app.core.graph import routing as r
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.graph.state import (
    CriticResult,
    EvidenceRecord,
    FinalClassification,
    FusedSegment,
    GraphClaim,
    OcrSegment,
    PipelineState,
    StanceResult,
    TranscriptSegment,
    VerificationResult,
)

# Check names.
CHECK_SCHEMA = "schema"
CHECK_CITATIONS = "citation_membership"
CHECK_QUOTES = "quote_membership"
CHECK_SOURCE_IDS = "source_ids"
CHECK_MERGE = "merge_plausibility"
CHECK_TIMESTAMPS = "timestamps"
CHECK_CONSISTENCY = "consistency"
CHECK_LENGTH = "length_limits"

ALL_CHECKS: tuple[str, ...] = (
    CHECK_SCHEMA, CHECK_CITATIONS, CHECK_QUOTES, CHECK_SOURCE_IDS,
    CHECK_MERGE, CHECK_TIMESTAMPS, CHECK_CONSISTENCY, CHECK_LENGTH,
)

# The one step validation can re-run (§10 "the failing step is re-run with the error
# message"): everything in ``final_result`` comes from the judge.
REPAIRABLE_STEPS: frozenset[str] = frozenset({r.JUDGE_CLASSIFICATION})
DEFAULT_MAX_REPAIRS = 1


@dataclass(frozen=True)
class ValidationLimits:
    """Bounds for the §10 length and timing checks. The length limits match what the
    producing nodes already truncate to, so a well-behaved node never trips them."""

    max_explanation_chars: int = 1_500  # judge.MAX_EXPLANATION_CHARS
    max_limitations: int = 10  # judge.MAX_LIMITATIONS
    max_limitation_chars: int = 300
    max_verifier_explanation_chars: int = 1_000  # verifier.MAX_EXPLANATION_CHARS
    max_rationale_chars: int = 500  # stance.MAX_RATIONALE_CHARS
    max_critic_issue_chars: int = 500
    max_claim_chars: int = 1_000
    # Loop budgets, so the consistency check sees the verdicts the judge saw (T07: an
    # exhausted claim abstains as INSUFFICIENT_EVIDENCE).
    budgets: Budgets = DEFAULT_BUDGETS
    # Pieces merged into one claim may be this far apart and still count as
    # overlapping (a caption that appears just after the words it repeats).
    merge_gap_seconds: float = 2.0
    # Times may run this far past the video's stated length (container rounding).
    duration_tolerance_seconds: float = 0.5
    # Quotes shorter than this are not checked (single words, IDs in quotes).
    min_quote_chars: int = 12


DEFAULT_LIMITS = ValidationLimits()


@dataclass(frozen=True)
class ValidationIssue:
    check: str
    step: str
    message: str
    claim_id: Optional[str] = None

    @property
    def code(self) -> str:
        return f"{self.check}:{self.step}" + (f":{self.claim_id}" if self.claim_id else "")

    @property
    def repairable(self) -> bool:
        return self.step in REPAIRABLE_STEPS

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


_ISSUE_RE = re.compile(r"^(?P<check>[a-z_]+):(?P<step>[a-z_]+)(?::(?P<claim>[^:\s]+))?: ")


def parse_issue(text: str) -> Optional[ValidationIssue]:
    """Read back an issue stored in ``validation_errors``. ``None`` for strings that
    weren't written by this module (they are treated as not repairable)."""
    m = _ISSUE_RE.match(text or "")
    if not m or m.group("check") not in ALL_CHECKS:
        return None
    return ValidationIssue(
        check=m.group("check"), step=m.group("step"),
        message=text[m.end():], claim_id=m.group("claim"),
    )


# ------------------------------------------------------------------ helpers


def _norm(text: str) -> str:
    """Case-, accent- and whitespace-insensitive form for quote matching."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(re.sub(r"[^\w' ]+", " ", text).split())


_QUOTE_RE = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')


def quoted_snippets(text: str) -> list[str]:
    """Double-quoted snippets in ``text`` (straight or curly quotes)."""
    return [a or b for a, b in _QUOTE_RE.findall(text or "")]


def _evidence_by_claim(state: PipelineState) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for key in ("retrieved_evidence", "reranked_evidence", "library_evidence"):
        for cid, records in (state.get(key) or {}).items():
            out.setdefault(cid, set()).update(e.evidence_id for e in records or [])
    return out


def _segments(state: PipelineState) -> dict[str, tuple[float, float, str]]:
    """Every segment ID the video has, with its timing and text."""
    out: dict[str, tuple[float, float, str]] = {}
    for s in state.get("transcript_segments") or []:
        out[s.segment_id] = (s.start, s.end, s.text)
    for s in state.get("ocr_segments") or []:
        out[s.segment_id] = (s.start, s.end, s.text)
    for s in state.get("fused_segments") or []:
        out.setdefault(s.segment_id, (s.start, s.end, " ".join([s.spoken, *s.on_screen])))
    return out


# ------------------------------------------------------------------ checks

_RECORD_TYPES: tuple[tuple[str, type[BaseModel], bool], ...] = (
    # (state field, record type, is a per-claim mapping)
    ("transcript_segments", TranscriptSegment, False),
    ("ocr_segments", OcrSegment, False),
    ("fused_segments", FusedSegment, False),
    ("claims", GraphClaim, False),
    ("stance_results", StanceResult, True),
    ("verification_results", VerificationResult, True),
    ("critic_results", CriticResult, True),
)

_FIELD_OWNER = {
    "transcript_segments": r.TRANSCRIBE_AUDIO,
    "ocr_segments": r.EXTRACT_OCR,
    "fused_segments": r.FUSE_MODALITIES,
    "claims": r.EXTRACT_CLAIMS,
    "stance_results": r.ANALYZE_STANCE,
    "verification_results": r.VERIFY_CLAIMS,
    "critic_results": r.CRITIQUE_VERIFICATION,
    "retrieved_evidence": r.RETRIEVE_EVIDENCE,
    "reranked_evidence": r.RERANK_EVIDENCE,
    "library_evidence": r.RERANK_EVIDENCE,  # T12: the library fallback runs in rerank
}


def _revalidate(record: object, model: type[BaseModel]) -> Optional[str]:
    """Re-check a record against its schema. Records normally arrive as validated
    Pydantic objects; a node (or a checkpoint) handing over a dict or a record built
    with ``model_construct`` is caught here."""
    try:
        data = record.model_dump(warnings=False) if isinstance(record, BaseModel) else record
        model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first.get("loc", ()))
        return f"{model.__name__} invalid at {loc or '<root>'}: {first.get('msg')}"
    except Exception as exc:  # not a mapping at all
        return f"{model.__name__} invalid: {type(exc).__name__}"
    return None


def check_schema(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for field, model, per_claim in _RECORD_TYPES:
        value = state.get(field)
        if value is None:
            continue
        items = value.items() if per_claim and isinstance(value, dict) else enumerate(value)
        for key, rec in items:
            err = _revalidate(rec, model)
            if err:
                cid = key if per_claim else getattr(rec, "claim_id", None)
                issues.append(ValidationIssue(CHECK_SCHEMA, _FIELD_OWNER[field], err, cid))
            elif per_claim and getattr(rec, "claim_id", key) != key:
                issues.append(ValidationIssue(
                    CHECK_SCHEMA, _FIELD_OWNER[field],
                    f"stored under {key!r} but its claim_id is {rec.claim_id!r}", key,
                ))
    for field in ("retrieved_evidence", "reranked_evidence", "library_evidence"):
        for cid, records in (state.get(field) or {}).items():
            for rec in records or []:
                err = _revalidate(rec, EvidenceRecord)
                if err:
                    issues.append(ValidationIssue(CHECK_SCHEMA, _FIELD_OWNER[field], err, cid))

    final = state.get("final_result")
    judge = r.JUDGE_CLASSIFICATION
    if final is None:
        issues.append(ValidationIssue(CHECK_SCHEMA, judge, "final_result missing"))
        return issues
    err = _revalidate(final, FinalClassification)
    if err:
        issues.append(ValidationIssue(CHECK_SCHEMA, judge, err))
        return issues
    if final.video_id != state.get("video_id"):
        issues.append(ValidationIssue(
            CHECK_SCHEMA, judge, f"video_id {final.video_id!r} is not this run's video",
        ))
    if not final.explanation.strip():
        issues.append(ValidationIssue(CHECK_SCHEMA, judge, "explanation is empty"))
    if not final.decision_rule:
        issues.append(ValidationIssue(CHECK_SCHEMA, judge, "decision_rule missing"))
    if final.confidence is not None and not 0.0 <= final.confidence <= 1.0:
        issues.append(ValidationIssue(CHECK_SCHEMA, judge, f"confidence {final.confidence} outside [0, 1]"))
    return issues


def check_citations(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """Every cited evidence ID was retrieved for that claim (§10). A paper retrieved
    for a different claim counts as misattributed."""
    issues: list[ValidationIssue] = []
    allowed = _evidence_by_claim(state)
    for cid, v in (state.get("verification_results") or {}).items():
        if not isinstance(v, VerificationResult):
            continue  # reported by the schema check
        for eid in dict.fromkeys([*v.supporting_evidence_ids, *v.contradicting_evidence_ids]):
            if eid not in allowed.get(cid, set()):
                issues.append(ValidationIssue(
                    CHECK_CITATIONS, r.VERIFY_CLAIMS,
                    f"verdict cites {eid!r}, which was not retrieved for this claim", cid,
                ))
    final = state.get("final_result")
    if isinstance(final, FinalClassification):
        deciding = set(final.claim_ids)
        ok = set().union(*(allowed.get(c, set()) for c in deciding)) if deciding else set()
        for eid in final.evidence_ids:
            if eid not in ok:
                where = "any claim" if not any(eid in s for s in allowed.values()) else "a deciding claim"
                issues.append(ValidationIssue(
                    CHECK_CITATIONS, r.JUDGE_CLASSIFICATION,
                    f"result cites {eid!r}, which was not retrieved for {where}",
                ))
    return issues


def check_quotes(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """Every quoted snippet appears in the transcript, OCR text or a claim's text (§10).

    Claim texts count as quotable because the explanation quotes claims and extraction
    keeps claims close to the original words (T10 checks that grounding). A snippet
    ending in "…" (the judge's truncation) must match as a prefix.
    """
    sources = [_norm(t) for _, _, t in _segments(state).values()]
    sources += [_norm(c.claim_text) for c in state.get("claims") or [] if isinstance(c, GraphClaim)]
    corpus = "\n".join(sources)

    def found(snippet: str) -> bool:
        s = _norm(snippet.rstrip("…").rstrip("."))
        return len(s) < limits.min_quote_chars or s in corpus

    issues: list[ValidationIssue] = []
    final = state.get("final_result")
    if isinstance(final, FinalClassification):
        for q in quoted_snippets(final.explanation):
            if not found(q):
                issues.append(ValidationIssue(
                    CHECK_QUOTES, r.JUDGE_CLASSIFICATION,
                    f"explanation quotes {q[:80]!r}, which is not in the video",
                ))
    for cid, s in (state.get("stance_results") or {}).items():
        if isinstance(s, StanceResult):
            for q in quoted_snippets(s.rationale):
                if not found(q):
                    issues.append(ValidationIssue(
                        CHECK_QUOTES, r.ANALYZE_STANCE,
                        f"stance rationale quotes {q[:80]!r}, which is not in the video", cid,
                    ))
    return issues


def check_source_ids(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """Every claim's and stance's segment IDs exist; every claim ID is a known claim."""
    issues: list[ValidationIssue] = []
    known_segments = set(_segments(state))
    claims = [c for c in state.get("claims") or [] if isinstance(c, GraphClaim)]
    claim_ids = {c.claim_id for c in claims}
    seen: set[str] = set()
    for c in claims:
        if c.claim_id in seen:
            issues.append(ValidationIssue(CHECK_SOURCE_IDS, r.EXTRACT_CLAIMS, "duplicate claim_id", c.claim_id))
        seen.add(c.claim_id)
        if not c.source_segment_ids:
            issues.append(ValidationIssue(CHECK_SOURCE_IDS, r.EXTRACT_CLAIMS, "claim cites no segments", c.claim_id))
        for sid in c.source_segment_ids:
            if sid not in known_segments:
                issues.append(ValidationIssue(
                    CHECK_SOURCE_IDS, r.EXTRACT_CLAIMS, f"source segment {sid!r} is not in the video", c.claim_id,
                ))
    for cid, s in (state.get("stance_results") or {}).items():
        if cid not in claim_ids:
            issues.append(ValidationIssue(CHECK_SOURCE_IDS, r.ANALYZE_STANCE, "stance for an unknown claim", cid))
        if isinstance(s, StanceResult):
            for sid in s.stance_segment_ids:
                if sid not in known_segments:
                    issues.append(ValidationIssue(
                        CHECK_SOURCE_IDS, r.ANALYZE_STANCE, f"stance cites segment {sid!r}, which is not in the video", cid,
                    ))
    for field, step in (("verification_results", r.VERIFY_CLAIMS), ("critic_results", r.CRITIQUE_VERIFICATION)):
        for cid in state.get(field) or {}:
            if cid not in claim_ids:
                issues.append(ValidationIssue(CHECK_SOURCE_IDS, step, "result for an unknown claim", cid))
    final = state.get("final_result")
    if isinstance(final, FinalClassification):
        for cid in final.claim_ids:
            if cid not in claim_ids:
                issues.append(ValidationIssue(
                    CHECK_SOURCE_IDS, r.JUDGE_CLASSIFICATION, f"result names unknown claim {cid!r}",
                ))
    return issues


def check_merge_plausibility(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """Pieces merged into one claim overlap in time (within ``merge_gap_seconds``),
    and the claim's own span overlaps them. Said at 0:04 and shown at 0:40 is not one
    moment, so it should have been two claims."""
    issues: list[ValidationIssue] = []
    segs = _segments(state)
    gap = limits.merge_gap_seconds
    for c in state.get("claims") or []:
        if not isinstance(c, GraphClaim):
            continue
        spans = sorted((segs[s][0], segs[s][1], s) for s in c.source_segment_ids if s in segs)
        if not spans:
            continue
        reach = spans[0][1]
        for start, end, sid in spans[1:]:
            if start - reach > gap:
                issues.append(ValidationIssue(
                    CHECK_MERGE, r.EXTRACT_CLAIMS,
                    f"segment {sid!r} starts {start - reach:.1f}s after the rest of the claim ends", c.claim_id,
                ))
            reach = max(reach, end)
        lo, hi = spans[0][0], reach
        if c.start_seconds > hi + gap or c.end_seconds < lo - gap:
            issues.append(ValidationIssue(
                CHECK_MERGE, r.EXTRACT_CLAIMS,
                f"claim time {c.start_seconds:.1f}-{c.end_seconds:.1f}s is outside its segments ({lo:.1f}-{hi:.1f}s)",
                c.claim_id,
            ))
    return issues


def check_timestamps(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """Within the video's length, not negative, start before end (§10). Segments may
    have zero length (Whisper emits those); claims may not."""
    issues: list[ValidationIssue] = []
    duration = state.get("video_duration_seconds")
    ceiling = None if duration is None else float(duration) + limits.duration_tolerance_seconds

    def bad(start: float, end: float, *, strict: bool) -> Optional[str]:
        if start < 0 or end < 0:
            return f"negative time ({start:.2f}-{end:.2f}s)"
        if start > end or (strict and start == end):
            return f"start {start:.2f}s is not before end {end:.2f}s"
        if ceiling is not None and end > ceiling:
            return f"ends at {end:.2f}s, after the video's {float(duration):.2f}s"
        return None

    for field, step in (("transcript_segments", r.TRANSCRIBE_AUDIO), ("ocr_segments", r.EXTRACT_OCR),
                        ("fused_segments", r.FUSE_MODALITIES)):
        for s in state.get(field) or []:
            if isinstance(s, BaseModel):
                msg = bad(s.start, s.end, strict=False)
                if msg:
                    issues.append(ValidationIssue(CHECK_TIMESTAMPS, step, f"segment {s.segment_id!r}: {msg}"))
    for c in state.get("claims") or []:
        if isinstance(c, GraphClaim):
            msg = bad(c.start_seconds, c.end_seconds, strict=True)
            if msg:
                issues.append(ValidationIssue(CHECK_TIMESTAMPS, r.EXTRACT_CLAIMS, msg, c.claim_id))
    return issues


def check_consistency(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """The label, rule and deciding claims are what the §9 rules give for these claims."""
    from app.core.graph.judge import claim_views, decide  # judge imports this package

    final = state.get("final_result")
    if not isinstance(final, FinalClassification):
        return []
    views, _ = claim_views(state, limits.budgets)
    checkable = [c for c in state.get("claims") or [] if isinstance(c, GraphClaim) and c.requires_verification]
    d = decide(views, has_claims=bool(checkable))
    issues = []
    if final.classification != d.label:
        issues.append(ValidationIssue(
            CHECK_CONSISTENCY, r.JUDGE_CLASSIFICATION,
            f"label {final.classification.value} but the rules give {d.label.value} ({d.rule})",
        ))
    else:
        if final.decision_rule and final.decision_rule != d.rule:
            issues.append(ValidationIssue(
                CHECK_CONSISTENCY, r.JUDGE_CLASSIFICATION,
                f"decision_rule {final.decision_rule!r} but the rules give {d.rule!r}",
            ))
        if set(final.claim_ids) != set(d.claim_ids):
            issues.append(ValidationIssue(
                CHECK_CONSISTENCY, r.JUDGE_CLASSIFICATION,
                f"deciding claims {sorted(final.claim_ids)} but the rules give {sorted(d.claim_ids)}",
            ))
    missing = [f for f in d.review_flags if f not in final.review_flags]
    if missing:
        issues.append(ValidationIssue(
            CHECK_CONSISTENCY, r.JUDGE_CLASSIFICATION, f"review flags missing: {missing}",
        ))
    return issues


def check_lengths(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def over(text: str, cap: int) -> bool:
        return len(text or "") > cap

    final = state.get("final_result")
    if isinstance(final, FinalClassification):
        j = r.JUDGE_CLASSIFICATION
        if over(final.explanation, limits.max_explanation_chars):
            issues.append(ValidationIssue(
                CHECK_LENGTH, j, f"explanation is {len(final.explanation)} chars (max {limits.max_explanation_chars})",
            ))
        if len(final.limitations) > limits.max_limitations:
            issues.append(ValidationIssue(
                CHECK_LENGTH, j, f"{len(final.limitations)} limitations (max {limits.max_limitations})",
            ))
        if any(over(x, limits.max_limitation_chars) for x in final.limitations):
            issues.append(ValidationIssue(CHECK_LENGTH, j, f"a limitation exceeds {limits.max_limitation_chars} chars"))
    for cid, v in (state.get("verification_results") or {}).items():
        if isinstance(v, VerificationResult):
            if over(v.explanation, limits.max_verifier_explanation_chars):
                issues.append(ValidationIssue(CHECK_LENGTH, r.VERIFY_CLAIMS, "verifier explanation too long", cid))
            if any(over(x, limits.max_limitation_chars) for x in v.limitations):
                issues.append(ValidationIssue(CHECK_LENGTH, r.VERIFY_CLAIMS, "verifier limitation too long", cid))
    for cid, s in (state.get("stance_results") or {}).items():
        if isinstance(s, StanceResult) and over(s.rationale, limits.max_rationale_chars):
            issues.append(ValidationIssue(CHECK_LENGTH, r.ANALYZE_STANCE, "stance rationale too long", cid))
    for cid, c in (state.get("critic_results") or {}).items():
        if isinstance(c, CriticResult) and any(over(x, limits.max_critic_issue_chars) for x in c.issues):
            issues.append(ValidationIssue(CHECK_LENGTH, r.CRITIQUE_VERIFICATION, "critic issue too long", cid))
    for c in state.get("claims") or []:
        if isinstance(c, GraphClaim) and over(c.claim_text, limits.max_claim_chars):
            issues.append(ValidationIssue(CHECK_LENGTH, r.EXTRACT_CLAIMS, "claim text too long", c.claim_id))
    return issues


CheckFn = Callable[[PipelineState, ValidationLimits], list[ValidationIssue]]

CHECKS: dict[str, CheckFn] = {
    CHECK_SCHEMA: check_schema,
    CHECK_CITATIONS: check_citations,
    CHECK_QUOTES: check_quotes,
    CHECK_SOURCE_IDS: check_source_ids,
    CHECK_MERGE: check_merge_plausibility,
    CHECK_TIMESTAMPS: check_timestamps,
    CHECK_CONSISTENCY: check_consistency,
    CHECK_LENGTH: check_lengths,
}
assert tuple(CHECKS) == ALL_CHECKS


def validate(state: PipelineState, limits: ValidationLimits = DEFAULT_LIMITS) -> list[ValidationIssue]:
    """Run every §10 check. A check that crashes is itself an issue: validation never
    lets output through because it couldn't look at it."""
    issues: list[ValidationIssue] = []
    for name, fn in CHECKS.items():
        try:
            issues += fn(state, limits)
        except Exception as exc:  # pragma: no cover - defensive
            issues.append(ValidationIssue(name, "validate_result", f"check crashed: {type(exc).__name__}"))
    return list(dict.fromkeys(issues))


def make_validate_result(
    limits: ValidationLimits = DEFAULT_LIMITS, *, budgets: Optional[Budgets] = None
) -> Callable[[PipelineState], dict]:
    """The ``validate_result`` node. Writes ``validation_errors`` (empty when the
    output passed) and ``validation_attempts`` (how many times it has run). Pass the
    graph's ``budgets`` (as for the judge)."""
    if budgets is not None:
        from dataclasses import replace

        limits = replace(limits, budgets=budgets)

    def validate_result(state: PipelineState) -> dict:
        issues = validate(state, limits)
        return {
            "validation_errors": [str(i) for i in issues],
            "validation_attempts": int(state.get("validation_attempts") or 0) + 1,
        }

    return validate_result


# ------------------------------------------------------------------ repair routing


def stored_issues(state: PipelineState) -> list[ValidationIssue]:
    """Issues stored in ``validation_errors``. Strings not written by this module (a
    custom validator) are kept as non-repairable issues with check ``""`` so they still
    reach review."""
    out = []
    for text in state.get("validation_errors") or []:
        out.append(parse_issue(text) or ValidationIssue("", "unknown", text))
    return out


def in_repair(state: PipelineState) -> bool:
    """True while the judge is being re-run to repair its output (§10)."""
    return bool(state.get("validation_errors")) and int(state.get("validation_attempts") or 0) >= 1


def needs_repair(state: PipelineState, max_repairs: int = DEFAULT_MAX_REPAIRS) -> bool:
    """One repair attempt: only after the first validation (attempts == 1, up to
    ``max_repairs``), and only when the judge's own output is at fault. A run whose
    ``validation_attempts`` was never set (a custom validator) is not repaired."""
    attempts = int(state.get("validation_attempts") or 0)
    if not 1 <= attempts <= max_repairs:
        return False
    return any(i.repairable for i in stored_issues(state))


def failed_checks(state: PipelineState) -> list[str]:
    """Review reasons for validation that still fails (after any repair):
    ``validation_failed:<check>[:<claim_id>]``, one per distinct check and claim."""
    reasons = []
    for i in stored_issues(state):
        reason = "validation_failed" + (f":{i.check}" if i.check else "")
        reasons.append(reason + (f":{i.claim_id}" if i.claim_id else ""))
    return list(dict.fromkeys(reasons))


def issues_for(issues: Iterable[ValidationIssue], check: str) -> list[ValidationIssue]:
    return [i for i in issues if i.check == check]
