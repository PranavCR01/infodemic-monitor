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
    r.RETRIEVE_EVIDENCE: frozenset({"retrieved_evidence", "retrieval_attempts", "search_trail"}),
    r.RERANK_EVIDENCE: frozenset({"reranked_evidence", "library_evidence", "found_study_evidence",
                                  "find_study_trail"}),
    r.VERIFY_CLAIMS: frozenset({"verification_results", "verification_revisions"}),
    r.CRITIQUE_VERIFICATION: frozenset({"critic_results"}),
    r.JUDGE_CLASSIFICATION: frozenset({"final_result"}),
    r.VALIDATE_RESULT: frozenset({"validation_errors", "validation_attempts"}),
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


def judge_by_rules(state: PipelineState, budgets: Budgets = DEFAULT_BUDGETS) -> FinalClassification:
    """The §9 judge policy (T08's deterministic rules, template explanation, no model).
    Claims whose critic objection outlived the loop budget abstain (T07,
    ``routing.verdicts_for_judge``).

    Kept for callers written against the T02 stub; the real node is
    ``judge.make_judge_classification``."""
    from app.core.graph.judge import judge  # local import: judge imports this package's state

    return judge(state, budgets=budgets)[0]


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

        return make_judge_classification(budgets=budgets)(state)

    def validate_result(state: PipelineState) -> dict:
        # T09: the real §10 validator is deterministic, so the default graph uses it.
        from app.core.graph.validation import make_validate_result

        return make_validate_result(budgets=budgets)(state)

    def route_for_review(state: PipelineState) -> dict:
        # T09: the real §11 review rule (judge flags and guardrail reasons included).
        from app.core.graph.review_policy import make_route_for_review

        return make_route_for_review(budgets=budgets)(state)

    def human_review(state: PipelineState) -> dict:
        # T09: the run does not pause here. The case is marked REVIEW_REQUIRED and
        # persisted with its reasons (persist_result, T11, via
        # app.services.review_service); the reviewer acts on the stored case later.
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
