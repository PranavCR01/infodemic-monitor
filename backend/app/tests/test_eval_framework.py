"""Evaluation dataset, runner, comparison and routing harness (sections 13, 14).

Uses the synthetic fixtures in fixtures/eval and mocked models only.
"""
import json
from pathlib import Path

import pytest

from app.core.routing import ModelServerError, ModelTimeoutError, load_routing, parse_routing
from app.core.routing.mock import MockModelClient
from app.core.schemas.pipeline import ClassificationResult, MisinfoLabel
from app.evaluation import cli
from app.evaluation.baseline import SingleCallBaseline
from app.evaluation.compare import compare_runs
from app.evaluation.dataset import (
    DatasetError,
    assign_split,
    dataset_hash,
    labeller_agreement,
    load_dataset,
)
from app.evaluation.records import EvidenceRef, PredictedClaim, VideoPrediction
from app.evaluation.runner import RunConfig, load_run, load_run_config, run_evaluation
from app.evaluation.scoring import TRACKED_FAILURES, score_predictions
from app.evaluation.selection import (
    Budget,
    Candidate,
    CandidateResult,
    StepItem,
    apply_selection,
    claim_set_f1,
    evaluate_candidate,
    label_macro_f1,
    select_model,
)

FIXTURES = Path(__file__).parent / "fixtures" / "eval"
BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


@pytest.fixture
def ds():
    return load_dataset(FIXTURES, version="fixture-1")


# --- dataset -----------------------------------------------------------------

def test_dataset_loads_both_levels(ds):
    assert len(ds.videos) == 6
    v02 = ds.video("v02")
    assert v02.label == MisinfoLabel.DEBUNKING
    c = v02.claims[0]
    assert (c.truth, c.stance, c.source) == ("CONTRADICTED", "REFUTES", "both")
    assert ds.video("v01").claims[0].relevant_pmids == ["1001", "1002"]
    assert ds.video("v04").claims[0].truth == "INSUFFICIENT_EVIDENCE"  # CANNOT_RECOGNIZE mapped
    assert ds.video("v06").claims == []
    assert ds.inputs["v02"].fusion.visual_text == "MYTH: GARLIC STOPS COLDS"


def test_split_is_by_video_with_no_overlap(ds):
    tune = {v.video_id for v in ds.split("tune")}
    test = {v.video_id for v in ds.split("test")}
    assert tune == {"v05", "v06"} and test == {"v01", "v02", "v03", "v04"}
    assert not tune & test
    assert len(ds.split("all")) == 6
    with pytest.raises(DatasetError):
        ds.split("train")


def test_assigned_split_is_deterministic():
    assert assign_split("v42") == assign_split("v42")
    assert {assign_split(f"v{i}") for i in range(50)} == {"tune", "test"}


def test_dataset_hash_is_recorded_and_pinned(ds, tmp_path):
    assert ds.hash == dataset_hash(FIXTURES)
    with pytest.raises(DatasetError, match="hash mismatch"):
        load_dataset(FIXTURES, expected_hash="0" * 64)
    copy = tmp_path / "ds"
    copy.mkdir()
    for name in ("videos.csv", "claims.csv", "inputs.jsonl"):
        (copy / name).write_text((FIXTURES / name).read_text())
    assert dataset_hash(copy) == ds.hash
    (copy / "claims.csv").write_text((FIXTURES / "claims.csv").read_text().replace("cures", "treats"))
    assert dataset_hash(copy) != ds.hash


def test_hard_case_coverage_report(ds):
    cov = ds.coverage()
    assert cov["debunking"] == 1 and cov["prompt_injection"] == 1
    assert cov["satire_sarcasm"] == 0  # missing categories are visible, not hidden


def test_label_consistency_check(ds, tmp_path):
    assert ds.label_inconsistencies() == []
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "videos.csv").write_text("video_id,video_level_label\nv1,NO_MISINFO\n")
    (bad / "claims.csv").write_text(
        "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\n"
        "v1,c1,X cures Y,MISINFO,ENDORSES\n")
    assert load_dataset(bad).label_inconsistencies() == ["v1: labelled NO_MISINFO, claims imply MISINFO"]


@pytest.mark.parametrize("videos,claims,match", [
    ("video_id,video_level_label\nv1,FAKE\n", "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\n", "unknown video label"),
    ("video_id,video_level_label\nv1,MISINFO\nv1,MISINFO\n", "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\n", "duplicate video_id"),
    ("video_id,video_level_label\nv1,MISINFO\n", "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\nv2,c1,x,MISINFO,ENDORSES\n", "unknown video"),
    ("video_id,video_level_label\nv1,MISINFO\n", "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\nv1,c1,x,MISINFO,LOVES\n", "unknown stance"),
    ("video_id,video_level_label\nv1,MISINFO\n", "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\nv1,c1,x,WRONGISH,ENDORSES\n", "unknown claim truth"),
    ("video_id,video_level_label,categories\nv1,MISINFO,fun\n", "video_id,claim_id,claim_text,ground_truth_label,speaker_stance\n", "unknown categories"),
])
def test_dataset_validation_errors(tmp_path, videos, claims, match):
    (tmp_path / "videos.csv").write_text(videos)
    (tmp_path / "claims.csv").write_text(claims)
    with pytest.raises(DatasetError, match=match):
        load_dataset(tmp_path)


def test_shared_claim_level_dataset_loads():
    """The real shared set (research/claim-level/dataset) uses the same loader; it is empty for now."""
    ds = load_dataset(REPO / "research" / "claim-level" / "dataset")
    assert ds.videos == []


def test_labeller_agreement_kappa_and_disagreements(ds):
    second = load_dataset(FIXTURES / "second_labeller")
    report = labeller_agreement(ds, second)
    assert report.videos_compared == 4 and report.claims_compared == 5
    assert report.stance_kappa == 1.0
    assert 0 < report.video_label_kappa < 1
    assert any("v04/c1: truth" in d for d in report.disagreements)


# --- systems -----------------------------------------------------------------

class FakeProvider:
    """Stands in for the single-call classifier; makes no API call."""

    def __init__(self, labels):
        self.labels = labels

    def classify(self, fusion):
        label = self.labels(fusion)
        return ClassificationResult(
            label=label, confidence=0.9, explanation="fake", evidence_snippets=[],
            provider="fake", model_used="fake-model-1", latency_ms=120,
        )


def baseline_that_says_misinfo_for_myths():
    def labels(fusion):
        text = fusion.combined_content.lower()
        if "cures" in text or "garlic" in text:  # mistakes the debunk for promotion
            return MisinfoLabel.MISINFO
        if "vitamin" in text:
            return MisinfoLabel.NO_MISINFO
        return MisinfoLabel.CANNOT_RECOGNIZE
    return SingleCallBaseline(FakeProvider(labels))


class ScriptedGraph:
    """A claim-level system with fixed outputs, to exercise every metric."""

    name = "graph-mock"

    def __init__(self, outputs):
        self.outputs = outputs

    def predict(self, video):
        out = self.outputs[video.video_id]
        if isinstance(out, Exception):
            raise out
        return out

    def versions(self):
        return {"verify_claims": {"model": "from-config", "prompt": "verify_v1"}}


def _claim(cid, text, stance, verdict, *, source=None, retrieved=(), cited=(), initial=None, critic=()):
    return PredictedClaim(
        claim_id=cid, claim_text=text, stance=stance, verdict=verdict, source=source,
        retrieved=[EvidenceRef(evidence_id=e, pmid=p) for e, p in retrieved],
        cited_evidence_ids=list(cited), initial_verdict=initial, critic_decisions=list(critic),
    )


def graph_outputs():
    return {
        "v01": VideoPrediction(
            video_id="v01", label=MisinfoLabel.MISINFO, confidence=0.8, cost_usd=0.02,
            claims=[_claim("c1", "Drinking hot water cures the flu", "ENDORSES", "CONTRADICTED",
                           source="speech", retrieved=[("ev1", "1001"), ("ev2", "9999")], cited=["ev1"],
                           initial="CONTRADICTED", critic=["APPROVE"])],
            trace=[{"step": "critique", "claim_id": "c1", "decision": "APPROVE"}],
        ),
        "v02": VideoPrediction(
            video_id="v02", label=MisinfoLabel.DEBUNKING, confidence=0.7, cost_usd=0.03,
            claims=[_claim("c1", "Garlic stops colds", "REFUTES", "CONTRADICTED", source="both",
                           retrieved=[("ev3", "2001")], cited=["ev3"], initial="SUPPORTED",
                           critic=["REVISE_VERIFICATION", "APPROVE"])],
        ),
        "v03": VideoPrediction(
            video_id="v03", label=MisinfoLabel.NO_MISINFO, confidence=0.9, cost_usd=0.02,
            claims=[_claim("c1", "Vitamin D supports bone health in older adults", "ENDORSES", "SUPPORTED",
                           source="speech", retrieved=[("ev4", "3001")], cited=["ev4", "ev_fake"])],
        ),
        "v04": VideoPrediction(
            # Calls an untested claim contradicted and promotes it: two tracked failures.
            video_id="v04", label=MisinfoLabel.MISINFO, confidence=0.6, cost_usd=0.04,
            review_required=True, review_reasons=["low confidence"],
            claims=[_claim("c1", "Herb X boosts immunity by 300 percent", "ENDORSES", "CONTRADICTED",
                           source="screen", retrieved=[("ev5", "4444")], cited=["ev5"],
                           initial="CONTRADICTED", critic=["RETRIEVE_MORE", "APPROVE"])],
            trace=[{"step": "critique", "claim_id": "c1", "decision": "RETRIEVE_MORE"},
                   {"step": "judge"}],  # the graph moved on without searching again
        ),
    }


def run_cfg(**kw):
    return RunConfig(benchmark="unit", dataset={"path": str(FIXTURES), "version": "fixture-1"},
                     metrics=["macro_f1", "accuracy", "false_misinfo_on_debunking", "cost_per_video",
                              "latency_p95_ms", "claim_recall"], **kw)


# --- runner ------------------------------------------------------------------

def test_baseline_run_records_everything(ds, tmp_path):
    routing = load_routing()
    record = run_evaluation(run_cfg(), baseline_that_says_misinfo_for_myths(), dataset=ds,
                            routing=routing, output_dir=tmp_path, code_revision="abc123")
    assert record.n_videos == 4 and record.split == "test"
    assert record.dataset_hash == ds.hash and record.dataset_version == "fixture-1"
    assert record.code_revision == "abc123"
    assert record.routing_hash == routing.config_hash()
    assert record.config_hash == run_cfg().config_hash()
    assert record.model_versions == {"classify": {"provider": "fake", "model": "fake-model-1"}}
    assert record.metrics["false_misinfo_on_debunking"] == 1.0
    assert record.metrics["claim_recall"] is None  # baseline has no claims: not applicable
    assert record.metrics["latency_p95_ms"] == 120
    assert set(record.metrics) == set(run_cfg().metrics)
    assert record.tracked_failures["debunking_as_promotion"]["videos"]["items"] == ["v02"]

    out = Path(record.output_dir)
    assert load_run(out) == record
    preds = [json.loads(line) for line in (out / "predictions.jsonl").read_text().splitlines()]
    assert [p["video_id"] for p in preds] == ["v01", "v02", "v03", "v04"]
    traces = [json.loads(line) for line in (out / "traces.jsonl").read_text().splitlines()]
    assert traces[0]["trace"][0]["model"] == "fake-model-1"


def test_save_options_can_skip_predictions(ds, tmp_path):
    cfg = run_cfg(save={"predictions": False, "traces": False})
    record = run_evaluation(cfg, baseline_that_says_misinfo_for_myths(), dataset=ds, output_dir=tmp_path)
    assert sorted(p.name for p in Path(record.output_dir).iterdir()) == ["run.json"]


def test_failed_video_is_recorded_not_fatal(ds, tmp_path):
    outputs = graph_outputs()
    outputs["v03"] = RuntimeError("provider exploded")
    record = run_evaluation(run_cfg(), ScriptedGraph(outputs), dataset=ds, output_dir=tmp_path)
    assert record.n_errors == 1 and record.n_videos == 4


def test_run_refuses_mismatched_dataset_hash(ds, tmp_path):
    cfg = RunConfig(benchmark="u", dataset={"path": str(FIXTURES), "hash": "f" * 64})
    with pytest.raises(ValueError, match="hash mismatch"):
        run_evaluation(cfg, baseline_that_says_misinfo_for_myths(), dataset=ds, output_dir=tmp_path)


def test_run_requires_inputs_for_every_video(tmp_path):
    for name in ("videos.csv", "claims.csv"):
        (tmp_path / name).write_text((FIXTURES / name).read_text())
    cfg = RunConfig(benchmark="u", dataset={"path": str(tmp_path)})
    with pytest.raises(ValueError, match="no inputs"):
        run_evaluation(cfg, baseline_that_says_misinfo_for_myths(), output_dir=tmp_path / "out")


def test_unknown_metric_rejected():
    with pytest.raises(ValueError, match="unknown metrics"):
        RunConfig(benchmark="u", dataset={"path": "x"}, metrics=["vibes"])


def test_repo_benchmark_config_is_valid():
    cfg = load_run_config(BACKEND / "config" / "benchmarks" / "infodemic_v1.yaml")
    assert cfg.pipeline.system == "baseline" and cfg.split == "test"


# --- scoring -----------------------------------------------------------------

def test_claim_level_scoring_and_tracked_failures(ds):
    videos = ds.split("test")
    metrics, failures = score_predictions(videos, graph_outputs())
    assert metrics["macro_f1"] is not None
    assert metrics["claim_recall"] == pytest.approx(4 / 5)   # v03/c2 missed
    assert metrics["claim_precision"] == 1.0
    assert metrics["claim_source_accuracy"] == 1.0
    assert metrics["stance_debunk_recall"] == 1.0
    assert metrics["verification_prf"]["CONTRADICTED"]["precision"] == pytest.approx(2 / 3)
    assert metrics["retrieval_recall_at_k"] == pytest.approx((0.5 + 1 + 1) / 3)
    assert metrics["citation_validity"] == pytest.approx(4 / 5)  # ev_fake was never retrieved
    assert metrics["critic_errors_caught"] == 1.0  # v02's wrong first verdict was challenged
    # Both interventions (v02 revise, v04 retrieve) were on verdicts that really were wrong.
    assert metrics["critic_unnecessary_retries"] == 0.0
    assert metrics["citation_support"] == 1.0  # ev1, ev3, ev4 are gold-relevant; ev_fake excluded
    assert metrics["review_share"] == 0.25
    assert metrics["cost_per_video"] == pytest.approx(0.0275)
    assert metrics["calibration_error"] is not None and len(metrics["reliability_diagram"]) == 10

    assert set(failures) == set(TRACKED_FAILURES)
    assert failures["insufficient_called_contradicted"]["items"] == ["v04/c1"]
    assert failures["critic_ignored"] == {"count": 1, "of": 1, "items": ["v04/c1"]}
    assert failures["prompt_injection"]["items"] == ["v04"]
    assert failures["speech_screen_disagreement"]["count"] == 0
    assert failures["debunking_as_promotion"]["videos"]["count"] == 0
    assert failures["citation_laundering"]["count"] == 0  # ev5 is on a claim with no gold PMIDs


def test_critic_request_honoured_when_retrieval_follows(ds):
    outputs = graph_outputs()
    outputs["v04"].trace = [{"step": "critique", "claim_id": "c1", "decision": "RETRIEVE_MORE"},
                            {"step": "retrieve", "claim_id": "c1"}]
    _, failures = score_predictions(ds.split("test"), outputs)
    assert failures["critic_ignored"]["count"] == 0
    outputs["v04"].trace = [{"step": "critique", "claim_id": "c1", "decision": "RETRIEVE_MORE",
                             "budget_exhausted": True}]
    _, failures = score_predictions(ds.split("test"), outputs)
    assert failures["critic_ignored"]["count"] == 0


def test_unnecessary_critic_retry_counted(ds):
    outputs = graph_outputs()
    outputs["v01"].claims[0].critic_decisions = ["RETRIEVE_MORE", "APPROVE"]  # verdict was already right
    metrics, _ = score_predictions(ds.split("test"), outputs)
    assert metrics["critic_unnecessary_retries"] == pytest.approx(1 / 3)


def test_citation_laundering_counted(ds):
    outputs = graph_outputs()
    outputs["v01"].claims[0].cited_evidence_ids = ["ev2"]  # real retrieved paper, not one bearing on the claim
    _, failures = score_predictions(ds.split("test"), outputs)
    assert failures["citation_laundering"]["items"] == ["v01/c1:ev2"]


# --- comparison ----------------------------------------------------------------

def _two_runs(ds, tmp_path):
    base = run_evaluation(run_cfg(), baseline_that_says_misinfo_for_myths(), dataset=ds,
                          output_dir=tmp_path / "b", code_revision="r")
    cand = run_evaluation(run_cfg(), ScriptedGraph(graph_outputs()), dataset=ds,
                          output_dir=tmp_path / "c", code_revision="r")
    return base, cand


def test_candidate_must_beat_baseline_and_not_regress_guards(ds, tmp_path):
    base, cand = _two_runs(ds, tmp_path)
    # The baseline has no cost recorded, so "cost not worse" can't be shown: blocked by default.
    blocked = compare_runs(cand, base, ["false_misinfo_on_debunking"])
    assert not blocked.ships and any("cost_per_video: missing" in r for r in blocked.reasons)

    ok = compare_runs(cand, base, ["false_misinfo_on_debunking"], allow_missing_guards=["cost_per_video"])
    assert ok.ships, ok.reasons
    assert ok.primary[0].improved  # lower is better for false MISINFO on debunking

    reverse = compare_runs(base, cand, ["macro_f1"], guards=["macro_f1"])
    assert not reverse.ships


def test_runs_on_different_datasets_are_not_comparable(ds, tmp_path):
    base, cand = _two_runs(ds, tmp_path)
    other = cand.model_copy(update={"dataset_hash": "x"})
    result = compare_runs(other, base, ["macro_f1"], guards=[])
    assert not result.ships and "not comparable" in result.reasons[0]


def test_cost_regression_blocks(ds, tmp_path):
    base, cand = _two_runs(ds, tmp_path)
    base = base.model_copy(update={"metrics": {**base.metrics, "cost_per_video": 0.001}})
    result = compare_runs(cand, base, ["false_misinfo_on_debunking"])
    assert not result.ships and any("cost_per_video: worse" in r for r in result.reasons)


# --- routing harness -------------------------------------------------------------

STANCE_ITEMS = [
    StepItem(item_id="i1", input="That's a myth.", gold="REFUTES"),
    StepItem(item_id="i2", input="It cures the flu!", gold="ENDORSES"),
    StepItem(item_id="i3", input="My aunt says so.", gold="QUOTES"),
    StepItem(item_id="i4", input="Researchers are studying it.", gold="NEUTRAL"),
]
STANCE_LABELS = ("ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR")


def _routing():
    return parse_routing({
        "version": "harness_v0",
        "routing": {
            "extract_claims": {"provider": "anthropic", "model": "small-1", "prompt": "extract_v1"},
            "analyze_stance": {"provider": "anthropic", "model": "small-1", "prompt": "stance_v1"},
            "verify_claims": {"provider": "anthropic", "model": "strong-1", "prompt": "verify_v1"},
            "critique": {"provider": "openai", "model": "other-1", "prompt": "critic_v1"},
            "judge_explanation": {"provider": "anthropic", "model": "medium-1", "prompt": "explain_v1"},
            "fallback": {"on": ["timeout", "5xx"], "retries": 0,
                         "use": {"provider": "openai", "model": "backup-1"}},
        },
        "pricing": {"small-1": {"input": 0.1, "output": 0.5}, "medium-1": {"input": 2, "output": 10},
                    "strong-1": {"input": 4, "output": 20}},
    })


def _stance_client(accuracy_by_model):
    """Mock that answers stance items correctly for some models only."""
    gold = {i.input: i.gold for i in STANCE_ITEMS}

    def respond(model, request):
        correct = accuracy_by_model[model]
        idx = [i.input for i in STANCE_ITEMS].index(request.input)
        return gold[request.input] if idx < correct else "UNCLEAR"
    return MockModelClient(respond, input_tokens=1000, output_tokens=10)


def test_harness_picks_best_scoring_candidate_within_budget():
    client = _stance_client({"small-1": 2, "medium-1": 3, "strong-1": 4})
    clients = {"anthropic": client, "openai": MockModelClient("UNCLEAR")}
    scorer = label_macro_f1(STANCE_LABELS)
    results = [
        evaluate_candidate("analyze_stance", Candidate(provider="anthropic", model=m, prompt="stance_v1"),
                           STANCE_ITEMS, base_config=_routing(), clients=clients, scorer=scorer)
        for m in ("small-1", "medium-1", "strong-1")
    ]
    assert [r.score for r in results] == sorted(r.score for r in results)
    assert results[0].cost_per_item == pytest.approx((1000 * 0.1 + 10 * 0.5) / 1e6)

    best = select_model(results)
    assert best.winner.candidate.model == "strong-1"

    # Budget excludes the strongest model; next best within budget wins.
    capped = select_model(results, Budget(max_cost_per_item=0.003))
    assert capped.winner.candidate.model == "medium-1"
    assert "anthropic/strong-1@stance_v1" in capped.excluded


def test_harness_tie_goes_to_cheaper_then_faster():
    def result(model, score, cost, p95):
        return CandidateResult(candidate=Candidate(provider="p", model=model, prompt="s1"),
                               step="analyze_stance", metric="stance_macro_f1", score=score,
                               n_items=10, n_failed=0, fallbacks_used=0,
                               cost_per_item=cost, latency_p95_ms=p95)
    sel = select_model([result("big-1", 0.900, 0.01, 900), result("small-1", 0.895, 0.001, 300),
                        result("tiny-1", 0.70, 0.0001, 100)], tie_margin=0.01)
    assert sel.winner.candidate.model == "small-1"
    sel = select_model([result("a-1", 0.9, 0.001, 500), result("b-1", 0.9, 0.001, 200)])
    assert sel.winner.candidate.model == "b-1"


def test_harness_does_not_credit_a_candidate_for_fallback_answers():
    t = ModelTimeoutError()
    flaky = MockModelClient(lambda model, req: "REFUTES", failures=[t, None, t, None])
    backup = MockModelClient(lambda model, req: "REFUTES")
    r = evaluate_candidate("analyze_stance", Candidate(provider="anthropic", model="small-1", prompt="stance_v2"),
                           STANCE_ITEMS[:1] * 4, base_config=_routing(),
                           clients={"anthropic": flaky, "openai": backup}, scorer=label_macro_f1(STANCE_LABELS))
    assert r.fallbacks_used == 2 and r.n_failed == 2
    assert select_model([r]).winner is None  # default failure budget is zero
    assert select_model([r], Budget(max_failure_rate=0.5)).winner is not None


def test_harness_counts_hard_failures_as_wrong():
    e = ModelServerError(status=500)
    dead = MockModelClient("REFUTES", failures=[e] * 10)
    r = evaluate_candidate("analyze_stance", Candidate(provider="anthropic", model="small-1", prompt="s"),
                           STANCE_ITEMS[:1], base_config=_routing(),
                           clients={"anthropic": dead, "openai": MockModelClient(failures=[e] * 10)},
                           scorer=label_macro_f1(STANCE_LABELS))
    assert r.n_failed == 1 and r.score == 0.0


def test_claim_set_scorer():
    scorer = claim_set_f1()
    assert scorer([["Garlic stops colds"]], [["garlic stops colds"]]) == 1.0
    assert scorer([["Garlic stops colds"]], [["vaccines cause autism"]]) == 0.0
    assert scorer([["Garlic stops colds"]], [[]]) == 0.0  # extracting nothing scores zero


def test_apply_selection_writes_new_routing_version():
    client = _stance_client({"small-1": 1, "strong-1": 4})
    clients = {"anthropic": client, "openai": MockModelClient()}
    results = [evaluate_candidate("analyze_stance", Candidate(provider="anthropic", model=m, prompt="stance_v2"),
                                  STANCE_ITEMS, base_config=_routing(), clients=clients,
                                  scorer=label_macro_f1(STANCE_LABELS)) for m in ("small-1", "strong-1")]
    new = apply_selection(_routing(), [select_model(results)], version="harness_v1")
    route = new.route("analyze_stance")
    assert (route.model, route.prompt, new.version) == ("strong-1", "stance_v2", "harness_v1")
    assert new.status == "provisional"  # only one step measured
    assert new.config_hash() != _routing().config_hash()


# --- CLI ----------------------------------------------------------------------

def test_cli_validate_and_dataset_info(capsys):
    assert cli.main(["validate-routing"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "provisional"
    assert cli.main(["dataset-info", str(FIXTURES)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["videos"] == 6 and info["splits"] == {"tune": 2, "test": 4}


def test_cli_run_refuses_without_paid_flag(capsys):
    assert cli.main(["run", str(BACKEND / "config" / "benchmarks" / "infodemic_v1.yaml")]) == 2
    assert "--allow-paid" in capsys.readouterr().err


def test_cli_compare(ds, tmp_path, capsys):
    base, cand = _two_runs(ds, tmp_path)
    code = cli.main(["compare", cand.output_dir, base.output_dir,
                     "--primary", "false_misinfo_on_debunking", "--guards", "macro_f1"])
    assert code == 0, capsys.readouterr().out
