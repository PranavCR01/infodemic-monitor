"""Tests for the LangGraph skeleton (T02, issue #29). No network, no models, no database.

The Postgres variant of the resume test runs only when LANGGRAPH_TEST_PG_DSN is set.
"""
from __future__ import annotations

import os
import subprocess
import sys
import typing
import uuid
import warnings
from collections import Counter

import pytest
from pydantic import BaseModel, ValidationError

from app.core.graph import routing as r
from app.core.graph.builder import OwnershipError, compile_graph, recursion_limit, run_config
from app.core.graph.checkpoint import (
    IncompatibleCheckpointError,
    check_resumable,
    make_serde,
    memory_checkpointer,
)
from app.core.graph import state as st
from app.core.graph.nodes import NODE_OUTPUTS, make_stub_nodes
from app.core.graph.routing import Budgets
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    GraphClaim,
    PipelineState,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    assert_checkpoint_safe,
    initial_state,
)
from app.core.schemas.pipeline import MisinfoLabel

JOB = "job-123"


def _input(job_id: str = JOB) -> PipelineState:
    return initial_state(
        job_id=job_id, video_id="vid-1", media_uri="videos/vid-1/video.mp4",
        pipeline_version="graph-skeleton-0.1",
    )


class Harness:
    """Stub nodes with call counters and optional per-node overrides."""

    def __init__(self, overrides=None, budgets: Budgets = r.DEFAULT_BUDGETS):
        self.calls: Counter[str] = Counter()
        self.budgets = budgets
        base = make_stub_nodes(budgets)
        base.update(overrides or {})
        self.nodes = {name: self._count(name, fn) for name, fn in base.items()}

    def _count(self, name, fn):
        def wrapped(state):
            self.calls[name] += 1
            return fn(state)
        return wrapped

    def compile(self, checkpointer=None):
        return compile_graph(self.nodes, checkpointer=checkpointer, budgets=self.budgets)

    def run(self, job_id: str = JOB, checkpointer=None):
        graph = self.compile(checkpointer or memory_checkpointer())
        return graph.invoke(_input(job_id), run_config(job_id, self.budgets))


def critic_returning(decide):
    """A critic stub whose decision for a claim is ``decide(claim_id, call_number)``."""
    calls: Counter[str] = Counter()

    def critic(state):
        results = dict(state.get("critic_results", {}))
        for cid in r.claims_to_critique(state):
            calls[cid] += 1
            decision = decide(cid, calls[cid])
            results[cid] = CriticResult(
                claim_id=cid, decision=decision,
                suggested_queries=[f"broader query {calls[cid]}"] if decision == CriticDecision.RETRIEVE_MORE else [],
            )
        return {"critic_results": results}

    return critic


# ------------------------------------------------------------------ state schema


def test_state_schema_is_versioned():
    s = _input()
    assert s["state_schema_version"] == st.STATE_SCHEMA_VERSION
    assert st.STATE_SCHEMA_VERSION.count(".") == 2


def test_state_has_every_field_from_issue_29():
    required = {
        "job_id", "video_id", "pipeline_version", "transcript_segments", "ocr_segments",
        "fused_segments", "claims", "stance_results", "retrieval_queries", "retrieved_evidence",
        "verification_results", "critic_results", "retrieval_attempts", "final_result",
        "validation_errors", "requires_human_review", "review_reasons", "errors",
    }
    assert required <= set(typing.get_type_hints(PipelineState))


def test_nested_models_are_strict_and_immutable():
    with pytest.raises(ValidationError):
        GraphClaim(claim_id="c1", claim_text="x", claim_category="y", source_segment_ids=[],
                   start_seconds=0, end_seconds=1, surprise="field")
    with pytest.raises(ValidationError):
        StanceResult(claim_id="c1", stance="PROMOTES", stance_segment_ids=[])
    claim = GraphClaim(claim_id="c1", claim_text="x", claim_category="y", source_segment_ids=[],
                       start_seconds=0, end_seconds=1)
    with pytest.raises(ValidationError):
        claim.claim_text = "changed"


def test_every_state_model_is_registered_for_checkpoints():
    defined = {
        obj for obj in vars(st).values()
        if isinstance(obj, type) and obj.__module__ == st.__name__
        and (issubclass(obj, BaseModel) or issubclass(obj, st.enum.Enum))
        and obj is not st._Record
    }
    assert defined <= set(st.CHECKPOINT_TYPES)
    assert MisinfoLabel in st.CHECKPOINT_TYPES


# ------------------------------------------------------------------- end to end


def test_graph_runs_start_to_finish_on_sample_transcript():
    h = Harness()
    out = h.run()
    assert [c.claim_id for c in out["claims"]] == ["c1", "c2"]
    # The caption 4–7 s is fused with the speech it overlaps (§3).
    assert out["claims"][0].source_segment_ids == ["t1", "o1"]
    assert out["stance_results"]["c2"].stance == Stance.REFUTES
    assert out["final_result"].classification == MisinfoLabel.MISINFO
    assert out["final_result"].claim_ids == ["c1"]
    assert out["validation_errors"] == []
    # The sample endorses one false claim and refutes another: a mixed video, which
    # the judge (T08, §9) flags for a person without changing the label.
    assert out["review_reasons"] == ["judge:mixed_video"]
    assert out["persisted_result_ref"] == f"artifacts/{JOB}/result.json"
    assert set(h.calls) == set(NODE_OUTPUTS)
    assert all(n == 1 for n in h.calls.values())


def _c2_neutral(state):
    """Stance stub with the sample's second claim NEUTRAL, so the video isn't mixed."""
    out = make_stub_nodes()[r.ANALYZE_STANCE](state)
    res = dict(out["stance_results"])
    if "c2" in res:
        res["c2"] = res["c2"].model_copy(update={"stance": Stance.NEUTRAL})
    return {"stance_results": res}


def test_unflagged_video_takes_the_pass_path_without_review():
    h = Harness({r.ANALYZE_STANCE: _c2_neutral})
    out = h.run()
    assert out["final_result"].classification == MisinfoLabel.MISINFO
    assert out["requires_human_review"] is False
    assert "review_status" not in out
    assert set(h.calls) == set(NODE_OUTPUTS) - {r.HUMAN_REVIEW}
    assert all(n == 1 for n in h.calls.values())


def test_final_state_is_checkpoint_safe():
    out = Harness().run()
    assert_checkpoint_safe(out)
    assert out["artifacts"][0].uri == "videos/vid-1/video.mp4"


def test_checkpoint_guard_rejects_bytes_and_huge_strings():
    with pytest.raises(ValueError, match="binary"):
        assert_checkpoint_safe({"artifacts": [b"\x00video"]})
    with pytest.raises(ValueError, match="exceeds"):
        assert_checkpoint_safe({"x": "a" * (st.MAX_CHECKPOINT_STRING + 1)})


# --------------------------------------------------------------- branch coverage


def test_no_verifiable_claims_skips_to_judge():
    def no_claims(state):
        return {"claims": []}

    h = Harness({r.EXTRACT_CLAIMS: no_claims})
    out = h.run()
    for skipped in (r.PLAN_RETRIEVAL, r.RETRIEVE_EVIDENCE, r.RERANK_EVIDENCE,
                    r.VERIFY_CLAIMS, r.CRITIQUE_VERIFICATION):
        assert h.calls[skipped] == 0
    assert out["final_result"].classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert "no checkable health claims" in out["final_result"].explanation.lower()
    assert h.calls[r.PERSIST_RESULT] == 1


def test_claims_not_requiring_verification_also_skip_to_judge():
    def unverifiable(state):
        return {"claims": [GraphClaim(claim_id="c1", claim_text="I love this tea",
                                      claim_category="opinion", source_segment_ids=["t1"],
                                      start_seconds=0, end_seconds=1,
                                      requires_verification=False)]}

    h = Harness({r.EXTRACT_CLAIMS: unverifiable})
    h.run()
    assert h.calls[r.PLAN_RETRIEVAL] == 0
    assert h.calls[r.JUDGE_CLASSIFICATION] == 1


def test_critic_retrieve_more_loops_back_to_retrieval_once():
    critic = critic_returning(
        lambda cid, n: CriticDecision.RETRIEVE_MORE if (cid == "c1" and n == 1) else CriticDecision.APPROVE
    )
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert h.calls[r.PLAN_RETRIEVAL] == 2
    assert out["retrieval_attempts"] == {"c1": 2, "c2": 1}
    assert out["retrieval_queries"]["c1"][-1] == "broader query 1"
    assert len(out["retrieved_evidence"]["c1"]) == 2
    assert out["review_reasons"] == ["judge:mixed_video"]  # no loop-related reason


def test_retrieval_loop_is_bounded_by_budget_then_review():
    critic = critic_returning(lambda cid, n: CriticDecision.RETRIEVE_MORE)
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert out["retrieval_attempts"] == {"c1": 3, "c2": 3}  # initial + 2 reformulations
    assert h.calls[r.PLAN_RETRIEVAL] == 3
    assert h.calls[r.JUDGE_CLASSIFICATION] == 1
    assert {"budget_exhausted:c1", "budget_exhausted:c2"} <= set(out["review_reasons"])
    assert h.calls[r.HUMAN_REVIEW] == 1
    assert out["review_status"] == st.ReviewStatus.REVIEW_REQUIRED
    assert h.calls[r.PERSIST_RESULT] == 1


def test_custom_budget_is_enforced_by_routing():
    critic = critic_returning(lambda cid, n: CriticDecision.RETRIEVE_MORE)
    h = Harness({r.CRITIQUE_VERIFICATION: critic}, budgets=Budgets(max_retrieval_attempts=1))
    out = h.run()
    assert out["retrieval_attempts"] == {"c1": 1, "c2": 1}
    assert h.calls[r.PLAN_RETRIEVAL] == 1


def test_critic_revise_verification_reruns_verifier_only():
    critic = critic_returning(
        lambda cid, n: CriticDecision.REVISE_VERIFICATION if (cid == "c2" and n == 1) else CriticDecision.APPROVE
    )
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert h.calls[r.PLAN_RETRIEVAL] == 1
    assert h.calls[r.VERIFY_CLAIMS] == 2
    assert out["verification_revisions"] == {"c2": 1}
    assert out["review_reasons"] == ["judge:mixed_video"]  # no loop-related reason


def test_revision_loop_is_bounded_by_budget():
    critic = critic_returning(lambda cid, n: CriticDecision.REVISE_VERIFICATION)
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert out["verification_revisions"] == {"c1": 1, "c2": 1}
    assert h.calls[r.VERIFY_CLAIMS] == 2
    assert "budget_exhausted:c1" in out["review_reasons"]
    assert h.calls[r.HUMAN_REVIEW] == 1


def test_mixed_decisions_in_one_pass():
    # c1 wants more evidence, c2 a revision: one retrieval pass serves c1 and the
    # verifier re-runs both in it.
    critic = critic_returning(
        lambda cid, n: (CriticDecision.RETRIEVE_MORE if cid == "c1" else CriticDecision.REVISE_VERIFICATION)
        if n == 1 else CriticDecision.APPROVE
    )
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert h.calls[r.PLAN_RETRIEVAL] == 2
    assert h.calls[r.VERIFY_CLAIMS] == 2
    assert out["retrieval_attempts"] == {"c1": 2, "c2": 1}
    assert out["verification_revisions"] == {"c2": 1}
    assert out["review_reasons"] == ["judge:mixed_video"]  # no loop-related reason


def test_critic_escalation_still_judged_then_sent_to_review():
    critic = critic_returning(lambda cid, n: CriticDecision.ESCALATE if cid == "c1" else CriticDecision.APPROVE)
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert h.calls[r.PLAN_RETRIEVAL] == 1
    assert h.calls[r.JUDGE_CLASSIFICATION] == 1
    assert "final_result" in out  # the reviewer gets a proposed label (§12)
    assert "critic_escalated:c1" in out["review_reasons"]
    assert h.calls[r.HUMAN_REVIEW] == 1


def test_validation_failure_routes_to_review():
    def bad_validation(state):
        return {"validation_errors": ["evidence ev_x was not retrieved"]}

    h = Harness({r.VALIDATE_RESULT: bad_validation})
    out = h.run()
    assert out["requires_human_review"] is True
    assert "validation_failed" in out["review_reasons"]
    assert h.calls[r.HUMAN_REVIEW] == 1
    assert h.calls[r.PERSIST_RESULT] == 1


def test_stub_validator_catches_unretrieved_citation():
    stub = make_stub_nodes()[r.VALIDATE_RESULT]
    state = Harness().run()
    forged = state["final_result"].model_copy(update={"evidence_ids": ["ev_fabricated"]})
    errors = stub({**state, "final_result": forged})["validation_errors"]
    # T09: the real §10 validator is the default; issues are "<check>:<step>: message".
    assert errors == [
        "citation_membership:judge_classification: result cites 'ev_fabricated', "
        "which was not retrieved for any claim"
    ]


def test_all_insufficient_evidence_abstains_as_cannot_recognize():
    def insufficient(state):
        return {"verification_results": {
            c: VerificationResult(claim_id=c, verdict=Verdict.INSUFFICIENT_EVIDENCE)
            for c in r.verifiable_claim_ids(state)
        }, "verification_revisions": {}}

    out = Harness({r.VERIFY_CLAIMS: insufficient}).run()
    assert out["final_result"].classification == MisinfoLabel.CANNOT_RECOGNIZE
    # Nothing could be judged because the evidence was too weak, so the case goes to a
    # person (§1, §11). c2 is refuted, so it decides as a possible debunk and is named as
    # weak evidence; c1 does not decide, so it no longer gets weak_evidence (D4 dropped:
    # deciding claims only). c1 is also an endorsed high-risk claim (treatment_efficacy)
    # the evidence couldn't settle.
    assert out["final_result"].decision_rule == "refuted_unsettled"
    assert out["requires_human_review"] is True
    assert {"weak_evidence:c2", "judge:possible_debunk:c2", "high_risk_uncertain:c1"} <= set(out["review_reasons"])
    assert "weak_evidence:c1" not in out["review_reasons"]


def test_unclear_stance_on_deciding_claim_triggers_review():
    def supported(state):
        return {"verification_results": {
            c: VerificationResult(claim_id=c, verdict=Verdict.SUPPORTED)
            for c in r.verifiable_claim_ids(state)
        }, "verification_revisions": {}}

    def unclear(state):
        return {"stance_results": {
            c.claim_id: StanceResult(claim_id=c.claim_id, stance=Stance.UNCLEAR, stance_segment_ids=[])
            for c in state["claims"]
        }}

    out = Harness({r.VERIFY_CLAIMS: supported, r.ANALYZE_STANCE: unclear}).run()
    assert out["final_result"].classification == MisinfoLabel.NO_MISINFO
    assert "unclear_stance:c1" in out["review_reasons"]


# -------------------------------------------------------------- router unit tests


def _claims(*ids):
    return [GraphClaim(claim_id=i, claim_text=i, claim_category="x", source_segment_ids=[],
                       start_seconds=0, end_seconds=1) for i in ids]


def test_route_after_stance():
    assert r.route_after_stance({"claims": []}) == r.JUDGE_CLASSIFICATION
    assert r.route_after_stance({"claims": _claims("c1")}) == r.PLAN_RETRIEVAL


@pytest.mark.parametrize(
    "decision,attempts,revisions,expected",
    [
        (CriticDecision.APPROVE, 1, 0, r.JUDGE_CLASSIFICATION),
        (CriticDecision.ESCALATE, 1, 0, r.JUDGE_CLASSIFICATION),
        (CriticDecision.RETRIEVE_MORE, 1, 0, r.PLAN_RETRIEVAL),
        (CriticDecision.RETRIEVE_MORE, 3, 0, r.JUDGE_CLASSIFICATION),
        (CriticDecision.REVISE_VERIFICATION, 1, 0, r.VERIFY_CLAIMS),
        (CriticDecision.REVISE_VERIFICATION, 1, 1, r.JUDGE_CLASSIFICATION),
    ],
)
def test_route_after_critic(decision, attempts, revisions, expected):
    state = {
        "claims": _claims("c1"),
        "retrieval_attempts": {"c1": attempts},
        "verification_revisions": {"c1": revisions},
        "verification_results": {"c1": VerificationResult(claim_id="c1", verdict=Verdict.MIXED)},
        "critic_results": {"c1": CriticResult(claim_id="c1", decision=decision)},
    }
    assert r.make_route_after_critic()(state) == expected


def test_route_after_policy():
    assert r.route_after_policy({"requires_human_review": True}) == r.HUMAN_REVIEW
    assert r.route_after_policy({"requires_human_review": False}) == r.PERSIST_RESULT


def test_recursion_limit_covers_worst_case_loops():
    # Every claim always asking for more work must finish within the limit.
    critic = critic_returning(lambda cid, n: CriticDecision.RETRIEVE_MORE if n % 2 else CriticDecision.REVISE_VERIFICATION)
    h = Harness({r.CRITIQUE_VERIFICATION: critic})
    out = h.run()
    assert out["retrieval_attempts"] == {"c1": 3, "c2": 3}
    assert recursion_limit() > 14


# ------------------------------------------------------------------- ownership


def test_each_field_has_exactly_one_owner():
    owners = Counter(f for fields in NODE_OUTPUTS.values() for f in fields)
    assert all(n == 1 for n in owners.values()), owners
    writable = set(typing.get_type_hints(PipelineState)) - st.INPUT_FIELDS - st.SHARED_FIELDS
    assert set(owners) == writable


def test_no_node_writes_another_nodes_fields():
    critic = critic_returning(
        lambda cid, n: [CriticDecision.RETRIEVE_MORE, CriticDecision.REVISE_VERIFICATION][n - 1]
        if n <= 2 else CriticDecision.ESCALATE
    )
    graph = Harness({r.CRITIQUE_VERIFICATION: critic}).compile(memory_checkpointer())
    seen = set()
    for chunk in graph.stream(_input(), run_config(JOB), stream_mode="updates"):
        for node, update in chunk.items():
            seen.add(node)
            assert set(update or {}) <= NODE_OUTPUTS[node] | st.SHARED_FIELDS, node
    assert seen == set(NODE_OUTPUTS)  # every node, including human_review, was checked


def test_builder_rejects_a_node_writing_foreign_fields():
    def rogue_stance(state):
        return {"stance_results": {}, "claims": []}

    with pytest.raises(OwnershipError, match="claims"):
        Harness({r.ANALYZE_STANCE: rogue_stance}).run()


def test_builder_rejects_unknown_node_names():
    with pytest.raises(KeyError):
        compile_graph({"not_a_node": lambda s: {}})


def test_any_node_may_append_errors():
    def ocr_with_error(state):
        return {"ocr_segments": [], "errors": [st.NodeError(node=r.EXTRACT_OCR, message="no frames")]}

    def asr_with_error(state):
        return {"transcript_segments": make_stub_nodes()[r.TRANSCRIBE_AUDIO](state)["transcript_segments"],
                "errors": [st.NodeError(node=r.TRANSCRIBE_AUDIO, message="low audio")]}

    out = Harness({r.EXTRACT_OCR: ocr_with_error, r.TRANSCRIBE_AUDIO: asr_with_error}).run()
    assert sorted(e.node for e in out["errors"]) == [r.EXTRACT_OCR, r.TRANSCRIBE_AUDIO]


# ---------------------------------------------------------------- checkpointing


def _flaky(fn):
    """Wrap a node so it raises on its first call only."""
    state = {"calls": 0}

    def wrapped(s):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("worker died mid-node")
        return fn(s)

    return wrapped


def run_resume_test(make_checkpointer):
    """Issue #29 resume test, shared by the InMemorySaver and Postgres variants."""
    run_id = uuid.uuid4().hex[:8]  # unique thread ids: a real database keeps old runs
    baseline = Harness().run(job_id=f"{JOB}-{run_id}-baseline", checkpointer=make_checkpointer())

    stubs = make_stub_nodes()
    h = Harness({r.VERIFY_CLAIMS: _flaky(stubs[r.VERIFY_CLAIMS])})
    graph = h.compile(make_checkpointer())
    job_id = f"{JOB}-{run_id}-resume"
    config = run_config(job_id)

    with pytest.raises(RuntimeError, match="worker died"):
        graph.invoke(_input(job_id), config)
    assert graph.get_state(config).next == (r.VERIFY_CLAIMS,)
    before = Counter(h.calls)

    check_resumable(graph, config)
    resumed = graph.invoke(None, config)

    # Earlier nodes did not run again; verification ran once more.
    for name, n in before.items():
        if name != r.VERIFY_CLAIMS:
            assert h.calls[name] == n, name
    assert h.calls[r.VERIFY_CLAIMS] == 2
    assert resumed["persisted_result_ref"] == f"artifacts/{job_id}/result.json"

    ignore = {"job_id", "persisted_result_ref"}
    assert {k: v for k, v in resumed.items() if k not in ignore} == {
        k: v for k, v in baseline.items() if k not in ignore
    }
    for snapshot in graph.get_state_history(config):
        assert_checkpoint_safe(snapshot.values)


def test_interrupted_run_resumes_from_checkpoint_in_memory():
    run_resume_test(memory_checkpointer)


def test_resume_refuses_incompatible_schema_version():
    graph = Harness().compile(memory_checkpointer())
    config = run_config("job-old")
    old = {**_input("job-old"), "state_schema_version": "0.9.0"}
    graph.invoke(old, config)
    with pytest.raises(IncompatibleCheckpointError):
        check_resumable(graph, config)


def test_serde_round_trips_every_state_type_without_warnings():
    out = Harness().run()
    serde = make_serde()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for key, value in out.items():
            assert serde.loads_typed(serde.dumps_typed(value)) == value, key


def test_resume_under_strict_msgpack():
    """Re-run the resume test in a fresh interpreter with LANGGRAPH_STRICT_MSGPACK=true
    (the flag is read at import time) and warnings promoted to errors."""
    code = (
        "import warnings; warnings.simplefilter('error');"
        "from app.tests.test_graph_skeleton import run_resume_test;"
        "from app.core.graph.checkpoint import memory_checkpointer;"
        "run_resume_test(memory_checkpointer); print('ok')"
    )
    env = {**os.environ, "LANGGRAPH_STRICT_MSGPACK": "true"}
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proc = subprocess.run([sys.executable, "-c", code], env=env, cwd=backend,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().endswith("ok")


@pytest.mark.skipif(not os.environ.get("LANGGRAPH_TEST_PG_DSN"),
                    reason="set LANGGRAPH_TEST_PG_DSN to run against a real Postgres")
def test_interrupted_run_resumes_from_checkpoint_postgres():
    from contextlib import ExitStack

    from app.core.graph.checkpoint import postgres_checkpointer

    with ExitStack() as stack:
        def make():
            return stack.enter_context(postgres_checkpointer(os.environ["LANGGRAPH_TEST_PG_DSN"]))

        run_resume_test(make)
