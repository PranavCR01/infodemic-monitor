"""Routing experiment runner (T38). Every client here is a mock: no model API and no
network is touched. The golden set is a tiny synthetic fixture with the real layout,
including one TEST-split video that must never be read."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from app.core.retrieval.pubmed import PubMedArticle
from app.core.retrieval.retriever import RetrievalResult, to_evidence
from app.core.routing.config import DEFAULT_ROUTING_PATH, ModelPrice, load_routing
from app.core.routing.mock import MockModelClient
from app.core.routing.router import ModelRequest, ModelResponse, ModelServerError
from app.evaluation.routing_experiment import cli
from app.evaluation.routing_experiment import experiment as ex
from app.evaluation.routing_experiment.cost import (
    GuardedClient,
    SpendCapError,
    SpendCapReached,
    SpendGuard,
    estimate_input_tokens,
)
from app.evaluation.routing_experiment.frozen import (
    FORMAT,
    FrozenEvidence,
    FrozenEvidenceError,
    Recorder,
    compose,
    write_frozen,
)
from app.evaluation.routing_experiment.golden import DirSource, GitSource, TestSplitError, TuneSet
from app.evaluation.routing_experiment.items import (
    efficacy_category,
    extraction_items,
    ocr_segments,
    stance_items,
    verify_items,
    video_input,
)
from app.evaluation.selection import Candidate, StepItem, evaluate_candidate, label_macro_f1

GOLDEN = Path(__file__).parent / "fixtures" / "routing_experiment" / "golden"
TEST_VIDEO = "v04"  # the fixture's test-split video


class SpySource(DirSource):
    """Records every file read, to prove the test split is never opened."""

    def __init__(self, path: Path):
        super().__init__(path)
        object.__setattr__(self, "reads", [])

    def read(self, relpath: str) -> str:
        self.reads.append(relpath)
        return super().read(relpath)


def tune(spy: bool = False) -> TuneSet:
    return TuneSet(SpySource(GOLDEN) if spy else DirSource(GOLDEN))


# ------------------------------------------------------------------ fakes


def article(pmid: str, title: str, abstract: str) -> PubMedArticle:
    return PubMedArticle(pmid=pmid, title=title, abstract=abstract, publication_year=2020,
                         publication_types=("Randomized Controlled Trial",))


class FakeRetriever:
    def __init__(self, fail_on: str = ""):
        self.queries: list[str] = []
        self.fail_on = fail_on

    def retrieve(self, query: str) -> RetrievalResult:
        self.queries.append(query)
        if self.fail_on and self.fail_on in query.lower():
            raise RuntimeError("PubMed down")
        words = query.replace('"', "").split()
        recs = [to_evidence(article(str(20000000 + len(self.queries) * 10 + i),
                                    f"Trial of {' '.join(words[:4])}",
                                    f"A randomised trial of {' '.join(words)} in adults."), query)
                for i in range(2)]
        return RetrievalResult(query=query, records=recs, pmids_found=len(recs))

    def articles(self, pmids):
        return [article(p, "Hot fluids and influenza", "Hot drinks relieve symptoms but do not shorten flu.")
                for p in pmids]


class FakeReferences:
    def __init__(self):
        self.searched: list[str] = []

    def search(self, text: str):
        self.searched.append(text)

        class R:
            records: list = []
            errors: list = []
        return R()


def recorded(tmp_path: Path, retriever=None) -> Path:
    t = tune()
    rec = Recorder(retriever or FakeRetriever(), FakeReferences())
    path = tmp_path / "frozen.json"
    write_frozen(path, rec.record(t), golden=t.source.describe())
    return path


# Tool outputs a well-behaved model would give, parsed out of the rendered request.
def responder(model: str, request: ModelRequest):
    content = request.input["messages"][0]["content"] if isinstance(request.input, dict) else str(request.input)
    if request.step == "analyze_stance":
        sid = re.search(r'"id": "([^"]+)"', content).group(1)
        claim_line = content.split("\n", 1)[0].lower()
        stance = "REFUTES" if "garlic" in claim_line else "ENDORSES"
        return {"stance": stance, "stance_segment_ids": [sid], "rationale": "The speaker says so."}
    if request.step == "verify_claims":
        return {"verdict": "INSUFFICIENT_EVIDENCE", "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [], "explanation": "Nothing tests this directly.",
                "limitations": []}
    if request.step == "extract_claims":
        bid = re.search(r"- (f\d+): speech", content).group(1)
        text = re.search(r"Drink hot water every morning\.|People say garlic prevents colds\.|Look at my new car\.",
                         content)
        return {"claims": [{"claim_text": text.group(0).rstrip("."), "claim_category": "other",
                            "source_segment_ids": [bid]}] if text else []}
    raise AssertionError(request.step)


def mock_clients(**kw):
    return lambda: {"anthropic": MockModelClient(responder, **kw), "openai": MockModelClient(responder, **kw)}


def never_called():
    raise AssertionError("a provider client was built: nothing may be called in a dry run or refused run")


def candidates_file(tmp_path: Path, steps=("extract_claims", "analyze_stance", "verify_claims"),
                    models=("claude-haiku-5-5", "claude-sonnet-5-5")) -> Path:
    prompts = {"extract_claims": "extract_v2", "analyze_stance": "stance_v1", "verify_claims": "verify_v3"}
    body = {"version": "t", "tie_margin": 0.01,
            "candidates": {s: [{"provider": "anthropic", "model": m, "prompt": prompts[s]} for m in models]
                           for s in steps}}
    p = tmp_path / "cands.yaml"
    p.write_text(json.dumps(body))  # JSON is valid YAML
    return p


def plan(tmp_path, **kw):
    frozen = FrozenEvidence.load(recorded(tmp_path))
    return ex.build_plan(tune(), ex.load_candidates(candidates_file(tmp_path, **kw)), load_routing(), frozen=frozen)


# ------------------------------------------------------------------ test-split guard


def test_tune_set_drops_test_split_rows_before_anything_sees_them():
    t = tune(spy=True)
    assert t.video_ids == ["v01", "v02", "v03"]
    assert TEST_VIDEO not in t.videos
    assert all(c.video_id != TEST_VIDEO for v in t.videos.values() for c in v.claims)
    assert "v04:c1" not in {k for k in t.reference_passages()}


def test_item_builder_refuses_test_split_videos_without_reading_them():
    t = tune(spy=True)
    with pytest.raises(TestSplitError):
        t.transcript(TEST_VIDEO)
    with pytest.raises(TestSplitError):
        video_input(t, TEST_VIDEO)
    with pytest.raises(TestSplitError):
        extraction_items(t, {}, [TEST_VIDEO])
    with pytest.raises(TestSplitError):
        ex.build_plan(t, ex.load_candidates(), load_routing(), videos=[TEST_VIDEO], allow_assumed_evidence=True)
    with pytest.raises(TestSplitError):
        t.transcript("v999")  # unknown ids are refused too
    assert not [r for r in t.source.reads if TEST_VIDEO in r]


def test_full_plan_never_reads_a_test_split_transcript(tmp_path):
    t = tune(spy=True)
    ex.build_plan(t, ex.load_candidates(), load_routing(), allow_assumed_evidence=True)
    assert sorted(r for r in t.source.reads if r.startswith("transcripts/")) == [
        "transcripts/v01.json", "transcripts/v02.json"]  # v03 is out of scope, v04 is test


def test_git_source_reads_with_git_show(monkeypatch):
    calls = []

    class Done:
        stdout = b"video_id,split\n"

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr("app.evaluation.routing_experiment.golden.subprocess.run", fake_run)
    assert GitSource("origin/data/golden-label-set", "research/x").read("videos.csv") == "video_id,split\n"
    assert calls == [["git", "show", "origin/data/golden-label-set:research/x/videos.csv"]]


# ------------------------------------------------------------------ items


def test_per_step_items_from_tune_split():
    t = tune()
    videos = {vid: video_input(t, vid) for vid in ("v01", "v02")}
    ext = extraction_items(t, videos)
    assert [i.item_id for i in ext] == ["v01", "v02"]  # out-of-scope v03 is left out (§14)
    assert ext[1].gold == ["Garlic prevents colds", "The recommended daily vitamin C intake for adults is 90 mg"]
    st = stance_items(t, videos)
    assert [(i.item_id, i.gold) for i in st] == [("v01:c1", "ENDORSES"), ("v02:c1", "REFUTES"), ("v02:c2", "ENDORSES")]
    claim = st[0].input.claim
    assert claim.source_segment_ids[:2] == ["t1", "t2"] and any(s.startswith("o") for s in claim.source_segment_ids)


def test_ocr_detections_collapse_into_captions_without_watermarks():
    data = json.loads((GOLDEN / "transcripts" / "v01.json").read_text())
    segs = ocr_segments(data)
    assert [s.text for s in segs] == ["HOT WATER CURES FLU"]  # merged across frames, longest kept
    assert (segs[0].start, segs[0].end) == (0.0, 4.0)
    assert all("TikTok" not in s.text for s in segs)  # in every frame: a watermark


def test_claim_category_is_a_fixed_rule_not_the_gold_verdict():
    assert efficacy_category("Hot water every morning cures the flu") == "treatment_efficacy"
    assert efficacy_category("Garlic prevents colds") == "prevention"
    assert efficacy_category("Adults need 90 mg of vitamin C") == "other"


def test_verify_items_use_frozen_evidence_and_gold_verdicts(tmp_path):
    t = tune()
    frozen = FrozenEvidence.load(recorded(tmp_path))
    items = verify_items(t, frozen)
    assert [(i.item_id, i.gold) for i in items] == [
        ("v01:c1", "CONTRADICTED"), ("v02:c1", "INSUFFICIENT_EVIDENCE"), ("v02:c2", "SUPPORTED")]
    v01 = items[0].input
    assert "ev_11111111" in {e.evidence_id for e in v01.evidence}  # the cited paper is in front of the model
    assert v01.allow_unsupported  # efficacy claim, searches ran without error
    assert "ref_vitc01" in {e.evidence_id for e in items[2].input.evidence}
    # The side a paper was cited for is never in what the model sees.
    assert all("contradict" not in (e.query or "") for e in v01.evidence)


def test_unsupported_gold_label_is_a_verify_item(tmp_path):
    path = recorded(tmp_path)
    data = json.loads(path.read_text())
    data["claims"]["v02:c1"]["retrieved"] = []
    path.write_text(json.dumps(data))
    item = verify_items(tune(), FrozenEvidence.load(path, "retrieved"))[1]
    assert item.input.evidence == [] and item.input.allow_unsupported  # code answers UNSUPPORTED, no call


def test_missing_or_stale_frozen_evidence_is_an_error(tmp_path):
    path = recorded(tmp_path)
    data = json.loads(path.read_text())
    del data["claims"]["v02:c2"]
    data["claims"]["v01:c1"]["claim_text"] = "something else"
    path.write_text(json.dumps(data))
    with pytest.raises(FrozenEvidenceError, match="text changed"):
        verify_items(tune(), FrozenEvidence.load(path), ["v01"])
    with pytest.raises(FrozenEvidenceError, match="no frozen evidence"):
        verify_items(tune(), FrozenEvidence.load(path), ["v02"])
    data["split"] = "test"
    path.write_text(json.dumps(data))
    with pytest.raises(FrozenEvidenceError, match="tune"):
        FrozenEvidence.load(path)


# ------------------------------------------------------------------ frozen retrieval


def test_recorder_spends_the_full_search_budget_once_per_claim(tmp_path):
    retriever, refs = FakeRetriever(), FakeReferences()
    claims = Recorder(retriever, refs).record(tune())
    assert sorted(claims) == ["v01:c1", "v02:c1", "v02:c2"]
    assert all(1 <= len(c["queries"]) <= 3 for c in claims.values())
    assert len(retriever.queries) == sum(len(c["queries"]) for c in claims.values())
    assert refs.searched == ["The recommended daily vitamin C intake for adults is 90 mg"]  # fact_of_record only
    assert [r["pmid"] for r in claims["v01:c1"]["cited"]] == ["11111111"]
    assert claims["v02:c2"]["cited"][0]["abstract"] == "Adults need 90 mg of vitamin C a day."
    # Resuming keeps what was recorded and makes no new request...
    again = FakeRetriever()
    assert Recorder(again, refs).record(tune(), existing=claims) == claims and again.queries == []
    # ...except for a claim whose search failed, which is recorded again.
    failed = {**claims, "v02:c1": {**claims["v02:c1"], "errors": ["PubMed retrieval failed for 'x': 502"]}}
    redo = Recorder(again, refs).record(tune(), existing=failed)
    assert again.queries and redo["v02:c1"]["errors"] == []


def test_search_errors_make_a_claim_ineligible_for_unsupported(tmp_path):
    path = recorded(tmp_path, FakeRetriever(fail_on="flu"))
    entry = FrozenEvidence.load(path).entry("v01:c1")
    assert entry.errors and not entry.allow_unsupported


def test_frozen_file_is_identical_for_every_candidate(tmp_path):
    path = recorded(tmp_path)
    data = json.loads(path.read_text())
    assert data["format"] == FORMAT and data["split"] == "tune"
    a = FrozenEvidence.load(path).entry("v01:c1").evidence
    b = FrozenEvidence.load(path).entry("v01:c1").evidence
    assert a == b


def test_compose_keeps_every_cited_item_under_the_cap():
    retrieved = [to_evidence(article(str(30000000 + i), f"Hot water trial {i}", "hot water flu adults"), "q")
                 for i in range(10)]
    cited = [to_evidence(article("11111111", "Unrelated title", "nothing"), "gold-cited")]
    out = compose("Hot water cures the flu", "research_question", retrieved, cited)
    assert len(out) == 10 and "ev_11111111" in {e.evidence_id for e in out}


# ------------------------------------------------------------------ dry run


def test_dry_run_counts_items_tokens_and_cost_and_calls_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ex, "default_client_factory", never_called)
    p = plan(tmp_path)
    est = ex.estimate(p)
    assert {s: d["items"] for s, d in est["steps"].items()} == {
        "extract_claims": 2, "analyze_stance": 3, "verify_claims": 3}
    haiku, sonnet = est["steps"]["verify_claims"]["candidates"]
    assert haiku["calls"] == 3 and haiku["input_tokens"] > 0
    assert 0 < haiku["expected_usd"] < sonnet["expected_usd"] <= sonnet["upper_bound_usd"]
    assert est["total_expected_usd"] > 0 and not est["unpriced_candidates"]

    frozen = recorded(tmp_path)
    rc = cli.main(["run", "--golden-dir", str(GOLDEN), "--candidates", str(candidates_file(tmp_path)),
                   "--frozen-evidence", str(frozen), "--max-usd", "100", "--out", str(tmp_path / "out")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry_run" in out and "| verify_claims | 3 |" in out
    assert not (tmp_path / "out" / "routing_v2.yaml").exists()


def test_dry_run_without_frozen_evidence_uses_assumed_sizes(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "default_client_factory", never_called)
    p = ex.build_plan(tune(), ex.load_candidates(), load_routing(), allow_assumed_evidence=True)
    est = ex.estimate(p)
    assert est["evidence_assumed"] and est["notes"]
    with pytest.raises(ex.ExperimentError):
        ex.build_plan(tune(), ex.load_candidates(), load_routing())


def test_repo_candidates_file_matches_the_leads_set():
    cf = ex.load_candidates()
    routing = load_routing()
    models = {s: [c.model for c in cands] for s, cands in cf.candidates.items()}
    assert models["extract_claims"][:2] == models["analyze_stance"][:2] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert models["verify_claims"][:2] == ["claude-sonnet-5-5", "claude-opus-5-5"]
    for step, cands in cf.candidates.items():
        assert cands[2].provider == "openai" and cands[2].reasoning_tokens > 0
        # T45 adds one sonnet candidate with the new prompt to extract and stance only.
        extra = {"extract_claims": "extract_v3", "analyze_stance": "stance_v2"}.get(step)
        assert [(c.model, c.prompt) for c in cands[3:]] == ([("claude-sonnet-5-5", extra)] if extra else [])
        # Every candidate is either priced or a TODO placeholder a live run refuses.
        assert all(routing.price(c.model) is not None or c.placeholder for c in cands)


def openai_plan(tmp_path, model="gpt-4o-2024-08-06", reasoning=0):
    p = plan(tmp_path, steps=("verify_claims",))
    extra = ex.ExperimentCandidate(provider="openai", model=model, prompt="verify_v3", reasoning_tokens=reasoning)
    p.candidates.candidates["verify_claims"].append(extra)
    return p


def test_reasoning_tokens_are_counted_as_output(tmp_path):
    plain = ex.estimate(openai_plan(tmp_path))["steps"]["verify_claims"]["candidates"][-1]
    reasoning = ex.estimate(openai_plan(tmp_path, reasoning=2000))["steps"]["verify_claims"]["candidates"][-1]
    assert reasoning["reasoning_tokens"] == 2000 * reasoning["calls"]
    extra = 2000 * reasoning["calls"] * load_routing().price("gpt-4o-2024-08-06").output / 1e6
    assert reasoning["expected_usd"] == pytest.approx(plain["expected_usd"] + extra, abs=1e-3)
    assert reasoning["upper_bound_usd"] > plain["upper_bound_usd"]


def test_placeholder_model_ids_are_refused_by_a_live_run(tmp_path):
    p = openai_plan(tmp_path, model="TODO-gpt-5-dated-snapshot-id")
    est = ex.estimate(p)
    assert est["placeholder_candidates"] == ["openai/TODO-gpt-5-dated-snapshot-id@verify_v3"]
    assert "TODO placeholder" in ex.render_markdown(est)
    with pytest.raises(ex.LiveRunRefused, match="placeholder"):
        ex.live_run(p, live=True, max_usd=1000, client_factory=never_called)


def test_verifier_sharing_the_critics_provider_is_flagged(tmp_path):
    p = openai_plan(tmp_path)  # the configured critic is OpenAI
    est = ex.estimate(p)
    assert len(est["critic_provider_warnings"]) == 1 and "openai/gpt-4o" in est["critic_provider_warnings"][0]
    # Make the OpenAI verifier win: only it answers correctly on the CONTRADICTED claim.
    def factory():
        def right(model, request):
            out = responder(model, request)
            if "flu" in request.input["messages"][0]["content"].lower():
                ids = re.findall(r"id: (ev_\d+)", request.input["messages"][0]["content"])
                out = {**out, "verdict": "CONTRADICTED", "contradicting_evidence_ids": ids[:1]}
            return out
        return {"anthropic": MockModelClient(responder), "openai": MockModelClient(right)}
    report = ex.live_run(p, live=True, max_usd=50, client_factory=factory)
    assert report["steps"]["verify_claims"]["selection"]["winner"]["candidate"]["provider"] == "openai"
    assert "same provider" in report["critic_same_provider"]
    assert "WARNING" in ex.render_markdown(report)
    clean = ex.live_run(plan(tmp_path, steps=("verify_claims",)), live=True, max_usd=50, client_factory=mock_clients())
    assert clean["critic_same_provider"] is None


# ------------------------------------------------------------------ live-run safeguards


@pytest.mark.parametrize("argv, message", [
    (["--live"], "needs --max-usd"),
    (["--live", "--max-usd", "0.000001"], "exceeds the cap"),
    (["--live", "--max-usd", "-5"], "positive"),
])
def test_live_run_is_refused_before_any_call(tmp_path, capsys, argv, message):
    frozen = recorded(tmp_path)
    rc = cli.cmd_run(cli.build_parser().parse_args(
        ["run", "--golden-dir", str(GOLDEN), "--candidates", str(candidates_file(tmp_path)),
         "--frozen-evidence", str(frozen), *argv]), client_factory=never_called)
    assert rc == 2
    assert message in capsys.readouterr().err


def test_live_needs_both_flags_in_the_api_too(tmp_path):
    p = plan(tmp_path)
    with pytest.raises(ex.LiveRunRefused, match="--live"):
        ex.live_run(p, live=False, max_usd=100, client_factory=never_called)
    with pytest.raises(ex.LiveRunRefused, match="--max-usd"):
        ex.live_run(p, live=True, max_usd=None, client_factory=never_called)


def test_unpriced_candidate_or_assumed_evidence_refuses_a_live_run(tmp_path):
    p = plan(tmp_path)
    p.routing = p.routing.model_copy(update={"pricing": {}})
    with pytest.raises(ex.LiveRunRefused, match="without a price"):
        ex.live_run(p, live=True, max_usd=1000, client_factory=never_called)
    p2 = ex.build_plan(tune(), ex.load_candidates(candidates_file(tmp_path)), load_routing(),
                       allow_assumed_evidence=True)
    with pytest.raises(ex.LiveRunRefused, match="frozen"):
        ex.live_run(p2, live=True, max_usd=1000, client_factory=never_called)


def test_spend_guard_refuses_a_call_that_could_cross_the_cap():
    guard = SpendGuard(cap_usd=0.01, pricing={"m": ModelPrice(input=10.0, output=10.0)})
    client = GuardedClient(MockModelClient("ok", input_tokens=200, output_tokens=50), guard)
    small = ModelRequest(step="analyze_stance", prompt_version="v", input={"messages": [], "max_tokens": 100})
    client.complete("m", small)
    assert guard.calls == 1 and guard.spent_usd == pytest.approx(0.0025)
    big = ModelRequest(step="analyze_stance", prompt_version="v", input={"messages": [], "max_tokens": 5000})
    with pytest.raises(SpendCapError):
        client.complete("m", big)
    assert client.inner.calls and len(client.inner.calls) == 1  # the refused call never reached the client
    with pytest.raises(SpendCapReached):
        guard.check()
    with pytest.raises(SpendCapError, match="no price"):
        GuardedClient(MockModelClient("ok"), SpendGuard(cap_usd=1, pricing={})).complete("x", small)
    with pytest.raises(ValueError):
        SpendGuard(cap_usd=0, pricing={})


def test_spend_guard_books_failed_calls_conservatively():
    guard = SpendGuard(cap_usd=1.0, pricing={"m": ModelPrice(input=1.0, output=1.0)})
    client = GuardedClient(MockModelClient("ok", failures=[ModelServerError("boom")]), guard)
    req = ModelRequest(step="s", prompt_version="v", input={"messages": [], "max_tokens": 100})
    with pytest.raises(ModelServerError):
        client.complete("m", req)
    assert guard.spent_usd > 0


def test_live_run_stops_at_the_cap_and_never_exceeds_it(tmp_path):
    p = plan(tmp_path)
    est = ex.estimate(p)
    cap = est["total_expected_usd"] * 1.0001  # passes the pre-check; long answers then hit the cap
    report = ex.live_run(p, live=True, max_usd=cap,
                         client_factory=mock_clients(input_tokens=100, output_tokens=2_000))
    assert report["stopped"] and report["spend"]["stopped_at_cap"]
    assert report["spend"]["spent_usd"] <= cap
    assert report["spend"]["refused_calls"] >= 1


def test_spend_guard_adapts_when_the_provider_counts_more_tokens_than_estimated(tmp_path):
    p = plan(tmp_path, steps=("analyze_stance",))
    cap = ex.estimate(p)["total_expected_usd"] * 1.0001
    first_call = {}

    def factory():
        client = MockModelClient(responder, input_tokens=200_000, output_tokens=10)
        orig = client.complete

        def complete(model, request):
            out = orig(model, request)
            first_call.setdefault("usd", 200_000 * load_routing().price(model).input / 1e6)
            return out
        client.complete = complete
        return {"anthropic": client}

    report = ex.live_run(p, live=True, max_usd=cap, client_factory=factory)
    assert report["stopped"]
    # Over by at most the single call that revealed the under-estimate; then it stops.
    assert report["spend"]["calls"] == 1
    assert report["spend"]["spent_usd"] <= cap + first_call["usd"]


def test_live_run_with_mock_clients_selects_reports_and_proposes(tmp_path):
    before = hashlib.sha256(DEFAULT_ROUTING_PATH.read_bytes()).hexdigest()
    p = plan(tmp_path)
    report = ex.live_run(p, live=True, max_usd=50, client_factory=mock_clients())
    assert not report["stopped"]
    for step in ("extract_claims", "analyze_stance", "verify_claims"):
        d = report["steps"][step]
        assert len(d["results"]) == 2 and d["selection"]["winner"] is not None
        assert all(r["cost_per_item"] is not None and r["latency_p95_ms"] is not None for r in d["results"])
    # Same answers from both: the cheaper (haiku) wins the tie (§13).
    assert report["steps"]["analyze_stance"]["selection"]["winner"]["candidate"]["model"] == "claude-haiku-5-5"
    assert report["steps"]["analyze_stance"]["results"][0]["score"] == 1.0  # the mock reads the debunk right
    assert report["steps"]["analyze_stance"]["extras"]["anthropic/claude-haiku-5-5@stance_v1"]["debunk_recall"] == 1.0
    assert "insufficient_called_contradicted" in report["steps"]["verify_claims"]["extras"][
        "anthropic/claude-haiku-5-5@verify_v3"]
    assert 0 < report["spend"]["spent_usd"] <= 50

    paths = ex.write_outputs(report, tmp_path / "out")
    proposed = load_routing(paths["routing_v2"])
    assert proposed.version == "routing_v2" and proposed.status == "provisional"  # critic/judge not measured
    assert proposed.route("analyze_stance").model == "claude-haiku-5-5"
    assert proposed.route("critique") == load_routing().route("critique")
    assert "PROPOSED" in Path(paths["routing_v2"]).read_text()
    md = Path(paths["report_md"]).read_text()
    assert "Chosen: **anthropic/claude-haiku-5-5@stance_v1**" in md
    assert json.loads(Path(paths["report_json"]).read_text())["spend"]["calls"] > 0
    assert hashlib.sha256(DEFAULT_ROUTING_PATH.read_bytes()).hexdigest() == before


def test_runner_never_writes_config_routing_yaml(tmp_path, monkeypatch):
    p = plan(tmp_path)
    report = ex.live_run(p, live=True, max_usd=50, client_factory=mock_clients())
    monkeypatch.setattr(ex, "PROPOSED_VERSION", "routing")
    with pytest.raises(ex.ExperimentError, match="never edits"):
        ex.write_outputs(report, DEFAULT_ROUTING_PATH.parent)


def test_cli_live_run_end_to_end_with_mock_clients(tmp_path, capsys):
    frozen = recorded(tmp_path)
    rc = cli.cmd_run(cli.build_parser().parse_args(
        ["run", "--golden-dir", str(GOLDEN), "--candidates", str(candidates_file(tmp_path, steps=("analyze_stance",))),
         "--frozen-evidence", str(frozen), "--live", "--max-usd", "5", "--out", str(tmp_path / "o")]),
        client_factory=mock_clients())
    assert rc == 0 and (tmp_path / "o" / "routing_v2.yaml").exists()
    assert "Spend:" in capsys.readouterr().out


def test_fallback_is_off_during_the_experiment():
    base = ex.experiment_base(load_routing())
    assert base.fallback.use is None and all(r.fallback is None for r in base.steps.values())


# ------------------------------------------------------------------ selection hook


def test_evaluate_candidate_run_item_counts_errors_and_fallbacks_as_failures():
    routing = load_routing()
    items = [StepItem(item_id=str(i), input={"messages": []}, gold="ENDORSES") for i in range(3)]
    cand = Candidate(provider="anthropic", model="claude-haiku-5-5", prompt="stance_v1")
    client = MockModelClient("ENDORSES", failures=[None, ModelServerError(), ModelServerError()])
    seen = []

    def run_item(router, item):
        try:
            return router.call("analyze_stance", item.input).output
        except Exception:
            return "UNCLEAR"  # a node's safe default; still a failure for the candidate

    res = evaluate_candidate("analyze_stance", cand, items, base_config=ex.experiment_base(routing),
                             clients={"anthropic": client}, scorer=label_macro_f1(["ENDORSES", "UNCLEAR"]),
                             run_item=run_item, after_item=lambda i, o: seen.append(o))
    assert res.n_failed == 1 and seen == ["ENDORSES", None, "ENDORSES"]


def test_token_estimate_grows_with_the_request():
    small = estimate_input_tokens("sys", {"messages": [{"role": "user", "content": "x" * 10}]})
    big = estimate_input_tokens("sys", {"messages": [{"role": "user", "content": "x" * 10_000}]})
    assert big - small == pytest.approx(9_990 / 3.5, abs=2)
