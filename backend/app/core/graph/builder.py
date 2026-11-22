"""Builds and compiles the pipeline graph (§4 flow).

    load → (transcribe ∥ ocr) → fuse → claims → stance ─┬─ no verifiable claims → judge
                                                        └─ plan → retrieve → rerank → verify → critic
    retrieve ─┬─ nothing found, budget left → plan (broader terms, §6)
              └─ otherwise                  → rerank
    critic ─┬─ RETRIEVE_MORE (budget left)        → plan
            ├─ REVISE_VERIFICATION (budget left)  → verify
            └─ otherwise (approve / escalate / exhausted) → judge
    judge → validate → review policy ─┬─ review required → human_review → persist
                                      └─ pass → persist → END
"""
from __future__ import annotations

from typing import Mapping

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.core.graph import routing as r
from app.core.graph.nodes import NODE_OUTPUTS, NodeFn, make_stub_nodes
from app.core.graph.routing import Budgets, DEFAULT_BUDGETS
from app.core.graph.state import SHARED_FIELDS, PipelineState


class OwnershipError(RuntimeError):
    """A node tried to write a state field it doesn't own."""


def _guard(name: str, fn: NodeFn) -> NodeFn:
    allowed = NODE_OUTPUTS[name] | SHARED_FIELDS

    def guarded(state: PipelineState) -> dict:
        update = fn(state) or {}
        foreign = set(update) - allowed
        if foreign:
            raise OwnershipError(f"node {name!r} wrote fields it doesn't own: {sorted(foreign)}")
        return update

    guarded.__name__ = name
    return guarded


def build_graph(
    nodes: Mapping[str, NodeFn] | None = None,
    *,
    budgets: Budgets = DEFAULT_BUDGETS,
) -> StateGraph:
    """Return the uncompiled graph. ``nodes`` overrides stubs by node name."""
    impl = make_stub_nodes(budgets)
    if nodes:
        unknown = set(nodes) - set(impl)
        if unknown:
            raise KeyError(f"unknown node names: {sorted(unknown)}")
        impl.update(nodes)

    g = StateGraph(PipelineState)
    for name, fn in impl.items():
        g.add_node(name, _guard(name, fn))

    g.add_edge(START, r.LOAD_ARTIFACTS)
    g.add_edge(r.LOAD_ARTIFACTS, r.TRANSCRIBE_AUDIO)
    g.add_edge(r.LOAD_ARTIFACTS, r.EXTRACT_OCR)
    g.add_edge([r.TRANSCRIBE_AUDIO, r.EXTRACT_OCR], r.FUSE_MODALITIES)
    g.add_edge(r.FUSE_MODALITIES, r.EXTRACT_CLAIMS)
    g.add_edge(r.EXTRACT_CLAIMS, r.ANALYZE_STANCE)
    g.add_conditional_edges(
        r.ANALYZE_STANCE, r.route_after_stance, [r.PLAN_RETRIEVAL, r.JUDGE_CLASSIFICATION]
    )
    g.add_edge(r.PLAN_RETRIEVAL, r.RETRIEVE_EVIDENCE)
    g.add_conditional_edges(
        r.RETRIEVE_EVIDENCE,
        r.make_route_after_retrieval(budgets),
        [r.PLAN_RETRIEVAL, r.RERANK_EVIDENCE],
    )
    g.add_edge(r.RERANK_EVIDENCE, r.VERIFY_CLAIMS)
    g.add_edge(r.VERIFY_CLAIMS, r.CRITIQUE_VERIFICATION)
    g.add_conditional_edges(
        r.CRITIQUE_VERIFICATION,
        r.make_route_after_critic(budgets),
        [r.PLAN_RETRIEVAL, r.VERIFY_CLAIMS, r.JUDGE_CLASSIFICATION],
    )
    g.add_edge(r.JUDGE_CLASSIFICATION, r.VALIDATE_RESULT)
    g.add_edge(r.VALIDATE_RESULT, r.ROUTE_FOR_REVIEW)
    g.add_conditional_edges(
        r.ROUTE_FOR_REVIEW, r.route_after_policy, [r.HUMAN_REVIEW, r.PERSIST_RESULT]
    )
    g.add_edge(r.HUMAN_REVIEW, r.PERSIST_RESULT)
    g.add_edge(r.PERSIST_RESULT, END)
    return g


def compile_graph(
    nodes: Mapping[str, NodeFn] | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    budgets: Budgets = DEFAULT_BUDGETS,
):
    return build_graph(nodes, budgets=budgets).compile(checkpointer=checkpointer)


def recursion_limit(budgets: Budgets = DEFAULT_BUDGETS, max_claims: int = 50) -> int:
    """An upper bound on super-steps for one run.

    The straight path is 14 super-steps. Every pass back from the critic uses up budget
    of at least one claim: a retrieval round (5 steps: plan, retrieve, rerank, verify,
    critic), a broadening round after an empty search (2 steps: plan, retrieve) or a
    revision (2 steps: verify, critic). So the loops are bounded by
    ``max_claims`` times each claim's budget. The budgets, not this number, are what
    stop loops; this only keeps LangGraph's safety limit above the real bound.
    """
    per_claim = 5 * (budgets.max_retrieval_attempts - 1) + 2 * budgets.max_verification_revisions
    return 14 + max_claims * per_claim + 10


def run_config(job_id: str, budgets: Budgets = DEFAULT_BUDGETS) -> dict:
    """Config for one run. ``thread_id = job_id`` so a retried job resumes its own run."""
    return {"configurable": {"thread_id": job_id}, "recursion_limit": recursion_limit(budgets)}
