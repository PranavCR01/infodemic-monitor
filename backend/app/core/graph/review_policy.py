"""The human-review rule (target design §11 "The review rule", §12; issue #36).

Whether a case goes to a person is decided by written code rules, not by a model. The
LLM steps supply judgments (verdicts, stances, critic decisions); code decides what
happens next. A case goes to review if **any** rule fires. Every rule is a named
function from state to review reasons, so each one is unit-tested on its own and the
evaluation can count how many cases each rule sends to review and how often reviewers
overturn them (§12 "what if review becomes a bottleneck?").

| Rule (``REVIEW_RULES`` key) | Reason(s) | Design source |
|---|---|---|
| ``weak_evidence``        | ``weak_evidence:<cid>``        | §11: a deciding claim is INSUFFICIENT_EVIDENCE, MIXED or UNSUPPORTED (T30: so every "MISINFO (unproven)" video is reviewed); deciding claims only (D4 dropped) |
| ``conflicting_evidence`` | ``conflicting_evidence:<cid>`` | §11: supporting and contradicting papers both exist for a deciding claim |
| ``weak_study_types``     | ``weak_study_types:<cid>``     | §11: a deciding claim rests only on weak study types |
| ``unclear_stance``       | ``unclear_stance:<cid>``       | §11: a deciding claim's stance is UNCLEAR (or missing) |
| ``critic_escalated``     | ``critic_escalated:<cid>``     | §11: the critic escalated or marked the case for review |
| ``budget_exhausted``     | ``budget_exhausted:<cid>``     | §11 "Effort": the critic wanted more work than the budget allowed |
| ``second_check_disagreed`` | ``second_check_disagreed:<cid>`` | §8/§11 (T67 change 1, off by default): the budget ran out with the critic still objecting and the judge kept the stored verdict |
| ``validation_failed``    | ``validation_failed:<check>[:<cid>]`` | §10/§11: a validation check failed after repair |
| ``low_confidence``       | ``low_confidence``             | §11: calibrated confidence below the threshold (dormant until T15) |
| ``high_risk_uncertain``  | ``high_risk_uncertain:<cid>``  | issue #36: an endorsed high-risk claim the evidence couldn't settle |
| ``judge_flags``          | ``judge:<flag>``               | §9: patterns the judge's rules can't settle (T08), and the reasons the rules add themselves, from every claim whichever rule sets the label (``denies_supported:<cid>``, ``unproven_claim:<cid>``, ``possible_debunk:<cid>``, ``mixed_video``; T16, T21, T30), and ``nothing_judged`` when nothing could be judged but a claim had INSUFFICIENT_EVIDENCE (T37; never lowers severity) |
| ``guardrails``           | ``prompt_injection_suspected:...``, ``guardrail:...`` | §15: suspected injection or a guardrail rejection (T10) |

The node writes ``requires_human_review`` and ``review_reasons``. The reasons are
persisted with the job (``human_reviews`` table, ``app.services.review_service``) so a
reviewer sees **why** the case was escalated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.core.graph import routing as r
from app.core.graph import validation as val
from app.core.graph.routing import Budgets, DEFAULT_BUDGETS
from app.core.graph.state import (
    EvidenceRecord,
    FinalClassification,
    GraphClaim,
    PipelineState,
    Stance,
    Verdict,
    VerificationResult,
)
from app.core.guardrails.injection import guardrail_review_reasons

DEFAULT_REVIEW_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "review_policy.yaml"


class ReviewPolicyConfig(BaseModel):
    """Thresholds and lookups for the review rule (``backend/config/review_policy.yaml``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = "review_v1"
    status: str = "provisional"
    confidence_threshold: float = Field(0.70, ge=0.0, le=1.0)
    weak_study_types: frozenset[str] = frozenset({"in_vitro", "animal", "case_report"})
    high_risk_categories: frozenset[str] = frozenset()


def load_review_policy(path: Path | str = DEFAULT_REVIEW_POLICY_PATH) -> ReviewPolicyConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return ReviewPolicyConfig.model_validate(data)


@lru_cache(maxsize=1)
def default_review_policy() -> ReviewPolicyConfig:
    return load_review_policy()


# ------------------------------------------------------------------ context


# §11: INSUFFICIENT_EVIDENCE, MIXED or UNSUPPORTED (T30) is a review trigger.
UNCERTAIN_VERDICTS = frozenset({Verdict.INSUFFICIENT_EVIDENCE, Verdict.MIXED, Verdict.UNSUPPORTED})


@dataclass(frozen=True)
class ReviewContext:
    """What the rules read, computed once from state."""

    state: PipelineState
    config: ReviewPolicyConfig
    budgets: Budgets
    final: Optional[FinalClassification]
    claims: dict[str, GraphClaim]
    deciding: tuple[str, ...]
    verdicts: dict[str, VerificationResult]
    evidence: dict[str, dict[str, EvidenceRecord]] = field(default_factory=dict)

    @classmethod
    def build(cls, state: PipelineState, config: ReviewPolicyConfig, budgets: Budgets) -> "ReviewContext":
        final = state.get("final_result")
        final = final if isinstance(final, FinalClassification) else None
        evidence: dict[str, dict[str, EvidenceRecord]] = {}
        for key in ("retrieved_evidence", "library_evidence", "reranked_evidence", "found_study_evidence"):
            for cid, records in (state.get(key) or {}).items():
                for e in records or []:
                    evidence.setdefault(cid, {})[e.evidence_id] = e  # reranked (scored) wins
        return cls(
            state=state, config=config, budgets=budgets, final=final,
            claims={c.claim_id: c for c in state.get("claims") or []},
            deciding=tuple(final.claim_ids) if final else (),
            # The verdicts the judge used (T07: exhausted claims abstain).
            verdicts=r.verdicts_for_judge(state, budgets),
            evidence=evidence,
        )

    def stance(self, cid: str) -> Optional[Stance]:
        s = (self.state.get("stance_results") or {}).get(cid)
        return s.stance if s else None


RuleFn = Callable[[ReviewContext], list[str]]


# ------------------------------------------------------------------ rules


def rule_weak_evidence(ctx: ReviewContext) -> list[str]:
    """A **deciding** claim is INSUFFICIENT_EVIDENCE, MIXED or UNSUPPORTED (§11 as
    written: the ``refuted_unsettled`` possible-debunk case, and the deciding claims of
    ``unproven``, so every "MISINFO (unproven)" video is reviewed).

    Non-deciding claims never fire it (decision D4 dropped, 2026-11-24). When nothing
    could be judged, the judge's ``nothing_judged`` reason (T37) sends the video instead;
    the reasons the design collects from every claim (``possible_debunk``,
    ``mixed_evidence``, ...) come from the judge, not from this rule."""
    return [
        f"weak_evidence:{cid}" for cid in ctx.deciding
        if ctx.verdicts.get(cid) and ctx.verdicts[cid].verdict in UNCERTAIN_VERDICTS
    ]


def rule_conflicting_evidence(ctx: ReviewContext) -> list[str]:
    """Supporting and contradicting papers both exist for a deciding claim: a fact
    code can check (§11 "Conflict")."""
    return [
        f"conflicting_evidence:{cid}" for cid in ctx.deciding
        if (v := ctx.verdicts.get(cid)) and v.supporting_evidence_ids and v.contradicting_evidence_ids
    ]


def _study_type(record: EvidenceRecord) -> str:
    if record.study_type:
        return record.study_type
    from app.core.retrieval.rerank import classify_study  # lookup on publication type

    return classify_study(record).value


def rule_weak_study_types(ctx: ReviewContext) -> list[str]:
    """Every paper a deciding claim's verdict cites is a lab, animal or single-case
    study (§11 "Study type"). A claim citing nothing is covered by other rules."""
    out = []
    for cid in ctx.deciding:
        v = ctx.verdicts.get(cid)
        if not v:
            continue
        cited = [ctx.evidence.get(cid, {}).get(e) for e in [*v.supporting_evidence_ids, *v.contradicting_evidence_ids]]
        cited = [e for e in cited if e is not None]
        if cited and all(_study_type(e) in ctx.config.weak_study_types for e in cited):
            out.append(f"weak_study_types:{cid}")
    return out


def rule_unclear_stance(ctx: ReviewContext) -> list[str]:
    return [
        f"unclear_stance:{cid}" for cid in ctx.deciding
        if (ctx.stance(cid) or Stance.UNCLEAR) == Stance.UNCLEAR
    ]


def _critic_reasons(ctx: ReviewContext, prefix: str) -> list[str]:
    # T07's ``routing.critic_review_reasons`` is the one definition of the critic
    # loop's review reasons; the two rules below split it so each is counted.
    return [x for x in r.critic_review_reasons(ctx.state, ctx.budgets) if x.startswith(prefix + ":")]


def rule_critic_escalated(ctx: ReviewContext) -> list[str]:
    """The critic chose ESCALATE or flagged the claim for review."""
    return _critic_reasons(ctx, "critic_escalated")


def rule_budget_exhausted(ctx: ReviewContext) -> list[str]:
    """The critic still wanted more work when the claim's loop budget ran out."""
    return _critic_reasons(ctx, "budget_exhausted")


def rule_second_check_disagreed(ctx: ReviewContext) -> list[str]:
    """T67 (1): the judge kept a verdict the critic still objected to when the budget ran
    out (only while ``routing.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED`` is on)."""
    return _critic_reasons(ctx, r.SECOND_CHECK_REASON)


def rule_validation_failed(ctx: ReviewContext) -> list[str]:
    """Validation still fails after the one repair (§10). Also fires when validation
    never ran, so invalid output can't bypass it by skipping the node."""
    if "validation_errors" not in ctx.state:
        return ["validation_failed:not_run"]
    return val.failed_checks(ctx.state)


def rule_low_confidence(ctx: ReviewContext) -> list[str]:
    """Calibrated confidence below the threshold. ``confidence`` stays ``None`` until
    calibration exists (T15); an uncalibrated number is never compared."""
    c = ctx.final.confidence if ctx.final else None
    return ["low_confidence"] if c is not None and c < ctx.config.confidence_threshold else []


def rule_high_risk_uncertain(ctx: ReviewContext) -> list[str]:
    """An endorsed claim in a high-risk category whose evidence was insufficient, mixed
    or not verifiable: the label didn't rest on it, but publishing without a person
    looking would leave dangerous advice unexamined (issue #36)."""
    uncertain = UNCERTAIN_VERDICTS | {Verdict.NOT_VERIFIABLE}
    out = []
    for cid, claim in ctx.claims.items():
        v = ctx.verdicts.get(cid)
        if (
            claim.claim_category in ctx.config.high_risk_categories
            and v is not None and v.verdict in uncertain
            and ctx.stance(cid) == Stance.ENDORSES
        ):
            out.append(f"high_risk_uncertain:{cid}")
    return out


def rule_judge_flags(ctx: ReviewContext) -> list[str]:
    return [f"judge:{f}" for f in (ctx.final.review_flags if ctx.final else [])]


def rule_guardrails(ctx: ReviewContext) -> list[str]:
    return guardrail_review_reasons(ctx.state)


REVIEW_RULES: dict[str, RuleFn] = {
    "validation_failed": rule_validation_failed,
    "weak_evidence": rule_weak_evidence,
    "conflicting_evidence": rule_conflicting_evidence,
    "weak_study_types": rule_weak_study_types,
    "unclear_stance": rule_unclear_stance,
    "critic_escalated": rule_critic_escalated,
    "budget_exhausted": rule_budget_exhausted,
    "second_check_disagreed": rule_second_check_disagreed,
    "low_confidence": rule_low_confidence,
    "high_risk_uncertain": rule_high_risk_uncertain,
    "judge_flags": rule_judge_flags,
    "guardrails": rule_guardrails,
}


@dataclass(frozen=True)
class ReviewDecision:
    requires_review: bool
    reasons: tuple[str, ...]
    fired: dict[str, tuple[str, ...]]  # rule name → its reasons (for per-rule counts)


def evaluate(
    state: PipelineState,
    config: Optional[ReviewPolicyConfig] = None,
    budgets: Budgets = DEFAULT_BUDGETS,
) -> ReviewDecision:
    """Apply every rule. Pure: reads state, calls no model."""
    ctx = ReviewContext.build(state, config or default_review_policy(), budgets)
    fired: dict[str, tuple[str, ...]] = {}
    reasons: list[str] = []
    for name, rule in REVIEW_RULES.items():
        got = tuple(dict.fromkeys(rule(ctx)))
        if got:
            fired[name] = got
            reasons += [x for x in got if x not in reasons]
    return ReviewDecision(requires_review=bool(reasons), reasons=tuple(reasons), fired=fired)


# The reason stored on a case a user asked for (T32, ``POST /v1/jobs/{id}/review-request``).
USER_REQUESTED_REASON = "user_requested"


def rule_of(reason: str) -> str:
    """The rule a stored reason came from (for per-rule review counts, §12)."""
    head = reason.split(":", 1)[0]
    if head == "judge":
        return "judge_flags"
    if head in ("guardrail", "prompt_injection_suspected"):
        return "guardrails"
    if head == USER_REQUESTED_REASON:
        # Not an automatic rule: someone asked for a person to check the result (T32).
        return USER_REQUESTED_REASON
    return head if head in REVIEW_RULES else "other"


def make_route_for_review(
    config: Optional[ReviewPolicyConfig] = None, budgets: Budgets = DEFAULT_BUDGETS
) -> Callable[[PipelineState], dict]:
    """The ``route_for_review`` node: writes ``requires_human_review`` and
    ``review_reasons``."""
    cfg = config or default_review_policy()

    def route_for_review(state: PipelineState) -> dict:
        d = evaluate(state, cfg, budgets)
        return {"requires_human_review": d.requires_review, "review_reasons": list(d.reasons)}

    return route_for_review
