import os
from uuid import uuid4

import pytest

from app.core.graph.checkpoint import postgres_checkpointer

from app.core.graph.builder import build_graph
from app.core.graph import builder as graph_builder

from app.core.graph.routing import (
    route_after_critic,
    route_after_stance,
    route_after_validation,
)
from app.core.graph.state import CriticResult, ExtractedClaim

from app.core.graph.nodes import (
    analyze_stance,
    critique_verification,
    extract_claims,
    extract_ocr,
    fuse_modalities,
    judge_classification,
    load_artifacts,
    persist_result,
    plan_retrieval,
    rerank_evidence,
    retrieve_evidence,
    route_for_review,
    transcribe_audio,
    validate_result,
    verify_claims,
)


def test_route_after_stance_goes_to_retrieval_for_verifiable_claim():
    state = {
        "claims": [
            ExtractedClaim(
                claim_id="claim-1",
                claim_text="sample claim",
                claim_category="health",
                source_segment_ids=["segment-1"],
                start_seconds=0.0,
                end_seconds=5.0,
                requires_verification=True,
            )
        ]
    }

    assert route_after_stance(state) == "plan_retrieval"


def test_route_after_stance_goes_to_judge_without_verifiable_claims():
    state = {
        "claims": [
            ExtractedClaim(
                claim_id="claim-1",
                claim_text="sample claim",
                claim_category="health",
                source_segment_ids=["segment-1"],
                start_seconds=0.0,
                end_seconds=5.0,
                requires_verification=False,
            )
        ]
    }

    assert route_after_stance(state) == "judge_classification"


def test_route_after_critic_approves_to_judge():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="APPROVE",
                issues=[],
                suggested_queries=[],
                requires_review=False,
            )
        },
        "retrieval_attempts": {"claim-1": 1},
    }

    assert route_after_critic(state) == "judge_classification"


def test_route_after_critic_retrieves_more_with_budget():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="RETRIEVE_MORE",
                issues=["evidence too weak"],
                suggested_queries=["new query"],
                requires_review=False,
            )
        },
        "retrieval_attempts": {"claim-1": 1},
    }

    assert route_after_critic(state) == "plan_retrieval"


def test_route_after_critic_revises_verification():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="REVISE_VERIFICATION",
                issues=["reasoning needs revision"],
                suggested_queries=[],
                requires_review=False,
            )
        },
        "retrieval_attempts": {"claim-1": 1},
    }

    assert route_after_critic(state) == "verify_claims"


def test_route_after_critic_escalates_to_review():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="ESCALATE",
                issues=["human review required"],
                suggested_queries=[],
                requires_review=True,
            )
        },
        "retrieval_attempts": {"claim-1": 1},
    }

    assert route_after_critic(state) == "route_for_review"


def test_route_after_validation_persists_when_valid():
    state = {
        "validation_errors": []
    }

    assert route_after_validation(state) == "persist_result"


def test_route_after_validation_reviews_when_invalid():
    state = {
        "validation_errors": ["missing final result"]
    }

    assert route_after_validation(state) == "route_for_review"


def test_graph_runs_end_to_end():
    graph = build_graph()

    initial_state = {
        "job_id": "test-job-1",
        "video_id": "test-video-1",
        "pipeline_version": "0.1.0",
        "media_uri": "file://sample.mp4",
        "transcript_segments": [],
        "ocr_segments": [],
        "fused_segments": [],
        "claims": [],
        "stance_results": {},
        "retrieval_queries": {},
        "retrieved_evidence": {},
        "verification_results": {},
        "critic_results": {},
        "retrieval_attempts": {},
        "validation_errors": [],
        "requires_human_review": False,
        "review_reasons": [],
        "errors": [],
    }
    result = graph.invoke(initial_state)

    assert result["final_result"].classification == "NO_MISINFO"
    assert len(result["claims"]) == 1
    assert len(result["retrieved_evidence"]) == 1
    assert result["validation_errors"] == []


def test_nodes_only_write_owned_fields():
    state = {
        "job_id": "test-job-1",
        "video_id": "test-video-1",
        "pipeline_version": "0.1.0",
        "media_uri": "file://sample.mp4",
        "transcript_segments": [],
        "ocr_segments": [],
        "fused_segments": [],
        "claims": [],
        "stance_results": {},
        "retrieval_queries": {},
        "retrieved_evidence": {},
        "verification_results": {},
        "critic_results": {},
        "retrieval_attempts": {},
        "validation_errors": [],
        "requires_human_review": False,
        "review_reasons": [],
        "errors": [],
    }

    expected_fields = {
        load_artifacts: set(),
        transcribe_audio: {"transcript_segments"},
        extract_ocr: {"ocr_segments"},
        fuse_modalities: {"fused_segments"},
        extract_claims: {"claims"},
        analyze_stance: {"stance_results"},
        plan_retrieval: {"retrieval_queries"},
        retrieve_evidence: {
            "retrieved_evidence",
            "retrieval_attempts",
        },
        rerank_evidence: set(),
        verify_claims: {"verification_results", "verification_revision_attempts"},
        critique_verification: {"critic_results"},
        judge_classification: {"final_result"},
        validate_result: {"validation_errors"},
        route_for_review: {
            "requires_human_review",
            "review_reasons",
        },
        persist_result: set(),
    }

    for node, allowed_fields in expected_fields.items():
        update = node(state)

        assert set(update.keys()) <= allowed_fields

def test_route_after_critic_reviews_when_budget_exhausted():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="RETRIEVE_MORE",
                issues=["insufficient evidence"],
                suggested_queries=["another query"],
                requires_review=False,
            )
        },
        "retrieval_attempts": {"claim-1": 3},
    }

    assert route_after_critic(state) == "route_for_review"


def test_route_after_critic_respects_review_flag():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="APPROVE",
                issues=[],
                suggested_queries=[],
                requires_review=True,
            )
        }
    }

    assert route_after_critic(state) == "route_for_review"


def test_route_after_critic_reviews_when_empty():
    state = {
        "critic_results": {}
    }

    assert route_after_critic(state) == "route_for_review"


def test_route_after_validation_respects_review_flag():
    state = {
        "validation_errors": [],
        "requires_human_review": True,
    }

    assert route_after_validation(state) == "route_for_review"


def test_retrieval_attempts_increment():
    state = {
        "retrieval_attempts": {}
    }

    first_update = retrieve_evidence(state)
    assert first_update["retrieval_attempts"]["claim-1"] == 1

    state.update(first_update)

    second_update = retrieve_evidence(state)
    assert second_update["retrieval_attempts"]["claim-1"] == 2

    state.update(second_update)

    third_update = retrieve_evidence(state)
    assert third_update["retrieval_attempts"]["claim-1"] == 3


def test_route_after_critic_reviews_when_revision_budget_exhausted():
    state = {
        "critic_results": {
            "claim-1": CriticResult(
                claim_id="claim-1",
                decision="REVISE_VERIFICATION",
                issues=["reasoning needs revision"],
                suggested_queries=[],
                requires_review=False,
            )
        },
        "verification_revision_attempts": {"claim-1": 1},
    }

    assert route_after_critic(state) == "route_for_review"


def test_verification_revision_attempts_increment():
    state = {
        "verification_revision_attempts": {},
        "critic_results": {},
    }

    first_update = verify_claims(state)

    assert first_update["verification_revision_attempts"].get(
        "claim-1", 0
    ) == 0

    state.update(first_update)

    state["critic_results"] = {
        "claim-1": CriticResult(
            claim_id="claim-1",
            decision="REVISE_VERIFICATION",
            issues=["reasoning needs revision"],
            suggested_queries=[],
            requires_review=False,
        )
    }

    second_update = verify_claims(state)

    assert second_update["verification_revision_attempts"]["claim-1"] == 1


def test_graph_stops_after_retrieval_budget_exhausted(monkeypatch):
    def always_request_retrieval(state):
        return {
            "critic_results": {
                "claim-1": CriticResult(
                    claim_id="claim-1",
                    decision="RETRIEVE_MORE",
                    issues=["insufficient evidence"],
                    suggested_queries=["another query"],
                    requires_review=False,
                )
            }
        }

    monkeypatch.setattr(
        graph_builder,
        "critique_verification",
        always_request_retrieval,
    )

    graph = graph_builder.build_graph()

    result = graph.invoke({
        "job_id": "test-retry-job",
        "video_id": "test-video-1",
        "pipeline_version": "0.1.0",
        "media_uri": "file://sample.mp4",
        "retrieval_attempts": {},
        "requires_human_review": False,
        "review_reasons": [],
    })

    assert result["retrieval_attempts"]["claim-1"] == 3
    assert result["requires_human_review"] is True


def test_graph_stops_after_verification_revision_exhausted(monkeypatch):
    def always_request_revision(state):
        return {
            "critic_results": {
                "claim-1": CriticResult(
                    claim_id="claim-1",
                    decision="REVISE_VERIFICATION",
                    issues=["reasoning needs revision"],
                    suggested_queries=[],
                    requires_review=False,
                )
            }
        }

    monkeypatch.setattr(
        graph_builder,
        "critique_verification",
        always_request_revision,
    )

    graph = graph_builder.build_graph()

    result = graph.invoke({
        "job_id": "test-revision-job",
        "video_id": "test-video-1",
        "pipeline_version": "0.1.0",
        "media_uri": "file://sample.mp4",
        "retrieval_attempts": {},
        "verification_revision_attempts": {},
        "requires_human_review": False,
        "review_reasons": [],
    })

    assert result["verification_revision_attempts"]["claim-1"] == 1
    assert result["requires_human_review"] is True
    assert result["retrieval_attempts"]["claim-1"] == 1


def test_postgres_checkpoint_resume():
    database_url = os.getenv("LANGGRAPH_TEST_DATABASE_URL")

    if not database_url:
        pytest.skip("PostgreSQL test database not configured")

    job_id = f"checkpoint-test-{uuid4()}"

    config = {
        "configurable": {
            "thread_id": job_id
        }
    }

    initial_state = {
        "job_id": job_id,
        "video_id": "test-video-1",
        "pipeline_version": "0.1.0",
        "media_uri": "file://sample.mp4",
        "retrieval_attempts": {},
        "verification_revision_attempts": {},
        "requires_human_review": False,
        "review_reasons": [],
    }

    with postgres_checkpointer(database_url) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)

        graph.invoke(
            initial_state,
            config=config,
            interrupt_before=["verify_claims"],
        )

        snapshot = graph.get_state(config)

        assert "verify_claims" in snapshot.next
        assert len(snapshot.values["retrieved_evidence"]) == 1
        assert "final_result" not in snapshot.values

    with postgres_checkpointer(database_url) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)

        result = graph.invoke(None, config=config)

        assert result["final_result"].classification == "NO_MISINFO"
        assert result["retrieval_attempts"]["claim-1"] == 1
        assert not graph.get_state(config).next