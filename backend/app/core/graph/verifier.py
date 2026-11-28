"""Evidence verifier node (target design §7; issue #33).

For each claim, one LLM call reads the claim and its reranked papers and decides what
the evidence says about that exact claim: SUPPORTED, CONTRADICTED, MIXED, UNSUPPORTED,
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
- **Unproven efficacy claims (T30, D1 = B).** UNSUPPORTED ("no evidence supports
  this", never "false") is offered only for an efficacy claim (``treatment_efficacy`` /
  ``prevention``) whose searches ran without error (``routing.unproven_eligible``). It
  must cite nothing. With no evidence at all such a claim gets UNSUPPORTED without a
  model call; any other claim, or a model's UNSUPPORTED for a claim that isn't
  eligible, is INSUFFICIENT_EVIDENCE. Whether the *full* search budget was used is
  checked later: the critic asks for another search while budget is left, and
  ``routing.verdicts_for_judge`` passes UNSUPPORTED to the judge only once it is spent.
- **Unproven guard (T49).** Right after each verdict the node runs
  ``unproven_guard.apply_unproven_guard``: UNSUPPORTED stands only if the claim's
  reranked evidence holds a record on topic for the claim's intervention; an empty or
  off-topic search gives INSUFFICIENT_EVIDENCE with ``search_found_nothing_on_topic``.
- **Unproven-label fixes (T64).** The guard also turns UNSUPPORTED into
  INSUFFICIENT_EVIDENCE when the claim names no condition or outcome
  (``outcome_unspecified``: the model's flag, enforced in code too) or the search kept
  fewer than 3 on-topic records and no on-topic systematic review / RCT / guideline
  (``search_too_thin``). After every pass, ``unproven_guard.apply_sibling_rule`` runs
  over all results: an UNSUPPORTED claim whose sibling about the same intervention (a
  prevention / efficacy claim) is SUPPORTED becomes INSUFFICIENT_EVIDENCE with
  ``contradicted_by_sibling_claim``.
- **Evidence context (T69, switch ``routing.CONTEXT_MISMATCH_RULE``, off).** When on, the
  tool gains the structured field ``evidence_context`` and a CONTRADICTED verdict whose
  contradicting papers study another population or exposure setting carries the
  limitation code ``evidence_context_mismatch:<kind>`` for the judge (§9). Off, the
  request and results are unchanged.
- **Claim context (T70, switch ``routing.CLAIM_CONTEXT``, off; prompt ``verify_v4``).** A
  claim with grounded, specific context (``claim_context.context_of``) is judged as meant:
  the context is fenced next to the claim, and the tool's ``evidence_context`` (T69's
  field, plus the value ``partial``) is asked for every verdict, with
  ``contradicted_as_stated``. Code derives ``setting_match`` (same / partial / different)
  and stores it as the limitation code ``setting_match:<v>``; a claim contradicted as
  stated but not as meant gets ``softened_by_context`` (the judge sets it aside and it is
  reviewed). A universal claim gets no context and keeps no context-derived code.
- **Loop-aware.** Only ``routing.claims_to_verify`` claims are (re)judged; others keep
  their verdict. A REVISE_VERIFICATION re-run counts against the revision budget and
  shows the critic's notes; a RETRIEVE_MORE re-run judges the new evidence.
- Writes ``verification_results`` and ``verification_revisions`` (the T02 ownership
  map), plus the shared, append-only ``errors``.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Literal, Optional, Protocol, Sequence

from pydantic import Field, field_validator

from app.core.graph import claim_context as cx
from app.core.graph import routing as r
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.graph.state import (
    ClaimContext,
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    GraphClaim,
    NodeError,
    PipelineState,
    Verdict,
    VerificationResult,
    VideoTopic,
)
from app.core.graph.stance import PromptNotFoundError, load_prompt  # shared prompt loader
from app.core.graph.unproven_guard import (
    OUTCOME_UNSPECIFIED_EXPLANATION,
    OUTCOME_UNSPECIFIED_LIMITATION,
    apply_sibling_rule,
    apply_unproven_guard,
)
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX
from app.core.guardrails.outputs import OutputViolation, VerificationOutput, _no_urls, parse_output
from app.core.user_text import evidence_ids_in, reword_reviewer, render_evidence_ids, source_name
from app.core.guardrails.untrusted import (
    DEFAULT_MAX_BLOCK_CHARS,
    GuardedPrompt,
    fence,
    guarded_system_prompt,
    verification_prompt,
)

STEP = "verify_claims"  # routing.yaml step name (§13)
DEFAULT_PROMPT_VERSION = "verify_v3"  # v2 adds authoritative references (T17); v3 UNSUPPORTED (T30)
TOOL_NAME = "record_verdict"
MAX_EVIDENCE_PER_CLAIM = 10  # §6 "Cap"; enforced here too in case the reranker isn't
DEFAULT_MAX_REPAIRS = 1
MAX_EXPLANATION_CHARS = 1_000
MAX_LIMITATION_CHARS = 300
UNPROVEN_EXPLANATION = (
    "No evidence supports this claim: the search found no study or reference that tests it, "
    "for or against."
)
NOT_ELIGIBLE_LIMITATION = (
    "no evidence either way; recorded as insufficient evidence because the unsupported "
    "verdict applies only to treatment or prevention claims whose search ran in full"
)

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
    # T64 (c): the claim names no condition or outcome, so it can't be UNSUPPORTED.
    outcome_unspecified: bool = False
    # T69: does the contradicting evidence study the claim's population and exposure
    # setting? Asked for only when ``routing.CONTEXT_MISMATCH_RULE`` is on (see
    # :func:`verify_tool`); recorded as a limitation code on a CONTRADICTED verdict.
    evidence_context: Optional[Literal["matches", "partial", "different_population",
                                       "different_exposure_setting"]] = None
    # T70: would the evidence contradict the claim's words alone? Asked only with
    # ``routing.CLAIM_CONTEXT`` on, for a claim judged in context. ``partial`` above is
    # also T70-only; with the switch off both are rejected as before (``check_switches``).
    contradicted_as_stated: Optional[bool] = None

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
            "outcome_unspecified": {
                "type": "boolean",
                "description": "True if the claim names no specific condition or outcome "
                               "('a potentially devastating condition', 'many diseases').",
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

# T69: the structured field the judge's context-mismatch rule reads. Only offered when
# ``routing.CONTEXT_MISMATCH_RULE`` is on, so with the switch off the request is unchanged.
EVIDENCE_CONTEXT_PROPERTY: dict = {
    "type": "string",
    "enum": list(r.EVIDENCE_CONTEXT_VALUES),
    "description": "For a CONTRADICTED verdict: do the contradicting papers study the claim's "
                   "population and exposure setting ('matches'), or a different population "
                   "('different_population') or exposure setting, route or dose "
                   "('different_exposure_setting', e.g. occupational solvent exposure for a "
                   "claim about a consumer product on skin)?",
}
EVIDENCE_CONTEXT_INSTRUCTION = (
    "If the verdict is CONTRADICTED, set evidence_context: 'matches' if the contradicting papers "
    "study the claim's population and exposure setting, 'different_population' if they study a "
    "different population, or 'different_exposure_setting' if they study a different setting, "
    "route or dose of exposure than the claim describes.\n"
)


# T70: the same field with CLAIM_CONTEXT on: one more value and asked for every verdict.
CLAIM_CONTEXT_EVIDENCE_PROPERTY: dict = {
    "type": "string",
    "enum": list(r.CLAIM_CONTEXT_EVIDENCE_VALUES),
    "description": "Do the papers you relied on study the claim's population and exposure setting as "
                   "meant: matches, partial (same route, much higher dose; a related population), "
                   "different_population or different_exposure_setting (another setting, route or dose)?",
}
CONTRADICTED_AS_STATED_PROPERTY: dict = {
    "type": "boolean",
    "description": "Would the papers contradict the claim's words taken alone, without the context?",
}


def verify_tool(*, context_mode: bool = False, in_context: bool = False) -> dict:
    """The ``record_verdict`` tool for the current switches: ``VERIFY_TOOL`` unchanged,
    plus ``evidence_context`` when ``routing.CONTEXT_MISMATCH_RULE`` is on (T69). With
    T70's ``context_mode`` the field takes ``partial`` too and is required, and a claim
    judged ``in_context`` must also answer ``contradicted_as_stated``."""
    if context_mode:
        schema = dict(VERIFY_TOOL["input_schema"])
        props = {**schema["properties"], "evidence_context": CLAIM_CONTEXT_EVIDENCE_PROPERTY}
        required = [*schema["required"], "evidence_context"]
        if in_context:
            props["contradicted_as_stated"] = CONTRADICTED_AS_STATED_PROPERTY
            required.append("contradicted_as_stated")
        schema["properties"], schema["required"] = props, required
        return {**VERIFY_TOOL, "input_schema": schema}
    if not r.CONTEXT_MISMATCH_RULE:
        return VERIFY_TOOL
    schema = dict(VERIFY_TOOL["input_schema"])
    schema["properties"] = {**schema["properties"], "evidence_context": EVIDENCE_CONTEXT_PROPERTY}
    return {**VERIFY_TOOL, "input_schema": schema}


# T70 instruction lines (replace T69's line when the switch is on).
CONTEXT_INSTRUCTION = (
    "Scope: SPECIFIC. Judge the claim as meant in the fenced block \"{cid}:context\" (video material). "
    "Answer evidence_context and contradicted_as_stated.\n"
)
AS_STATED_INSTRUCTION = "Scope: UNIVERSAL. Judge the claim exactly as stated. Answer evidence_context.\n"


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
        if e.journal:
            parts.append(f"journal: {_meta(e.journal)}")
        if e.pub_date:
            parts.append(f"published: {_meta(e.pub_date)}")
        if e.publisher:
            parts.append(f"publisher: {_meta(e.publisher)}")
        if e.retrieved_at:
            parts.append(f"retrieved: {_meta(e.retrieved_at[:10])}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def _instructions(
    claim: GraphClaim,
    evidence: Sequence[EvidenceRecord],
    repair_note: Optional[str],
    allow_unsupported: bool = False,
    context_mode: bool = False,
    in_context: bool = False,
) -> str:
    unsupported = (
        "UNSUPPORTED is allowed for this claim (a treatment or prevention claim): use it if no "
        "paper tests the claim for or against, and cite nothing. If the claim names no specific "
        "condition or outcome (for example 'a potentially devastating condition' or 'many "
        "diseases'), set outcome_unspecified to true: such a claim cannot be UNSUPPORTED, so "
        "the verdict is INSUFFICIENT_EVIDENCE."
        if allow_unsupported else
        "UNSUPPORTED is NOT allowed for this claim; if nothing tests it, the verdict is "
        "INSUFFICIENT_EVIDENCE."
    )
    text = (
        f"Judge claim {claim.claim_id} (in the fenced claim block) against the papers below.\n"
        f"Claim category: {_meta(claim.claim_category)}. {unsupported}\n\n"
        f"EVIDENCE INDEX (metadata from the retrieval tools; cite only these IDs):\n{evidence_index(evidence)}\n\n"
        "Each paper's title and abstract are in fenced blocks with the same id.\n"
        "Cite papers by ID only in the two evidence-ID lists. In the explanation and limitations, "
        "never write an evidence ID (ev_...): name a paper by its short title or its PMID. "
        "When the claim names a journal or a publication date, check it against the journal and "
        "published date in the index.\n"
    )
    if repair_note:
        text += (
            "\nYOUR PREVIOUS ANSWER WAS REJECTED by an automatic check: "
            f"{repair_note}\nAnswer again, following the citation rules exactly.\n"
        )
    if context_mode:  # T70 (replaces T69's line: the same field, asked for every verdict)
        text += CONTEXT_INSTRUCTION.format(cid=_meta(claim.claim_id)) if in_context else AS_STATED_INSTRUCTION
    elif r.CONTEXT_MISMATCH_RULE:
        text += EVIDENCE_CONTEXT_INSTRUCTION  # T69
    return text + f"\nCall {TOOL_NAME} with your verdict."


def build_prompt(
    claim: GraphClaim,
    evidence: Sequence[EvidenceRecord],
    system_prompt: str,
    *,
    critic: Optional[CriticResult] = None,
    repair_note: Optional[str] = None,
    max_chars: int = DEFAULT_MAX_BLOCK_CHARS,
    allow_unsupported: bool = False,
    context_mode: bool = False,
    context: Optional[ClaimContext] = None,
    topic: Optional[VideoTopic] = None,
) -> GuardedPrompt:
    """The fenced prompt: T10's verification builder with our instructions, plus the
    critic's notes on a revision (fenced: they are a model's words about untrusted text).
    T70: a claim judged in context gets its context fenced right after the claim."""
    in_context = context_mode and cx.is_specific(context)
    prompt = verification_prompt(
        claim, evidence, task=_instructions(claim, evidence, repair_note, allow_unsupported,
                                            context_mode, in_context),
        max_chars=max_chars,
    )
    blocks = list(prompt.blocks)
    if in_context:
        blocks.insert(1, fence(cx.verifier_block(context, topic), kind="claim_context",
                               item_id=f"{claim.claim_id}:context", max_chars=max_chars))
    if critic and critic.decision == CriticDecision.REVISE_VERIFICATION and critic.issues:
        notes = (
            "NOTES FROM A SECOND AUTOMATED CHECK on the previous verdict (a model, not a person; if "
            "you refer to them, call them 'a second automated check', never 'the reviewer'):\n"
            + "\n".join(f"- {i}" for i in critic.issues)
        )
        blocks.append(fence(notes, kind="model_output", item_id=f"{claim.claim_id}:critic", max_chars=max_chars))
    return prompt.model_copy(update={"system": guarded_system_prompt(system_prompt), "blocks": tuple(blocks)})


def build_request(prompt: GuardedPrompt, *, context_mode: bool = False, in_context: bool = False) -> dict:
    """Provider-neutral request body: one user message plus a forced tool call."""
    return {
        "messages": [{"role": "user", "content": prompt.render()}],
        "tools": [verify_tool(context_mode=context_mode, in_context=in_context)],
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
    - UNSUPPORTED means no evidence either way, so it cites nothing (T30).
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
    if out.verdict == Verdict.UNSUPPORTED and (sup or con):
        raise InvalidVerification(
            "inconsistent_citation",
            "UNSUPPORTED means no paper tests the claim either way, so it cites no evidence IDs",
        )


def parse_verification(raw: Any, allowed_ids: Iterable[str], *, context_mode: bool = False,
                       in_context: bool = False) -> VerifierToolOutput:
    """Parse and check one answer. Raises ``InvalidVerification``."""
    try:
        out = parse_output(STEP, raw, VerifierToolOutput)
    except OutputViolation as exc:
        raise InvalidVerification("output_rejected", exc.reason) from None
    check_switches(out, context_mode=context_mode, in_context=in_context)  # type: ignore[arg-type]
    check_citations(out, allowed_ids)  # type: ignore[arg-type]
    return out  # type: ignore[return-value]


def check_switches(out: VerifierToolOutput, *, context_mode: bool, in_context: bool) -> None:
    """T70's fields exist only with its switch on: without it an answer carrying them is
    rejected exactly as before T70 (unknown field / out-of-set value). With it on, a
    claim judged in context must answer both structured questions."""
    if not context_mode:
        if out.contradicted_as_stated is not None:
            raise InvalidVerification("output_rejected", "schema violation at contradicted_as_stated: "
                                                         "Extra inputs are not permitted")
        if out.evidence_context == "partial":
            raise InvalidVerification("output_rejected", "schema violation at evidence_context: "
                                                         "Input should be 'matches', 'different_population' "
                                                         "or 'different_exposure_setting'")
        return
    if in_context and (out.evidence_context is None or out.contradicted_as_stated is None):
        raise InvalidVerification("output_rejected", "evidence_context and contradicted_as_stated are "
                                                     "required for a claim judged in its context")
    if not in_context and out.contradicted_as_stated is not None:
        raise InvalidVerification("output_rejected", "contradicted_as_stated is only for a claim judged "
                                                     "in its context")


# ------------------------------------------------------------------ user-facing text (T65)


def source_names(evidence: Sequence[EvidenceRecord]) -> dict[str, Optional[str]]:
    """Evidence id → how user-facing text names the paper (short title, else PMID)."""
    return {e.evidence_id: source_name(e.title, e.pmid) for e in evidence}


def ids_in_text(out: VerifierToolOutput) -> list[str]:
    """Evidence ids written into the explanation or limitations (T65 a): internal ids
    must not reach the reader."""
    return evidence_ids_in(" ".join([out.explanation, *out.limitations]))


def clean_text(text: str, names: dict[str, Optional[str]]) -> str:
    """Last line of the output check: ids rendered as source names, the critic called
    "a second automated check" rather than "the reviewer"."""
    return reword_reviewer(render_evidence_ids(text, names))


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
    allow_unsupported: bool = False,
    context_mode: bool = False,
    context: Optional[ClaimContext] = None,
    topic: Optional[VideoTopic] = None,
) -> tuple[VerificationResult, list[NodeError]]:
    """Verify one claim. Never raises for model trouble: the safe default is
    INSUFFICIENT_EVIDENCE with the reason recorded.

    ``context_mode`` (T70, switch on with verify_v4): ``context`` is the claim's grounded
    specific context, or None for a universal claim (judged as stated).

    ``allow_unsupported`` (``routing.unproven_eligible``): the claim may be judged
    UNSUPPORTED (T30). Without it, a model's UNSUPPORTED becomes INSUFFICIENT_EVIDENCE."""
    evidence = list(evidence)[:MAX_EVIDENCE_PER_CLAIM]
    allowed = [e.evidence_id for e in evidence]
    errors: list[NodeError] = []
    in_context = context_mode and cx.is_specific(context)

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
        # never contradicted; there is nothing for a model to read. For an efficacy
        # claim it is UNSUPPORTED (T30): no evidence supports it.
        if allow_unsupported:
            return VerificationResult(
                claim_id=claim.claim_id, verdict=Verdict.UNSUPPORTED,
                explanation=UNPROVEN_EXPLANATION,
                limitations=["no evidence was retrieved for this claim"],
                prompt_version=prompt_version,
            ), errors
        return insufficient("no evidence was retrieved for this claim"), errors

    repair_note: Optional[str] = None
    model: Optional[str] = None
    for attempt in range(max_repairs + 1):
        if context_mode:
            prompt = build_prompt(
                claim, evidence, system_prompt, critic=critic, repair_note=repair_note, max_chars=max_chars,
                allow_unsupported=allow_unsupported, context_mode=True, context=context, topic=topic,
            )
            request = build_request(prompt, context_mode=True, in_context=in_context)
        else:
            prompt = build_prompt(
                claim, evidence, system_prompt, critic=critic, repair_note=repair_note, max_chars=max_chars,
                allow_unsupported=allow_unsupported,
            )
            request = build_request(prompt)
        try:
            result = caller.call(STEP, request, system=prompt.system)
        except Exception as exc:  # routing / provider errors: don't guess a verdict
            errors.append(NodeError(
                node=r.VERIFY_CLAIMS, message=f"model call failed: {type(exc).__name__}: {exc}",
                claim_id=claim.claim_id, retryable=True,
            ))
            return insufficient("verdict not determined: the verifier model could not be reached", model=model), errors
        model, recorded_version = _record_meta(result)
        try:
            out = parse_verification(getattr(result, "output", None), allowed,
                                     context_mode=context_mode, in_context=in_context)
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
        leaked = ids_in_text(out)
        if leaked and attempt < max_repairs:
            # T65 (a): one repair; if the answer still carries ids, they are rendered below.
            repair_note = (
                f"the explanation or limitations contain internal evidence IDs ({', '.join(leaked[:5])}); "
                "keep IDs in the evidence-ID lists only and name papers by short title or PMID"
            )
            errors.append(NodeError(
                node=r.VERIFY_CLAIMS, message=f"repair requested: evidence_id_in_text: {', '.join(leaked[:5])}",
                claim_id=claim.claim_id,
            ))
            continue
        names = source_names(evidence)
        out = out.model_copy(update={
            "explanation": clean_text(out.explanation, names),
            "limitations": [t for t in (clean_text(x, names) for x in out.limitations) if t],
        })
        if out.verdict == Verdict.UNSUPPORTED and not allow_unsupported:
            # Harm, mechanism and other claims with no evidence stay insufficient (§7).
            return VerificationResult(
                claim_id=claim.claim_id, verdict=Verdict.INSUFFICIENT_EVIDENCE,
                explanation=out.explanation[:MAX_EXPLANATION_CHARS],
                limitations=[*(s[:MAX_LIMITATION_CHARS] for s in out.limitations), NOT_ELIGIBLE_LIMITATION],
                raw_confidence=out.raw_confidence, model=model,
                prompt_version=recorded_version or prompt_version,
            ), errors
        if out.verdict == Verdict.UNSUPPORTED and out.outcome_unspecified:
            # T64 (c): the model says the claim names no outcome; no study can test it.
            return VerificationResult(
                claim_id=claim.claim_id, verdict=Verdict.INSUFFICIENT_EVIDENCE,
                explanation=OUTCOME_UNSPECIFIED_EXPLANATION,
                limitations=[*(s[:MAX_LIMITATION_CHARS] for s in out.limitations), OUTCOME_UNSPECIFIED_LIMITATION],
                raw_confidence=out.raw_confidence, model=model,
                prompt_version=recorded_version or prompt_version,
            ), errors
        return VerificationResult(
            claim_id=claim.claim_id,
            verdict=out.verdict,
            supporting_evidence_ids=list(out.supporting_evidence_ids),
            contradicting_evidence_ids=list(out.contradicting_evidence_ids),
            explanation=out.explanation[:MAX_EXPLANATION_CHARS],
            limitations=[*(s[:MAX_LIMITATION_CHARS] for s in out.limitations),
                         *(_claim_context_codes(out, in_context) if context_mode else _context_codes(out))],
            raw_confidence=out.raw_confidence,  # raw; calibration is T15 (§11)
            model=model,
            prompt_version=recorded_version or prompt_version,
        ), errors
    raise AssertionError("unreachable")  # pragma: no cover


def _context_codes(out: VerifierToolOutput) -> list[str]:
    """T69: the limitation code for a CONTRADICTED verdict whose evidence the model said
    is about a different population or exposure setting (switch on only)."""
    if (r.CONTEXT_MISMATCH_RULE and out.verdict == Verdict.CONTRADICTED
            and out.evidence_context in r.CONTEXT_MISMATCH_KINDS):
        return [f"{r.CONTEXT_MISMATCH_LIMITATION}:{out.evidence_context}"]
    return []


def _claim_context_codes(out: VerifierToolOutput, in_context: bool) -> list[str]:
    """T70: the structured codes for a verdict, switch on. Every verdict keeps
    ``setting_match:<v>`` (derived from ``evidence_context``; informational, the judge
    does not read it). Only a claim judged in context can also keep T69's mismatch code
    (a CONTRADICTED verdict about another setting or population) and
    ``softened_by_context`` (contradicted as stated, not as meant): a universal claim is
    judged as stated, and nothing context-derived softens it."""
    codes: list[str] = []
    setting = r.SETTING_MATCH.get(out.evidence_context or "")
    if setting:
        codes.append(f"{r.SETTING_MATCH_LIMITATION}:{setting}")
    if not in_context:
        return codes
    if out.verdict == Verdict.CONTRADICTED and out.evidence_context in r.CONTEXT_MISMATCH_KINDS:
        codes.append(f"{r.CONTEXT_MISMATCH_LIMITATION}:{out.evidence_context}")
    if out.contradicted_as_stated and out.verdict != Verdict.CONTRADICTED:
        codes.append(r.SOFTENED_LIMITATION)
    return codes


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
    cx.check_prompts(verify_version=version)  # T70: switch on needs verify_v4
    context_mode = r.CLAIM_CONTEXT and version in cx.VERIFY_CONTEXT_PROMPTS

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
            evidence = list(reranked.get(cid, []))[:MAX_EVIDENCE_PER_CLAIM]
            if context_mode:
                result, errs = verify_claim(
                    claims[cid], evidence, caller, system_prompt, version,
                    critic=critic, max_repairs=max_repairs, max_chars=max_chars,
                    allow_unsupported=r.unproven_eligible(state, cid),
                    context_mode=True, context=cx.context_of(state, cid), topic=state.get("video_topic"),
                )
            else:
                result, errs = verify_claim(
                    claims[cid], evidence, caller, system_prompt, version,
                    critic=critic, max_repairs=max_repairs, max_chars=max_chars,
                    allow_unsupported=r.unproven_eligible(state, cid),
                )
            # T49 (§7): UNSUPPORTED only with an on-topic record in what retrieval kept.
            result = apply_unproven_guard(claims[cid], evidence, result)
            results[cid] = result
            errors += errs
        # T64 (b): a SUPPORTED sibling about the same intervention outranks UNSUPPORTED.
        results = apply_sibling_rule(list(claims.values()), results)
        update: dict = {"verification_results": results, "verification_revisions": revisions}
        if errors:
            update["errors"] = errors
        return update

    return verify_claims

