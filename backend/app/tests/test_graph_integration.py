"""T11 (#38): the graph behind a flag, with a single-call fallback.

No real model or PubMed call is made: models go through ``ModelRouter`` with a
scripted client (routing.yaml decides the model ids), PubMed through recorded fixtures.
"""
from __future__ import annotations

import asyncio
import json
import re
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.graph import claims as cl
from app.core.graph import routing as r
from app.core.graph.checkpoint import memory_checkpointer
from app.core.graph.state import FusedSegment, GraphClaim, OcrSegment, TranscriptSegment
from app.core.inference.classifier import InferenceProvider
from app.core.inference.providers import graph_provider as gp
from app.core.retrieval.retriever import EvidenceRetriever
from app.core.routing.clients import (
    AnthropicModelClient,
    OpenAIModelClient,
    map_provider_error,
)
from app.core.routing.config import load_routing
from app.core.routing.router import (
    ModelCallError,
    ModelRequest,
    ModelResponse,
    ModelRouter,
    ModelServerError,
    ModelTimeoutError,
)
from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel
from app.tests.pubmed_fixtures import RecordedPubMed

BACKEND = Path(__file__).resolve().parents[2]
HOT = "Drinking hot water every morning cures the flu."
GARLIC = "Some people say garlic stops colds. That's a myth."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ------------------------------------------------------------------ helpers


def fusion(with_segments: bool = True) -> FusionResult:
    meta: dict[str, Any] = {"ocr_disabled": True}
    if with_segments:
        meta["transcript_segments"] = [
            {"start": 3.5, "end": 8.0, "text": HOT},
            {"start": 8.5, "end": 12.0, "text": GARLIC},
        ]
    text = f"{HOT} {GARLIC}"
    return FusionResult(transcript=text, visual_text="", combined_content=f"[AUDIO TRANSCRIPT]\n{text}", metadata=meta)


def _content(inp: Any) -> str:
    return inp if isinstance(inp, str) else inp["messages"][0]["content"]


def default_script(step: str, inp: Any) -> Any:
    """A well-behaved model for every routed step."""
    text = _content(inp)
    if step == "extract_claims":
        ids = re.findall(r"^- (\S+): speech", text, re.M)
        out = []
        for bid in ids:
            block = re.search(rf'id="{re.escape(bid)}"[^\n]*>>>\n(.*?)\n<<<END', text, re.S)
            if block:
                out.append({"claim_text": block.group(1), "claim_category": "treatment_efficacy",
                            "source_segment_ids": [bid]})
        return {"claims": out}
    if step == "analyze_stance":
        seg = re.search(r"extracted from segments: (\S+?)(?:,|\n)", text).group(1)
        stance = "REFUTES" if "myth" in text.lower().split("video segments")[0] else "ENDORSES"
        return {"stance": stance, "stance_segment_ids": [seg], "rationale": "scripted"}
    if step == "verify_claims":
        ids = re.findall(r"^- id: (\S+)", text, re.M)
        return {"verdict": "CONTRADICTED", "supporting_evidence_ids": [],
                "contradicting_evidence_ids": ids[:1], "explanation": "The trials found no effect.",
                "limitations": [], "raw_confidence": 0.8}
    if step == "critique":
        return {"decision": "APPROVE", "issues": [], "suggested_queries": [], "requires_review": False}
    if step == "judge_explanation":
        return {"explanation": "Written by the scripted test model."}
    raise AssertionError(f"unexpected step {step}")


class ScriptedClient:
    """``ModelClient`` answering each step from a script; records what it was sent."""

    def __init__(self, script: Callable[[str, Any], Any] = default_script):
        self.script = script
        self.requests: list[ModelRequest] = []

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        out = self.script(request.step, request.input)
        if isinstance(out, Exception):
            raise out
        return ModelResponse(output=out, input_tokens=10, output_tokens=5)


def make_router(client: ScriptedClient) -> ModelRouter:
    return ModelRouter(load_routing(), {"anthropic": client, "openai": client})


class FakeSingleCall:
    """Stands in for the OpenAI/Anthropic single-call provider."""

    def __init__(self, fail: Optional[Exception] = None):
        self.calls = 0
        self.fail = fail

    def classify(self, fusion: FusionResult) -> ClassificationResult:
        self.calls += 1
        if self.fail:
            raise self.fail
        return ClassificationResult(
            label=MisinfoLabel.MISINFO, confidence=0.9, explanation="single call",
            evidence_snippets=[HOT], provider="openai", model_used="single-call-model", latency_ms=5,
        )


def make_provider(client: Optional[ScriptedClient] = None, *, fallback=None, **kw) -> gp.GraphProvider:
    client = client or ScriptedClient()
    retriever = EvidenceRetriever(RecordedPubMed().client())
    return gp.GraphProvider(caller=make_router(client), retriever=retriever,
                            fallback=fallback or FakeSingleCall(), **kw)


# ------------------------------------------------------------ claim extractor


def seg_state(*fused: FusedSegment, transcript=(), ocr=()) -> dict:
    return {"fused_segments": list(fused), "transcript_segments": list(transcript), "ocr_segments": list(ocr)}


class StepCaller:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list = []

    def call(self, step, input, *, system=None):
        self.calls.append(SimpleNamespace(step=step, input=input, system=system))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(output=out, record=SimpleNamespace(model="m", prompt_version="extract_v1"))


T1 = TranscriptSegment(segment_id="t1", start=3.5, end=8.0, text=HOT)
O1 = OcrSegment(segment_id="o1", start=4.0, end=7.0, text="HOT WATER = NO FLU", confidence=0.9)
F1 = FusedSegment(segment_id="f1", start=3.5, end=8.0, spoken=HOT, on_screen=["HOT WATER = NO FLU"],
                  sources=["t1", "o1"])


def test_extractor_maps_blocks_to_pieces_and_computes_timestamps():
    caller = StepCaller([{"claims": [{"claim_text": "Drinking hot water every morning cures the flu",
                                      "claim_category": "treatment_efficacy",
                                      "source_segment_ids": ["f1", "f1.screen1"]}]}])
    out = cl.make_extract_claims(caller)(seg_state(F1, transcript=[T1], ocr=[O1]))
    [c] = out["claims"]
    assert c.claim_id == "c1"
    assert c.source_segment_ids == ["t1", "o1"]  # the §4 example's shape
    assert (c.start_seconds, c.end_seconds) == (3.5, 8.0)
    req = caller.calls[0].input
    assert req["tool_choice"] == {"type": "tool", "name": "record_claims"}
    assert "<<<UNTRUSTED" in req["messages"][0]["content"]  # fenced (§15)
    from app.core.guardrails.untrusted import is_guarded_system_prompt

    assert is_guarded_system_prompt(caller.calls[0].system)


def test_extractor_drops_ungrounded_claims_and_flags_review():
    caller = StepCaller([{"claims": [{"claim_text": "Vaccines cause autism in toddlers",
                                      "claim_category": "causation", "source_segment_ids": ["f1"]}]}])
    out = cl.make_extract_claims(caller)(seg_state(F1, transcript=[T1], ocr=[O1]))
    assert out["claims"] == []
    assert any("claim_ungrounded" in e.message and e.message.startswith("guardrail:") for e in out["errors"])


def test_extractor_repairs_once_then_rejects_fabricated_ids():
    bad = {"claims": [{"claim_text": HOT, "claim_category": "other", "source_segment_ids": ["t99"]}]}
    good = {"claims": [{"claim_text": HOT, "claim_category": "other", "source_segment_ids": ["f1"]}]}
    caller = StepCaller([bad, good])
    out = cl.make_extract_claims(caller)(seg_state(F1, transcript=[T1], ocr=[O1]))
    assert len(out["claims"]) == 1 and len(caller.calls) == 2
    assert "REJECTED" in caller.calls[1].input["messages"][0]["content"]

    caller = StepCaller([bad, bad])
    out = cl.make_extract_claims(caller)(seg_state(F1, transcript=[T1], ocr=[O1]))
    assert out["claims"] == []
    assert any("output_rejected" in e.message for e in out["errors"])
    assert not cl.extraction_unavailable(out["errors"])


def test_extractor_unreachable_model_is_marked_for_fallback():
    out = cl.make_extract_claims(StepCaller([TimeoutError("down")]))(seg_state(F1, transcript=[T1]))
    assert out["claims"] == []
    assert cl.extraction_unavailable(out["errors"])
    assert out["errors"][0].retryable


def test_extractor_no_segments_makes_no_call():
    caller = StepCaller([])
    assert cl.make_extract_claims(caller)({"fused_segments": []}) == {"claims": []}
    assert caller.calls == []


def test_dedup_merges_repeats_but_never_across_negation():
    def claim(cid, text, start, src):
        return GraphClaim(claim_id=cid, claim_text=text, claim_category="other",
                          source_segment_ids=[src], start_seconds=start, end_seconds=start + 2)

    a = claim("a", "Hot water cures the flu", 4, "t1")
    b = claim("b", "hot water cures the flu!", 14, "t4")
    neg = claim("n", "Hot water does not cure the flu", 20, "t5")
    other = claim("o", "Garlic stops colds", 30, "t6")
    kept, merged = cl.dedup_claims([a, b, neg, other])
    assert merged == 1 and [k.claim_id for k in kept] == ["a", "n", "o"]
    assert kept[0].source_segment_ids == ["t1", "t4"] and kept[0].end_seconds == 16
    assert cl.lexical_similarity("X cures Y", "X does not cure Y") == 0.0


def test_long_videos_are_windowed_with_overlap_and_edge_duplicates_merged():
    segs = [FusedSegment(segment_id=f"f{i}", start=i * 30.0, end=i * 30.0 + 25, spoken=f"Claim number {i} here")
            for i in range(20)]  # 0–595 s
    wins = cl.windows(segs, window_seconds=240, overlap_seconds=20)
    assert len(wins) >= 3
    ids = [{s.segment_id for s in w} for w in wins]
    assert all(a & b for a, b in zip(ids, ids[1:]))  # windows overlap

    def answer(step, input, *, system=None):
        ids = re.findall(r"^- (f\d+): speech", input["messages"][0]["content"], re.M)
        return SimpleNamespace(output={"claims": [
            {"claim_text": f"Claim number {i[1:]} here", "claim_category": "other", "source_segment_ids": [i]}
            for i in ids]}, record=None)

    caller = SimpleNamespace(call=answer)
    out = cl.make_extract_claims(caller, window_seconds=240, overlap_seconds=20)({"fused_segments": segs})
    texts = [c.claim_text for c in out["claims"]]
    assert len(texts) == 20 == len(set(texts))  # each claim exactly once


def test_extract_prompt_file_exists_and_routing_names_it():
    # extract_v2 (T17) adds claim_kind; v1 stays on disk for recorded runs.
    assert load_routing().route("extract_claims").prompt == "extract_v2"
    assert (BACKEND / "app/core/graph/prompts/extract_v2.md").is_file()
    assert (BACKEND / "app/core/graph/prompts/extract_v1.md").is_file()


@pytest.mark.parametrize("path", [
    "app/core/graph/claims.py", "app/core/inference/providers/graph_provider.py", "app/core/routing/clients.py",
])
def test_no_model_id_in_code(path):
    src = (BACKEND / path).read_text()
    assert not re.search(r"claude-|gpt-|gemini|haiku|sonnet|opus", src, re.I)


# ------------------------------------------------------------ provider clients


def test_anthropic_client_returns_forced_tool_input():
    sent = {}

    class Messages:
        def create(self, **kw):
            sent.update(kw)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="thinking"),
                         SimpleNamespace(type="tool_use", name="record_claims", input={"claims": []})],
                usage=SimpleNamespace(input_tokens=7, output_tokens=3))

    client = AnthropicModelClient(SimpleNamespace(messages=Messages()))
    req = ModelRequest(step="extract_claims", prompt_version="extract_v1", system="SYS", input={
        "messages": [{"role": "user", "content": "hi"}], "tools": [cl.EXTRACT_TOOL],
        "tool_choice": cl.TOOL_CHOICE, "max_tokens": 100, "temperature": 0})
    resp = client.complete("routed-model", req)
    assert resp.output == {"claims": []} and (resp.input_tokens, resp.output_tokens) == (7, 3)
    assert sent["model"] == "routed-model" and sent["system"] == "SYS" and sent["tool_choice"]["name"] == "record_claims"


def test_openai_client_translates_tools_and_parses_arguments():
    sent = {}

    class Completions:
        def create(self, **kw):
            sent.update(kw)
            call = SimpleNamespace(function=SimpleNamespace(name="record_claims", arguments='{"claims": []}'))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
                                   usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2))

    client = OpenAIModelClient(SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    req = ModelRequest(step="critique", prompt_version="v", system="SYS", input={
        "messages": [{"role": "user", "content": "hi"}], "tools": [cl.EXTRACT_TOOL], "tool_choice": cl.TOOL_CHOICE})
    resp = client.complete("m", req)
    assert resp.output == {"claims": []}
    assert sent["messages"][0] == {"role": "system", "content": "SYS"}
    assert sent["tools"][0]["function"]["parameters"] == cl.EXTRACT_TOOL["input_schema"]
    assert sent["tool_choice"] == {"type": "function", "function": {"name": "record_claims"}}


def test_text_input_returns_text_for_guarded_router():
    class Messages:
        def create(self, **kw):
            assert "tools" not in kw
            return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"a": 1}')], usage=None)

    out = AnthropicModelClient(SimpleNamespace(messages=Messages())).complete(
        "m", ModelRequest(step="s", prompt_version="v", input="rendered prompt"))
    assert out.output == '{"a": 1}'


def test_provider_errors_map_to_router_kinds():
    def err(name, status=None):
        cls = type(name, (Exception,), {})
        e = cls("x")
        e.status_code = status
        return e

    assert isinstance(map_provider_error(err("APITimeoutError")), ModelTimeoutError)
    assert isinstance(map_provider_error(err("InternalServerError", 503)), ModelServerError)
    assert map_provider_error(err("RateLimitError", 429)).kind == "rate_limit"
    assert map_provider_error(err("APIConnectionError")).kind == "connection"
    plain = map_provider_error(err("BadRequestError", 400))
    assert type(plain) is ModelCallError  # not retried, not fallen back on


def test_router_falls_back_to_configured_model_on_5xx():
    calls = []

    class Flaky:
        def complete(self, model, request):
            calls.append(model)
            if len(calls) <= 2:
                raise ModelServerError("boom", status=503)
            return ModelResponse(output={"ok": True})

    router = ModelRouter(load_routing(), {"anthropic": Flaky(), "openai": Flaky()})
    res = router.call("extract_claims", {"messages": []})
    assert res.record.fallback_used and res.record.fallback_reason == "5xx"
    assert calls[-1] == load_routing().fallback.use.model


# --------------------------------------------------------- fusion → segments


def test_whisper_segments_are_used_when_kept():
    t, o, est = gp.segments_from_fusion(fusion())
    assert [(s.segment_id, s.start, s.end) for s in t] == [("t1", 3.5, 8.0), ("t2", 8.5, 12.0)]
    assert o == [] and not est


def test_without_segments_timing_is_estimated_and_ordered():
    t, _, est = gp.segments_from_fusion(fusion(with_segments=False))
    assert est and [s.text for s in t] == ["Drinking hot water every morning cures the flu.",
                                           "Some people say garlic stops colds.", "That's a myth."]
    assert all(a.end <= b.start for a, b in zip(t, t[1:]))


# ----------------------------------------------------------- graph provider


def test_graph_provider_implements_inference_provider_and_returns_claims():
    client = ScriptedClient()
    provider = make_provider(client)
    assert isinstance(provider, InferenceProvider)
    outcome = provider.run(fusion(), job_id="job-ok", video_id="vid-1")
    assert outcome.pipeline == "graph" and not outcome.fallback_used
    c = outcome.classification
    assert c.provider == "langgraph" and c.label in set(MisinfoLabel)
    assert c.claims and {x.text for x in c.claims} == {HOT, GARLIC}
    stances = {k: v.stance.value for k, v in outcome.state["stance_results"].items()}
    assert sorted(stances.values()) == ["ENDORSES", "REFUTES"]
    assert outcome.state["final_result"] is not None
    steps = {req.step for req in client.requests}
    assert {"extract_claims", "analyze_stance", "verify_claims", "critique"} <= steps
    assert outcome.model_calls and all(rec.error is None for rec in outcome.model_calls)
    # classify() is the protocol method and gives the same kind of answer
    assert make_provider().classify(fusion()).provider == "langgraph"


def test_graph_exception_still_yields_a_classification():
    def explode(state):
        raise RuntimeError("node crashed")

    fallback = FakeSingleCall()
    provider = make_provider(fallback=fallback, node_overrides={r.RERANK_EVIDENCE: explode})
    outcome = provider.run(fusion(), job_id="job-crash")
    assert outcome.fallback_used and outcome.pipeline == "graph_fallback"
    assert outcome.fallback_reason.startswith("graph_error:RuntimeError")
    assert outcome.classification.explanation == "single call" and fallback.calls == 1
    assert not outcome.requires_human_review


def test_timeout_falls_back():
    ticks = iter(range(0, 10_000, 100))
    provider = make_provider(timeout_seconds=250, clock=lambda: float(next(ticks)))
    outcome = provider.run(fusion(), job_id="job-slow")
    assert outcome.fallback_reason == "timeout"


def test_unreachable_extractor_falls_back_instead_of_reporting_no_claims():
    def script(step, inp):
        return ModelServerError("down", status=503) if step == "extract_claims" else default_script(step, inp)

    outcome = make_provider(ScriptedClient(script)).run(fusion(), job_id="job-noextract")
    assert outcome.fallback_reason == "extraction_unavailable"
    assert outcome.classification.provider == "openai"


def test_every_model_call_after_extraction_failing_falls_back():
    def script(step, inp):
        if step == "extract_claims":
            return default_script(step, inp)
        return ModelServerError("down", status=503)

    outcome = make_provider(ScriptedClient(script)).run(fusion(), job_id="job-down")
    assert outcome.fallback_reason == "models_unavailable"

    # One step down (only the critic) is not an outage: the graph's answer stands.
    def critic_down(step, inp):
        return ModelServerError("down", status=503) if step == "critique" else default_script(step, inp)

    assert make_provider(ScriptedClient(critic_down)).run(fusion(), job_id="job-partial").pipeline == "graph"


def test_no_result_falls_back():
    provider = make_provider(node_overrides={r.JUDGE_CLASSIFICATION: lambda s: {}})
    outcome = provider.run(fusion(), job_id="job-nores")
    assert outcome.fallback_used
    assert outcome.fallback_reason == "no_result" or outcome.fallback_reason.startswith("graph_error:")


def test_fallback_errors_propagate_like_the_single_call():
    from app.core.exceptions import InferenceProviderError

    err = InferenceProviderError(provider="openai", cause=RuntimeError("both down"))
    provider = make_provider(fallback=FakeSingleCall(fail=err),
                             node_overrides={r.RERANK_EVIDENCE: lambda s: 1 / 0})
    with pytest.raises(InferenceProviderError):
        provider.run(fusion(), job_id="job-both")


def _with_category(category: str) -> Callable[[str, Any], Any]:
    def script(step: str, inp: Any) -> Any:
        out = default_script(step, inp)
        if step == "extract_claims":
            for c in out["claims"]:
                c["claim_category"] = category
        return out
    return script


NOTHING_FOUND = {
    r.RETRIEVE_EVIDENCE: lambda s: {"retrieved_evidence": {c.claim_id: [] for c in s["claims"]},
                                    "retrieval_attempts": {c.claim_id: 3 for c in s["claims"]}},
}


def test_abstention_is_not_replaced_by_the_single_call():
    """No evidence for a harm claim → INSUFFICIENT → CANNOT_RECOGNIZE: a designed answer,
    not a failure."""
    fallback = FakeSingleCall()
    provider = make_provider(ScriptedClient(_with_category("side_effects")), fallback=fallback,
                             node_overrides=NOTHING_FOUND)
    outcome = provider.run(fusion(), job_id="job-abstain")
    assert outcome.pipeline == "graph" and fallback.calls == 0
    assert outcome.classification.label == MisinfoLabel.CANNOT_RECOGNIZE


def test_unproven_efficacy_claim_end_to_end_is_misinfo_unproven_and_reviewed():
    """T30 (D1 = B): endorsed treatment claims the full search found nothing for →
    UNSUPPORTED → MISINFO with basis ``unproven``, always reviewed; not a failure."""
    fallback = FakeSingleCall()
    provider = make_provider(fallback=fallback, node_overrides=NOTHING_FOUND)
    outcome = provider.run(fusion(), job_id="job-unproven")
    assert outcome.pipeline == "graph" and fallback.calls == 0
    assert outcome.classification.label == MisinfoLabel.MISINFO
    final = outcome.state["final_result"]
    assert final.misinfo_basis == "unproven" and final.decision_rule == "unproven"
    assert outcome.state["requires_human_review"]
    assert any(x.startswith("judge:unproven_claim:") for x in outcome.state["review_reasons"])
    assert "false" not in outcome.classification.explanation.lower()


def test_finished_run_is_reused_and_unfinished_run_resumes():
    cp = memory_checkpointer()
    client = ScriptedClient()
    provider = make_provider(client, checkpointer=cp)
    first = provider.run(fusion(), job_id="job-twice")
    n = len(client.requests)
    again = provider.run(fusion(), job_id="job-twice")  # Celery redelivery
    assert again.resumed and len(client.requests) == n
    assert again.classification.label == first.classification.label

    # A worker dies in verify_claims: the rerun resumes and doesn't re-extract.
    cp2 = memory_checkpointer()
    client2 = ScriptedClient()
    boom = {"armed": True}
    from app.core.graph.verifier import make_verify_claims

    real_verify = make_verify_claims(make_router(client2))

    def flaky_verify(state):
        if boom["armed"]:
            raise RuntimeError("worker died")
        return real_verify(state)

    p2 = make_provider(client2, checkpointer=cp2, node_overrides={r.VERIFY_CLAIMS: flaky_verify})
    assert p2.run(fusion(), job_id="job-crash-resume").fallback_used
    extract_calls = sum(1 for q in client2.requests if q.step == "extract_claims")
    boom["armed"] = False
    resumed = p2.run(fusion(), job_id="job-crash-resume")
    assert resumed.resumed and resumed.pipeline == "graph"
    assert sum(1 for q in client2.requests if q.step == "extract_claims") == extract_calls


# --------------------------------------------------------------- flag & task


def test_flag_defaults_to_off():
    from app.core.config import Settings

    assert Settings.model_fields["USE_GRAPH_PIPELINE"].default is False


def test_single_call_path_unchanged_when_flag_off(monkeypatch):
    import app.core.pipeline as pl

    fused = fusion(with_segments=False)
    calls = {}

    class Fusion:
        def fuse(self, path, **kw):
            calls["fuse_kwargs"] = kw
            return fused

    monkeypatch.setattr(pl, "MultimodalFusion", Fusion)
    monkeypatch.setattr(pl, "get_provider", lambda: FakeSingleCall())

    async def fake_ground(transcript):
        return []

    import app.core.grounding.pubmed as pm
    monkeypatch.setattr(pm, "ground_transcript", fake_ground)
    f, c = asyncio.run(pl.run_pipeline("v.mp4"))
    assert calls["fuse_kwargs"] == {}  # no segments requested, no graph
    assert c.provider == "openai" and c.citations == []


def _db():
    from app.db.base import Base
    import app.db.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(db, status="STARTED"):
    from app.db.models.job import Job, JobStatus
    from app.db.models.video import Video

    v = Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1)
    db.add(v)
    db.add(Job(id="job-1", video_id="vid-1", status=JobStatus(status)))
    db.commit()


def test_task_runs_graph_only_when_flag_on(monkeypatch):
    import app.worker.tasks as tasks
    from app.core.config import settings

    db = _db()
    _job(db)
    import app.db.session as sess
    monkeypatch.setattr(sess, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")

    ran = {}
    import app.core.pipeline as pl

    async def single(path):
        ran["single"] = True
        return fusion(False), FakeSingleCall().classify(None)

    monkeypatch.setattr(pl, "run_pipeline", single)
    monkeypatch.setattr(tasks, "_run_graph_job", lambda *a: ran.setdefault("graph", True) and {})

    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", False)
    tasks.process_video_task.run("job-1")
    assert ran == {"single": True}

    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    db.query(Result).delete()
    db.get(Job, "job-1").status = JobStatus.STARTED
    db.commit()
    ran.clear()
    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", True)
    tasks.process_video_task.run("job-1")
    assert ran == {"graph": True}


def test_task_skips_a_job_that_already_finished(monkeypatch):
    import app.worker.tasks as tasks
    from app.core.config import settings
    from app.db.models.result import Result

    db = _db()
    _job(db, status="SUCCESS")
    db.add(Result(job_id="job-1", label="MISINFO", confidence=0.5, explanation="x", evidence_snippets=[],
                  combined_content="", provider="p", model_used="m", latency_ms=1))
    db.commit()
    import app.db.session as sess
    monkeypatch.setattr(sess, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", True)
    monkeypatch.setattr(tasks, "_run_graph_job", lambda *a: pytest.fail("re-ran a finished job"))
    assert tasks.process_video_task.run("job-1")["skipped"] is True


def test_graph_job_end_to_end_through_the_task(monkeypatch):
    """Flag on: the Celery task runs the graph and persists claim-level rows."""
    import app.worker.tasks as tasks
    import app.core.inference.providers.graph_provider as gpm
    import app.core.pipeline as pl
    from app.core.config import settings
    from app.db.models.claim import ClaimRow
    from app.db.models.result import Result

    db = _db()
    _job(db)
    import app.db.session as sess
    monkeypatch.setattr(sess, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "USE_GRAPH_PIPELINE", True)

    class Fusion:
        def fuse(self, path, keep_segments=False):
            assert keep_segments
            return fusion()

    monkeypatch.setattr(pl, "MultimodalFusion", Fusion)
    monkeypatch.setattr(gpm, "build_graph_provider", lambda checkpointer=None: make_provider(checkpointer=checkpointer))
    out = tasks.process_video_task.run("job-1")
    assert out["pipeline"] == "graph"
    res = db.query(Result).filter_by(job_id="job-1").one()
    assert res.pipeline == "graph" and res.provider == "langgraph"
    assert db.query(ClaimRow).filter_by(job_id="job-1").count() == 2


# ------------------------------------------------------------- persistence


def test_persist_graph_outcome_writes_claim_level_rows_idempotently():
    from app.db.models.claim import (ClaimEvidenceRow, ClaimRow, EvidenceRecordRow, ModelRunRow,
                                     TranscriptSegmentRow)
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.services.pipeline_result_service import claim_level_view, persist_outcome

    db = _db()
    _job(db)
    outcome = make_provider().run(fusion(), job_id="job-1", video_id="vid-1")
    for _ in range(2):  # Celery may deliver twice
        persist_outcome(db, "job-1", fusion(), outcome)
    assert db.query(Result).count() == 1
    assert db.query(ClaimRow).count() == 2
    assert db.query(TranscriptSegmentRow).count() == 2
    assert db.query(ModelRunRow).count() == len(outcome.model_calls)
    assert db.query(EvidenceRecordRow).count() >= 1 and db.query(ClaimEvidenceRow).count() >= 1
    res = db.query(Result).one()
    assert res.pipeline == "graph" and res.pipeline_version == "graph_v1"
    assert res.decision_rule == outcome.state["final_result"].decision_rule
    view = claim_level_view(db, "job-1")
    assert {v["text"] for v in view} == {HOT, GARLIC}
    assert all(v["verdict"] == "CONTRADICTED" and v["evidence"] for v in view)
    job = db.get(Job, "job-1")
    assert job.status == (JobStatus.REVIEW_REQUIRED if outcome.requires_human_review else JobStatus.SUCCESS)


def test_review_required_outcome_opens_a_case():
    from app.db.models.job import Job, JobStatus
    from app.db.models.review import HumanReview
    from app.services.pipeline_result_service import persist_outcome

    db = _db()
    _job(db)
    outcome = make_provider().run(fusion(), job_id="job-1")
    outcome.state = {**outcome.state, "requires_human_review": True, "review_reasons": ["judge:mixed_video"]}
    persist_outcome(db, "job-1", fusion(), outcome)
    assert db.get(Job, "job-1").status == JobStatus.REVIEW_REQUIRED
    assert db.query(HumanReview).one().reasons == ["judge:mixed_video"]


def test_fallback_outcome_is_recorded_without_claim_rows():
    from app.db.models.claim import ClaimRow
    from app.db.models.result import Result
    from app.services.pipeline_result_service import persist_outcome

    db = _db()
    _job(db)
    outcome = make_provider(node_overrides={r.RERANK_EVIDENCE: lambda s: 1 / 0}).run(fusion(), job_id="job-1")
    persist_outcome(db, "job-1", fusion(), outcome)
    res = db.query(Result).one()
    assert res.pipeline == "graph_fallback" and res.fallback_reason.startswith("graph_error:ZeroDivisionError")
    assert res.provider == "openai" and db.query(ClaimRow).count() == 0


def test_migration_0008_upgrades_and_downgrades_on_sqlite(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    command.upgrade(cfg, "0008")
    insp = inspect(create_engine(url))
    tables = set(insp.get_table_names())
    assert {"claims", "claim_stances", "evidence_records", "claim_evidence", "verification_results",
            "critic_reviews", "model_runs", "transcript_segments", "ocr_segments"} <= tables
    assert {"pipeline", "fallback_reason", "decision_rule"} <= {c["name"] for c in insp.get_columns("results")}
    command.downgrade(cfg, "0007")
    insp = inspect(create_engine(url))
    assert "claims" not in insp.get_table_names()
    assert "pipeline" not in {c["name"] for c in insp.get_columns("results")}


def test_orm_models_match_migration(tmp_path, monkeypatch):
    """Every column the ORM declares exists after ``alembic upgrade head``."""
    from alembic import command
    from alembic.config import Config

    from app.db.models.claim import CLAIM_LEVEL_MODELS
    from app.db.models.result import Result

    url = f"sqlite:///{tmp_path / 'h.db'}"
    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    for model in (*CLAIM_LEVEL_MODELS, Result):
        cols = {c["name"] for c in insp.get_columns(model.__tablename__)}
        assert {c.name for c in model.__table__.columns} <= cols, model.__tablename__


# --------------------------------------------------------------------- API


def _api_db_with(outcome_kind: str):
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.services.pipeline_result_service import persist_outcome

    db = _db()
    _job(db)
    if outcome_kind == "single":
        db.add(Result(job_id="job-1", label="MISINFO", confidence=0.9, explanation="x", evidence_snippets=["q"],
                      combined_content="", provider="openai", model_used="m", latency_ms=1))
        db.get(Job, "job-1").status = JobStatus.SUCCESS
        db.commit()
    else:
        outcome = make_provider().run(fusion(), job_id="job-1")
        if outcome_kind == "review":
            outcome.state = {**outcome.state, "requires_human_review": True, "review_reasons": ["critic:escalated"]}
        persist_outcome(db, "job-1", fusion(), outcome)
    return db


@pytest.mark.parametrize("kind", ["single", "graph", "review"])
def test_result_endpoint_serves_both_paths(kind):
    from app.api.routers.jobs import get_result

    db = _api_db_with(kind)
    from app.db.models.job import Job
    db.get(Job, "job-1").user_id = "user-1"  # T28: results are served to the job's owner only
    db.commit()
    out = get_result("job-1", db=db, current_user={"sub": "user-1"})
    # The fields the existing frontend reads are always there.
    for key in ("label", "confidence", "explanation", "evidence_snippets", "citations", "provider",
                "model_used", "latency_ms"):
        assert key in out
    if kind == "single":
        assert out["claims"] == [] and out["pipeline"] is None and out["review"] is None
    else:
        assert len(out["claims"]) == 2 and out["pipeline"] == "graph"
    if kind == "review":
        # T26 added fields to ``review``; the two the current frontend reads are unchanged.
        assert out["review"]["status"] == "REVIEW_REQUIRED"
        assert out["review"]["reasons"] == ["critic:escalated"]
    json.dumps(out, default=str)  # serialisable


def test_frontend_handles_review_required_and_claims():
    src = (BACKEND.parent / "frontend/app/jobs/[job_id]/JobDetailClient.tsx").read_text()
    assert '"REVIEW_REQUIRED"' in src and "result.claims" in src and "awaiting human review" in src
    page = (BACKEND.parent / "frontend/app/jobs/[job_id]/page.tsx").read_text()
    assert "REVIEW_REQUIRED" in page


def test_production_wiring_from_settings(monkeypatch):
    """build_graph_provider: routed models, guarded PubMed with T13's shared Redis query
    cache, the single-call fallback. Nothing is called."""
    from unittest.mock import MagicMock

    import redis

    from app.core.config import Settings
    from app.core.retrieval.cache import RedisQueryCache

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda url: MagicMock()))
    from app.core.config import settings as live

    monkeypatch.setattr(live, "OPENAI_API_KEY", "sk-dummy")  # the fallback reads global settings
    s = Settings(DATABASE_URL="sqlite://", DATABASE_URL_SYNC="sqlite://", USE_GRAPH_PIPELINE=True,
                 OPENAI_API_KEY="sk-dummy", ANTHROPIC_API_KEY="sk-ant-dummy")
    p = gp.build_graph_provider(s)
    assert isinstance(p.retriever.cache, RedisQueryCache)
    assert set(p.caller.clients) == {"anthropic", "openai"}
    assert p.timeout_seconds == s.GRAPH_TIMEOUT_SECONDS

    assert gp.shared_query_cache(s.model_copy(update={"GRAPH_SHARED_RETRIEVAL": False})) is None


# --- T18 smoke run: the Anthropic client against current models --------------------

class _BadRequest(Exception):
    status_code = 400


def _forced_req(max_tokens=512):
    return ModelRequest(step="analyze_stance", prompt_version="v", system="SYS", input={
        "messages": [{"role": "user", "content": "hi"}], "tools": [cl.EXTRACT_TOOL],
        "tool_choice": cl.TOOL_CHOICE, "max_tokens": max_tokens, "temperature": 0})


def _tool_reply():
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="record_claims", input={"claims": []})],
                           usage=SimpleNamespace(input_tokens=5, output_tokens=2))


def test_anthropic_client_never_sends_temperature():
    sent = {}

    class Messages:
        def create(self, **kw):
            sent.update(kw)
            return _tool_reply()

    AnthropicModelClient(SimpleNamespace(messages=Messages())).complete("m", _forced_req())
    assert "temperature" not in sent and "top_p" not in sent and "top_k" not in sent


def test_anthropic_client_falls_back_to_auto_when_a_model_refuses_forced_tool_choice():
    calls = []

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            if kw["tool_choice"]["type"] == "tool":
                raise _BadRequest('Error code: 400 - tool_choice: type "tool" and "any" are not supported for this model.')
            return _tool_reply()

    client = AnthropicModelClient(SimpleNamespace(messages=Messages()))
    resp = client.complete("strict-model", _forced_req())
    assert resp.output == {"claims": []}
    retry = calls[1]
    assert retry["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert "record_claims" in retry["system"] and retry["system"].startswith("SYS")
    assert retry["max_tokens"] >= 8192  # room for always-on thinking
    # Remembered per model: the next call goes straight to auto, no second 400.
    client.complete("strict-model", _forced_req())
    assert [c["tool_choice"]["type"] for c in calls] == ["tool", "auto", "auto"]
    # Another model still gets the forced call first.
    client.complete("other-model", _forced_req())
    assert [c["tool_choice"]["type"] for c in calls[3:]] == ["tool", "auto"]


def test_anthropic_client_auto_reply_without_the_tool_parses_as_none():
    class Messages:
        def create(self, **kw):
            if kw["tool_choice"]["type"] == "tool":
                raise _BadRequest('tool_choice: type "tool" and "any" are not supported for this model.')
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="I think it is ENDORSES")], usage=None)

    resp = AnthropicModelClient(SimpleNamespace(messages=Messages())).complete("m", _forced_req())
    assert resp.output is None  # the node's parser applies its safe default


def test_anthropic_client_other_bad_requests_are_not_retried():
    calls = []

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            raise _BadRequest("messages: field required")

    with pytest.raises(ModelCallError):
        AnthropicModelClient(SimpleNamespace(messages=Messages())).complete("m", _forced_req())
    assert len(calls) == 1


def test_single_call_providers_report_token_usage():
    from app.core.inference.providers.anthropic_provider import AnthropicProvider
    from app.core.inference.providers.openai_provider import OpenAIProvider

    oa = OpenAIProvider.__new__(OpenAIProvider)
    oa._model, oa.last_usage = "alias", None
    msg = SimpleNamespace(content='{"label": "NO_MISINFO", "confidence": 0.9, "explanation": "x", "evidence_snippets": []}')
    oa._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        model="pinned-id", choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3)))))
    oa.classify(FusionResult(transcript="t", visual_text="", combined_content="t", metadata={}))
    assert oa.last_usage == {"model": "pinned-id", "input_tokens": 11, "output_tokens": 3}

    an = AnthropicProvider.__new__(AnthropicProvider)
    an._model, an.last_usage = "m", None
    an._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        model="m", content=[SimpleNamespace(type="tool_use", input={"label": "MISINFO", "confidence": 1})],
        usage=SimpleNamespace(input_tokens=7, output_tokens=2))))
    an.classify(FusionResult(transcript="t", visual_text="", combined_content="t", metadata={}))
    assert an.last_usage == {"model": "m", "input_tokens": 7, "output_tokens": 2}
