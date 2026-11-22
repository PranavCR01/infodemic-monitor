"""Loop budgets, per-claim work sets and the graph's conditional edges (§4, §8, §11).

Everything here is plain code: the budgets are enforced by routing, not by prompts, and
every claim reaches a terminal state. Routers only read state; they never write it.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.graph.state import CriticDecision, PipelineState


@dataclass(frozen=True)
class Budgets:
    """Per-claim loop limits (§6 "When nothing comes back", §8 "Budgets").

    ``max_retrieval_attempts`` counts every search round for a claim: the initial search
    plus 2 reformulations = 3. ``max_verification_revisions`` counts verifier re-runs
    requested by the critic's REVISE_VERIFICATION, on top of the first verification.
    """

    max_retrieval_attempts: int = 3
    max_verification_revisions: int = 1


DEFAULT_BUDGETS = Budgets()

# Node names (kept here so routers and the builder agree on them).
LOAD_ARTIFACTS = "load_artifacts"
TRANSCRIBE_AUDIO = "transcribe_audio"
EXTRACT_OCR = "extract_ocr"
FUSE_MODALITIES = "fuse_modalities"
EXTRACT_CLAIMS = "extract_claims"
ANALYZE_STANCE = "analyze_stance"
PLAN_RETRIEVAL = "plan_retrieval"
RETRIEVE_EVIDENCE = "retrieve_evidence"
RERANK_EVIDENCE = "rerank_evidence"
VERIFY_CLAIMS = "verify_claims"
CRITIQUE_VERIFICATION = "critique_verification"
JUDGE_CLASSIFICATION = "judge_classification"
VALIDATE_RESULT = "validate_result"
ROUTE_FOR_REVIEW = "route_for_review"
HUMAN_REVIEW = "human_review"
PERSIST_RESULT = "persist_result"


# ------------------------------------------------------------------ work sets


def verifiable_claim_ids(state: PipelineState) -> list[str]:
    return [c.claim_id for c in state.get("claims", []) if c.requires_verification]


def _decision(state: PipelineState, claim_id: str) -> CriticDecision | None:
    result = state.get("critic_results", {}).get(claim_id)
    return result.decision if result else None


def claims_to_retrieve(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> list[str]:
    """Claims that need a (first or further) search round now."""
    attempts = state.get("retrieval_attempts", {})
    out = []
    for cid in verifiable_claim_ids(state):
        n = attempts.get(cid, 0)
        if n == 0:
            out.append(cid)
        elif _decision(state, cid) == CriticDecision.RETRIEVE_MORE and n < budgets.max_retrieval_attempts:
            out.append(cid)
    return out


def claims_to_verify(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> list[str]:
    """Claims the verifier should (re)judge now.

    A claim is verified when it has no verdict yet, when the critic asked for more
    evidence (the verifier must see the new papers), or when the critic asked for a
    revision and the revision budget allows it.
    """
    results = state.get("verification_results", {})
    revisions = state.get("verification_revisions", {})
    out = []
    for cid in verifiable_claim_ids(state):
        decision = _decision(state, cid)
        if cid not in results:
            out.append(cid)
        elif decision == CriticDecision.RETRIEVE_MORE:
            out.append(cid)
        elif (
            decision == CriticDecision.REVISE_VERIFICATION
            and revisions.get(cid, 0) < budgets.max_verification_revisions
        ):
            out.append(cid)
    return out


def claims_to_critique(state: PipelineState) -> list[str]:
    """Verified claims without a terminal critic decision (APPROVE / ESCALATE)."""
    terminal = {CriticDecision.APPROVE, CriticDecision.ESCALATE}
    return [
        cid
        for cid in verifiable_claim_ids(state)
        if cid in state.get("verification_results", {}) and _decision(state, cid) not in terminal
    ]


def exhausted_claim_ids(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> list[str]:
    """Claims whose last critic decision asked for more work the budget can't give."""
    attempts = state.get("retrieval_attempts", {})
    revisions = state.get("verification_revisions", {})
    out = []
    for cid in verifiable_claim_ids(state):
        decision = _decision(state, cid)
        if decision == CriticDecision.RETRIEVE_MORE and attempts.get(cid, 0) >= budgets.max_retrieval_attempts:
            out.append(cid)
        elif (
            decision == CriticDecision.REVISE_VERIFICATION
            and revisions.get(cid, 0) >= budgets.max_verification_revisions
        ):
            out.append(cid)
    return out


# ------------------------------------------------------------------- routers


def route_after_stance(state: PipelineState) -> str:
    """No verifiable claims → straight to the judge (§4 "no claims at all")."""
    return PLAN_RETRIEVAL if verifiable_claim_ids(state) else JUDGE_CLASSIFICATION


def make_route_after_critic(budgets: Budgets = DEFAULT_BUDGETS):
    """Critic decision → retrieve more / re-verify / judge (§8).

    More evidence takes priority: a claim waiting on a revision is re-verified in the
    same pass after the new evidence arrives. ESCALATE and exhausted budgets go on to
    the judge, so the reviewer sees a proposed label; the review rule after validation
    then sends the case to a person (§11, §12).
    """

    def route_after_critic(state: PipelineState) -> str:
        if any(_decision(state, c) == CriticDecision.RETRIEVE_MORE for c in claims_to_retrieve(state, budgets)):
            return PLAN_RETRIEVAL
        if any(
            _decision(state, c) == CriticDecision.REVISE_VERIFICATION
            for c in claims_to_verify(state, budgets)
        ):
            return VERIFY_CLAIMS
        return JUDGE_CLASSIFICATION

    return route_after_critic


def route_after_policy(state: PipelineState) -> str:
    """Review rule outcome → human review or persist (§10–§12)."""
    return HUMAN_REVIEW if state.get("requires_human_review") else PERSIST_RESULT
