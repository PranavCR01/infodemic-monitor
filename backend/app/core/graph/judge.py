"""Judge node: one label for the video (target design §9; issue #35).

By the time the judge runs, each claim has a stance (§5) and a verdict (§7). Turning
those into one video label is a written policy, so it is code: the same inputs always
give the same label. An LLM only writes the explanation; it never chooses the label.

**The policy (§9, checked in order).** Only claims in ``state["claims"]`` that have a
verdict take part.

0. ``analysis_incomplete`` (T67 change 3, lead 2026-11-26): the verifier failed
   (``verification_failed``) for at least half of the verifiable claims → CANNOT_RECOGNIZE,
   always reviewed (video-level reason ``analysis_incomplete``). T67's other two rules
   (``THIN_CONTRADICTION_RULE``; routing's ``KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED``)
   are built but off: they failed the T67 replay gate.

   Set aside, not deciding (T67 (2) and T69, one mechanism: :func:`set_aside_reason`):
   a CONTRADICTED claim can keep its verdict yet be unable to decide rules 1, 4 and 5;
   it raises its own review reason and the label falls through. T69
   (``routing.CONTEXT_MISMATCH_RULE``, off): the only ENDORSES + CONTRADICTED claim,
   whose contradicting records are all narrative reviews or lab / modelling studies and
   which the verifier's structured ``evidence_context`` field marked as another
   population or exposure setting, raises ``contradiction_context_mismatch:<cid>``.

1. ``endorsed_contradicted``: any claim is ENDORSES + CONTRADICTED → MISINFO.
2. ``refuted_supported``: otherwise any claim is REFUTES + SUPPORTED (the speaker
   denies something true) → MISINFO, always sent to review (reason
   ``denies_supported:<cid>``).
3. ``unproven`` (T30, D1 = B): otherwise any claim is ENDORSES + UNSUPPORTED
   (an efficacy claim the full search found no evidence for or against) → MISINFO
   with ``misinfo_basis`` ``unproven``, always sent to review (reason
   ``unproven_claim:<cid>``).
4. ``refuted_contradicted``: otherwise any claim is REFUTES + CONTRADICTED → DEBUNKING.
5. ``judged_nothing_false_endorsed``: otherwise at least one claim is SUPPORTED or
   CONTRADICTED → NO_MISINFO.
6. ``refuted_unsettled``: otherwise any claim is REFUTES + MIXED / INSUFFICIENT_EVIDENCE
   / UNSUPPORTED → CANNOT_RECOGNIZE, sent to review as a possible debunk (reason
   ``possible_debunk:<cid>``).
7. ``nothing_judged``: otherwise (all INSUFFICIENT_EVIDENCE / MIXED / UNSUPPORTED /
   NOT_VERIFIABLE) → CANNOT_RECOGNIZE; ``no_claims`` when there were no checkable claims.
   If any claim is INSUFFICIENT_EVIDENCE, the rule adds the review reason
   ``nothing_judged`` (T37): a person should see what the system could not check (§11).
   It never lowers a case's priority; severity still comes from the claims (§12). A video with no claims, or
   only NOT_VERIFIABLE ones, is not sent for this reason.

**Review coverage (T64 f, lead 2026-11-26).** When the label is NO_MISINFO and at least
half of the ENDORSED claims in category ``treatment_efficacy`` or ``prevention`` are
INSUFFICIENT_EVIDENCE (and there is at least one such claim), the judge adds the
video-level review reason ``main_claims_unchecked``: the label rests on side claims while
the video's main claims could not be checked. The label is unchanged and severity still
comes from the claims (§12), so it never lowers a case's priority.

**Sibling claims (T64 b).** An UNSUPPORTED claim the verify step turned into
INSUFFICIENT_EVIDENCE because a sibling claim about the same intervention is SUPPORTED
(limitation ``contradicted_by_sibling_claim``) no longer decides the label, but an
ENDORSES one keeps its ``unproven_claim:<cid>`` review reason, so a person still sees it.

MISINFO carries a ``misinfo_basis`` (§9): ``contradicted`` (rule 1),
``denies_supported`` (rule 2) or ``unproven`` (rule 3). The label stays one of the four;
``display_label`` gives the interface text ("MISINFO (unproven)").

The label comes with the claims that decided it and only the evidence those claims'
verdicts cited, so the explanation can point at them.

**The rules' own review reasons (§9, third return value).** Rules 2, 3 and 6 add review
reasons, and since T21 they are collected from *every* claim, whichever rule decides the
label: each REFUTES + SUPPORTED claim raises ``denies_supported:<cid>`` and each
REFUTES + MIXED / INSUFFICIENT_EVIDENCE claim raises ``possible_debunk:<cid>`` even when
an earlier rule (e.g. NO_MISINFO) sets the label; each ENDORSES + UNSUPPORTED claim
raises ``unproven_claim:<cid>``. A mixed video (one false or unproven claim endorsed,
another false claim refuted) is MISINFO and always reviewed (``mixed_video``).
``Decision.rule_review_reasons`` returns these, and they are also in
``Decision.review_flags`` (and so ``final_result.review_flags``), which the review
policy (T09) turns into ``judge:<reason>`` review reasons. Using the existing flag
channel keeps the state schema (§4–5) unchanged.

**Patterns the rules can't settle (§9 "Where an LLM still helps").** Code detects them
and records them in ``final_result.review_flags``; the review policy turns them into
review reasons. They never change the label: a person settles them (see
context/MULTI_AGENT.md §7h for why not an LLM).

- ``mixed_video``: a false or unproven claim is endorsed and another false claim is
  refuted.
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

**Wording (T30).** Explanations and review notes use display wording: no internal
label or verdict names (``CANNOT_RECOGNIZE``) and no claim IDs; a claim is named by its
position ("the first claim") and, where it decides the label, its text. An unproven
claim is described as "no evidence supports this claim", never as false. A model-written
explanation that breaks these rules is replaced by the template.

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
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
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
from app.core.schemas.pipeline import Claim, ClassificationResult, MisinfoLabel, PubMedCitation, display_label

STEP = "judge_explanation"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "explain_v2"  # v2: display wording, unproven (T30)
TOOL_NAME = "record_explanation"
MAX_EXPLANATION_CHARS = 1_500  # §10 length limits
MAX_LIMITATIONS = 10
MAX_LIMITATION_CHARS = 300
MAX_CLAIMS_IN_PROMPT = 10
MAX_QUOTE_CHARS = 200

# Rule names (stored in ``final_result.decision_rule``).
RULE_ENDORSED_CONTRADICTED = "endorsed_contradicted"
RULE_REFUTED_SUPPORTED = "refuted_supported"
RULE_ENDORSED_UNSUPPORTED = "unproven"  # T30; the frontend adapter expects this exact string
RULE_REFUTED_CONTRADICTED = "refuted_contradicted"
RULE_JUDGED = "judged_nothing_false_endorsed"
RULE_REFUTED_UNSETTLED = "refuted_unsettled"
RULE_NOTHING_JUDGED = "nothing_judged"
RULE_NO_CLAIMS = "no_claims"
RULE_ANALYSIS_INCOMPLETE = "analysis_incomplete"  # T67 (3): checked before rule 1

# Review flags (prefixes; per-claim flags end in ``:<claim_id>``).
FLAG_MIXED_VIDEO = "mixed_video"
FLAG_UNCLEAR_STANCE = "unclear_stance_contradicted"
FLAG_NOT_REFUTED = "false_claim_not_refuted"
FLAG_MIXED_EVIDENCE = "mixed_evidence"
FLAG_VERIFICATION_FAILED = "verification_failed"
# Review reasons the §9 rules add themselves (one per deciding claim).
FLAG_DENIES_SUPPORTED = "denies_supported"
FLAG_POSSIBLE_DEBUNK = "possible_debunk"
FLAG_UNPROVEN = "unproven_claim"  # T30
FLAG_NOTHING_JUDGED = "nothing_judged"  # T37: video-level (§11)
FLAG_MAIN_CLAIMS_UNCHECKED = "main_claims_unchecked"  # T64 (f): video-level, label unchanged
FLAG_THIN_CONTRADICTION = "thin_contradiction"  # T67 (2): per claim; the claim can't decide
FLAG_ANALYSIS_INCOMPLETE = "analysis_incomplete"  # T67 (3): video-level
FLAG_CONTEXT_MISMATCH = "contradiction_context_mismatch"  # T69: per claim; the claim can't decide
MAIN_CLAIM_CATEGORIES = frozenset({"treatment_efficacy", "prevention"})
SIBLING_LIMITATION = "contradicted_by_sibling_claim"  # T64 (b), set by unproven_guard
# Since T21 these are collected from every claim, not only when their rule fires, and a
# mixed video is always reviewed (§9).
RULE_REVIEW_FLAGS = frozenset({
    FLAG_DENIES_SUPPORTED, FLAG_POSSIBLE_DEBUNK, FLAG_UNPROVEN, FLAG_MIXED_VIDEO, FLAG_NOTHING_JUDGED,
    FLAG_MAIN_CLAIMS_UNCHECKED, FLAG_THIN_CONTRADICTION, FLAG_ANALYSIS_INCOMPLETE, FLAG_CONTEXT_MISMATCH,
})

# T67 (2), lead 2026-11-26: an ENDORSES / REFUTES + CONTRADICTED claim decides the label
# (rules 1 and 4, and so also rule 5) only if the evidence it cites against the claim
# holds at least ``MIN_CONTRADICTING_ON_TOPIC`` records on topic for the claim's
# intervention (T49's check) or at least one systematic review, RCT or guideline.
# Otherwise the verdict stays but the claim can't decide, the label falls through, and
# the claim raises ``thin_contradiction:<cid>``.
# OFF (False): the T67 replay gate dropped this change. It made three tune labels worse
# (T66 v88; golden v119 and v177, all gold MISINFO): T49's intervention-term check finds no
# usable terms in non-English or non-intervention claims ("El Cancer es un hongo",
# "multiple personality"), so well-cited contradictions read as thin
# (evals/reports/T67/report.md). Turning it on is a lead decision.
THIN_CONTRADICTION_RULE = False
MIN_CONTRADICTING_ON_TOPIC = 2

# T69 (switch: ``routing.CONTEXT_MISMATCH_RULE``, off). Production jobs cf2ea579 and
# f85f2daa (tune v135, golden NO_MISINFO) were MISINFO, decided only by "Benzene doesn't
# get through skin easily", contradicted by two narrative reviews of occupational solvent
# exposure. The rule sets such a claim aside the same way T67 (2) sets a thin one aside
# (one mechanism, :func:`set_aside_reason`), when all of these hold:
#   - it is the ONLY ENDORSES + CONTRADICTED claim (rule 1 would rest on it alone);
#   - every contradicting record it cites (and at least one) is a narrative review or a
#     lab / in-silico / modelling study (``rerank.StudyType`` narrative_review, in_vitro):
#     no primary human study, systematic review, RCT or guideline;
#   - the verifier's structured ``evidence_context`` field said the contradicting
#     evidence studies a different population or exposure setting (stored as the
#     limitation code ``CONTEXT_MISMATCH_LIMITATION:<kind>``; never read from prose).
# The verdict stays, the label falls through, and the claim raises
# ``contradiction_context_mismatch:<cid>`` (always reviewed).
CONTEXT_MISMATCH_LIMITATION = r.CONTEXT_MISMATCH_LIMITATION
CONTEXT_MISMATCH_KINDS = r.CONTEXT_MISMATCH_KINDS
NARRATIVE_OR_MODELLING_TYPES = frozenset({"narrative_review", "in_vitro"})

# T67 (3), lead addendum 2026-11-26 ~23:00 UTC (production job 3d48e75e: the verifier was
# unreachable for 10 of 11 claims and one SUPPORTED side claim made the video NO_MISINFO):
# when the verifier failed (``verification_failed``: a retryable verify error) for at
# least ``ANALYSIS_INCOMPLETE_SHARE`` of the verifiable claims, the label is
# CANNOT_RECOGNIZE by rule ``analysis_incomplete``, checked before rule 1, with the
# video-level review reason ``analysis_incomplete``. Other rule reasons are still collected.
ANALYSIS_INCOMPLETE_RULE = True
ANALYSIS_INCOMPLETE_SHARE = 0.5

# ``misinfo_basis`` values (§9), set only when the label is MISINFO.
BASIS_CONTRADICTED = "contradicted"
BASIS_DENIES_SUPPORTED = "denies_supported"
BASIS_UNPROVEN = "unproven"
MISINFO_BASES = (BASIS_CONTRADICTED, BASIS_DENIES_SUPPORTED, BASIS_UNPROVEN)

JUDGED_VERDICTS = frozenset({Verdict.SUPPORTED, Verdict.CONTRADICTED})
# A refuted claim whose evidence can't settle it is a possible debunk. UNSUPPORTED is in
# this set (T30): a speaker refuting an untested cure is the clearest possible debunk,
# and leaving it out would drop the review flag it raised as INSUFFICIENT_EVIDENCE.
UNSETTLED_VERDICTS = frozenset({Verdict.MIXED, Verdict.INSUFFICIENT_EVIDENCE, Verdict.UNSUPPORTED})

__all__ = [
    "STEP", "DEFAULT_PROMPT_VERSION", "TOOL_NAME", "EXPLAIN_TOOL", "TOOL_CHOICE",
    "ClaimView", "Decision", "PromptNotFoundError",
    "claim_views", "decide", "template_explanation", "check_explanation",
    "build_prompt", "build_request", "judge", "make_judge_classification",
    "claim_label", "to_classification_result", "display_label", "claim_reference",
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
    position: int = 0  # 1-based place in extraction order (0: unknown; see ``_names``)
    stance_rationale: str = ""  # the stance step's rationale (T47: carries the sarcasm note)
    # T67 (2): the records retrieved for this claim, by ID (for the thin-contradiction
    # check). Empty when the caller built the view without them.
    evidence: tuple[EvidenceRecord, ...] = field(default=(), compare=False)

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id

    @property
    def verdict(self) -> Verdict:
        return self.verification.verdict

    @property
    def stance_or_unclear(self) -> Stance:
        return self.stance or Stance.UNCLEAR

    @property
    def sarcastic(self) -> bool:
        """T47: a REFUTES stance the stance step says rests on sarcasm or mockery. The
        stance prompts start such a rationale with "Sarcasm:"; the label is unchanged
        (a sarcastic debunk is still REFUTES), only the explanation mentions it."""
        return self.stance == Stance.REFUTES and bool(_SARCASM_RE.match(self.stance_rationale or ""))


# T47: the stance prompts start the rationale of a sarcastic or mocking debunk with
# "Sarcasm:". Matched loosely ("Sarcastic:", "sarcasm -") so a small wording slip
# still reaches the explanation; nothing else in the rationale is shown to users.
_SARCASM_RE = re.compile(r"\s*sarcas(?:m|tic)\b", re.IGNORECASE)
SARCASM_NOTE = " (using sarcasm)"


def _sarcasm(v: ClaimView) -> str:
    return SARCASM_NOTE if v.sarcastic else ""


def _evidence_by_claim(state: PipelineState) -> dict[str, dict[str, EvidenceRecord]]:
    out: dict[str, dict[str, EvidenceRecord]] = {}
    for key in ("retrieved_evidence", "reranked_evidence", "library_evidence", "found_study_evidence"):
        for cid, records in (state.get(key) or {}).items():
            for e in records or []:
                out.setdefault(cid, {}).setdefault(e.evidence_id, e)
    return out


def claim_views(
    state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS
) -> tuple[list[ClaimView], list[NodeError]]:
    """The claims the policy decides over, in extraction order, plus errors for any
    verdict that refers to a claim not in state (it is ignored).

    Verdicts come from ``routing.verdicts_for_judge`` (T07): a claim whose critic still
    objected when its loop budget ran out abstains as INSUFFICIENT_EVIDENCE, so a
    rejected verdict can't decide the label (§8)."""
    claims = list(state.get("claims") or [])
    known = {c.claim_id for c in claims}
    stances: dict[str, StanceResult] = state.get("stance_results") or {}
    verdicts: dict[str, VerificationResult] = r.verdicts_for_judge(state, budgets)
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
            position=i,
            stance_rationale=stances[c.claim_id].rationale if c.claim_id in stances else "",
            evidence=tuple(evidence.get(c.claim_id, {}).values()),
        )
        for i, c in enumerate(claims, start=1) if c.claim_id in verdicts
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
    misinfo_basis: Optional[str] = None  # T30: set only for MISINFO

    @property
    def claim_ids(self) -> list[str]:
        return [v.claim_id for v in self.deciding]

    @property
    def rule_review_reasons(self) -> list[str]:
        """The review reasons the rule that fired adds itself (§9's third value)."""
        return [f for f in self.review_flags if f.partition(":")[0] in RULE_REVIEW_FLAGS]


def _cited(view: ClaimView, rule: str) -> list[str]:
    """The evidence a deciding claim contributes: what shows it false for MISINFO /
    DEBUNKING by contradiction, what shows it true when the speaker denies it."""
    v = view.verification
    if rule in (RULE_ENDORSED_CONTRADICTED, RULE_REFUTED_CONTRADICTED):
        return list(v.contradicting_evidence_ids)
    if rule == RULE_REFUTED_SUPPORTED:
        return list(v.supporting_evidence_ids)
    if rule == RULE_ENDORSED_UNSUPPORTED:
        return []  # nothing tests the claim, so there is nothing to cite
    return [*v.supporting_evidence_ids, *v.contradicting_evidence_ids]


def main_claims_unchecked(views: Sequence[ClaimView]) -> bool:
    """T64 (f): at least half of the endorsed treatment / prevention claims (and at least
    one) are INSUFFICIENT_EVIDENCE."""
    main = [v for v in views if v.stance == Stance.ENDORSES and v.claim.claim_category in MAIN_CLAIM_CATEGORIES]
    unchecked = [v for v in main if v.verdict == Verdict.INSUFFICIENT_EVIDENCE]
    return bool(main) and 2 * len(unchecked) >= len(main)


def cited_contradicting(view: ClaimView) -> list[EvidenceRecord]:
    """The records a verdict cites against its claim, among those retrieved for it."""
    by_id = {e.evidence_id: e for e in view.evidence}
    return [by_id[eid] for eid in dict.fromkeys(view.verification.contradicting_evidence_ids) if eid in by_id]


def thin_contradiction(view: ClaimView) -> bool:
    """T67 (2): a CONTRADICTED verdict whose contradicting evidence (among the records
    retrieved for the claim) has fewer than ``MIN_CONTRADICTING_ON_TOPIC`` records on
    topic for the claim's intervention (T49's ``on_topic`` check, cited records not
    counted as on topic by default) and no systematic review, RCT or guideline."""
    from app.core.graph import unproven_guard as ug  # avoid an import cycle at load time

    if view.verdict != Verdict.CONTRADICTED:
        return False
    cited = cited_contradicting(view)
    if any(ug._study_type(e) in ug.STRONG_STUDY_TYPES for e in cited):
        return False
    return len(ug.on_topic_ids(view.claim, cited)) < MIN_CONTRADICTING_ON_TOPIC


def context_mismatch_kind(verification: VerificationResult) -> Optional[str]:
    """T69: the mismatch the verifier recorded in its structured ``evidence_context``
    field (stored as ``CONTEXT_MISMATCH_LIMITATION:<kind>``, an exact code), or None.
    Free-text limitations are never read."""
    for lim in verification.limitations or []:
        head, sep, kind = lim.partition(":")
        if sep and head == CONTEXT_MISMATCH_LIMITATION and kind in CONTEXT_MISMATCH_KINDS:
            return kind
    return None


def contradiction_rests_on_narrative_or_modelling(view: ClaimView) -> bool:
    """T69: every contradicting record the verdict cites (at least one) is a narrative
    review or a lab / modelling study (``NARRATIVE_OR_MODELLING_TYPES``; study type from
    the record, else PubMed's publication type)."""
    from app.core.graph import unproven_guard as ug  # avoid an import cycle at load time

    cited = cited_contradicting(view)
    return bool(cited) and all(ug._study_type(e) in NARRATIVE_OR_MODELLING_TYPES for e in cited)


def context_mismatched_contradiction(view: ClaimView) -> bool:
    """T69: an ENDORSES + CONTRADICTED verdict that rests only on narrative reviews or
    modelling and that the verifier flagged as being about another population or
    exposure setting. (Whether it is the *only* such claim is checked in ``decide``.)"""
    return (
        view.stance == Stance.ENDORSES and view.verdict == Verdict.CONTRADICTED
        and context_mismatch_kind(view.verification) is not None
        and contradiction_rests_on_narrative_or_modelling(view)
    )


def set_aside_reason(view: ClaimView, *, sole_endorsed_contradicted: bool) -> Optional[str]:
    """One mechanism for "the verdict stays but the claim can't decide" (T67 (2), T69):
    the review flag the claim raises, or None when it may decide. Each rule has its own
    switch; T67's thin check is applied first."""
    if THIN_CONTRADICTION_RULE and view.stance in (Stance.ENDORSES, Stance.REFUTES) and thin_contradiction(view):
        return FLAG_THIN_CONTRADICTION
    if r.CONTEXT_MISMATCH_RULE and sole_endorsed_contradicted and context_mismatched_contradiction(view):
        return FLAG_CONTEXT_MISMATCH
    return None


def analysis_incomplete(views: Sequence[ClaimView]) -> bool:
    """T67 (3): the verifier failed for at least half of the verifiable claims (and one)."""
    checkable = [v for v in views if v.claim.requires_verification]
    failed = [v for v in checkable if v.verification_failed]
    return bool(failed) and len(failed) >= ANALYSIS_INCOMPLETE_SHARE * len(checkable)


def decide(views: Sequence[ClaimView], *, has_claims: Optional[bool] = None) -> Decision:
    """Apply the §9 rules in order. Pure: no state, no model."""
    views = list(views)
    has_claims = bool(views) if has_claims is None else has_claims

    # T67 (2) / T69: contradictions that keep their verdict but can't decide (rules 1, 4
    # and 5); each raises its flag (thin_contradiction:<cid> or
    # contradiction_context_mismatch:<cid>). T69 applies only to the sole endorsed
    # contradicted claim, counted before any claim is set aside.
    n_endorsed_contradicted = sum(
        1 for v in views if v.stance == Stance.ENDORSES and v.verdict == Verdict.CONTRADICTED)
    set_aside = [
        (v, why) for v in views
        if (why := set_aside_reason(v, sole_endorsed_contradicted=n_endorsed_contradicted == 1))
    ]
    thin = [v for v, _ in set_aside]
    thin_ids = {v.claim_id for v in thin}
    endorsed_false = [v for v in views if v.stance == Stance.ENDORSES and v.verdict == Verdict.CONTRADICTED
                      and v.claim_id not in thin_ids]
    denied_true = [v for v in views if v.stance == Stance.REFUTES and v.verdict == Verdict.SUPPORTED]
    unproven = [v for v in views if v.stance == Stance.ENDORSES and v.verdict == Verdict.UNSUPPORTED]
    refuted_false = [v for v in views if v.stance == Stance.REFUTES and v.verdict == Verdict.CONTRADICTED
                     and v.claim_id not in thin_ids]
    judged = [v for v in views if v.verdict in JUDGED_VERDICTS and v.claim_id not in thin_ids]
    refuted_open = [v for v in views if v.stance == Stance.REFUTES and v.verdict in UNSETTLED_VERDICTS]

    # Review reasons come from every claim, whichever rule decides the label (§9, T21).
    # T64 (b): demoted by a SUPPORTED sibling; no longer decides, still reviewed.
    sibling_demoted = [
        v for v in views if v.stance == Stance.ENDORSES and v.verdict == Verdict.INSUFFICIENT_EVIDENCE
        and SIBLING_LIMITATION in (v.verification.limitations or [])
    ]
    rule_flags: list[str] = [
        *(f"{FLAG_DENIES_SUPPORTED}:{v.claim_id}" for v in denied_true),
        *(f"{FLAG_UNPROVEN}:{v.claim_id}" for v in [*unproven, *sibling_demoted]),
        *(f"{FLAG_POSSIBLE_DEBUNK}:{v.claim_id}" for v in refuted_open),
        *(f"{why}:{v.claim_id}" for v, why in set_aside),
    ]
    if (endorsed_false or unproven) and refuted_false:
        rule_flags.append(FLAG_MIXED_VIDEO)  # MISINFO, always reviewed
    basis: Optional[str] = None
    if ANALYSIS_INCOMPLETE_RULE and analysis_incomplete(views):
        # T67 (3): too much of the analysis is missing for any rule below to be trusted.
        label, rule, deciding = MisinfoLabel.CANNOT_RECOGNIZE, RULE_ANALYSIS_INCOMPLETE, []
        rule_flags.append(FLAG_ANALYSIS_INCOMPLETE)
    elif endorsed_false:
        label, rule, deciding = MisinfoLabel.MISINFO, RULE_ENDORSED_CONTRADICTED, endorsed_false
        basis = BASIS_CONTRADICTED
    elif denied_true:
        label, rule, deciding = MisinfoLabel.MISINFO, RULE_REFUTED_SUPPORTED, denied_true
        basis = BASIS_DENIES_SUPPORTED
    elif unproven:
        label, rule, deciding = MisinfoLabel.MISINFO, RULE_ENDORSED_UNSUPPORTED, unproven
        basis = BASIS_UNPROVEN
    elif refuted_false:
        label, rule, deciding = MisinfoLabel.DEBUNKING, RULE_REFUTED_CONTRADICTED, refuted_false
    elif judged:
        label, rule, deciding = MisinfoLabel.NO_MISINFO, RULE_JUDGED, judged
    elif refuted_open:
        label, rule, deciding = MisinfoLabel.CANNOT_RECOGNIZE, RULE_REFUTED_UNSETTLED, refuted_open
    else:
        label = MisinfoLabel.CANNOT_RECOGNIZE
        rule = RULE_NOTHING_JUDGED if has_claims else RULE_NO_CLAIMS
        deciding = []
        # §9 last branch (T37): a claim needed checking but the evidence was too thin, so
        # a person should still see it. No claims, or only NOT_VERIFIABLE
        # ones, are not sent.
        if any(v.verdict == Verdict.INSUFFICIENT_EVIDENCE for v in views):
            rule_flags.append(FLAG_NOTHING_JUDGED)
    if label == MisinfoLabel.NO_MISINFO and main_claims_unchecked(views):
        rule_flags.append(FLAG_MAIN_CLAIMS_UNCHECKED)

    # Citations: only IDs the deciding verdicts cited AND that were retrieved for that
    # same claim. Anything else is dropped and recorded (sends the run to review).
    evidence_ids: list[str] = []
    errors: list[NodeError] = []
    for v in deciding:
        for eid in _cited(v, rule):
            if eid in v.allowed_evidence_ids:
                if eid not in evidence_ids:
                    evidence_ids.append(eid)
            else:
                errors.append(NodeError(
                    node=r.JUDGE_CLASSIFICATION, claim_id=v.claim_id,
                    message=f"{GUARDRAIL_ERROR_PREFIX}uncited_evidence verdict cites {eid!r}, "
                            "which was not retrieved for this claim; left out of the result",
                ))

    flags: list[str] = list(rule_flags)
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
        misinfo_basis=basis,
    )


# ------------------------------------------------------------------ text


def _quote(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_QUOTE_CHARS else text[: MAX_QUOTE_CHARS - 1] + "…"


def _ids(ids: Iterable[str]) -> str:
    ids = list(ids)
    return ", ".join(ids) if ids else "none"


_ORDINALS = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
)


def claim_reference(position: int) -> str:
    """How explanations name a claim: by its place in the video, never by its ID."""
    if 1 <= position <= len(_ORDINALS):
        return f"the {_ORDINALS[position - 1]} claim"
    return f"claim {position}" if position > 0 else "a claim"


def _names(views: Iterable[ClaimView]) -> dict[str, str]:
    """claim_id → "the first claim", from each claim's place in the video (its position
    among all extracted claims, or its order here when that is unknown)."""
    return {v.claim_id: claim_reference(v.position or i) for i, v in enumerate(views, start=1)}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


# Plain-language verdicts and stances (no internal enum names in user-facing text).
_VERDICT_TEXT = {
    Verdict.SUPPORTED: "is supported by the evidence",
    Verdict.CONTRADICTED: "is contradicted by the evidence",
    Verdict.MIXED: "has mixed evidence",
    Verdict.UNSUPPORTED: "has no evidence for or against it",
    Verdict.INSUFFICIENT_EVIDENCE: "has insufficient evidence",
    Verdict.NOT_VERIFIABLE: "cannot be checked",
}
_EVIDENCE_STATE = {
    Verdict.MIXED: "the evidence is mixed",
    Verdict.INSUFFICIENT_EVIDENCE: "the evidence is insufficient",
    Verdict.UNSUPPORTED: "no study tests it either way",
}
_STANCE_TEXT = {
    Stance.ENDORSES: "the speaker endorses it",
    Stance.REFUTES: "the speaker refutes it",
    Stance.QUOTES: "the speaker quotes it",
    Stance.NEUTRAL: "the speaker is neutral",
    Stance.UNCLEAR: "the speaker's stance is unclear",
}

_FLAG_TEXT = {
    FLAG_MIXED_VIDEO: "the video endorses one claim the evidence contradicts or does not support, "
                      "and refutes another that the evidence contradicts",
    FLAG_UNCLEAR_STANCE: "the speaker's stance on {ref}, which the evidence contradicts, is unclear",
    FLAG_NOT_REFUTED: "{ref} is contradicted by the evidence but repeated without being refuted",
    FLAG_MIXED_EVIDENCE: "the evidence on {ref} is mixed",
    FLAG_VERIFICATION_FAILED: "{ref} could not be checked (the verifier was unavailable)",
    FLAG_DENIES_SUPPORTED: "the speaker denies {ref}, which the evidence supports",
    FLAG_POSSIBLE_DEBUNK: "the speaker may be debunking {ref}, which the evidence can't settle",
    FLAG_UNPROVEN: "no evidence supports {ref}, which the speaker presents as working",
    FLAG_NOTHING_JUDGED: "no claim in this video could be checked against the evidence",
    FLAG_MAIN_CLAIMS_UNCHECKED: "at least half of the treatment and prevention claims the speaker "
                                "makes could not be checked against the evidence",
    FLAG_ANALYSIS_INCOMPLETE: "the evidence check could not run for at least half of the claims, so the "
                              "video could not be assessed",
    FLAG_CONTEXT_MISMATCH: "the evidence against {ref} comes only from reviews or modelling about a "
                           "different population or exposure setting, so it does not decide the label on its own",
    FLAG_THIN_CONTRADICTION: "the evidence against {ref} is too thin to decide the label on its own "
                             "(fewer than two papers on its topic and no review, trial or guideline)",
}


def flag_text(flag: str, names: Optional[dict[str, str]] = None) -> str:
    """A review flag in plain words. ``names`` maps claim IDs to "the first claim"."""
    name, _, cid = flag.partition(":")
    ref = (names or {}).get(cid) or (f"claim {cid}" if cid else "")
    return _FLAG_TEXT.get(name, name.replace("_", " ")).format(ref=ref, cid=cid)


def _review_note(d: Decision, names: dict[str, str]) -> str:
    if not d.review_flags:
        return ""
    return " Needs review: " + "; ".join(flag_text(f, names) for f in d.review_flags) + "."


def template_explanation(d: Decision) -> str:
    """Deterministic explanation, used when no explanation model is configured or its
    answer is rejected. Always names the rule's deciding claims and evidence, in display
    wording: claims by position and text, no internal label or verdict names (T30)."""
    names = _names(d.all_claims or d.deciding)

    def said(v: ClaimView) -> str:
        return f'{names[v.claim_id]} ("{_quote(v.claim.claim_text)}")'

    if d.rule == RULE_NO_CLAIMS:
        text = "No checkable health claims were found in the video."
    elif d.rule == RULE_ANALYSIS_INCOMPLETE:
        failed = [v for v in d.all_claims if v.verification_failed]
        text = (
            f"The analysis is incomplete: the evidence check could not run for {len(failed)} of "
            f"{len([v for v in d.all_claims if v.claim.requires_verification])} claims, so the "
            "video could not be assessed. A person should check it, or it should be analysed again."
        )
    elif d.rule == RULE_NOTHING_JUDGED:
        parts = [f"{names[v.claim_id]} {_VERDICT_TEXT[v.verdict]}" for v in d.all_claims]
        text = "No claim could be judged against the evidence: " + "; ".join(parts) + "."
    elif d.rule == RULE_ENDORSED_CONTRADICTED:
        parts = [
            f"the speaker endorses {said(v)}, and the evidence contradicts it "
            f"({_ids(v.verification.contradicting_evidence_ids)})"
            for v in d.deciding
        ]
        text = _cap("; ".join(parts)) + "."
    elif d.rule == RULE_REFUTED_SUPPORTED:
        parts = [
            f"the speaker denies {said(v)}{_sarcasm(v)}, but the evidence supports it "
            f"({_ids(v.verification.supporting_evidence_ids)})"
            for v in d.deciding
        ]
        text = _cap("; ".join(parts)) + "."
    elif d.rule == RULE_ENDORSED_UNSUPPORTED:
        parts = [f"the speaker presents {said(v)} as working" for v in d.deciding]
        text = (
            _cap("; ".join(parts))
            + ", but a full search of the research and reference sources found no evidence for "
            "or against it: no evidence supports this claim. Promoting an untested treatment or "
            "prevention claim is misleading, so the video is labelled MISINFO (unproven)."
        )
    elif d.rule == RULE_REFUTED_CONTRADICTED:
        parts = [
            f"the speaker refutes {said(v)}{_sarcasm(v)}, and the evidence contradicts it "
            f"({_ids(v.verification.contradicting_evidence_ids)})"
            for v in d.deciding
        ]
        text = _cap("; ".join(parts)) + ", and the speaker endorses no claim the evidence contradicts."
        if any(v.sarcastic for v in d.deciding):
            # T47 (lead, 2026-11-25): show DEBUNKED, with the subtlety in the explanation.
            text = "Debunked (the speaker uses sarcasm): " + text
    elif d.rule == RULE_REFUTED_UNSETTLED:
        parts = [
            f"the speaker refutes {said(v)}{_sarcasm(v)}, but {_EVIDENCE_STATE.get(v.verdict, 'the evidence is unsettled')}"
            for v in d.deciding
        ]
        text = (
            "No claim could be judged against the evidence; "
            + "; ".join(parts) + ", so this may be a debunk the sources can't settle."
        )
    else:
        supported = [names[v.claim_id] for v in d.deciding if v.verdict == Verdict.SUPPORTED]
        contradicted = [
            f"{names[v.claim_id]} ({_STANCE_TEXT[v.stance_or_unclear]}{' using sarcasm' if v.sarcastic else ''})"
            for v in d.deciding if v.verdict == Verdict.CONTRADICTED
        ]
        n = len(d.deciding)
        text = (
            f"{n} claim{'s' if n != 1 else ''} could be judged against the evidence, and no claim "
            "the speaker endorses is contradicted."
        )
        if supported:
            text += f" Supported by the evidence: {', '.join(supported)}."
        if contradicted:
            text += f" Contradicted but not endorsed: {', '.join(contradicted)}."
    text += _review_note(d, names)
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
        out.append(_not_judged_note(undecided))
    return out[:MAX_LIMITATIONS]


def _not_judged_note(undecided: list) -> str:
    """"Not judged (no usable evidence): INSUFFICIENT_EVIDENCE c1, c2; NOT_VERIFIABLE c5",
    kept within ``MAX_LIMITATION_CHARS``: real videos have 20+ claims, and the old
    one-entry-per-claim form broke the §10 length check on its own (T18 smoke run)."""
    head = "Not judged (no usable evidence): "
    groups: dict[str, list[str]] = {}
    for v in undecided:
        groups.setdefault(v.verdict.value, []).append(v.claim_id)
    text = head + "; ".join(f"{verdict} {', '.join(ids)}" for verdict, ids in groups.items())
    if len(text) <= MAX_LIMITATION_CHARS:
        return text
    text = head + "; ".join(f"{verdict} ({len(ids)} claims)" for verdict, ids in groups.items())
    return text[:MAX_LIMITATION_CHARS]


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
    names = _names(d.all_claims or views)
    rows = []
    for v in views:
        rows.append(
            f"- {_meta(v.claim_id)} | call it: {names.get(v.claim_id, 'the claim')}"
            f" | stance: {v.stance_or_unclear.value} | verdict: {v.verdict.value}"
            f" | supporting: {_meta(_ids(v.verification.supporting_evidence_ids))}"
            f" | contradicting: {_meta(_ids(v.verification.contradicting_evidence_ids))}"
            f" | deciding: {'yes' if v.claim_id in deciding else 'no'}"
            + (" | sarcasm: yes" if v.sarcastic else "")
        )
    flags = "\n".join(f"- {flag_text(f, names)}" for f in d.review_flags) or "- none"
    return (
        f"The video label has already been decided by written rules: "
        f"{display_label(d.label, d.misinfo_basis)} "
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
        if v.sarcastic:  # T47: the stance step's note on the sarcasm, for the nuance
            blocks.append(fence(v.stance_rationale, kind="model_output",
                                item_id=f"{v.claim_id}:stance", max_chars=max_chars))
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
# Internal enum names (``CANNOT_RECOGNIZE``, ``INSUFFICIENT_EVIDENCE``) and the word
# "false" for an unproven claim never reach a reader (T30).
_ENUM_NAME = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b")
_FALSE_WORD = re.compile(r"\bfalse\b", re.IGNORECASE)
_EVIDENCE_ID = re.compile(r"\b(?:ev|lib|ref)_[A-Za-z0-9_]+")  # PubMed, library (T12), reference (T17)
_PMID = re.compile(r"\bPMID:?\s*(\d+)", re.IGNORECASE)


def check_explanation(
    text: str, d: Decision, evidence: dict[str, dict[str, EvidenceRecord]] | None = None
) -> str:
    """Raise ``InvalidExplanation`` unless ``text`` is consistent with the decision:
    it names no other label and mentions only evidence IDs / PMIDs the decision cites.
    T30: no internal enum names, no claim IDs, and an unproven label is never called
    false."""
    for m in _LABEL_WORDS.finditer(text):
        word = m.group(0).lower()
        named = (MisinfoLabel.CANNOT_RECOGNIZE if word.startswith("cannot")
                 else _LABEL_ALIASES.get(word))
        if named is not None and named != d.label:
            raise InvalidExplanation(f"explanation names label {named.value}, not {d.label.value}")
    enum = _ENUM_NAME.search(text)
    if enum:
        raise InvalidExplanation(f"explanation uses the internal name {enum.group(0)!r}")
    ids = {v.claim_id for v in (*d.all_claims, *d.deciding)}
    named = [w for w in re.findall(r"[A-Za-z0-9_]+", text) if w in ids]
    if named:
        raise InvalidExplanation(f"explanation names claims by ID: {sorted(set(named))}")
    if d.misinfo_basis == BASIS_UNPROVEN and _FALSE_WORD.search(text):
        raise InvalidExplanation("an unproven claim is described as false")
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
    text += _review_note(d, _names(d.all_claims or d.deciding))
    return text[:MAX_EXPLANATION_CHARS], model, version or prompt_version, []


# ------------------------------------------------------------------ node


def judge(
    state: PipelineState,
    caller: Optional[StepCaller] = None,
    *,
    system_prompt: Optional[str] = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
    budgets: Budgets = DEFAULT_BUDGETS,
) -> tuple[FinalClassification, list[NodeError]]:
    views, errors = claim_views(state, budgets)
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
        misinfo_basis=d.misinfo_basis,
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
    budgets: Budgets = DEFAULT_BUDGETS,
) -> Callable[[PipelineState], dict]:
    """Build the ``judge_classification`` node. Pass the graph's ``budgets`` so exhausted
    claims are recognised (T07).

    With no ``caller`` the explanation is the deterministic template (no model call).
    With a caller (T01's ``ModelRouter``), the routed ``judge_explanation`` step writes
    it; the prompt file is loaded here so a bad routing config fails at start-up.
    """
    version = system_prompt = None
    if caller is not None:
        version = resolve_prompt_version(caller, prompt_version)
        system_prompt = load_prompt(version)

    def judge_classification(state: PipelineState) -> dict:
        # §10 repair (T09): validation found a fault in the judge's output and re-ran
        # it. The label is recomputed from state by the rules; the only model output,
        # the explanation, is replaced by the deterministic template, which always
        # passes validation. So the repair costs no model call.
        from app.core.graph.validation import in_repair  # validation imports judge

        repairing = in_repair(state)
        final, errors = judge(
            state, None if repairing else caller, system_prompt=system_prompt,
            prompt_version=version or DEFAULT_PROMPT_VERSION, max_chars=max_chars,
            budgets=budgets,
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
    if verdict == Verdict.SUPPORTED and stance == Stance.REFUTES:
        return MisinfoLabel.MISINFO  # the speaker denies something true
    if verdict == Verdict.UNSUPPORTED and stance == Stance.ENDORSES:
        return MisinfoLabel.MISINFO  # an unproven efficacy claim promoted (T30)
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
