from __future__ import annotations
from app.core.graph.state import PipelineState

def route_after_stance(state: PipelineState) -> str:
    claims = state.get("claims", [])

    has_verifiable_claims = any(
        claim.requires_verification for claim in claims
    )

    if has_verifiable_claims:
        return "plan_retrieval"

    return "judge_classification"

def route_after_critic(state: PipelineState) -> str:
    critic_results = state.get("critic_results", {})
    retrieval_attempts = state.get("retrieval_attempts", {})
    revision_attempts = state.get(
        "verification_revision_attempts", {}
    )

    if not critic_results:
        return "route_for_review"

    if any(
        result.decision == "ESCALATE" or result.requires_review
        for result in critic_results.values()
    ):
        return "route_for_review"

    if any(
        result.decision == "RETRIEVE_MORE"
        and retrieval_attempts.get(result.claim_id, 0) >= 3
        for result in critic_results.values()
    ):
        return "route_for_review"

    if any(
        result.decision == "REVISE_VERIFICATION"
        and revision_attempts.get(result.claim_id, 0) >= 1
        for result in critic_results.values()
    ):
        return "route_for_review"

    if any(
        result.decision == "RETRIEVE_MORE"
        for result in critic_results.values()
    ):
        return "plan_retrieval"

    if any(
        result.decision == "REVISE_VERIFICATION"
        for result in critic_results.values()
    ):
        return "verify_claims"

    return "judge_classification"


def route_after_validation(state: PipelineState) -> str:
    validation_errors = state.get("validation_errors", [])
    final_result = state.get("final_result")

    if (
        validation_errors
        or state.get("requires_human_review", False)
        or (final_result and final_result.requires_human_review)
    ):
        return "route_for_review"

    return "persist_result"