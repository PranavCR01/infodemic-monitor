"""Review reasons as structured objects with plain-language text (target design §12; T26).

The review rule stores reasons as short strings (``weak_evidence:c2``,
``judge:possible_debunk:c1``, ``validation_failed:quotes:c3``, ...; the formats are
listed in ``app.core.graph.review_policy``). A reviewer is meant to see *why* a case was
escalated (§12), so the API also returns each reason parsed into
``{code, rule, claim_id, detail, text, raw}``, where ``text`` comes from
``REASON_TEXT``: the one table of plain-language wording for every reason code. An
unknown code still gets a generic sentence, never an error.

The stored strings are not changed, and the API keeps returning them as ``reasons``
(the current frontend shows them); the structured form is the additive
``reason_details``.

**Wording (T30, frontend finding).** ``text`` is for analysts: it says "this claim"
rather than a claim ID (the interface adds the claim's number from ``claim_id``), and
never shows node, check or rule names; those stay in ``detail`` and ``raw`` for the
audit trail.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

# code → plain-language text. ``{claim}`` becomes "this claim" (or "a claim" when the
# reason names none), ``{on_claim}`` " on this claim" (or nothing); ``{source}`` is a
# plain name for where suspicious text was found. Node, check and rule names never
# appear here; they stay in ``detail``.
REASON_TEXT: dict[str, str] = {
    # review rules (§11)
    "weak_evidence": "The evidence for {claim} is too weak or too mixed to decide.",
    "conflicting_evidence": "Some papers support {claim} and others contradict it.",
    "weak_study_types": "{Claim} rests only on weak kinds of study (lab, animal or single-case reports).",
    "unclear_stance": "It is unclear whether the speaker agrees with {claim}.",
    "critic_escalated": "The automatic critic asked for a person to check {claim}.",
    "budget_exhausted": "The search for evidence on {claim} ran out of attempts before it was settled.",
    # T67 (1): the critic is "a second automated check" in user-facing text (T65)
    "second_check_disagreed": "A second automated check still disagreed with the verdict on {claim} when "
                              "its attempts ran out; the verdict was kept for a person to confirm.",
    "validation_failed": "An automatic consistency check on the result failed{on_claim}.",
    "low_confidence": "The system's confidence in the result is low.",
    "high_risk_uncertain": "{Claim} is about a high-risk health topic and the evidence could not settle it.",
    # judge flags (§9), stored as ``judge:<flag>[:<cid>]``
    "mixed_video": "The video endorses one claim the evidence contradicts or does not support, and refutes another.",
    "unclear_stance_contradicted": "The evidence contradicts {claim}, but the speaker's stance on it is unclear.",
    "false_claim_not_refuted": "{Claim} is contradicted by the evidence but is repeated without being refuted.",
    "mixed_evidence": "The evidence on {claim} is mixed.",
    "verification_failed": "{Claim} could not be checked because the verifier was unavailable.",
    "denies_supported": "The speaker denies {claim}, which the evidence supports.",
    "unproven_claim": "The speaker presents {claim} as working, but the full search found no evidence "
                      "for or against it: no evidence supports this claim.",
    "possible_debunk": "The speaker refutes {claim}, but the evidence could not settle it: possibly a debunk.",
    # T37: video-level (§11)
    "nothing_judged": "No claim in this video could be checked against the evidence.",
    # T64 (f): video-level; the label is unchanged
    "main_claims_unchecked": "The label rests on side claims: at least half of the treatment and "
                             "prevention claims the speaker makes could not be checked against the evidence.",
    # T67 (2): per claim; the claim did not decide the label
    "thin_contradiction": "The evidence against {claim} is too thin to decide the label on its own: fewer "
                          "than two papers on its topic and no review, trial or guideline.",
    # guardrails (§15)
    "prompt_injection_suspected": "Text in {source} looks like an attempt to instruct the system.",
    "guardrail": "A safety check stopped part of the analysis{on_claim}.",
    # asked for by a person (T32), not raised by a rule
    "user_requested": "Someone asked for a person to check this result.",
}
GENERIC_TEXT = "An automatic check flagged this result for a person to look at."

# Where suspicious text was found (``prompt_injection_suspected:<source>:<id>``).
_SOURCE_TEXT = {
    "transcript": "the speech transcript",
    "on_screen": "the on-screen text",
    "claim": "a claim",
    "evidence_title": "a paper's title",
    "evidence_abstract": "a paper's abstract",
}

# reason heads whose next part is the claim id
_CLAIM_RULES = {
    "weak_evidence", "conflicting_evidence", "weak_study_types", "unclear_stance",
    "critic_escalated", "budget_exhausted", "high_risk_uncertain", "second_check_disagreed",
}


class ReasonView(BaseModel):
    """One review reason, parsed. ``raw`` is the stored string."""

    code: str
    rule: str
    claim_id: Optional[str] = None
    detail: Optional[str] = None
    text: str
    raw: str


def _looks_like_claim_id(part: str) -> bool:
    return bool(part) and part[0].isalpha() and part[1:].isdigit()


def parse_reason(raw: str) -> ReasonView:
    from app.core.graph.review_policy import rule_of

    head, _, rest = raw.partition(":")
    parts = rest.split(":") if rest else []
    code, claim_id, detail = head, None, None
    if head == "judge":
        code = parts[0] if parts else "judge"
        claim_id = parts[1] if len(parts) > 1 else None
    elif head in _CLAIM_RULES:
        claim_id = parts[0] if parts else None
    elif head == "validation_failed":
        if parts and _looks_like_claim_id(parts[-1]) and len(parts) > 1:
            claim_id = parts[-1]
            parts = parts[:-1]
        detail = ":".join(parts).replace("_", " ") or None
    elif head == "prompt_injection_suspected":
        # prompt_injection_suspected:<source>:<item_id>; the item is a segment or a
        # paper, not a claim
        detail = (parts[0].replace("_", " ") if parts else "input")
    elif head == "guardrail":
        # guardrail:<node>:<kind>[:<cid>]
        if parts and _looks_like_claim_id(parts[-1]) and len(parts) > 2:
            claim_id = parts[-1]
            parts = parts[:-1]
        detail = " ".join(p.replace("_", " ") for p in parts) or None
    else:
        detail = rest or None
    return ReasonView(code=code, rule=rule_of(raw), claim_id=claim_id, detail=detail,
                      text=reason_text(code, claim_id, detail), raw=raw)


def reason_text(code: str, claim_id: Optional[str] = None, detail: Optional[str] = None) -> str:
    template = REASON_TEXT.get(code)
    if template is None:
        return GENERIC_TEXT
    claim = "this claim" if claim_id else "a claim"
    source = _SOURCE_TEXT.get((detail or "").replace(" ", "_"), "the video's text or the sources")
    return template.format(claim=claim, Claim=claim[0].upper() + claim[1:], source=source,
                           on_claim=" on this claim" if claim_id else "")


def parse_reasons(raws: Optional[list]) -> list[ReasonView]:
    return [parse_reason(str(r)) for r in (raws or [])]
