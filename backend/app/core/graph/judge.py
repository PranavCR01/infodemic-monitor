"""Judge node: one label for the video (target design §9; issue #35).

By the time the judge runs, each claim has a stance (§5) and a verdict (§7). Turning
those into one video label is a written policy, so it is code: the same inputs always
give the same label. An LLM only writes the explanation; it never chooses the label.

**The policy (§9, checked in order).** Only claims in ``state["claims"]`` that have a
verdict take part.

1. ``endorsed_contradicted``: any claim is ENDORSES + CONTRADICTED → MISINFO.
2. ``refuted_contradicted``: otherwise any claim is REFUTES + CONTRADICTED → DEBUNKING.
3. ``judged_nothing_false_endorsed``: otherwise at least one claim is SUPPORTED or
   CONTRADICTED → NO_MISINFO.
4. ``nothing_judged``: otherwise (all INSUFFICIENT_EVIDENCE / MIXED / NOT_VERIFIABLE)
   → CANNOT_RECOGNIZE; ``no_claims`` when there were no checkable claims at all.

The label comes with the claims that decided it and only the evidence those claims'
verdicts cited, so the explanation can point at them.

**Patterns the rules can't settle (§9 "Where an LLM still helps").** Code detects them
and records them in ``final_result.review_flags``; the review policy turns them into
review reasons. They never change the label: a person settles them (see
context/MULTI_AGENT.md §7h for why not an LLM).

- ``mixed_video``: a false claim is endorsed and another false claim is refuted.
- ``unclear_stance_contradicted:<cid>``: a contradicted claim's stance is UNCLEAR (or
  missing) and the label is not MISINFO, so the label rests on a stance nobody could
  read.
- ``false_claim_not_refuted:<cid>``: the label is NO_MISINFO although a contradicted
  claim is QUOTES or NEUTRAL (T10's adversarial finding: nudging the stance step alone
  must not clear a video).
- ``mixed_evidence:<cid>``: a claim's evidence is MIXED (§9 probe: "the science is split"
  is something a person should see).
- ``verification_failed:<cid>``: the verifier could not be reached for a claim (T06
  note), so its INSUFFICIENT_EVIDENCE is not a real finding.

Materiality and satire are not detected by code yet (no reliable signal without a
labelled set); they are left for the review rule and later work.

**Citations.** The judge cites only claim IDs in ``claims`` and evidence IDs that were
retrieved (or reranked) for that same claim. A verdict citing anything else is dropped
from the citation list and recorded as a ``guardrail:`` error, which sends the run to
review.

Writes only ``final_result`` (plus the shared, append-only ``errors``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol, Sequence

from app.core.graph import routing as r
from app.core.graph.state import (
    EvidenceRecord,
    FinalClassification,
    GraphClaim,
    NodeError,
    PipelineState,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
)
from app.core.graph.stance import PromptNotFoundError, load_prompt  # shared prompt loader
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX
from app.core.guardrails.outputs import ExplanationOutput, OutputViolation, parse_output
from app.core.guardrails.untrusted import (
    DEFAULT_MAX_BLOCK_CHARS,
    GuardedPrompt,
    explanation_prompt,
    fence,
    guarded_system_prompt,
)
from app.core.schemas.pipeline import Claim, ClassificationResult, MisinfoLabel, PubMedCitation

STEP = "judge_explanation"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "explain_v1"
TOOL_NAME = "record_explanation"
MAX_EXPLANATION_CHARS = 1_500  # §10 length limits
MAX_LIMITATIONS = 10
MAX_LIMITATION_CHARS = 300
MAX_CLAIMS_IN_PROMPT = 10
MAX_QUOTE_CHARS = 200

# Rule names (stored in ``final_result.decision_rule``).
RULE_ENDORSED_CONTRADICTED = "endorsed_contradicted"
RULE_REFUTED_CONTRADICTED = "refuted_contradicted"
RULE_JUDGED = "judged_nothing_false_endorsed"
RULE_NOTHING_JUDGED = "nothing_judged"
RULE_NO_CLAIMS = "no_claims"

# Review flags (prefixes; per-claim flags end in ``:<claim_id>``).
FLAG_MIXED_VIDEO = "mixed_video"
FLAG_UNCLEAR_STANCE = "unclear_stance_contradicted"
FLAG_NOT_REFUTED = "false_claim_not_refuted"
FLAG_MIXED_EVIDENCE = "mixed_evidence"
FLAG_VERIFICATION_FAILED = "verification_failed"

JUDGED_VERDICTS = frozenset({Verdict.SUPPORTED, Verdict.CONTRADICTED})

__all__ = [
    "STEP", "DEFAULT_PROMPT_VERSION", "TOOL_NAME", "EXPLAIN_TOOL", "TOOL_CHOICE",
    "ClaimView", "Decision", "PromptNotFoundError",
    "claim_views", "decide", "template_explanation", "check_explanation",
    "build_prompt", "build_request", "judge", "make_judge_classification",
    "claim_label", "to_classification_result",
]


class StepCaller(Protocol):
    """Anything that runs one routed LLM step (T01's ``ModelRouter`` satisfies this)."""

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> Any: ...


# ------------------------------------------------------------------ inputs


@dataclass(frozen=True)
class ClaimView:
    """One claim with everything the policy reads about it."""

    claim: GraphClaim
    stance: Optional[Stance]  # None: no stance result (treated like UNCLEAR)
    verification: VerificationResult
    allowed_evidence_ids: frozenset[str]
    verification_failed: bool = False

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id

    @property
    def verdict(self) -> Verdict:
        return self.verification.verdict

    @property
    def stance_or_unclear(self) -> Stance:
        return self.stance or Stance.UNCLEAR


def _evidence_by_claim(state: PipelineState) -> dict[str, dict[str, EvidenceRecord]]:
    out: dict[str, dict[str, EvidenceRecord]] = {}
    for key in ("retrieved_evidence", "reranked_evidence"):
        for cid, records in (state.get(key) or {}).items():
            for e in records or []:
                out.setdefault(cid, {}).setdefault(e.evidence_id, e)
    return out


def claim_views(state: PipelineState) -> tuple[list[ClaimView], list[NodeError]]:
    """The claims the policy decides over, in extraction order, plus errors for any
    verdict that refers to a claim not in state (it is ignored)."""
    claims = list(state.get("claims") or [])
    known = {c.claim_id for c in claims}
    stances: dict[str, StanceResult] = state.get("stance_results") or {}
    verdicts: dict[str, VerificationResult] = state.get("verification_results") or {}
    evidence = _evidence_by_claim(state)
    failed = {
        e.claim_id for e in state.get("errors") or []
        if e.node == r.VERIFY_CLAIMS and e.retryable and e.claim_id
    }
    errors = [
        NodeError(node=r.JUDGE_CLASSIFICATION, claim_id=cid,
                  message=f"{GUARDRAIL_ERROR_PREFIX}unknown_claim verdict for a claim not in state was ignored")
        for cid in verdicts if cid not in known
    ]
    views = [
        ClaimView(
            claim=c,
            stance=stances[c.claim_id].stance if c.claim_id in stances else None,
            verification=verdicts[c.claim_id],
            allowed_evidence_ids=frozenset(evidence.get(c.claim_id, {})),
            verification_failed=c.claim_id in failed,
        )
        for c in claims if c.claim_id in verdicts
    ]
    return views, errors


# ------------------------------------------------------------------ policy


@dataclass(frozen=True)
class Decision:
    """The rules' output: label, the rule that fired, the deciding claims and the
    evidence they cite, and the patterns a person should look at."""

    label: MisinfoLabel
    rule: str
    deciding: tuple[ClaimView, ...]
    evidence_ids: tuple[str, ...]
    review_flags: tuple[str, ...]
    errors: tuple[NodeError, ...] = ()
    all_claims: tuple[ClaimView, ...] = field(default=(), compare=False)

    @property
    def claim_ids(self) -> list[str]:
        return [v.claim_id for v in self.deciding]


def _cited(view: ClaimView, label: MisinfoLabel) -> list[str]:
    v = view.verification
    if label in (MisinfoLabel.MISINFO, MisinfoLabel.DEBUNKING):
        return list(v.contradicting_evidence_ids)
    return [*v.supporting_evidence_ids, *v.contradicting_evidence_ids]


def decide(views: Sequence[ClaimView], *, has_claims: Optional[bool] = None) -> Decision:
    """Apply the §9 rules in order. Pure: no state, no model."""
    views = list(views)
    has_claims = bool(views) if has_claims is None else has_claims

    endorsed_false = [v for v in views if v.stance == Stance.ENDORSES and v.verdict == Verdict.CONTRADICTED]
    refuted_false = [v for v in views if v.stance == Stance.REFUTES and v.verdict == Verdict.CONTRADICTED]
    judged = [v for v in views if v.verdict in JUDGED_VERDICTS]

    if endorsed_false:
        label, rule, deciding = MisinfoLabel.MISINFO, RULE_ENDORSED_CONTRADICTED, endorsed_false
    elif refuted_false:
        label, rule, deciding = MisinfoLabel.DEBUNKING, RULE_REFUTED_CONTRADICTED, refuted_false
    elif judged:
        label, rule, deciding = MisinfoLabel.NO_MISINFO, RULE_JUDGED, judged
    else:
        label = MisinfoLabel.CANNOT_RECOGNIZE
        rule = RULE_NOTHING_JUDGED if has_claims else RULE_NO_CLAIMS
        deciding = []

    # Citations: only IDs the deciding verdicts cited AND that were retrieved for that
    # same claim. Anything else is dropped and recorded (sends the run to review).
    evidence_ids: list[str] = []
    errors: list[NodeError] = []
    for v in deciding:
        for eid in _cited(v, label):
            if eid in v.allowed_evidence_ids:
                if eid not in evidence_ids:
                    evidence_ids.append(eid)
            else:
                errors.append(NodeError(
                    node=r.JUDGE_CLASSIFICATION, claim_id=v.claim_id,
                    message=f"{GUARDRAIL_ERROR_PREFIX}uncited_evidence verdict cites {eid!r}, "
                            "which was not retrieved for this claim; left out of the result",
                ))

    flags: list[str] = []
    if endorsed_false and refuted_false:
        flags.append(FLAG_MIXED_VIDEO)
    for v in views:
        contradicted = v.verdict == Verdict.CONTRADICTED
        if contradicted and v.stance_or_unclear == Stance.UNCLEAR and label != MisinfoLabel.MISINFO:
            flags.append(f"{FLAG_UNCLEAR_STANCE}:{v.claim_id}")
        if contradicted and v.stance in (Stance.QUOTES, Stance.NEUTRAL) and label == MisinfoLabel.NO_MISINFO:
            flags.append(f"{FLAG_NOT_REFUTED}:{v.claim_id}")
        if v.verdict == Verdict.MIXED:
            flags.append(f"{FLAG_MIXED_EVIDENCE}:{v.claim_id}")
        if v.verification_failed:
            flags.append(f"{FLAG_VERIFICATION_FAILED}:{v.claim_id}")

    return Decision(
        label=label, rule=rule, deciding=tuple(deciding), evidence_ids=tuple(evidence_ids),
        review_flags=tuple(dict.fromkeys(flags)), errors=tuple(errors), all_claims=tuple(views),
    )


# ------------------------------------------------------------------ text


def _quote(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_QUOTE_CHARS else text[: MAX_QUOTE_CHARS - 1] + "…"


def _ids(ids: Iterable[str]) -> str:
    ids = list(ids)
    return ", ".join(ids) if ids else "none"


_FLAG_TEXT = {
    FLAG_MIXED_VIDEO: "the video endorses one false claim and refutes another",
    FLAG_UNCLEAR_STANCE: "the speaker's stance on contradicted claim {cid} is unclear",
    FLAG_NOT_REFUTED: "contradicted claim {cid} is repeated without being refuted",
    FLAG_MIXED_EVIDENCE: "the evidence on claim {cid} is mixed",
    FLAG_VERIFICATION_FAILED: "claim {cid} could not be verified (verifier unavailable)",
}


def flag_text(flag: str) -> str:
    name, _, cid = flag.partition(":")
    return _FLAG_TEXT.get(name, name).format(cid=cid)


def template_explanation(d: Decision) -> str:
    """Deterministic explanation, used when no explanation model is configured or its
    answer is rejected. Always names the rule's deciding claims and evidence."""
    if d.rule == RULE_NO_CLAIMS:
        text = "CANNOT_RECOGNIZE: no checkable health claims were found in the video."
    elif d.rule == RULE_NOTHING_JUDGED:
        parts = [f"{v.claim_id} {v.verdict.value.lower().replace('_', ' ')}" for v in d.all_claims]
        text = (
            "CANNOT_RECOGNIZE: no claim could be judged against the evidence ("
            + "; ".join(parts) + ")."
        )
    elif d.rule == RULE_ENDORSED_CONTRADICTED:
        parts = [
            f'claim {v.claim_id} ("{_quote(v.claim.claim_text)}") is endorsed by the speaker and '
            f"contradicted by the evidence ({_ids(v.verification.contradicting_evidence_ids)})"
            for v in d.deciding
        ]
        text = "MISINFO because " + "; ".join(parts) + "."
    elif d.rule == RULE_REFUTED_CONTRADICTED:
        parts = [
            f'claim {v.claim_id} ("{_quote(v.claim.claim_text)}") is refuted by the speaker and '
            f"contradicted by the evidence ({_ids(v.verification.contradicting_evidence_ids)})"
            for v in d.deciding
        ]
        text = "DEBUNKING because " + "; ".join(parts) + ", and no false claim is endorsed."
    else:
        supported = [v.claim_id for v in d.deciding if v.verdict == Verdict.SUPPORTED]
        contradicted = [
            f"{v.claim_id} ({v.stance_or_unclear.value.lower()})"
            for v in d.deciding if v.verdict == Verdict.CONTRADICTED
        ]
        text = (
            f"NO_MISINFO: {len(d.deciding)} claim(s) could be judged against the evidence and "
            "no claim the speaker endorses is contradicted."
        )
        if supported:
            text += f" Supported: {_ids(supported)}."
        if contradicted:
            text += f" Contradicted but not endorsed: {_ids(contradicted)}."
    if d.review_flags:
        text += " Needs review: " + "; ".join(flag_text(f) for f in d.review_flags) + "."
    return text[:MAX_EXPLANATION_CHARS]


def limitations_for(d: Decision) -> list[str]:
    """The deciding verdicts' limitations (deduplicated), then notes for claims that
    took no part because nothing could be judged."""
    out: list[str] = []
    for v in d.deciding:
        for lim in v.verification.limitations:
            s = f"{v.claim_id}: {lim}"[:MAX_LIMITATION_CHARS]
            if s not in out:
                out.append(s)
    deciding = {v.claim_id for v in d.deciding}
    undecided = [v for v in d.all_claims if v.claim_id not in deciding and v.verdict not in JUDGED_VERDICTS]
    if undecided and d.label != MisinfoLabel.CANNOT_RECOGNIZE:
        out.append(
            "Not judged (no usable evidence): "
            + ", ".join(f"{v.claim_id} {v.verdict.value}" for v in undecided)
        )
    return out[:MAX_LIMITATIONS]


# ------------------------------------------------------------------ explanation model


EXPLAIN_TOOL: dict = {
    "name": TOOL_NAME,
    "description": "Record the explanation of a video label that has already been decided by rules.",
    "input_schema": {
        "type": "object",
        "properties": {
            "explanation": {
                "type": "string",
                "description": "Two to four plain sentences for a public-health analyst.",
            },
        },
        "required": ["explanation"],
        "additionalProperties": False,
    },
}
TOOL_CHOICE: dict = {"type": "tool", "name": TOOL_NAME}

_META_RE = re.compile(r"[^A-Za-z0-9 ,.;:()/_+-]")


def _meta(text: Any) -> str:
    return _META_RE.sub("", str(text))[:120]


def _prompt_claims(d: Decision) -> list[ClaimView]:
    flagged = {f.partition(":")[2] for f in d.review_flags}
    chosen = [v for v in d.all_claims if v.claim_id in {x.claim_id for x in d.deciding} or v.claim_id in flagged]
    return (chosen or list(d.all_claims))[:MAX_CLAIMS_IN_PROMPT]


def _instructions(d: Decision, views: Sequence[ClaimView]) -> str:
    deciding = {v.claim_id for v in d.deciding}
    rows = []
    for v in views:
        rows.append(
            f"- {_meta(v.claim_id)} | stance: {v.stance_or_unclear.value} | verdict: {v.verdict.value}"
            f" | supporting: {_meta(_ids(v.verification.supporting_evidence_ids))}"
            f" | contradicting: {_meta(_ids(v.verification.contradicting_evidence_ids))}"
            f" | deciding: {'yes' if v.claim_id in deciding else 'no'}"
        )
    flags = "\n".join(f"- {flag_text(f)}" for f in d.review_flags) or "- none"
    return (
        f"The video label has already been decided by written rules: {d.label.value} "
        f"(rule: {d.rule}). Do not change, question or soften it.\n\n"
        f"CLAIM TABLE (decided by earlier steps; reliable):\n" + "\n".join(rows) + "\n\n"
        f"Evidence IDs you may mention: {_ids(d.evidence_ids)}.\n"
        f"Points a reviewer must check:\n{flags}\n\n"
        "The claims' wording and the verifier's notes are in fenced blocks below.\n"
        f"Call {TOOL_NAME} with the explanation."
    )


def build_prompt(
    d: Decision, system_prompt: str, *, max_chars: int = DEFAULT_MAX_BLOCK_CHARS
) -> GuardedPrompt:
    """T10's explanation builder (claims fenced), with our instructions and the
    verifier's explanations fenced as ``model_output``."""
    views = _prompt_claims(d)
    prompt = explanation_prompt(
        d.label.value, [v.claim for v in views], task=_instructions(d, views), max_chars=max_chars
    )
    blocks = list(prompt.blocks)
    for v in views:
        if v.verification.explanation:
            blocks.append(fence(v.verification.explanation, kind="model_output",
                                item_id=f"{v.claim_id}:verifier", max_chars=max_chars))
    return prompt.model_copy(update={
        "system": guarded_system_prompt(system_prompt),
        "blocks": tuple(blocks),
        "citable_ids": frozenset(d.evidence_ids),
    })


def build_request(prompt: GuardedPrompt) -> dict:
    return {
        "messages": [{"role": "user", "content": prompt.render()}],
        "tools": [EXPLAIN_TOOL],
        "tool_choice": TOOL_CHOICE,
        "max_tokens": 600,
        "temperature": 0,
    }


class InvalidExplanation(ValueError):
    pass


# Label names as written in upper case (the prompt asks for that), longer names first
# so "NO-MISINFO" isn't read as "MISINFO". Case-sensitive with word boundaries, so
# ordinary prose ("misinformation", "the speaker debunked it") is not a label.
_LABEL_WORDS = re.compile(
    r"\b(?:NO[_ -]MISINFO|CANNOT[_ ]RECOGNI[SZ]E|DEBUNKING|DEBUNKED|MISINFO)\b"
)
_LABEL_ALIASES = {
    "no_misinfo": MisinfoLabel.NO_MISINFO, "no-misinfo": MisinfoLabel.NO_MISINFO,
    "no misinfo": MisinfoLabel.NO_MISINFO, "misinfo": MisinfoLabel.MISINFO,
    "debunking": MisinfoLabel.DEBUNKING, "debunked": MisinfoLabel.DEBUNKING,
}
_EVIDENCE_ID = re.compile(r"\bev_[A-Za-z0-9_]+")
_PMID = re.compile(r"\bPMID:?\s*(\d+)", re.IGNORECASE)


def check_explanation(
    text: str, d: Decision, evidence: dict[str, dict[str, EvidenceRecord]] | None = None
) -> str:
    """Raise ``InvalidExplanation`` unless ``text`` is consistent with the decision:
    it names no other label and mentions only evidence IDs / PMIDs the decision cites."""
    for m in _LABEL_WORDS.finditer(text):
        word = m.group(0).lower()
        named = (MisinfoLabel.CANNOT_RECOGNIZE if word.startswith("cannot")
                 else _LABEL_ALIASES.get(word))
        if named is not None and named != d.label:
            raise InvalidExplanation(f"explanation names label {named.value}, not {d.label.value}")
    allowed = set(d.evidence_ids)
    unknown = [e for e in _EVIDENCE_ID.findall(text) if e not in allowed]
    if unknown:
        raise InvalidExplanation(f"explanation mentions evidence IDs the result doesn't cite: {unknown}")
    if _PMID.search(text):
        pmids = {
            rec.pmid for cid_map in (evidence or {}).values()
            for eid, rec in cid_map.items() if eid in allowed and rec.pmid
        }
        bad = [p for p in _PMID.findall(text) if p not in pmids]
        if bad:
            raise InvalidExplanation(f"explanation mentions PMIDs the result doesn't cite: {bad}")
    return text


def _record_meta(result: Any) -> tuple[Optional[str], Optional[str]]:
    rec = getattr(result, "record", None)
    return getattr(rec, "model", None), getattr(rec, "prompt_version", None)


def explain(
    d: Decision,
    caller: StepCaller,
    system_prompt: str,
    prompt_version: str,
    evidence: dict[str, dict[str, EvidenceRecord]],
    *,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> tuple[str, Optional[str], Optional[str], list[NodeError]]:
    """Ask the explanation model; fall back to the template on any failure. Returns
    ``(text, model, prompt_version, errors)``; model/version are None for the template."""
    prompt = build_prompt(d, system_prompt, max_chars=max_chars)
    try:
        result = caller.call(STEP, build_request(prompt), system=prompt.system)
    except Exception as exc:
        return template_explanation(d), None, None, [NodeError(
            node=r.JUDGE_CLASSIFICATION, retryable=True,
            message=f"explanation model call failed: {type(exc).__name__}: {exc}; template used",
        )]
    model, version = _record_meta(result)
    try:
        out = parse_output(STEP, getattr(result, "output", None), ExplanationOutput)
        text = check_explanation(out.explanation.strip(), d, evidence)  # type: ignore[attr-defined]
        if not text:
            raise InvalidExplanation("empty explanation")
    except (OutputViolation, InvalidExplanation) as exc:
        return template_explanation(d), None, None, [NodeError(
            node=r.JUDGE_CLASSIFICATION,
            message=f"explanation rejected ({exc}); template used",
        )]
    if d.review_flags:
        text += " Needs review: " + "; ".join(flag_text(f) for f in d.review_flags) + "."
    return text[:MAX_EXPLANATION_CHARS], model, version or prompt_version, []


# ------------------------------------------------------------------ node


def judge(
    state: PipelineState,
    caller: Optional[StepCaller] = None,
    *,
    system_prompt: Optional[str] = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> tuple[FinalClassification, list[NodeError]]:
    views, errors = claim_views(state)
    checkable = [c for c in state.get("claims") or [] if c.requires_verification]
    d = decide(views, has_claims=bool(checkable))
    errors += list(d.errors)
    model = version = None
    if caller is not None and system_prompt is not None:
        text, model, version, errs = explain(
            d, caller, system_prompt, prompt_version, _evidence_by_claim(state), max_chars=max_chars
        )
        errors += errs
    else:
        text = template_explanation(d)
    final = FinalClassification(
        video_id=state["video_id"],
        classification=d.label,
        claim_ids=d.claim_ids,
        evidence_ids=list(d.evidence_ids),
        explanation=text,
        limitations=limitations_for(d),
        confidence=None,  # §11: video confidence = lowest calibrated deciding claim; T15
        decision_rule=d.rule,
        review_flags=list(d.review_flags),
        model=model,
        prompt_version=version,
    )
    return final, errors


def resolve_prompt_version(caller: StepCaller, prompt_version: Optional[str]) -> str:
    if prompt_version:
        return prompt_version
    route = getattr(caller, "route", None)
    if callable(route):
        try:
            return route(STEP).prompt
        except Exception:
            pass
    return DEFAULT_PROMPT_VERSION


def make_judge_classification(
    caller: Optional[StepCaller] = None,
    *,
    prompt_version: Optional[str] = None,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> Callable[[PipelineState], dict]:
    """Build the ``judge_classification`` node.

    With no ``caller`` the explanation is the deterministic template (no model call).
    With a caller (T01's ``ModelRouter``), the routed ``judge_explanation`` step writes
    it; the prompt file is loaded here so a bad routing config fails at start-up.
    """
    version = system_prompt = None
    if caller is not None:
        version = resolve_prompt_version(caller, prompt_version)
        system_prompt = load_prompt(version)

    def judge_classification(state: PipelineState) -> dict:
        final, errors = judge(
            state, caller, system_prompt=system_prompt,
            prompt_version=version or DEFAULT_PROMPT_VERSION, max_chars=max_chars,
        )
        update: dict = {"final_result": final}
        if errors:
            update["errors"] = errors
        return update

    return judge_classification


# ------------------------------------------------------------------ mapping


def claim_label(stance: Optional[Stance], verdict: Optional[Verdict]) -> MisinfoLabel:
    """Per-claim label for ``ClassificationResult.claims``: the §9 rules applied to one
    claim."""
    if verdict == Verdict.CONTRADICTED and stance == Stance.ENDORSES:
        return MisinfoLabel.MISINFO
    if verdict == Verdict.CONTRADICTED and stance == Stance.REFUTES:
        return MisinfoLabel.DEBUNKING
    if verdict in JUDGED_VERDICTS:
        return MisinfoLabel.NO_MISINFO
    return MisinfoLabel.CANNOT_RECOGNIZE


def _segment_texts(state: PipelineState) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in state.get("transcript_segments") or []:
        out[s.segment_id] = s.text
    for s in state.get("ocr_segments") or []:
        out[s.segment_id] = s.text
    for f in state.get("fused_segments") or []:
        out.setdefault(f.segment_id, " ".join([f.spoken, *f.on_screen]).strip())
    return out


def to_classification_result(
    state: PipelineState,
    *,
    latency_ms: int,
    provider: str = "langgraph",
    model_used: Optional[str] = None,
) -> ClassificationResult:
    """Map the graph's ``final_result`` onto the existing ``ClassificationResult`` (for
    T11's ``InferenceProvider``). Only IDs already in state are used.

    - ``evidence_snippets``: the exact speech/caption text behind the deciding claims'
      stances (falling back to their source segments), as the single-call path quotes
      the content.
    - ``citations``: one ``PubMedCitation`` per cited evidence record that has a PMID.
    - ``claims``: every claim with a verdict, labelled by ``claim_label``.
    - ``confidence``: ``final_result.confidence`` once calibrated (T15). Until then the
      lowest *raw* verifier confidence among the deciding claims, or 0.0 when there is
      none. The legacy schema needs a number; it is uncalibrated, like today's.
    """
    final: FinalClassification = state["final_result"]
    claims = {c.claim_id: c for c in state.get("claims") or []}
    stances = state.get("stance_results") or {}
    verdicts = state.get("verification_results") or {}
    evidence = _evidence_by_claim(state)
    texts = _segment_texts(state)

    snippets: list[str] = []
    for cid in final.claim_ids:
        s = stances.get(cid)
        seg_ids = (s.stance_segment_ids if s and s.stance_segment_ids else
                   claims[cid].source_segment_ids if cid in claims else [])
        for sid in seg_ids:
            t = texts.get(sid)
            if t and t not in snippets:
                snippets.append(t)

    def citation(cid: str, eid: str) -> Optional[PubMedCitation]:
        rec = evidence.get(cid, {}).get(eid)
        if rec is None or not rec.pmid:
            return None
        return PubMedCitation(
            claim_id=cid, claim=claims[cid].claim_text, title=rec.title, pmid=rec.pmid,
            url=rec.source_url or f"https://pubmed.ncbi.nlm.nih.gov/{rec.pmid}/",
        )

    cited = set(final.evidence_ids)
    citations: list[PubMedCitation] = []
    for cid in final.claim_ids:
        v = verdicts.get(cid)
        for eid in ([*v.supporting_evidence_ids, *v.contradicting_evidence_ids] if v else []):
            c = citation(cid, eid) if eid in cited else None
            if c and c not in citations:
                citations.append(c)

    out_claims: list[Claim] = []
    for cid, c in claims.items():
        v = verdicts.get(cid)
        if v is None:
            continue
        s = stances.get(cid)
        ids = [e for e in (*v.supporting_evidence_ids, *v.contradicting_evidence_ids)
               if e in evidence.get(cid, {})]
        out_claims.append(Claim(
            claim_id=cid, text=c.claim_text,
            label=claim_label(s.stance if s else None, v.verdict),
            confidence=v.raw_confidence if v.raw_confidence is not None else 0.0,
            evidence=[v.explanation] if v.explanation else [],
            citations=[x for x in (citation(cid, e) for e in ids) if x],
        ))

    if final.confidence is not None:
        confidence = final.confidence
    else:
        raws = [verdicts[c].raw_confidence for c in final.claim_ids
                if c in verdicts and verdicts[c].raw_confidence is not None]
        confidence = min(raws) if raws else 0.0

    return ClassificationResult(
        label=final.classification,
        confidence=confidence,
        explanation=final.explanation,
        evidence_snippets=snippets[:5],
        provider=provider,
        model_used=model_used or final.model or "rules",
        latency_ms=latency_ms,
        citations=citations or None,
        claims=out_claims or None,
    )
