"""Critic node (target design §8; issue #34).

The verifier makes the call; the critic reviews it before it is accepted, looking for
what is wrong rather than approving. Each review ends in one decision:

- ``APPROVE``: the verdict stands and goes on to the judge;
- ``RETRIEVE_MORE``: the evidence is too indirect; search again with
  ``suggested_queries`` (the planner sanitises them, §15);
- ``REVISE_VERIFICATION``: the evidence is fine but the reasoning isn't; re-run the
  verifier with the critic's ``issues`` as notes;
- ``ESCALATE``: can't be resolved here; send to a person.

How it works:

- **Two layers.** Deterministic code checks run first and always (citation integrity:
  every cited ID was retrieved for this claim and is in only one list; verdict and
  citations agree, so "absence of evidence is not contradiction" is a code rule;
  strength: a SUPPORTED/CONTRADICTED verdict resting only on animal, lab, case-report
  or opinion papers; nothing usable survived reranking; an UNSUPPORTED verdict while
  search budget is left, T30). Then one LLM call covers what
  code can't: claim fidelity, relevance, what the papers actually say, logic,
  completeness and stance consistency. A code finding can't be overruled by the model:
  the stricter decision wins (ESCALATE > RETRIEVE_MORE > REVISE_VERIFICATION > APPROVE).
- **Independent of the verifier.** Its own prompt (``prompts/critic_v1.md``) and its own
  routing step, ``critique`` in ``config/routing.yaml``, which names a different
  provider from ``verify_claims``. No model id appears in this file.
- **Forced structured output**, parsed with T10's strict ``CriticOutput``. An answer that
  breaks the contract is a guardrail error and the review becomes ESCALATE (the safe
  default in ``guardrails.outputs``). A model *outage* is not an attack: the review falls
  back to the code checks alone and records a retryable error, because the pipeline must
  work without the critic (§8 "a quality layer, not a dependency").
- **Optional.** ``make_critique_verification(None)`` runs the code checks only, with no
  model call; that is the configuration the §8 probe compares against.
- **Budgets are not enforced here.** Routing enforces them (``routing.py``). The critic
  records the claim's search and revision counts at review time (``reviewed_attempt``,
  ``reviewed_revision``) so routing can tell an exhausted claim, which is frozen, from
  one with new evidence. When it asks for work the budget can't give, it says so in
  ``issues``; the claim then abstains and goes to review (``routing.verdicts_for_judge``,
  ``routing.critic_review_reasons``).
- Writes only ``critic_results`` (plus the shared, append-only ``errors``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from app.core.graph import routing as r
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    GraphClaim,
    NodeError,
    PipelineState,
    StanceResult,
    Verdict,
    VerificationResult,
)
from app.core.graph.stance import PromptNotFoundError, load_prompt
from app.core.graph.verifier import StepCaller, evidence_index
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX
from app.core.guardrails.outputs import CriticOutput, OutputViolation, parse_output
from app.core.guardrails.untrusted import (
    DEFAULT_MAX_BLOCK_CHARS,
    GuardedPrompt,
    critic_prompt,
    guarded_system_prompt,
)
from app.core.retrieval.planning import sanitize_query

STEP = "critique"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "critic_v1"
TOOL_NAME = "record_critique"
MAX_ISSUE_CHARS = 300
MAX_QUERIES = 3

# Study types (T05 ``rerank.StudyType`` values) that can't carry a verdict about people
# on their own (§6, §7 "Directness").
WEAK_STUDY_TYPES: frozenset[str] = frozenset({"animal", "in_vitro", "case_report", "opinion"})

# Stricter decisions win when code and model disagree.
_SEVERITY = {
    CriticDecision.APPROVE: 0,
    CriticDecision.REVISE_VERIFICATION: 1,
    CriticDecision.RETRIEVE_MORE: 2,
    CriticDecision.ESCALATE: 3,
}

__all__ = [
    "STEP", "DEFAULT_PROMPT_VERSION", "TOOL_NAME", "CRITIC_TOOL", "TOOL_CHOICE",
    "WEAK_STUDY_TYPES", "Finding", "PromptNotFoundError",
    "code_checks", "build_prompt", "build_request", "review_claim", "make_critique_verification",
]


CRITIC_TOOL: dict = {
    "name": TOOL_NAME,
    "description": "Record your review of the proposed verdict.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": [d.value for d in CriticDecision],
                "description": "APPROVE, RETRIEVE_MORE, REVISE_VERIFICATION or ESCALATE.",
            },
            "issues": {
                "type": "array", "items": {"type": "string"},
                "description": "One short sentence per problem found, naming evidence IDs.",
            },
            "suggested_queries": {
                "type": "array", "items": {"type": "string"}, "maxItems": MAX_QUERIES,
                "description": "For RETRIEVE_MORE: short PubMed search phrases.",
            },
            "requires_review": {
                "type": "boolean",
                "description": "True if a person should look at this claim.",
            },
        },
        "required": ["decision", "issues", "suggested_queries", "requires_review"],
        "additionalProperties": False,
    },
}
TOOL_CHOICE: dict = {"type": "tool", "name": TOOL_NAME}


# ------------------------------------------------------------------ code checks


@dataclass(frozen=True)
class Finding:
    """One defect the deterministic checks found."""

    check: str  # e.g. "citation_integrity", "strength"
    decision: CriticDecision
    issue: str


def code_checks(
    verification: VerificationResult,
    evidence: Sequence[EvidenceRecord],
    *,
    retrieved: Sequence[EvidenceRecord] = (),
    search_budget_left: bool = False,
) -> list[Finding]:
    """Defects that need no judgement. ``evidence`` is what the verifier was shown (the
    claim's reranked evidence); ``retrieved`` is everything retrieved for the claim.
    ``search_budget_left``: the claim has search rounds left (T30: UNSUPPORTED needs
    the full budget, so it asks for another, broader search)."""
    by_id = {e.evidence_id: e for e in evidence}
    sup = list(verification.supporting_evidence_ids)
    con = list(verification.contradicting_evidence_ids)
    v = verification.verdict
    out: list[Finding] = []

    unknown = list(dict.fromkeys(i for i in (*sup, *con) if i not in by_id))
    if unknown:
        out.append(Finding("citation_integrity", CriticDecision.REVISE_VERIFICATION,
                           f"cites evidence IDs that were not retrieved for this claim: {unknown}"))
    both = sorted(set(sup) & set(con))
    if both:
        out.append(Finding("citation_integrity", CriticDecision.REVISE_VERIFICATION,
                           f"lists the same paper as supporting and contradicting: {both}"))

    if v == Verdict.CONTRADICTED and not con:
        out.append(Finding("strength", CriticDecision.REVISE_VERIFICATION,
                           "CONTRADICTED without a contradicting paper: absence of evidence is "
                           "INSUFFICIENT_EVIDENCE, not CONTRADICTED"))
    elif v == Verdict.SUPPORTED and not sup:
        out.append(Finding("strength", CriticDecision.REVISE_VERIFICATION,
                           "SUPPORTED without a supporting paper"))
    elif v == Verdict.MIXED and not (sup and con):
        out.append(Finding("strength", CriticDecision.REVISE_VERIFICATION,
                           "MIXED needs at least one supporting and one contradicting paper"))
    elif v == Verdict.UNSUPPORTED and (sup or con):
        out.append(Finding("strength", CriticDecision.REVISE_VERIFICATION,
                           "UNSUPPORTED means no paper tests the claim either way, so it cites none"))

    if v in (Verdict.SUPPORTED, Verdict.CONTRADICTED):
        deciding = [by_id[i] for i in (sup if v == Verdict.SUPPORTED else con) if i in by_id]
        if deciding and all((e.study_type or "") in WEAK_STUDY_TYPES for e in deciding):
            kinds = sorted({e.study_type or "" for e in deciding})
            out.append(Finding(
                "strength", CriticDecision.REVISE_VERIFICATION,
                f"{v.value} rests only on {'/'.join(kinds)} evidence "
                f"({', '.join(e.evidence_id for e in deciding)}), which does not test a claim "
                "about people; the honest verdict may be INSUFFICIENT_EVIDENCE",
            ))

    if not evidence and retrieved and v in (Verdict.INSUFFICIENT_EVIDENCE, Verdict.UNSUPPORTED):
        out.append(Finding("relevance", CriticDecision.RETRIEVE_MORE,
                           "every retrieved paper was filtered out as off-topic; search again"))
    if v == Verdict.UNSUPPORTED and search_budget_left:
        out.append(Finding("search_budget", CriticDecision.RETRIEVE_MORE,
                           "no evidence either way yet; an unsupported verdict needs the full search "
                           "budget, so search again with broader terms"))
    return out


# ------------------------------------------------------------------ prompt


def _instructions(
    claim: GraphClaim, stance: Optional[StanceResult], verification: VerificationResult,
    evidence: Sequence[EvidenceRecord],
) -> str:
    stance_label = stance.stance.value if stance else "UNKNOWN"
    return (
        f"Review the verdict on claim {claim.claim_id} (in the fenced claim block).\n\n"
        f"SPEAKER'S STANCE: {stance_label}\n"
        f"PROPOSED VERDICT: {verification.verdict.value}\n"
        f"CITED AS SUPPORTING: {', '.join(verification.supporting_evidence_ids) or '(none)'}\n"
        f"CITED AS CONTRADICTING: {', '.join(verification.contradicting_evidence_ids) or '(none)'}\n\n"
        f"EVIDENCE INDEX (metadata from PubMed):\n{evidence_index(evidence)}\n\n"
        "The verifier's explanation and each paper's title and abstract are in fenced blocks.\n\n"
        f"Call {TOOL_NAME} with your decision."
    )


def build_prompt(
    claim: GraphClaim,
    stance: Optional[StanceResult],
    verification: VerificationResult,
    evidence: Sequence[EvidenceRecord],
    system_prompt: str,
    *,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> GuardedPrompt:
    """T10's fenced critic prompt with our instructions and the critic's own system prompt.
    The verifier's explanation is fenced as ``model_output``."""
    prompt = critic_prompt(
        claim, verification, evidence,
        task=_instructions(claim, stance, verification, evidence), max_chars=max_chars,
    )
    return prompt.model_copy(update={"system": guarded_system_prompt(system_prompt)})


def build_request(prompt: GuardedPrompt) -> dict:
    return {
        "messages": [{"role": "user", "content": prompt.render()}],
        "tools": [CRITIC_TOOL],
        "tool_choice": TOOL_CHOICE,
        "max_tokens": 1024,
        "temperature": 0,
    }


# ------------------------------------------------------------------ review


def _clean_issues(issues: Iterable[str]) -> list[str]:
    return [i.strip()[:MAX_ISSUE_CHARS] for i in issues if i and i.strip()]


def _clean_queries(queries: Iterable[str]) -> list[str]:
    out = [q for q in (sanitize_query(x) for x in queries) if q]
    return list(dict.fromkeys(out))[:MAX_QUERIES]


def _record_meta(result: Any) -> tuple[Optional[str], Optional[str]]:
    rec = getattr(result, "record", None)
    return getattr(rec, "model", None), getattr(rec, "prompt_version", None)


def review_claim(
    claim: GraphClaim,
    stance: Optional[StanceResult],
    verification: VerificationResult,
    evidence: Sequence[EvidenceRecord],
    caller: Optional[StepCaller],
    system_prompt: str = "",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    *,
    retrieved: Sequence[EvidenceRecord] = (),
    attempts: int = 0,
    revisions: int = 0,
    budgets: Budgets = DEFAULT_BUDGETS,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> tuple[CriticResult, list[NodeError]]:
    """Review one verdict. Never raises for model trouble."""
    cid = claim.claim_id
    errors: list[NodeError] = []
    findings = code_checks(
        verification, evidence, retrieved=retrieved,
        search_budget_left=attempts < budgets.max_retrieval_attempts,
    )
    decision = max((f.decision for f in findings), key=_SEVERITY.__getitem__, default=CriticDecision.APPROVE)
    issues = [f.issue for f in findings]
    checks = [f"code:{f.check}" for f in findings]
    queries: list[str] = []
    requires_review = False
    model = version = None

    # Nothing to read: no evidence was shown to the verifier. The code checks are the
    # whole review (an INSUFFICIENT verdict on nothing is right by construction).
    if caller is not None and evidence:
        prompt = build_prompt(claim, stance, verification, evidence, system_prompt, max_chars=max_chars)
        try:
            result = caller.call(STEP, build_request(prompt), system=prompt.system)
        except Exception as exc:  # outage: fall back to the code checks (see module doc)
            errors.append(NodeError(
                node=r.CRITIQUE_VERIFICATION, claim_id=cid, retryable=True,
                message=f"model call failed: {type(exc).__name__}: {exc}; code checks only",
            ))
            checks.append("model_unavailable")
        else:
            model, version = _record_meta(result)
            try:
                out: CriticOutput = parse_output(STEP, getattr(result, "output", None), CriticOutput)  # type: ignore[assignment]
            except OutputViolation as exc:
                errors.append(NodeError(
                    node=r.CRITIQUE_VERIFICATION, claim_id=cid,
                    message=f"{GUARDRAIL_ERROR_PREFIX}output_rejected {exc.reason}",
                ))
                decision, requires_review = CriticDecision.ESCALATE, True
                issues.append("the critic's answer was rejected by the output check")
                checks.append("guardrail")
            else:
                checks.append("model")
                if _SEVERITY[out.decision] > _SEVERITY[decision]:
                    decision = out.decision
                issues += _clean_issues(out.issues)
                queries = _clean_queries(out.suggested_queries)
                requires_review = out.requires_review or out.decision == CriticDecision.ESCALATE

    if decision == CriticDecision.RETRIEVE_MORE and attempts >= budgets.max_retrieval_attempts:
        outcome = ("the full search found nothing, so the claim stays unsupported"
                   if verification.verdict == Verdict.UNSUPPORTED else "the claim abstains")
        issues.append(f"search budget exhausted ({attempts} of {budgets.max_retrieval_attempts} rounds): "
                      f"{outcome} and goes to review")
    elif decision == CriticDecision.REVISE_VERIFICATION and revisions >= budgets.max_verification_revisions:
        issues.append(f"revision budget exhausted ({revisions} of {budgets.max_verification_revisions}): "
                      "the claim abstains and goes to review")
    if decision != CriticDecision.RETRIEVE_MORE:
        queries = []

    return CriticResult(
        claim_id=cid,
        decision=decision,
        issues=list(dict.fromkeys(issues)),
        suggested_queries=queries,
        requires_review=requires_review,
        reviewed_attempt=attempts,
        reviewed_revision=revisions,
        checks=list(dict.fromkeys(checks)),
        model=model,
        prompt_version=(version or prompt_version) if caller is not None else None,
    ), errors


def resolve_prompt_version(caller: Any, prompt_version: Optional[str]) -> str:
    if prompt_version:
        return prompt_version
    route = getattr(caller, "route", None)
    if callable(route):
        try:
            return route(STEP).prompt
        except Exception:
            pass
    return DEFAULT_PROMPT_VERSION


def make_critique_verification(
    caller: Optional[StepCaller],
    *,
    budgets: Budgets = DEFAULT_BUDGETS,
    prompt_version: Optional[str] = None,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> Callable[[PipelineState], dict]:
    """Build the ``critique_verification`` node; pass it as
    ``build_graph({CRITIQUE_VERIFICATION: node}, budgets=...)`` with the same budgets.

    ``caller=None`` gives the code-checks-only critic (no model call). Otherwise the
    prompt file is loaded here, so a bad routing config fails at start-up.
    """
    version = resolve_prompt_version(caller, prompt_version) if caller is not None else DEFAULT_PROMPT_VERSION
    system_prompt = load_prompt(version) if caller is not None else ""

    def critique_verification(state: PipelineState) -> dict:
        claims = {c.claim_id: c for c in state.get("claims", []) or []}
        stances = state.get("stance_results", {}) or {}
        verdicts = state.get("verification_results", {}) or {}
        reranked = state.get("reranked_evidence", {}) or {}
        retrieved = state.get("retrieved_evidence", {}) or {}
        attempts = state.get("retrieval_attempts", {}) or {}
        revisions = state.get("verification_revisions", {}) or {}
        results = dict(state.get("critic_results", {}) or {})
        errors: list[NodeError] = []
        for cid in r.claims_to_critique(state):
            result, errs = review_claim(
                claims[cid], stances.get(cid), verdicts[cid], reranked.get(cid, []), caller,
                system_prompt, version,
                retrieved=retrieved.get(cid, []), attempts=attempts.get(cid, 0),
                revisions=revisions.get(cid, 0), budgets=budgets, max_chars=max_chars,
            )
            results[cid] = result
            errors += errs
        update: dict = {"critic_results": results}
        if errors:
            update["errors"] = errors
        return update

    return critique_verification
