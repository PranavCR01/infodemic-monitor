from __future__ import annotations

from app.core.graph.state import (
    ExtractedClaim,
    FusedSegment,
    OCRSegment,
    PipelineState,
    StanceResult,
    TranscriptSegment,
    EvidenceRecord,
    VerificationResult,
    CriticResult,
    FinalClassification,
)


def load_artifacts(state: PipelineState) -> dict:
    return {}


def transcribe_audio(state: PipelineState) -> dict:
    return {
        "transcript_segments": [
            TranscriptSegment(
                segment_id="transcript-1",
                start_seconds=0.0,
                end_seconds=5.0,
                text="Sample transcript segment.",
            )
        ]
    }


def extract_ocr(state: PipelineState) -> dict:
    return {
        "ocr_segments": [
            OCRSegment(
                segment_id="ocr-1",
                timestamp_seconds=1.0,
                text="Sample OCR text.",
            )
        ]
    }


def fuse_modalities(state: PipelineState) -> dict:
    return {
        "fused_segments": [
            FusedSegment(
                segment_id="fused-1",
                text="Sample fused content.",
                source_segment_ids=["transcript-1", "ocr-1"],
            )
        ]
    }


def extract_claims(state: PipelineState) -> dict:
    return {
        "claims": [
            ExtractedClaim(
                claim_id="claim-1",
                claim_text="Sample health claim.",
                claim_category="health",
                source_segment_ids=["fused-1"],
                start_seconds=0.0,
                end_seconds=5.0,
                requires_verification=True,
            )
        ]
    }


def analyze_stance(state: PipelineState) -> dict:
    return {
        "stance_results": {
            "claim-1": StanceResult(
                claim_id="claim-1",
                stance="ENDORSES",
                source_segment_ids=["fused-1"],
            )
        }
    }


def plan_retrieval(state: PipelineState) -> dict:
    return {
        "retrieval_queries": {
            "claim-1": ["sample health claim"]
        }
    }


def retrieve_evidence(state: PipelineState) -> dict:
    retrieval_attempts = state.get("retrieval_attempts", {}).copy()

    retrieval_attempts["claim-1"] = (
        retrieval_attempts.get("claim-1", 0) + 1
    )

    return {
        "retrieved_evidence": {
            "claim-1": [
                EvidenceRecord(
                    evidence_id="evidence-1",
                    pmid=None,
                    doi=None,
                    title="Sample evidence article",
                    abstract="Sample abstract.",
                    publication_year=2024,
                    publication_type=["Journal Article"],
                    source_url="https://example.com/evidence-1",
                    retrieved_at="2026-11-11T00:00:00Z",
                    relevance_score=1.0,
                )
            ]
        },
        "retrieval_attempts": retrieval_attempts,
    }


def rerank_evidence(state: PipelineState) -> dict:
    return {}


def verify_claims(state: PipelineState) -> dict:
    revision_attempts = state.get(
        "verification_revision_attempts", {}
    ).copy()

    previous_critic = state.get("critic_results", {}).get("claim-1")

    if (
        previous_critic
        and previous_critic.decision == "REVISE_VERIFICATION"
    ):
        revision_attempts["claim-1"] = (
            revision_attempts.get("claim-1", 0) + 1
        )

    return {
        "verification_results": {
            "claim-1": VerificationResult(
                claim_id="claim-1",
                verdict="SUPPORTED",
                supporting_evidence_ids=["evidence-1"],
                contradicting_evidence_ids=[],
                explanation="Stub verification result.",
                limitations=[],
            )
        },
        "verification_revision_attempts": revision_attempts,
    }


def critique_verification(state: PipelineState) -> dict:
    return {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="APPROVE",
                issues=[],
                suggested_queries=[],
                requires_review=False,
            )
        }
    }


def judge_classification(state: PipelineState) -> dict:
    return {
        "final_result": FinalClassification(
            video_id=state["video_id"],
            classification="NO_MISINFO",
            claim_ids=["claim-1"],
            evidence_ids=["evidence-1"],
            explanation="Stub final classification.",
            limitations=[],
            requires_human_review=False,
            review_reasons=[],
        )
    }


def validate_result(state: PipelineState) -> dict:
    return {
        "validation_errors": [],
    }


def route_for_review(state: PipelineState) -> dict:
    return {
        "requires_human_review": True,
        "review_reasons": ["Stub human review route."],
    }


def persist_result(state: PipelineState) -> dict:
    return {}