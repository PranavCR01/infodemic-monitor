"""The T18 smoke-run script's offline parts: golden-set transcript parsing and cost
arithmetic. No model or network is touched."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "smoke_run.py"


@pytest.fixture(scope="module")
def smoke():
    spec = importlib.util.spec_from_file_location("smoke_run", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEGMENTS = {"language": "en", "duration_seconds": 12.5, "segments": [
    {"id": "t1", "start": 0.0, "end": 3.0, "text": " If you think you can do it,"},
    {"id": "t2", "start": 3.0, "end": 5.0, "text": "you can do it. "},
    {"id": "t3", "start": 5.0, "end": 6.0, "text": "   "},
]}


@pytest.mark.parametrize("encode", [lambda d: d, repr, json.dumps], ids=["dict", "python-repr", "json-string"])
def test_transcript_formats_in_the_golden_set_all_load(smoke, tmp_path, encode):
    path = tmp_path / "v01.json"
    path.write_text(json.dumps({"video_id": "v01", "transcript": encode(SEGMENTS)}))
    fusion = smoke.fusion_from_transcript(path)
    assert fusion.transcript == "If you think you can do it, you can do it."
    assert fusion.combined_content.startswith("[AUDIO TRANSCRIPT]\n")
    assert fusion.visual_text == "" and fusion.metadata["ocr_disabled"] is True
    assert [s["text"] for s in fusion.metadata["transcript_segments"]] == [
        "If you think you can do it,", "you can do it."]
    assert fusion.metadata["duration_seconds"] == 12.5


def test_cost_uses_routing_prices_and_flags_unpriced_models(smoke):
    prices = {"priced": SimpleNamespace(input=2.0, output=10.0)}
    routing = SimpleNamespace(price=prices.get)
    assert smoke.price_of(routing, "priced", 1_000_000, 100_000) == pytest.approx(3.0)
    assert smoke.price_of(routing, "unknown", 10, 10) is None
    assert smoke.total([1.0, None, 0.5]) == (1.5, True)
    assert smoke.total([1.0, 0.5]) == (1.5, False)
