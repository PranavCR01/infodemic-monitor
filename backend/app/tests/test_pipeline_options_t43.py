"""T43: the use_ocr switch (config/pipeline.yaml). Mocked models only; no paid calls.

use_ocr lives in one config file, is applied outside the extraction node (provider
wiring and the routing experiment's item builder), defaults to true, and with false
the extractor sees the transcript alone while stance keeps OCR.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.core import pipeline_options as po
from app.core.graph import claims as claims_mod
from app.core.graph.routing import EXTRACT_CLAIMS
from app.core.graph.state import OcrSegment, TranscriptSegment
from app.core.routing.config import load_routing
from app.evaluation.routing_experiment import cli
from app.evaluation.routing_experiment import experiment as ex
from app.evaluation.routing_experiment.frozen import FrozenEvidence
from app.tests.test_routing_experiment import GOLDEN, candidates_file, mock_clients, recorded, tune

NO_OCR = po.parse_pipeline_options({"extraction": {"use_ocr": False}})


def state():
    t = [TranscriptSegment(segment_id="t1", start=0.0, end=2.0, text="Drink hot water every morning.")]
    o = [OcrSegment(segment_id="o1", start=0.0, end=2.0, text="HOT WATER CURES FLU", confidence=1.0),
         OcrSegment(segment_id="o2", start=5.0, end=6.0, text="GARLIC STOPS COLDS", confidence=1.0)]
    from app.core.graph.nodes import fuse_by_overlap
    return {"transcript_segments": t, "ocr_segments": o, "fused_segments": fuse_by_overlap(t, o)}


def test_repo_config_keeps_ocr_on_and_is_the_default():
    opts = po.load_pipeline_options()
    assert opts.extraction.use_ocr is True
    assert po.DEFAULT_OPTIONS.extraction.use_ocr is True
    raw = yaml.safe_load(po.DEFAULT_PIPELINE_OPTIONS_PATH.read_text())
    assert raw["extraction"]["use_ocr"] is True


def test_unknown_keys_and_missing_file_are_errors(tmp_path):
    with pytest.raises(Exception):
        po.parse_pipeline_options({"extraction": {"use_orc": False}})
    with pytest.raises(FileNotFoundError):
        po.load_pipeline_options(tmp_path / "nope.yaml")
    assert po.parse_pipeline_options(None).extraction.use_ocr is True


def test_extraction_input_drops_every_caption_only_when_off():
    s = state()
    assert po.extraction_input(s, po.DEFAULT_OPTIONS) == s
    off = po.extraction_input(s, NO_OCR)
    assert off["ocr_segments"] == []
    assert [f.on_screen for f in off["fused_segments"]] == [[]]  # caption-only o2 segment is gone too
    assert all(not any(x.startswith("o") for x in f.sources) for f in off["fused_segments"])
    assert len(s["ocr_segments"]) == 2 and len(s["fused_segments"]) == 2  # input not modified


def test_wrapped_node_sees_no_ocr_and_identity_when_on():
    seen = []

    def node(st):
        seen.append(st)
        return {"claims": []}

    assert po.wrap_extract_node(node, po.DEFAULT_OPTIONS) is node
    wrapped = po.wrap_extract_node(node, NO_OCR)
    assert wrapped(state()) == {"claims": []}
    assert seen[0]["ocr_segments"] == [] and all(not f.on_screen for f in seen[0]["fused_segments"])


def test_graph_provider_build_nodes_applies_the_switch(monkeypatch):
    from app.core.inference.providers import graph_provider as gp

    calls = {}

    def fake_make(caller, **kw):
        def node(st):
            calls["state"] = st
            return {"claims": []}
        return node

    monkeypatch.setattr(gp, "make_extract_claims", fake_make)
    monkeypatch.setattr(gp, "make_analyze_stance", lambda caller, **kw: (lambda st: {}))
    monkeypatch.setattr(gp, "make_verify_claims", lambda caller, **kw: (lambda st: {}))
    monkeypatch.setattr(gp, "make_critique_verification", lambda caller, **kw: (lambda st: {}))
    monkeypatch.setattr(gp, "make_judge_classification", lambda caller, **kw: (lambda st: {}))
    monkeypatch.setattr(gp, "make_retrieval_nodes", lambda retriever, **kw: {})
    on = gp.build_nodes(object(), object())  # default: config/pipeline.yaml (use_ocr: true)
    on[EXTRACT_CLAIMS](state())
    assert len(calls["state"]["ocr_segments"]) == 2
    off = gp.build_nodes(object(), object(), pipeline_options=NO_OCR)
    off[EXTRACT_CLAIMS](state())
    assert calls["state"]["ocr_segments"] == []


def test_extraction_node_code_does_not_read_the_flag():
    src = Path(claims_mod.__file__).read_text()
    assert "use_ocr" not in src and "pipeline_options" not in src


def _plan(tmp_path, options=po.DEFAULT_OPTIONS):
    frozen = FrozenEvidence.load(recorded(tmp_path))
    return ex.build_plan(tune(), ex.load_candidates(candidates_file(tmp_path)), load_routing(), frozen=frozen,
                         pipeline_options=options)


def test_experiment_without_ocr_changes_extraction_items_only(tmp_path):
    on, off = _plan(tmp_path), _plan(tmp_path, NO_OCR)
    v_on = {i.item_id: i.input for i in on.items["extract_claims"]}
    v_off = {i.item_id: i.input for i in off.items["extract_claims"]}
    assert v_on["v01"].ocr and not v_off["v01"].ocr
    assert all(not f.on_screen for f in v_off["v01"].fused)
    assert v_off["v01"].transcript == v_on["v01"].transcript
    # Stance still gets OCR.
    assert [i.input.ocr for i in off.items["analyze_stance"]] == [i.input.ocr for i in on.items["analyze_stance"]]
    assert any(i.input.ocr for i in off.items["analyze_stance"])
    est_on, est_off = ex.estimate(on), ex.estimate(off)
    assert est_on["use_ocr"] is True and est_off["use_ocr"] is False
    tok = lambda e: e["steps"]["extract_claims"]["candidates"][0]["input_tokens"]  # noqa: E731
    assert tok(est_off) < tok(est_on)
    assert "WITHOUT on-screen text" in ex.render_markdown(est_off)
    assert "WITHOUT on-screen text" not in ex.render_markdown(est_on)


def test_cli_pipeline_options_flag(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ex, "default_client_factory", lambda: pytest.fail("no client in a dry run"))
    off = tmp_path / "pipeline_no_ocr.yaml"
    off.write_text("version: pipeline_v1\nextraction:\n  use_ocr: false\n")
    frozen = recorded(tmp_path)
    rc = cli.main(["run", "--golden-dir", str(GOLDEN), "--candidates", str(candidates_file(tmp_path)),
                   "--frozen-evidence", str(frozen), "--pipeline-options", str(off), "--out", str(tmp_path / "o")])
    assert rc == 0
    assert json.loads((tmp_path / "o" / "report.json").read_text())["use_ocr"] is False


def test_live_run_records_use_ocr_and_per_item_outputs(tmp_path):
    p = _plan(tmp_path, NO_OCR)
    report = ex.live_run(p, live=True, max_usd=50, client_factory=mock_clients())
    assert report["pipeline_options"]["extraction"]["use_ocr"] is False
    paths = ex.write_outputs(report, tmp_path / "out")
    per = json.loads(Path(paths["per_item_json"]).read_text())
    assert "_per_item" not in json.loads(Path(paths["report_json"]).read_text())
    ext_items = per["steps"]["extract_claims"]["anthropic/claude-haiku-5-5@extract_v2"]
    assert [i["item_id"] for i in ext_items] == ["v01", "v02"]
    claim = ext_items[0]["output"][0]
    assert claim["text"] == "Drink hot water every morning"
    assert set(claim) >= {"start", "end", "source_segment_ids", "category"}
    stance = per["steps"]["analyze_stance"]["anthropic/claude-haiku-5-5@stance_v1"]
    assert [(i["item_id"], i["gold"], i["output"]) for i in stance][1] == ("v02:c1", "REFUTES", "REFUTES")
    verify = per["steps"]["verify_claims"]["anthropic/claude-sonnet-5-5@verify_v3"]
    assert all(i["output"] == "INSUFFICIENT_EVIDENCE" for i in verify)
