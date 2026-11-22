"""The guarded graph as a system under adversarial test.

``guarded_nodes`` are reference implementations of the LLM steps that go through
the guardrails exactly as real nodes must: prompts from ``untrusted`` builders,
calls through ``GuardedRouter``, answers parsed by ``outputs`` and checked against
the IDs the step was shown, retrieval through ``ToolGateway``. The other nodes are
the T02 stubs (fusion, judge rules, validation, review policy).

When the real nodes land (T03–T09), the harness should run them instead; until
then this shows what the guardrails contain on their own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.graph import routing as r
from app.core.graph.builder import compile_graph, run_config
from app.core.graph.nodes import NodeFn
from app.core.graph.routing import DEFAULT_BUDGETS, Budgets
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    FinalClassification,
    GraphClaim,
    NodeError,
    PipelineState,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.core.guardrails.config import GuardrailConfig, load_guardrails
from app.core.guardrails.guarded_router import GuardedRouter
from app.core.guardrails.injection import GUARDRAIL_ERROR_PREFIX, detect
from app.core.guardrails.limits import cap_claims
from app.core.guardrails.outputs import (
    CriticOutput,
    ExtractionOutput,
    OutputViolation,
    StanceOutput,
    VerificationOutput,
    check_segment_citations,
    check_verification,
    grounding_overlap,
)
from app.core.guardrails.tools import ToolGateway, ToolLimitError
from app.core.guardrails.untrusted import critic_prompt, extraction_prompt, stance_prompt, verification_prompt
from app.core.routing.config import RoutingConfig, load_routing
from app.core.routing.router import ModelRouter, RoutingError
from app.evaluation.adversarial.cases import AdversarialCase
from app.evaluation.adversarial.simulated import ObedientModel

MIN_GROUNDING = 0.5


def _gerr(node: str, kind: str, detail: str = "", claim_id: Optional[str] = None) -> NodeError:
    return NodeError(node=node, message=f"{GUARDRAIL_ERROR_PREFIX}{kind} {detail}".strip(), claim_id=claim_id)


def fixture_backend(case: AdversarialCase):
    """Recorded PubMed responses for a case: a search returns the records stored
    for the claim whose text is the query."""
    by_query = {c.text.strip().lower(): c.evidence for c in case.claims}

    def pubmed_search(query: str, max_results: int) -> list[dict]:
        records = by_query.get(query.strip().lower(), [])
        return [e.model_dump() for e in records[:max_results]]

    return {"pubmed_search": pubmed_search}


def guarded_nodes(
    case: AdversarialCase, router: GuardedRouter, gateway: ToolGateway,
    *, guardrails: Optional[GuardrailConfig] = None, budgets: Budgets = DEFAULT_BUDGETS,
) -> dict[str, NodeFn]:
    g = guardrails or load_guardrails()
    block_chars = g.input.max_segment_chars

    def transcribe_audio(state: PipelineState) -> dict:
        return {"transcript_segments": case.transcript_segments()}

    def extract_ocr(state: PipelineState) -> dict:
        return {"ocr_segments": case.ocr_segments()}

    def _segment_texts(state: PipelineState) -> dict[str, str]:
        texts = {t.segment_id: t.text for t in state.get("transcript_segments", [])}
        texts.update({o.segment_id: o.text for o in state.get("ocr_segments", [])})
        for f in state.get("fused_segments", []):
            texts[f.segment_id] = " ".join([f.spoken, *f.on_screen])
        return texts

    def extract_claims(state: PipelineState) -> dict:
        node = r.EXTRACT_CLAIMS
        segments = state.get("fused_segments", [])
        if not segments:
            return {"claims": []}
        prompt = extraction_prompt(segments, max_chars=block_chars)
        try:
            out: ExtractionOutput = router.call(prompt).output  # type: ignore[assignment]
        except (OutputViolation, RoutingError) as exc:
            return {"claims": [], "errors": [_gerr(node, "output_rejected", str(exc))]}
        texts = _segment_texts(state)
        claims, errors = [], []
        for item in out.claims:
            valid, _fabricated = check_segment_citations(item.source_segment_ids, prompt.citable_ids)
            source = " ".join(texts.get(s, "") for s in valid)
            if not valid or grounding_overlap(item.claim_text, source) < MIN_GROUNDING:
                errors.append(_gerr(node, "claim_ungrounded", item.claim_text[:80]))
                continue
            starts = [s.start for s in segments if s.segment_id in valid or set(s.sources) & set(valid)]
            ends = [s.end for s in segments if s.segment_id in valid or set(s.sources) & set(valid)]
            claims.append(GraphClaim(
                claim_id=f"c{len(claims) + 1}", claim_text=item.claim_text,
                claim_category=item.claim_category, source_segment_ids=valid,
                start_seconds=min(starts, default=0.0), end_seconds=max(ends, default=0.0),
                requires_verification=item.requires_verification,
            ))
        claims, dropped = cap_claims(claims, g.input)
        if dropped:
            errors.append(_gerr(node, "claims_capped", f"{dropped} claims over the limit"))
        return {"claims": claims, "errors": errors}

    def analyze_stance(state: PipelineState) -> dict:
        node = r.ANALYZE_STANCE
        segments = state.get("fused_segments", [])
        texts = _segment_texts(state)
        results, errors = {}, []
        for c in state.get("claims", []):
            prompt = stance_prompt(c, segments, max_chars=block_chars)
            fallback = StanceResult(claim_id=c.claim_id, stance=Stance.UNCLEAR, stance_segment_ids=[])
            try:
                out: StanceOutput = router.call(prompt).output  # type: ignore[assignment]
            except (OutputViolation, RoutingError) as exc:
                results[c.claim_id] = fallback
                errors.append(_gerr(node, "output_rejected", str(exc), c.claim_id))
                continue
            valid, _ = check_segment_citations(out.stance_segment_ids, prompt.citable_ids)
            if out.stance != Stance.UNCLEAR and not valid:
                results[c.claim_id] = fallback
                errors.append(_gerr(node, "stance_uncited", claim_id=c.claim_id))
                continue
            # A stance can't rest on words that read as instructions to us.
            if any(detect(texts.get(s, "")) for s in valid):
                results[c.claim_id] = fallback
                errors.append(_gerr(node, "stance_cites_injection", claim_id=c.claim_id))
                continue
            results[c.claim_id] = StanceResult(
                claim_id=c.claim_id, stance=out.stance, stance_segment_ids=valid, rationale=out.rationale,
            )
        return {"stance_results": results, "errors": errors}

    def retrieve_evidence(state: PipelineState) -> dict:
        node = r.RETRIEVE_EVIDENCE
        evidence = dict(state.get("retrieved_evidence", {}))
        attempts = dict(state.get("retrieval_attempts", {}))
        errors = []
        for cid in r.claims_to_retrieve(state, budgets):
            attempts[cid] = attempts.get(cid, 0) + 1
            query = (state.get("retrieval_queries", {}).get(cid) or [""])[-1]
            try:
                rows = gateway.call("pubmed_search", query=query, max_results=10)
            except ToolLimitError as exc:
                errors.append(_gerr(node, f"tool_{exc.kind}", claim_id=cid))
                rows = []
            known = {e.evidence_id for e in evidence.get(cid, [])}
            new = [
                EvidenceRecord(
                    evidence_id=f"pmid:{row['pmid']}", source="pubmed", pmid=row["pmid"],
                    title=row["title"], abstract=row.get("abstract", ""),
                    publication_year=row.get("year"), query=query,
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/",
                )
                for row in rows if f"pmid:{row['pmid']}" not in known
            ]
            evidence[cid] = [*evidence.get(cid, []), *new]
        return {"retrieved_evidence": evidence, "retrieval_attempts": attempts, "errors": errors}

    def verify_claims(state: PipelineState) -> dict:
        node = r.VERIFY_CLAIMS
        claims = {c.claim_id: c for c in state.get("claims", [])}
        results = dict(state.get("verification_results", {}))
        revisions = dict(state.get("verification_revisions", {}))
        errors = []
        for cid in r.claims_to_verify(state, budgets):
            critic = state.get("critic_results", {}).get(cid)
            if critic and critic.decision == CriticDecision.REVISE_VERIFICATION:
                revisions[cid] = revisions.get(cid, 0) + 1
            evidence = state.get("reranked_evidence", {}).get(cid, [])
            prompt = verification_prompt(claims[cid], evidence, max_chars=block_chars)
            try:
                out: VerificationOutput = router.call(prompt).output  # type: ignore[assignment]
            except (OutputViolation, RoutingError) as exc:
                results[cid] = VerificationResult(
                    claim_id=cid, verdict=Verdict.INSUFFICIENT_EVIDENCE,
                    limitations=["verifier answer rejected by guardrails"],
                )
                errors.append(_gerr(node, "output_rejected", str(exc), cid))
                continue
            out, fabricated = check_verification(out, prompt.citable_ids)
            if fabricated:
                errors.append(_gerr(node, "fabricated_citation", ",".join(fabricated), cid))
            results[cid] = VerificationResult(
                claim_id=cid, verdict=out.verdict,
                supporting_evidence_ids=out.supporting_evidence_ids,
                contradicting_evidence_ids=out.contradicting_evidence_ids,
                explanation=out.explanation, limitations=out.limitations,
            )
        return {"verification_results": results, "verification_revisions": revisions, "errors": errors}

    def critique_verification(state: PipelineState) -> dict:
        node = r.CRITIQUE_VERIFICATION
        claims = {c.claim_id: c for c in state.get("claims", [])}
        results = dict(state.get("critic_results", {}))
        errors = []
        for cid in r.claims_to_critique(state):
            evidence = state.get("reranked_evidence", {}).get(cid, [])
            prompt = critic_prompt(claims[cid], state["verification_results"][cid], evidence, max_chars=block_chars)
            try:
                out: CriticOutput = router.call(prompt).output  # type: ignore[assignment]
            except (OutputViolation, RoutingError) as exc:
                results[cid] = CriticResult(claim_id=cid, decision=CriticDecision.ESCALATE, requires_review=True)
                errors.append(_gerr(node, "output_rejected", str(exc), cid))
                continue
            results[cid] = CriticResult(
                claim_id=cid, decision=out.decision, issues=out.issues,
                suggested_queries=out.suggested_queries, requires_review=out.requires_review,
            )
        return {"critic_results": results, "errors": errors}

    return {
        r.TRANSCRIBE_AUDIO: transcribe_audio,
        r.EXTRACT_OCR: extract_ocr,
        r.EXTRACT_CLAIMS: extract_claims,
        r.ANALYZE_STANCE: analyze_stance,
        r.RETRIEVE_EVIDENCE: retrieve_evidence,
        r.VERIFY_CLAIMS: verify_claims,
        r.CRITIQUE_VERIFICATION: critique_verification,
    }


@dataclass
class GraphOutcome:
    label: Optional[str]
    final: Optional[FinalClassification]
    review_required: bool
    review_reasons: list[str]
    retrieved_ids: set[str]
    claim_ids: set[str]
    cited_ids: set[str]
    validation_errors: list[str]
    triggered_steps: list[str] = field(default_factory=list)
    error: Optional[str] = None


def run_guarded_graph(
    case: AdversarialCase, *, routing: Optional[RoutingConfig] = None,
    guardrails: Optional[GuardrailConfig] = None,
) -> GraphOutcome:
    g = guardrails or load_guardrails()
    model = ObedientModel(case)
    client = model.client()
    routing = routing or load_routing()
    providers = {s.provider for s in routing.steps.values()}
    providers |= {f.provider for f in (routing.fallback.use, *(s.fallback for s in routing.steps.values())) if f}
    router = GuardedRouter(ModelRouter(routing, {p: client for p in providers}))
    gateway = ToolGateway(fixture_backend(case), g.tools)
    try:
        graph = compile_graph(guarded_nodes(case, router, gateway, guardrails=g))
        job = f"adv-{case.id}"
        state = graph.invoke(
            initial_state(job_id=job, video_id=case.id, media_uri=f"memory://{case.id}", pipeline_version="adversarial"),
            run_config(job),
        )
    except Exception as exc:  # a crash is an outcome too: output outside the schema
        return GraphOutcome(None, None, False, [], set(), set(), set(), [], model.triggered_steps,
                            error=f"{type(exc).__name__}: {exc}")
    finally:
        gateway.close()
    final = state.get("final_result")
    retrieved = {e.evidence_id for recs in state.get("retrieved_evidence", {}).values() for e in recs}
    cited = set(final.evidence_ids) if final else set()
    for v in state.get("verification_results", {}).values():
        cited.update(v.supporting_evidence_ids, v.contradicting_evidence_ids)
    return GraphOutcome(
        label=final.classification.value if final else None,
        final=final,
        review_required=bool(state.get("requires_human_review")),
        review_reasons=list(state.get("review_reasons", [])),
        retrieved_ids=retrieved,
        claim_ids={c.claim_id for c in state.get("claims", [])},
        cited_ids=cited,
        validation_errors=list(state.get("validation_errors", [])),
        triggered_steps=model.triggered_steps,
    )
