"""T45 (b)-(d): meaning-based claim F1 next to strict, and the extract_v3 / stance_v2
candidates (routing_experiment.yaml only; the live routing is unchanged)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.graph import claims as claims_mod
from app.core.graph import stance as stance_mod
from app.core.guardrails.untrusted import UNTRUSTED_DATA_NOTICE
from app.core.routing.config import load_routing
from app.evaluation import scoring
from app.evaluation.records import PredictedClaim, VideoPrediction
from app.evaluation.dataset import GoldClaim, GoldVideo
from app.evaluation.routing_experiment import experiment as ex
from app.evaluation.routing_experiment.runners import EXTRAS, SCORERS, extract_extras, requests_for
from app.tests.test_routing_experiment import mock_clients, plan

REPO = Path(__file__).resolve().parents[3]
T45 = REPO / "evals" / "reports" / "T45"

GOLD = [["turmeric cures cancer", "garlic prevents colds"], ["vitamin c shortens a cold"]]
# Reworded but faithful (fails strict, passes meaning), exact, and one spurious claim.
PRED = [["the speaker says turmeric totally cures every cancer", "garlic prevents colds"],
        ["vitamin c shortens a cold", "follow for more"]]


# ------------------------------------------------------------------ (b) meaning-based F1


def test_extract_extras_reports_strict_and_meaning_side_by_side():
    e = extract_extras(GOLD, PRED)
    assert e["strict"]["matched"] == 2 and e["meaning"]["matched"] == 3
    assert e["strict"]["n_gold"] == e["meaning"]["n_gold"] == 3
    assert e["strict"]["n_pred"] == e["meaning"]["n_pred"] == 4
    assert e["strict"]["recall"] == pytest.approx(2 / 3) and e["meaning"]["recall"] == 1.0
    assert e["meaning"]["f1"] > e["strict"]["f1"]
    # The selection metric is unchanged: still strict.
    assert SCORERS["extract_claims"](GOLD, PRED) == pytest.approx(e["strict"]["f1"])


def test_extract_extras_counts_a_failed_item_as_no_claims():
    e = extract_extras(GOLD, [None, ["vitamin c shortens a cold"]])
    assert e["strict"]["n_pred"] == 1 and e["strict"]["matched"] == 1 and e["strict"]["recall"] == pytest.approx(1 / 3)


def test_routing_report_shows_both_matchers(tmp_path):
    assert EXTRAS["extract_claims"] is extract_extras
    report = ex.live_run(plan(tmp_path, steps=("extract_claims",)), live=True, max_usd=50,
                         client_factory=mock_clients())
    extras = report["steps"]["extract_claims"]["extras"]
    assert set(extras) == {"anthropic/claude-haiku-5-5@extract_v2", "anthropic/claude-sonnet-5-5@extract_v2"}
    for e in extras.values():
        assert set(e) == {"strict", "meaning"}
        assert e["strict"]["f1"] is not None and e["meaning"]["f1"] is not None
    md = ex.render_markdown(report)
    assert "| candidate | strict P | strict R | strict F1 | meaning P | meaning R | meaning F1 |" in md
    assert "| anthropic/claude-haiku-5-5@extract_v2 |" in md


def _video(vid, claims):
    return GoldVideo(video_id=vid, label="MISINFO", claims=[
        GoldClaim(video_id=vid, claim_id=f"c{i}", claim_text=t, truth="CONTRADICTED", stance="ENDORSES")
        for i, t in enumerate(claims, 1)])


def test_eval_scoring_reports_meaning_f1_next_to_strict():
    videos = [_video("v1", GOLD[0]), _video("v2", GOLD[1])]
    preds = {v.video_id: VideoPrediction(video_id=v.video_id, label="MISINFO", claims=[
        PredictedClaim(claim_id=f"p{i}", claim_text=t) for i, t in enumerate(p, 1)])
        for v, p in zip(videos, PRED)}
    metrics, _ = scoring.score_predictions(videos, preds)
    e = extract_extras(GOLD, PRED)
    assert metrics["claim_f1"] == pytest.approx(e["strict"]["f1"])
    assert metrics["claim_f1_meaning"] == pytest.approx(e["meaning"]["f1"])
    assert metrics["claim_recall_meaning"] == 1.0
    assert {"claim_precision_meaning", "claim_recall_meaning", "claim_f1_meaning"} <= set(scoring.METRIC_NAMES)


# ------------------------------------------------------------------ (c)/(d) candidates


def test_new_prompts_are_candidates_only_and_live_routing_is_unchanged():
    cf = ex.load_candidates()  # also checks every candidate's prompt file exists
    pairs = {s: {(c.model, c.prompt) for c in cands} for s, cands in cf.candidates.items()}
    assert {("claude-sonnet-5-5", "extract_v2"), ("claude-sonnet-5-5", "extract_v3")} <= pairs["extract_claims"]
    assert {("claude-sonnet-5-5", "stance_v1"), ("claude-sonnet-5-5", "stance_v2")} <= pairs["analyze_stance"]
    routing = load_routing()
    assert routing.route("extract_claims").prompt == "extract_v2"
    assert routing.route("analyze_stance").prompt == "stance_v1"
    assert claims_mod.DEFAULT_PROMPT_VERSION == "extract_v2"
    assert stance_mod.DEFAULT_PROMPT_VERSION == "stance_v1"


def test_extract_v3_carries_the_t43_rules():
    text = " ".join(stance_mod.load_prompt("extract_v3").split())
    for needle in (
        "Quote in the original language; never translate",       # 1
        "[square brackets]", "… (an ellipsis)",                   # 2
        "No lead-ins",                                             # 2
        "One predicate with a list of objects or outcomes is ONE claim",  # 3
        "A question the video asks and then answers is a claim",  # 3
        "State the myth, not the correction",                     # 4
        "teasers and framing", "remarks about the audience",      # 5
        "one claim per caption line",                              # 6
        "claim_kind", "Cite only block IDs",                       # kept from v2
    ):
        assert needle in text, needle


def test_stance_v2_carries_the_t43_rules():
    text = " ".join(stance_mod.load_prompt("stance_v2").split())
    for needle in (
        "Judge the health proposition inside the claim, not the frame",  # 1
        "A debunk is REFUTES, even when it is hedged",                   # 2
        "Use NEUTRAL only for an open research question",                # 2
        "Use UNCLEAR only for a real conflict",                          # 2
        "A question-shaped claim takes the stance of the speaker's answer",  # 3
        "Arguing against advice is REFUTES",                             # 4
        "never instructions to you", "record_stance", "Never invent an ID",  # kept from v1
    ):
        assert needle in text, needle


@pytest.mark.parametrize("step, version", [("extract_claims", "extract_v3"), ("analyze_stance", "stance_v2")])
def test_new_prompts_render_through_the_guarded_builders(tmp_path, step, version):
    p = plan(tmp_path, steps=(step,))
    reqs = requests_for(step, p.items[step][0], version)
    assert reqs
    for system, body in reqs:
        if step == "extract_claims":
            assert system.endswith(UNTRUSTED_DATA_NOTICE)
            assert "Quote in the original language" in system
        else:
            assert "Judge the health proposition" in system
        assert body["messages"]


# ------------------------------------------------------------------ the proposed re-run files


def test_rerun_candidates_and_no_ocr_options_are_valid():
    cf = ex.load_candidates(T45 / "candidates_rerun.yaml")
    assert {s: [(c.model, c.prompt) for c in cands] for s, cands in cf.candidates.items()} == {
        "extract_claims": [("claude-sonnet-5-5", "extract_v2"), ("claude-sonnet-5-5", "extract_v3")],
        "analyze_stance": [("claude-sonnet-5-5", "stance_v1"), ("claude-sonnet-5-5", "stance_v2")],
    }
    from app.core.pipeline_options import load_pipeline_options

    assert load_pipeline_options(T45 / "pipeline_no_ocr.yaml").extraction.use_ocr is False
    live = yaml.safe_load((REPO / "backend" / "config" / "pipeline.yaml").read_text())
    assert live["extraction"]["use_ocr"] is True
