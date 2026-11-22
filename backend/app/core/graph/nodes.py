"""Node ownership map and deterministic stub nodes.

Each later task replaces one stub with the real node (T03 retrieval, T04 stance, ...).
A real node must keep the same signature, ``(state) -> dict``, and write only the
fields listed for it in ``NODE_OUTPUTS``; the builder rejects anything else.

The stubs make no model or network calls. They turn a small sample video into
plausible records so the whole graph can run end to end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.core.graph import routing as r
from app.core.graph.routing import Budgets, DEFAULT_BUDGETS
from app.core.graph.state import (
    ArtifactRef,
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    FinalClassification,
    FusedSegment,
    GraphClaim,
    OcrSegment,
    PipelineState,
    ReviewStatus,
    Stance,
    StanceResult,
    TranscriptSegment,
    Verdict,
    VerificationResult,
)
from app.core.guardrails.injection import guardrail_review_reasons
from app.core.schemas.pipeline import MisinfoLabel

NodeFn = Callable[[PipelineState], dict]

# Which state fields each node may write (§5.1 ownership). ``errors`` is shared and
# append-only, so any node may also add to it.
NODE_OUTPUTS: dict[str, frozenset[str]] = {
    r.LOAD_ARTIFACTS: frozenset({"artifacts"}),
    r.TRANSCRIBE_AUDIO: frozenset({"transcript_segments"}),
    r.EXTRACT_OCR: frozenset({"ocr_segments"}),
    r.FUSE_MODALITIES: frozenset({"fused_segments"}),
    r.EXTRACT_CLAIMS: frozenset({"claims"}),
    r.ANALYZE_STANCE: frozenset({"stance_results"}),
    r.PLAN_RETRIEVAL: frozenset({"retrieval_queries"}),
    r.RETRIEVE_EVIDENCE: frozenset({"retrieved_evidence", "retrieval_attempts"}),
    r.RERANK_EVIDENCE: frozenset({"reranked_evidence"}),
    r.VERIFY_CLAIMS: frozenset({"verification_results", "verification_revisions"}),
    r.CRITIQUE_VERIFICATION: frozenset({"critic_results"}),
    r.JUDGE_CLASSIFICATION: frozenset({"final_result"}),
    r.VALIDATE_RESULT: frozenset({"validation_errors"}),
    r.ROUTE_FOR_REVIEW: frozenset({"requires_human_review", "review_reasons"}),
    r.HUMAN_REVIEW: frozenset({"review_status"}),
    r.PERSIST_RESULT: frozenset({"persisted_result_ref"}),
}

MAX_EVIDENCE_PER_CLAIM = 10  # §6 "Cap"


@dataclass(frozen=True)
class SampleVideo:
    """Canned extraction output the stubs return (the §2–§3 example)."""

    transcript: list[TranscriptSegment] = field(
        default_factory=lambda: [
            TranscriptSegment(
                segment_id="t1", start=3.5, end=8.0,
                text="Drinking hot water every morning cures the flu.",
            ),
            TranscriptSegment(
                segment_id="t2", start=8.5, end=12.0,
                text="Some people say garlic stops colds. That's a myth.",
            ),
        ]
    )
    ocr: list[OcrSegment] = field(
        default_factory=lambda: [
            OcrSegment(segment_id="o1", start=4.0, end=7.0, text="HOT WATER = NO FLU", confidence=0.93),
        ]
    )


# ------------------------------------------------------------- stub helpers


def fuse_by_overlap(
    transcript: list[TranscriptSegment], ocr: list[OcrSegment]
) -> list[FusedSegment]:
    """Minimal §3 fusion: attach each caption to the speech it overlaps most; keep
    orphan captions as their own segments."""
    attached: dict[str, list[OcrSegment]] = {t.segment_id: [] for t in transcript}
    orphans: list[OcrSegment] = []
    for o in ocr:
        best, best_overlap = None, 0.0
        for t in transcript:
            overlap = min(t.end, o.end) - max(t.start, o.start)
            if overlap > best_overlap:
                best, best_overlap = t.segment_id, overlap
        if best is None:
            orphans.append(o)
        else:
            attached[best].append(o)
    fused = [
        FusedSegment(
            segment_id=f"f{i}", start=t.start, end=t.end, spoken=t.text,
            on_screen=[o.text for o in attached[t.segment_id]],
            sources=[t.segment_id, *[o.segment_id for o in attached[t.segment_id]]],
        )
        for i, t in enumerate(transcript, start=1)
    ]
    for o in orphans:
        fused.append(
            FusedSegment(
                segment_id=f"f{len(fused) + 1}", start=o.start, end=o.end,
                on_screen=[o.text], sources=[o.segment_id],
            )
        )
    return sorted(fused, key=lambda f: f.start)


def judge_by_rules(state: PipelineState) -> FinalClassification:
    """The §9 judge policy (T08's deterministic rules, template explanation, no model).

    Kept for callers written against the T02 stub; the real node is
    ``judge.make_judge_classification``."""
    from app.core.graph.judge import judge  # local import: judge imports this package's state

    return judge(state)[0]


# -------------------------------------------------------------------- stubs


def make_stub_nodes(
    budgets: Budgets = DEFAULT_BUDGETS, sample: SampleVideo | None = None
) -> dict[str, NodeFn]:
    """Deterministic stand-ins for every node in the §4 flow."""
    sample = sample or SampleVideo()

    def load_artifacts(state: PipelineState) -> dict:
        return {"artifacts": [ArtifactRef(kind="video", uri=state["media_uri"])]}

    def transcribe_audio(state: PipelineState) -> dict:
        return {"transcript_segments": list(sample.transcript)}

    def extract_ocr(state: PipelineState) -> dict:
        return {"ocr_segments": [o for o in sample.ocr if o.confidence >= 0.5]}

    def fuse_modalities(state: PipelineState) -> dict:
        return {
            "fused_segments": fuse_by_overlap(
                state.get("transcript_segments", []), state.get("ocr_segments", [])
            )
        }

    def extract_claims(state: PipelineState) -> dict:
        claims = [
            GraphClaim(
                claim_id=f"c{i}",
                claim_text=f.spoken or f.on_screen[0],
                claim_category="treatment_efficacy",
                source_segment_ids=list(f.sources),
                start_seconds=f.start,
                end_seconds=f.end,
            )
            for i, f in enumerate(state.get("fused_segments", []), start=1)
        ]
        return {"claims": claims}

    def analyze_stance(state: PipelineState) -> dict:
        out = {}
        for c in state.get("claims", []):
            refutes = "myth" in c.claim_text.lower()
            out[c.claim_id] = StanceResult(
                claim_id=c.claim_id,
                stance=Stance.REFUTES if refutes else Stance.ENDORSES,
                stance_segment_ids=list(c.source_segment_ids),
            )
        return {"stance_results": out}

    def plan_retrieval(state: PipelineState) -> dict:
        queries = dict(state.get("retrieval_queries", {}))
        claims = {c.claim_id: c for c in state.get("claims", [])}
        for cid in r.claims_to_retrieve(state, budgets):
            critic = state.get("critic_results", {}).get(cid)
            new = list(critic.suggested_queries) if critic and critic.suggested_queries else [claims[cid].claim_text]
            queries[cid] = [*queries.get(cid, []), *new]
        return {"retrieval_queries": queries}

    def retrieve_evidence(state: PipelineState) -> dict:
        evidence = dict(state.get("retrieved_evidence", {}))
        attempts = dict(state.get("retrieval_attempts", {}))
        for cid in r.claims_to_retrieve(state, budgets):
            n = attempts.get(cid, 0) + 1
            query = state.get("retrieval_queries", {}).get(cid, [""])[-1]
            record = EvidenceRecord(
                evidence_id=f"ev_stub_{cid}_{n}", source="pubmed", pmid=f"0000{n}",
                title=f"Stub paper {n} for {cid}", abstract="Stub abstract.",
                publication_type=["Randomized Controlled Trial"], query=query,
                source_url=f"https://pubmed.ncbi.nlm.nih.gov/0000{n}/",
            )
            evidence[cid] = [*evidence.get(cid, []), record]
            attempts[cid] = n
        return {"retrieved_evidence": evidence, "retrieval_attempts": attempts}

    def rerank_evidence(state: PipelineState) -> dict:
        reranked = {
            cid: sorted(records, key=lambda e: -(e.relevance_score or 0.0))[:MAX_EVIDENCE_PER_CLAIM]
            for cid, records in state.get("retrieved_evidence", {}).items()
        }
        return {"reranked_evidence": reranked}

    def verify_claims(state: PipelineState) -> dict:
        results = dict(state.get("verification_results", {}))
        revisions = dict(state.get("verification_revisions", {}))
        for cid in r.claims_to_verify(state, budgets):
            critic = state.get("critic_results", {}).get(cid)
            if critic and critic.decision == CriticDecision.REVISE_VERIFICATION:
                revisions[cid] = revisions.get(cid, 0) + 1
            ids = [e.evidence_id for e in state.get("reranked_evidence", {}).get(cid, [])]
            results[cid] = VerificationResult(
                claim_id=cid,
                verdict=Verdict.CONTRADICTED if ids else Verdict.INSUFFICIENT_EVIDENCE,
                contradicting_evidence_ids=ids,
                explanation="stub verdict",
            )
        return {"verification_results": results, "verification_revisions": revisions}

    def critique_verification(state: PipelineState) -> dict:
        results = dict(state.get("critic_results", {}))
        for cid in r.claims_to_critique(state):
            results[cid] = CriticResult(claim_id=cid, decision=CriticDecision.APPROVE)
        return {"critic_results": results}

    def judge_classification(state: PipelineState) -> dict:
        # T08: the real judge is deterministic, so the default graph uses it (template
        # explanation, no model). Pass make_judge_classification(router) for the LLM text.
        from app.core.graph.judge import make_judge_classification

        return make_judge_classification()(state)

    def validate_result(state: PipelineState) -> dict:
        errors = []
        final = state.get("final_result")
        if final is None:
            return {"validation_errors": ["final_result missing"]}
        claim_ids = {c.claim_id for c in state.get("claims", [])}
        retrieved = {
            e.evidence_id for recs in state.get("retrieved_evidence", {}).values() for e in recs
        }
        errors += [f"unknown claim_id {c}" for c in final.claim_ids if c not in claim_ids]
        errors += [f"evidence {e} was not retrieved" for e in final.evidence_ids if e not in retrieved]
        return {"validation_errors": errors}

    def route_for_review(state: PipelineState) -> dict:
        reasons: list[str] = []
        final = state.get("final_result")
        deciding = set(final.claim_ids) if final else set()
        verdicts = state.get("verification_results", {})
        stances = state.get("stance_results", {})
        if state.get("validation_errors"):
            reasons.append("validation_failed")
        for cid, c in state.get("critic_results", {}).items():
            if c.decision == CriticDecision.ESCALATE or c.requires_review:
                reasons.append(f"critic_escalated:{cid}")
        for cid in r.exhausted_claim_ids(state, budgets):
            reasons.append(f"budget_exhausted:{cid}")
        for cid in deciding:
            v = verdicts.get(cid)
            if v and v.verdict in (Verdict.INSUFFICIENT_EVIDENCE, Verdict.MIXED):
                reasons.append(f"weak_evidence:{cid}")
            s = stances.get(cid)
            if s and s.stance == Stance.UNCLEAR:
                reasons.append(f"unclear_stance:{cid}")
        # §9: patterns the judge's rules can't settle (mixed video, unclear stance on a
        # false claim, ...) go to a person. T09: keep this when replacing the stub.
        if final:
            reasons += [f"judge:{f}" for f in final.review_flags if f"judge:{f}" not in reasons]
        # §15: suspected injections and guardrail rejections always go to review.
        # T09: keep this call when replacing the stub.
        reasons += [x for x in guardrail_review_reasons(state) if x not in reasons]
        return {"requires_human_review": bool(reasons), "review_reasons": reasons}

    def human_review(state: PipelineState) -> dict:
        # The real step pauses the run for a reviewer (T09); the stub only marks it.
        return {"review_status": ReviewStatus.REVIEW_REQUIRED}

    def persist_result(state: PipelineState) -> dict:
        # Stub: the real step writes to the database (T11). Only the reference is kept.
        return {"persisted_result_ref": f"artifacts/{state['job_id']}/result.json"}

    nodes = {
        r.LOAD_ARTIFACTS: load_artifacts,
        r.TRANSCRIBE_AUDIO: transcribe_audio,
        r.EXTRACT_OCR: extract_ocr,
        r.FUSE_MODALITIES: fuse_modalities,
        r.EXTRACT_CLAIMS: extract_claims,
        r.ANALYZE_STANCE: analyze_stance,
        r.PLAN_RETRIEVAL: plan_retrieval,
        r.RETRIEVE_EVIDENCE: retrieve_evidence,
        r.RERANK_EVIDENCE: rerank_evidence,
        r.VERIFY_CLAIMS: verify_claims,
        r.CRITIQUE_VERIFICATION: critique_verification,
        r.JUDGE_CLASSIFICATION: judge_classification,
        r.VALIDATE_RESULT: validate_result,
        r.ROUTE_FOR_REVIEW: route_for_review,
        r.HUMAN_REVIEW: human_review,
        r.PERSIST_RESULT: persist_result,
    }
    assert set(nodes) == set(NODE_OUTPUTS)
    return nodes
