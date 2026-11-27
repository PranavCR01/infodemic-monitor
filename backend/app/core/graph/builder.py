from __future__ import annotations

from langgraph.graph import END, START, StateGraph

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
from app.core.graph.routing import (
    route_after_critic,
    route_after_stance,
    route_after_validation,
)
from app.core.graph.state import PipelineState


def build_graph(checkpointer=None):
    builder = StateGraph(PipelineState)

    builder.add_node("load_artifacts", load_artifacts)
    builder.add_node("transcribe_audio", transcribe_audio)
    builder.add_node("extract_ocr", extract_ocr)
    builder.add_node("fuse_modalities", fuse_modalities)
    builder.add_node("extract_claims", extract_claims)
    builder.add_node("analyze_stance", analyze_stance)
    builder.add_node("plan_retrieval", plan_retrieval)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("rerank_evidence", rerank_evidence)
    builder.add_node("verify_claims", verify_claims)
    builder.add_node("critique_verification", critique_verification)
    builder.add_node("judge_classification", judge_classification)
    builder.add_node("validate_result", validate_result)
    builder.add_node("route_for_review", route_for_review)
    builder.add_node("persist_result", persist_result)

    builder.add_edge(START, "load_artifacts")

    builder.add_edge("load_artifacts", "transcribe_audio")
    builder.add_edge("load_artifacts", "extract_ocr")

    builder.add_edge(
        ["transcribe_audio", "extract_ocr"],
        "fuse_modalities",
    )

    builder.add_edge("fuse_modalities", "extract_claims")
    builder.add_edge("extract_claims", "analyze_stance")

    builder.add_conditional_edges(
        "analyze_stance",
        route_after_stance,
    )

    builder.add_edge("plan_retrieval", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "rerank_evidence")
    builder.add_edge("rerank_evidence", "verify_claims")
    builder.add_edge("verify_claims", "critique_verification")

    builder.add_conditional_edges(
        "critique_verification",
        route_after_critic,
    )

    builder.add_edge("judge_classification", "validate_result")

    builder.add_conditional_edges(
        "validate_result",
        route_after_validation,
    )

    builder.add_edge("route_for_review", "persist_result")
    builder.add_edge("persist_result", END)

    return builder.compile(checkpointer=checkpointer)