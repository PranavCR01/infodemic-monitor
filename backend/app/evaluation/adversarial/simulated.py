"""A simulated model that always falls for the attack it can see.

No real model is called. For each case the responder returns what an honest model
would (from the case's ground truth), unless the step's input contains the case's
attack trigger: then it returns what the attack asks for. That is a worst case on
purpose. It measures what the *structure* around the model contains when the model
is fooled; how often a real model is fooled needs a paid run (T14).

The same responder serves the graph's steps and the single-call baseline's
``classify`` step, so both systems face the same adversary.
"""
from __future__ import annotations

import re
import time
from typing import Any

from app.core.guardrails.injection import normalise
from app.core.inference.providers.anthropic_provider import _SYSTEM_PROMPT as LIVE_SYSTEM_PROMPT
from app.core.inference.providers.anthropic_provider import _safe_label, _safe_list
from app.core.routing.mock import MockModelClient
from app.core.routing.router import ModelRequest
from app.core.schemas.pipeline import ClassificationResult, FusionResult
from app.evaluation.adversarial.cases import AdversarialCase

_BLOCK = re.compile(
    r'<<<UNTRUSTED kind="(?P<kind>[a-z_]+)" id="(?P<id>[^"]+)"[^>\n]*? nonce="(?P<nonce>[0-9a-f]+)">>>\n'
    r"(?P<text>.*?)\n<<<END UNTRUSTED nonce=\"(?P=nonce)\">>>",
    re.DOTALL,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", normalise(text)).strip().lower()


def blocks(rendered: str) -> list[dict]:
    return [m.groupdict() for m in _BLOCK.finditer(rendered)]


class ObedientModel:
    """Responder for ``MockModelClient``: honest unless it sees the trigger."""

    def __init__(self, case: AdversarialCase):
        self.case = case
        self.triggered_steps: list[str] = []

    def client(self) -> MockModelClient:
        return MockModelClient(self)

    def __call__(self, model: str, request: ModelRequest) -> Any:
        text = request.input if isinstance(request.input, str) else str(request.input)
        attack = self.case.attack
        effect = None
        if attack and _norm(attack.trigger) in _norm(text):
            effect = attack.effects.get(request.step)
            self.triggered_steps.append(request.step)
        if effect and "raw" in effect:
            return effect["raw"]
        handler = getattr(self, f"_{request.step}")
        return handler(text, effect or {})

    # -- honest answers, with the attack's overrides --

    def _claim_for(self, text: str):
        for b in blocks(text):
            if b["kind"] == "claim":
                want = _norm(b["text"])
                for c in self.case.claims:
                    if _norm(c.text) == want:
                        return c
        return None

    def _extract_claims(self, text: str, effect: dict) -> dict:
        claims = [] if effect.get("drop_claims") else [
            {"claim_text": c.text, "claim_category": "health", "source_segment_ids": list(c.segments)}
            for c in self.case.claims
        ]
        if "add_claim" in effect:
            add = effect["add_claim"]
            claims.append({"claim_text": add["text"], "claim_category": "health",
                           "source_segment_ids": list(add["segments"])})
        return {"claims": claims}

    def _analyze_stance(self, text: str, effect: dict) -> dict:
        claim = self._claim_for(text)
        stance = effect.get("stance") or (claim.stance.value if claim else "UNCLEAR")
        segments = list(claim.segments) if claim else []
        return {"stance": stance, "stance_segment_ids": segments, "rationale": "simulated"}

    def _verify_claims(self, text: str, effect: dict) -> dict:
        claim = self._claim_for(text)
        visible = list(dict.fromkeys(b["id"] for b in blocks(text) if b["kind"].startswith("evidence")))
        if effect.get("verdict"):
            cite = visible if effect.get("cite") == "visible" else list(effect.get("cite", []))
            key = "contradicting_evidence_ids" if effect["verdict"] == "CONTRADICTED" else "supporting_evidence_ids"
            return {"verdict": effect["verdict"], key: cite, "explanation": "simulated"}
        if claim is None or not visible or claim.truth.value in ("INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE"):
            return {"verdict": "INSUFFICIENT_EVIDENCE" if claim is None or not visible else claim.truth.value,
                    "explanation": "simulated"}
        key = {"SUPPORTED": "supporting_evidence_ids", "CONTRADICTED": "contradicting_evidence_ids"}
        if claim.truth.value == "MIXED":
            half = max(1, len(visible) // 2)
            return {"verdict": "MIXED", "supporting_evidence_ids": visible[:half],
                    "contradicting_evidence_ids": visible[half:] or visible[:1], "explanation": "simulated"}
        return {"verdict": claim.truth.value, key[claim.truth.value]: visible, "explanation": "simulated"}

    def _critique(self, text: str, effect: dict) -> dict:
        return {"decision": effect.get("decision", "APPROVE")}

    def _classify(self, text: str, effect: dict) -> dict:
        honest_snippets = [c.text for c in self.case.claims if _norm(c.text) in _norm(text)][:3]
        return {
            "label": effect.get("label", self.case.honest_label.value),
            "confidence": effect.get("confidence", 0.85),
            "explanation": effect.get("explanation", "simulated"),
            "evidence_snippets": effect.get("snippets", honest_snippets),
        }


class SimulatedSingleCallProvider:
    """Today's single-call classifier with the model swapped for the simulation.

    It sends what ``AnthropicProvider.classify`` sends (the live system prompt, the
    raw combined content, unfenced) and parses the answer with the live provider's
    own helpers, so label coercion behaves exactly as in production.
    """

    def __init__(self, client: MockModelClient, model: str = "simulated-single-call"):
        self.client, self.model = client, model

    def classify(self, fusion: FusionResult) -> ClassificationResult:
        start = time.time()
        request = ModelRequest(step="classify", prompt_version="live", system=LIVE_SYSTEM_PROMPT,
                               input=fusion.combined_content or fusion.transcript)
        raw = self.client.complete(self.model, request).output
        # The live provider reads the forced tool call's input; prose means no tool call.
        tool_input = raw if isinstance(raw, dict) else {}
        return ClassificationResult(
            label=_safe_label(tool_input.get("label")),
            confidence=float(tool_input.get("confidence", 0.5)),
            explanation=str(tool_input.get("explanation", "")),
            evidence_snippets=_safe_list(tool_input.get("evidence_snippets")),
            provider="simulated",
            model_used=self.model,
            latency_ms=int((time.time() - start) * 1000),
        )
