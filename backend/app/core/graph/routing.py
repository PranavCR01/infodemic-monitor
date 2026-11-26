"""Loop budgets, per-claim work sets and the graph's conditional edges (§4, §8, §11).

Everything here is plain code: the budgets are enforced by routing, not by prompts, and
every claim reaches a terminal state. Routers only read state; they never write it.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.claim_category import is_evidence_meta
from app.core.graph.state import CriticDecision, PipelineState, Verdict, VerificationResult


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


def unchanged_since_review(state: PipelineState, claim_id: str) -> bool:
    """True if nothing new happened to the claim since the critic last reviewed it:
    no further search round and no further revision. Only critics that record
    ``reviewed_attempt``/``reviewed_revision`` (the T07 node) can be judged this way;
    for any other critic result this is False, which keeps the T02 behaviour."""
    c = state.get("critic_results", {}).get(claim_id)
    if c is None or c.reviewed_attempt is None or c.reviewed_revision is None:
        return False
    return (
        state.get("retrieval_attempts", {}).get(claim_id, 0) == c.reviewed_attempt
        and state.get("verification_revisions", {}).get(claim_id, 0) == c.reviewed_revision
    )


def claims_to_broaden(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> list[str]:
    """Claims whose searches so far found nothing and that have budget left: planning
    retries them with broader terms before anything else happens (§6 "When nothing
    comes back"). Only claims the retriever has already searched count (their key is
    present in ``retrieved_evidence``)."""
    attempts = state.get("retrieval_attempts", {})
    evidence = state.get("retrieved_evidence", {})
    return [
        cid
        for cid in verifiable_claim_ids(state)
        if cid in evidence
        and not evidence[cid]
        and 0 < attempts.get(cid, 0) < budgets.max_retrieval_attempts
    ]


def claims_to_retrieve(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> list[str]:
    """Claims that need a (first or further) search round now: never searched, the
    critic asked for more evidence, or every search so far came back empty. All three
    draw on the same per-claim budget."""
    attempts = state.get("retrieval_attempts", {})
    broaden = set(claims_to_broaden(state, budgets))
    out = []
    for cid in verifiable_claim_ids(state):
        n = attempts.get(cid, 0)
        if n == 0 or cid in broaden:
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
            # Re-judge once the new search has run. A claim whose search budget ran
            # out gets no new evidence, so it is not re-verified while other claims
            # loop (T07; needs the critic's ``reviewed_attempt``).
            if not unchanged_since_review(state, cid):
                out.append(cid)
        elif (
            decision == CriticDecision.REVISE_VERIFICATION
            and revisions.get(cid, 0) < budgets.max_verification_revisions
        ):
            out.append(cid)
    return out


def claims_to_critique(state: PipelineState) -> list[str]:
    """Verified claims without a terminal critic decision (APPROVE / ESCALATE) whose
    verdict changed since the last review. An exhausted claim keeps its last review
    rather than being reviewed again on the same verdict."""
    terminal = {CriticDecision.APPROVE, CriticDecision.ESCALATE}
    return [
        cid
        for cid in verifiable_claim_ids(state)
        if cid in state.get("verification_results", {})
        and _decision(state, cid) not in terminal
        and not unchanged_since_review(state, cid)
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


# ------------------------------------------------------------------ unproven (T30)

# §7 UNSUPPORTED applies only to efficacy claims: "X cures, treats, prevents or
# reverses Y". Harm, mechanism and every other category stay INSUFFICIENT_EVIDENCE
# ("no evidence of harm is not evidence of harm").
UNPROVEN_CATEGORIES: frozenset[str] = frozenset({"treatment_efficacy", "prevention"})

# Any error from these nodes for a claim means its search did not run as planned, so
# "nothing was found" is not established (an outage must never read as "unproven").
_RETRIEVAL_NODES = frozenset({PLAN_RETRIEVAL, RETRIEVE_EVIDENCE, RERANK_EVIDENCE})

UNPROVEN_DOWNGRADE_LIMITATION = (
    "no evidence was found, but the conditions for an unsupported verdict were not met "
    "(efficacy claim, nothing cited, full search budget used, no search errors); "
    "recorded as insufficient evidence"
)


def retrieval_incomplete(state: PipelineState, claim_id: str) -> bool:
    """True if any search step recorded an error for this claim."""
    return any(
        e.claim_id == claim_id and e.node in _RETRIEVAL_NODES for e in state.get("errors") or []
    )


def unproven_category(state: PipelineState, claim_id: str) -> bool:
    """An efficacy claim (§7). T51: a statement about the state or strength of the
    evidence ("the evidence that X prevents Y is overwhelming") never is, whatever
    category it carries: the fixed rules are checked here as well as in the extractor,
    so a claim from any path (an older run, the single-call fallback) is covered."""
    for c in state.get("claims") or []:
        if c.claim_id == claim_id:
            return (
                c.requires_verification
                and (c.claim_category or "").strip() in UNPROVEN_CATEGORIES
                and not is_evidence_meta(c.claim_text)
            )
    return False


def unproven_eligible(state: PipelineState, claim_id: str) -> bool:
    """The claim may be judged UNSUPPORTED at all: an efficacy claim whose searches ran
    without error. The verifier checks this before it accepts or produces the verdict."""
    return unproven_category(state, claim_id) and not retrieval_incomplete(state, claim_id)


def retrieval_budget_spent(state: PipelineState, claim_id: str, budgets: Budgets = DEFAULT_BUDGETS) -> bool:
    """The claim's full search budget (initial search + reformulations) has been used."""
    return state.get("retrieval_attempts", {}).get(claim_id, 0) >= budgets.max_retrieval_attempts


def unproven_allowed(
    state: PipelineState, v: VerificationResult, budgets: Budgets = DEFAULT_BUDGETS
) -> bool:
    """Whether an UNSUPPORTED verdict may reach the judge (§7, D1 = B): an efficacy
    claim, nothing cited either way, the full search budget used, no search errors."""
    return (
        not v.supporting_evidence_ids
        and not v.contradicting_evidence_ids
        and unproven_eligible(state, v.claim_id)
        and retrieval_budget_spent(state, v.claim_id, budgets)
    )


ABSTENTION_LIMITATION = (
    "the critic's objection was not resolved within the loop budget; "
    "verdict withheld (insufficient evidence)"
)


def verdicts_for_judge(
    state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS
) -> dict[str, VerificationResult]:
    """The verdicts the judge may use (§8 "When the budget runs out, the claim ends as
    insufficient evidence or goes to review").

    A claim whose critic still asked for more work when the budget ran out abstains:
    the judge sees INSUFFICIENT_EVIDENCE with no citations, so an objected-to verdict
    can never decide the video label. (It also goes to review:
    ``critic_review_reasons``.) An ESCALATE keeps its verdict, so the reviewer sees a
    proposed label (§12). The stored ``verification_results`` are not changed.

    T30: an UNSUPPORTED verdict that fails ``unproven_allowed`` (not an efficacy claim,
    something cited, search budget not used up, or a search error) is passed on as
    INSUFFICIENT_EVIDENCE.
    """
    out = dict(state.get("verification_results", {}))
    for cid in exhausted_claim_ids(state, budgets):
        v = out.get(cid)
        if v is None or v.verdict in (Verdict.INSUFFICIENT_EVIDENCE, Verdict.UNSUPPORTED) and not (
            v.supporting_evidence_ids or v.contradicting_evidence_ids
        ):
            # Nothing cited: there is no objected-to evidence to withhold. An
            # UNSUPPORTED claim whose budget ran out is exactly "the full search found
            # nothing" (T30), so it keeps its verdict (gated below).
            continue
        out[cid] = v.model_copy(update={
            "verdict": Verdict.INSUFFICIENT_EVIDENCE,
            "supporting_evidence_ids": [],
            "contradicting_evidence_ids": [],
            "limitations": [*v.limitations, ABSTENTION_LIMITATION],
        })
    # T30: an UNSUPPORTED verdict reaches the judge only if §7's conditions hold;
    # otherwise the claim is judged INSUFFICIENT_EVIDENCE.
    for cid, v in list(out.items()):
        if v.verdict == Verdict.UNSUPPORTED and not unproven_allowed(state, v, budgets):
            out[cid] = v.model_copy(update={
                "verdict": Verdict.INSUFFICIENT_EVIDENCE,
                "limitations": [*v.limitations, UNPROVEN_DOWNGRADE_LIMITATION],
            })
    return out


def critic_review_reasons(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> list[str]:
    """Review reasons that come from the critic loop (§8, §12): an ESCALATE or a review
    flag from the critic, and every claim whose budget ran out. T09: keep this call
    when replacing the ``route_for_review`` stub."""
    reasons: list[str] = []
    for cid, c in state.get("critic_results", {}).items():
        if c.decision == CriticDecision.ESCALATE or c.requires_review:
            reasons.append(f"critic_escalated:{cid}")
    reasons += [f"budget_exhausted:{cid}" for cid in exhausted_claim_ids(state, budgets)]
    return list(dict.fromkeys(reasons))


# ------------------------------------------------------------------- routers


def route_after_stance(state: PipelineState) -> str:
    """No verifiable claims → straight to the judge (§4 "no claims at all")."""
    return PLAN_RETRIEVAL if verifiable_claim_ids(state) else JUDGE_CLASSIFICATION


def make_route_after_retrieval(budgets: Budgets = DEFAULT_BUDGETS):
    """Empty results with budget left → plan a broader query; otherwise rerank (§6)."""

    def route_after_retrieval(state: PipelineState) -> str:
        return PLAN_RETRIEVAL if claims_to_broaden(state, budgets) else RERANK_EVIDENCE

    return route_after_retrieval


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


def route_after_validation(state: PipelineState) -> str:
    """Validation failed in the judge's own output, first time → re-run the judge once
    (§10 "one repair attempt"); otherwise on to the review rule, which sends any
    remaining failure to a person."""
    from app.core.graph.validation import needs_repair  # validation imports routing

    return JUDGE_CLASSIFICATION if needs_repair(state) else ROUTE_FOR_REVIEW


def route_after_policy(state: PipelineState) -> str:
    """Review rule outcome → human review or persist (§10–§12)."""
    return HUMAN_REVIEW if state.get("requires_human_review") else PERSIST_RESULT
