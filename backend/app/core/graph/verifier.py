"""Evidence verifier node (target design §7; issue #33).

For each claim, one LLM call reads the claim and its reranked papers and decides what
the evidence says about that exact claim: SUPPORTED, CONTRADICTED, MIXED,
INSUFFICIENT_EVIDENCE or NOT_VERIFIABLE. It judges the claim, not the speaker (§5).

How it fits:

- **Model choice comes from routing config.** The node takes a ``StepCaller`` (T01's
  ``ModelRouter`` has the shape); the step is ``verify_claims`` in
  ``config/routing.yaml`` and the prompt version comes from there too. No model id
  appears in this file.
- **Forced structured output.** The request carries the ``record_verdict`` tool and a
  ``tool_choice`` forcing it. The tool input is parsed with ``VerifierToolOutput``
  (T10's strict ``VerificationOutput`` plus ``raw_confidence``): unknown fields,
  out-of-set verdicts, URLs in free text and over-long fields are rejected.
- **Untrusted text is fenced** (§15): the claim, titles and abstracts go through
  T10's ``verification_prompt`` builder; critic notes (a model's words about untrusted
  text) are fenced as ``model_output``. Trusted PubMed metadata (study type,
  publication type, year) goes in the instructions as an evidence index.
- **Citations are checked in code, and an invalid answer is rejected, not trimmed.**
  The answer may cite only evidence IDs retrieved for *this* claim; a paper can't be
  in both lists; SUPPORTED needs a supporting ID, CONTRADICTED a contradicting one,
  MIXED both. Any violation rejects the whole answer. The verifier gets one repair
  attempt that names the problem and the allowed IDs; if that fails too, the verdict
  is INSUFFICIENT_EVIDENCE with a ``guardrail:`` error, which sends the run to review
  (``guardrail_review_reasons``). Nothing a model cites is silently dropped and kept.
- **Absence of evidence is not contradiction.** A claim with no reranked evidence gets
  INSUFFICIENT_EVIDENCE without a model call, and CONTRADICTED is impossible without
  a cited contradicting paper.
- **Loop-aware.** Only ``routing.claims_to_verify`` claims are (re)judged; others keep
  their verdict. A REVISE_VERIFICATION re-run counts against the revision budget and
  shows the critic's notes; a RETRIEVE_MORE re-run judges the new evidence.
- Writes ``verification_results`` and ``verification_revisions`` (the T02 ownership
  map), plus the shared, append-only ``errors``.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Optional, Protocol, Sequence

from pydantic import Field, field_validator

from app.core.graph import routing as r
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    GraphClaim,
    NodeError,
    PipelineState,
    Verdict,
    VerificationResult,
)
from app.core.graph.stance import PromptNotFoundError, load_prompt  # shared prompt loader
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX
from app.core.guardrails.outputs import OutputViolation, VerificationOutput, _no_urls, parse_output
from app.core.guardrails.untrusted import (
    DEFAULT_MAX_BLOCK_CHARS,
    GuardedPrompt,
    fence,
    guarded_system_prompt,
    verification_prompt,
)

STEP = "verify_claims"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "verify_v1"
TOOL_NAME = "record_verdict"
MAX_EVIDENCE_PER_CLAIM = 10  # §6 "Cap"; enforced here too in case the reranker isn't
DEFAULT_MAX_REPAIRS = 1
MAX_EXPLANATION_CHARS = 1_000
MAX_LIMITATION_CHARS = 300

__all__ = [
    "DEFAULT_PROMPT_VERSION", "STEP", "TOOL_NAME", "VERIFY_TOOL", "TOOL_CHOICE",
    "VerifierToolOutput", "InvalidVerification", "PromptNotFoundError",
    "build_prompt", "build_request", "check_citations", "parse_verification",
    "verify_claim", "make_verify_claims",
]


# ------------------------------------------------------------------ schemas


class VerifierToolOutput(VerificationOutput):
    """What the model must return through ``record_verdict``.

    T10's ``VerificationOutput`` (strict: unknown keys rejected, explanation without
    URLs, bounded lists) plus the raw, uncalibrated confidence §11 asks for.
    """

    raw_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("limitations")
    @classmethod
    def _limitations_clean(cls, v: list[str]) -> list[str]:
        return [_no_urls(s.strip()) for s in v if s and s.strip()]

    @field_validator("supporting_evidence_ids", "contradicting_evidence_ids")
    @classmethod
    def _ids_nonblank(cls, v: list[str]) -> list[str]:
        ids = [s.strip() for s in v]
        if any(not s for s in ids):
            raise ValueError("blank evidence id")
        return list(dict.fromkeys(ids))


VERIFY_TOOL: dict = {
    "name": TOOL_NAME,
    "description": "Record what the retrieved evidence says about the claim, citing evidence IDs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": [v.value for v in Verdict],
                "description": "What the evidence says about the claim as stated.",
            },
            "supporting_evidence_ids": {
                "type": "array", "items": {"type": "string"},
                "description": "IDs from the EVIDENCE INDEX of papers that back the claim.",
            },
            "contradicting_evidence_ids": {
                "type": "array", "items": {"type": "string"},
                "description": "IDs from the EVIDENCE INDEX of papers that test the claim and find against it.",
            },
            "explanation": {
                "type": "string",
                "description": "One to three sentences on what the deciding papers found.",
            },
            "limitations": {
                "type": "array", "items": {"type": "string"},
                "description": "Short notes on gaps: indirect population, outcome or intervention; weak designs.",
            },
            "raw_confidence": {
                "type": "number", "minimum": 0, "maximum": 1,
                "description": "Confidence in the verdict, 0 to 1 (raw; calibrated later).",
            },
        },
        "required": [
            "verdict", "supporting_evidence_ids", "contradicting_evidence_ids",
            "explanation", "limitations",
        ],
        "additionalProperties": False,
    },
}
TOOL_CHOICE: dict = {"type": "tool", "name": TOOL_NAME}


class StepCaller(Protocol):
    """Anything that runs one routed LLM step (T01's ``ModelRouter`` satisfies this)."""

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> Any: ...


# ------------------------------------------------------------------ prompt


_META_RE = re.compile(r"[^A-Za-z0-9 ,.;:()/_+-]")


def _meta(text: Any) -> str:
    """PubMed metadata is trusted, but keep it to plain characters so a malformed
    record can't smuggle anything into the instructions."""
    return _META_RE.sub("", str(text))[:120]


def evidence_index(evidence: Sequence[EvidenceRecord]) -> str:
    if not evidence:
        return "(no papers were retrieved for this claim)"
    lines = []
    for e in evidence:
        parts = [f"id: {_meta(e.evidence_id)}", f"source: {e.source}"]
        if e.study_type:
            parts.append(f"study type: {_meta(e.study_type)}")
        if e.publication_type:
            parts.append("publication type: " + _meta(", ".join(e.publication_type)))
        if e.publication_year:
            parts.append(f"year: {int(e.publication_year)}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def _instructions(claim: GraphClaim, evidence: Sequence[EvidenceRecord], repair_note: Optional[str]) -> str:
    text = (
        f"Judge claim {claim.claim_id} (in the fenced claim block) against the papers below.\n\n"
        f"EVIDENCE INDEX (metadata from PubMed; cite only these IDs):\n{evidence_index(evidence)}\n\n"
        "Each paper's title and abstract are in fenced blocks with the same id.\n"
    )
    if repair_note:
        text += (
            "\nYOUR PREVIOUS ANSWER WAS REJECTED by an automatic check: "
            f"{repair_note}\nAnswer again, following the citation rules exactly.\n"
        )
    return text + f"\nCall {TOOL_NAME} with your verdict."


def build_prompt(
    claim: GraphClaim,
    evidence: Sequence[EvidenceRecord],
    system_prompt: str,
    *,
    critic: Optional[CriticResult] = None,
    repair_note: Optional[str] = None,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> GuardedPrompt:
    """The fenced prompt: T10's verification builder with our instructions, plus the
    critic's notes on a revision (fenced: they are a model's words about untrusted text)."""
    prompt = verification_prompt(
        claim, evidence, task=_instructions(claim, evidence, repair_note), max_chars=max_chars
    )
    blocks = list(prompt.blocks)
    if critic and critic.decision == CriticDecision.REVISE_VERIFICATION and critic.issues:
        notes = "REVIEWER NOTES on the previous verdict:\n" + "\n".join(f"- {i}" for i in critic.issues)
        blocks.append(fence(notes, kind="model_output", item_id=f"{claim.claim_id}:critic", max_chars=max_chars))
    return prompt.model_copy(update={"system": guarded_system_prompt(system_prompt), "blocks": tuple(blocks)})


def build_request(prompt: GuardedPrompt) -> dict:
    """Provider-neutral request body: one user message plus a forced tool call."""
    return {
        "messages": [{"role": "user", "content": prompt.render()}],
        "tools": [VERIFY_TOOL],
        "tool_choice": TOOL_CHOICE,
        "max_tokens": 1024,
        "temperature": 0,
    }


# ------------------------------------------------------------------ checks


class InvalidVerification(ValueError):
    """The verifier's answer can't be accepted. ``kind`` names the guardrail."""

    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


def check_citations(out: VerifierToolOutput, allowed_ids: Iterable[str]) -> None:
    """Raise ``InvalidVerification`` if the citations break the §7/§10 rules.

    - every cited ID must be in the claim's retrieved set (``fabricated_citation``);
    - a paper may not be both supporting and contradicting (``inconsistent_citation``);
    - SUPPORTED needs ≥1 supporting ID, CONTRADICTED ≥1 contradicting ID, MIXED both
      (``inconsistent_citation``). This is what makes "absence of evidence is not
      contradiction" a code rule rather than a prompt request.
    """
    allowed = set(allowed_ids)
    cited = [*out.supporting_evidence_ids, *out.contradicting_evidence_ids]
    unknown = list(dict.fromkeys(c for c in cited if c not in allowed))
    if unknown:
        raise InvalidVerification(
            "fabricated_citation", f"cited evidence IDs that were not retrieved for this claim: {unknown}"
        )
    both = sorted(set(out.supporting_evidence_ids) & set(out.contradicting_evidence_ids))
    if both:
        raise InvalidVerification("inconsistent_citation", f"IDs listed as both supporting and contradicting: {both}")
    sup, con = bool(out.supporting_evidence_ids), bool(out.contradicting_evidence_ids)
    if out.verdict == Verdict.SUPPORTED and not sup:
        raise InvalidVerification("inconsistent_citation", "SUPPORTED without any supporting evidence ID")
    if out.verdict == Verdict.CONTRADICTED and not con:
        raise InvalidVerification(
            "inconsistent_citation",
            "CONTRADICTED without any contradicting evidence ID (absence of evidence is "
            "INSUFFICIENT_EVIDENCE, not CONTRADICTED)",
        )
    if out.verdict == Verdict.MIXED and not (sup and con):
        raise InvalidVerification("inconsistent_citation", "MIXED needs both supporting and contradicting IDs")


def parse_verification(raw: Any, allowed_ids: Iterable[str]) -> VerifierToolOutput:
    """Parse and check one answer. Raises ``InvalidVerification``."""
    try:
        out = parse_output(STEP, raw, VerifierToolOutput)
    except OutputViolation as exc:
        raise InvalidVerification("output_rejected", exc.reason) from None
    check_citations(out, allowed_ids)  # type: ignore[arg-type]
    return out  # type: ignore[return-value]


# ------------------------------------------------------------------ node


def _gerr(kind: str, detail: str, claim_id: str) -> NodeError:
    return NodeError(
        node=r.VERIFY_CLAIMS, message=f"{GUARDRAIL_ERROR_PREFIX}{kind} {detail}".strip(), claim_id=claim_id
    )


def _record_meta(result: Any) -> tuple[Optional[str], Optional[str]]:
    rec = getattr(result, "record", None)
    return getattr(rec, "model", None), getattr(rec, "prompt_version", None)


def verify_claim(
    claim: GraphClaim,
    evidence: Sequence[EvidenceRecord],
    caller: StepCaller,
    system_prompt: str,
    prompt_version: str,
    *,
    critic: Optional[CriticResult] = None,
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> tuple[VerificationResult, list[NodeError]]:
    """Verify one claim. Never raises for model trouble: the safe default is
    INSUFFICIENT_EVIDENCE with the reason recorded."""
    evidence = list(evidence)[:MAX_EVIDENCE_PER_CLAIM]
    allowed = [e.evidence_id for e in evidence]
    errors: list[NodeError] = []

    def insufficient(limitation: str, *, model: Optional[str] = None, version: Optional[str] = None) -> VerificationResult:
        return VerificationResult(
            claim_id=claim.claim_id,
            verdict=Verdict.INSUFFICIENT_EVIDENCE,
            explanation="",
            limitations=[limitation[:MAX_LIMITATION_CHARS]],
            model=model,
            prompt_version=version or prompt_version,
        )

    if not evidence:
        # §6/§7: nothing retrieved (or nothing survived reranking) is insufficient,
        # never contradicted; there is nothing for a model to read.
        return insufficient("no evidence was retrieved for this claim"), errors

    repair_note: Optional[str] = None
    model: Optional[str] = None
    for attempt in range(max_repairs + 1):
        prompt = build_prompt(
            claim, evidence, system_prompt, critic=critic, repair_note=repair_note, max_chars=max_chars
        )
        try:
            result = caller.call(STEP, build_request(prompt), system=prompt.system)
        except Exception as exc:  # routing / provider errors: don't guess a verdict
            errors.append(NodeError(
                node=r.VERIFY_CLAIMS, message=f"model call failed: {type(exc).__name__}: {exc}",
                claim_id=claim.claim_id, retryable=True,
            ))
            return insufficient("verdict not determined: the verifier model could not be reached", model=model), errors
        model, recorded_version = _record_meta(result)
        try:
            out = parse_verification(getattr(result, "output", None), allowed)
        except InvalidVerification as exc:
            if attempt < max_repairs:
                repair_note = f"{exc.reason}. Allowed evidence IDs: {', '.join(allowed)}."
                errors.append(NodeError(
                    node=r.VERIFY_CLAIMS, message=f"repair requested: {exc.kind}: {exc.reason}",
                    claim_id=claim.claim_id,
                ))
                continue
            errors.append(_gerr(exc.kind, exc.reason, claim.claim_id))
            return insufficient(
                f"verdict not determined: the verifier's answer was rejected ({exc.kind})",
                model=model, version=recorded_version,
            ), errors
        return VerificationResult(
            claim_id=claim.claim_id,
            verdict=out.verdict,
            supporting_evidence_ids=list(out.supporting_evidence_ids),
            contradicting_evidence_ids=list(out.contradicting_evidence_ids),
            explanation=out.explanation[:MAX_EXPLANATION_CHARS],
            limitations=[s[:MAX_LIMITATION_CHARS] for s in out.limitations],
            raw_confidence=out.raw_confidence,  # raw; calibration is T15 (§11)
            model=model,
            prompt_version=recorded_version or prompt_version,
        ), errors
    raise AssertionError("unreachable")  # pragma: no cover


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


def make_verify_claims(
    caller: StepCaller,
    *,
    budgets: Budgets = DEFAULT_BUDGETS,
    prompt_version: Optional[str] = None,
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> Callable[[PipelineState], dict]:
    """Build the ``verify_claims`` node; pass it as ``build_graph({VERIFY_CLAIMS: node})``.

    The prompt file is loaded here, so a bad routing config fails at start-up.
    """
    version = resolve_prompt_version(caller, prompt_version)
    system_prompt = load_prompt(version)

    def verify_claims(state: PipelineState) -> dict:
        claims = {c.claim_id: c for c in state.get("claims", []) or []}
        results = dict(state.get("verification_results", {}) or {})
        revisions = dict(state.get("verification_revisions", {}) or {})
        critics = state.get("critic_results", {}) or {}
        reranked = state.get("reranked_evidence", {}) or {}
        errors: list[NodeError] = []
        for cid in r.claims_to_verify(state, budgets):
            critic = critics.get(cid)
            if critic and critic.decision == CriticDecision.REVISE_VERIFICATION:
                revisions[cid] = revisions.get(cid, 0) + 1
            result, errs = verify_claim(
                claims[cid], reranked.get(cid, []), caller, system_prompt, version,
                critic=critic, max_repairs=max_repairs, max_chars=max_chars,
            )
            results[cid] = result
            errors += errs
        update: dict = {"verification_results": results, "verification_revisions": revisions}
        if errors:
            update["errors"] = errors
        return update

    return verify_claims

