"""Drive one item through the real graph node with a candidate's router.

``selection.evaluate_candidate`` builds a ``ModelRouter`` pointed at the candidate and
calls ``run_item(router, item)``. Going through the node (not a bare request) means each
candidate gets production's prompt for its prompt version, the fenced untrusted input,
the forced tool call, the output checks and the single repair attempt; and its answer is
scored after the same safe defaults production applies (an invalid stance answer is
UNCLEAR, an invalid verdict is INSUFFICIENT_EVIDENCE).

``requests_for`` renders the same requests without calling anything; the dry run
counts their tokens.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from app.core.graph import claims as claims_mod
from app.core.graph import stance as stance_mod
from app.core.graph import verifier as verifier_mod
from app.core.graph.state import initial_state
from app.core.guardrails.config import load_guardrails
from app.core.routing.router import ModelRouter
from app.evaluation.routing_experiment.items import (
    STANCE_LABELS,
    VERDICT_LABELS,
    StanceInput,
    VerifyInput,
    VideoInput,
)
from app.evaluation.selection import Scorer, StepItem, claim_set_f1, label_macro_f1

RunItem = Callable[[ModelRouter, StepItem], Any]


def _version(router: ModelRouter, step: str) -> str:
    return router.config.route(step).prompt


def _state(video_id: str, **fields: Any) -> dict:
    s = initial_state(job_id=f"t38-{video_id}", video_id=video_id, media_uri="", pipeline_version="t38")
    s.update(fields)
    return s


def run_extract(router: ModelRouter, item: StepItem) -> list[str]:
    v: VideoInput = item.input
    node = claims_mod.make_extract_claims(router, prompt_version=_version(router, claims_mod.STEP))
    out = node(_state(v.video_id, transcript_segments=v.transcript, ocr_segments=v.ocr, fused_segments=v.fused))
    return [c.claim_text for c in out.get("claims", [])]


def run_stance(router: ModelRouter, item: StepItem) -> str:
    x: StanceInput = item.input
    node = stance_mod.make_analyze_stance(router, prompt_version=_version(router, stance_mod.STEP))
    out = node(_state(item.item_id, transcript_segments=x.transcript, ocr_segments=x.ocr,
                      fused_segments=x.fused, claims=[x.claim]))
    return out["stance_results"][x.claim.claim_id].stance.value


def run_verify(router: ModelRouter, item: StepItem) -> str:
    x: VerifyInput = item.input
    version = _version(router, verifier_mod.STEP)
    result, _errors = verifier_mod.verify_claim(
        x.claim, x.evidence, router, verifier_mod.load_prompt(version), version,
        allow_unsupported=x.allow_unsupported,
    )
    return result.verdict.value


RUNNERS: dict[str, RunItem] = {
    "extract_claims": run_extract,
    "analyze_stance": run_stance,
    "verify_claims": run_verify,
}

SCORERS: dict[str, Scorer] = {
    "extract_claims": claim_set_f1(),
    "analyze_stance": label_macro_f1(list(STANCE_LABELS)),
    "verify_claims": label_macro_f1(list(VERDICT_LABELS)),
}


# ------------------------------------------------------------------ rendering (no calls)


def requests_for(step: str, item: StepItem, prompt_version: str) -> list[tuple[str, dict]]:
    """The ``(system, request)`` pairs the node would send for this item on a first
    attempt (repairs not included), rendered without any model call."""
    if step == "extract_claims":
        v: VideoInput = item.input
        g = load_guardrails()
        system = claims_mod.load_prompt(prompt_version)
        piece_ids = {t.segment_id for t in v.transcript} | {o.segment_id for o in v.ocr}
        out = []
        for window in claims_mod.windows(v.fused, claims_mod.DEFAULT_WINDOW_SECONDS, claims_mod.DEFAULT_OVERLAP_SECONDS):
            blocks = claims_mod.block_sources(window, piece_ids)
            prompt = claims_mod.build_prompt(window, blocks, system, max_chars=g.input.max_segment_chars)
            out.append((prompt.system or "", claims_mod.build_request(prompt)))
        return out
    if step == "analyze_stance":
        x: StanceInput = item.input
        state = _state(item.item_id, transcript_segments=x.transcript, ocr_segments=x.ocr, fused_segments=x.fused)
        segments = stance_mod.context_for_claim(x.claim, stance_mod._pool(state), stance_mod._fused_pool(state))
        if not segments:
            return []
        return [(stance_mod.load_prompt(prompt_version), stance_mod.build_request(x.claim, segments))]
    if step == "verify_claims":
        x2: VerifyInput = item.input
        evidence = list(x2.evidence)[: verifier_mod.MAX_EVIDENCE_PER_CLAIM]
        if not evidence:
            return []  # decided in code without a model call (§6/§7)
        prompt = verifier_mod.build_prompt(
            x2.claim, evidence, verifier_mod.load_prompt(prompt_version), allow_unsupported=x2.allow_unsupported)
        return [(prompt.system or "", verifier_mod.build_request(prompt))]
    raise ValueError(f"unknown step {step!r}")


def max_repairs(step: str) -> int:
    return {"extract_claims": claims_mod.MAX_REPAIRS, "verify_claims": verifier_mod.DEFAULT_MAX_REPAIRS}.get(step, 0)


def stance_extras(gold: list[str], pred: list[Optional[str]]) -> dict:
    """§14 "tracked separately": recall on refuted claims and debunks read as ENDORSES."""
    refutes = [p for g, p in zip(gold, pred) if g == "REFUTES"]
    return {
        "debunk_recall": (sum(p == "REFUTES" for p in refutes) / len(refutes)) if refutes else None,
        "debunk_read_as_endorses": sum(p == "ENDORSES" for p in refutes),
        "n_refutes": len(refutes),
    }


def verify_extras(gold: list[str], pred: list[Optional[str]]) -> dict:
    """§14 "tracked separately": insufficient evidence called contradiction; and how
    UNSUPPORTED fares (it is the rarest verdict)."""
    unsupported = [p for g, p in zip(gold, pred) if g == "UNSUPPORTED"]
    return {
        "insufficient_called_contradicted": sum(
            g in ("INSUFFICIENT_EVIDENCE", "UNSUPPORTED") and p == "CONTRADICTED" for g, p in zip(gold, pred)),
        "unsupported_recall": (sum(p == "UNSUPPORTED" for p in unsupported) / len(unsupported)) if unsupported else None,
        "n_unsupported": len(unsupported),
    }


EXTRAS: dict[str, Callable[[list, list], dict]] = {
    "analyze_stance": stance_extras,
    "verify_claims": verify_extras,
}
