"""T68 (f) sanity check on mocked vision replies and the (g) comparison harness.
No model is called: the check uses recorded/mocked replies, the harness mocked clients."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.extraction.vision_ocr import CARD, DOCUMENT, SUBTITLE, TextBox
from app.evaluation import screen_text_check as chk
from app.evaluation import vision_ocr_compare as cmp


@pytest.fixture(scope="module")
def report():
    return chk.run()


def _video(rep, vid, variant="as_labelled"):
    return next(v for v in rep["videos"] if v["video_id"] == vid and v["variant"] == variant)


def test_v36_screen_only_claims_reach_extraction(report):
    v = _video(report, "v36")
    assert v["golden_screen_claims"] == 12 and v["split"] == "tune"
    assert v["after"]["screen_only_recall"] == {"found": 12, "of": 12, "missed": []}
    assert v["frames"] <= 16 and v["vision_requests"] == 4
    assert v["after"]["chars_to_extraction"] < v["before"]["chars_to_extraction"]


def test_v36_infographic_labelled_as_document_loses_its_claims(report):
    v = _video(report, "v36", "pinterest_as_document")
    assert v["after"]["screen_only_recall"]["missed"] == ["c15", "c16", "c17"]


def test_v135_documents_and_subtitles_never_reach_extraction(report):
    v = _video(report, "v135")
    assert v["routing"]["document_or_chart"] == 11 and v["routing"]["subtitle_dropped"] == 15
    assert v["routing"]["subtitle_kept"] == 0
    kinds = {s["kind"] for s in v["after"]["new_content_segments"]}
    assert kinds <= {CARD}  # what still reaches extraction unspoken is cards only
    assert v["after"]["segments_to_extraction"] == 3 and v["before"]["segments_to_extraction"] == 14
    fx = chk.load_fixture("v135")
    leaked = [b["text"] for s in fx["scenes"] for b in s["boxes"] if b["kind"] == DOCUMENT and b["text"]]
    sent = " ".join(s["text"] for s in v["after"]["new_content_segments"])
    assert leaked and not any(t[:40] in sent for t in leaked)
    assert any("JAAD" in h for h in v["hints_for_golden_claims"]["c6"])
    assert any("Valisure" in h for h in v["hints_for_golden_claims"]["c1"])


def test_fixtures_are_marked_synthetic():
    for vid in chk.VIDEOS:
        assert chk.load_fixture(vid)["synthetic"] is True


# ------------------------------------------------------------------ (g) harness


def test_estimate_prices_every_candidate_and_marks_assumed_prices():
    est = cmp.estimate(cmp.load_config(), 30, {"claude-haiku-5-5": {"input": 0.1, "output": 0.5},
                                               "claude-sonnet-5-5": {"input": 2.0, "output": 10.0}})
    ids = [c["id"] for c in est["candidates"]]
    assert ids == ["haiku-5-5", "sonnet-5-5", "gpt-6.1-terra", "gpt-6-luna"]
    assert est["candidates"][0]["price_source"] == "config/routing.yaml"
    assert est["candidates"][2]["price_source"].startswith("ASSUMED")
    assert all(c["usd_upper"] >= c["usd_expected"] > 0 for c in est["candidates"])
    assert cmp.image_tokens("anthropic", 720, 1280) == 1229
    assert cmp.image_tokens("openai", 720, 1280) == 85 + 170 * 6


def test_live_run_is_refused_without_approval(capsys):
    assert cmp.main(["run", "--frames-file", "nope.jsonl"]) == 2
    assert "refused" in capsys.readouterr().out


def test_score_frame_counts_kinds_text_and_leaks():
    expected = [{"kind": CARD, "text": "Irish Sea Moss: Cures Thyroid Issues"}, {"kind": DOCUMENT, "note": "x"},
                {"kind": SUBTITLE, "text": "this is ten times more"}]
    got = [TextBox(CARD, "Irish Sea Moss: Cures Thyroid Issues"), TextBox(DOCUMENT, "", "shows a report"),
           TextBox(CARD, "this is ten times more")]  # subtitle given the wrong kind
    raw = [{"kind": DOCUMENT, "text": "Figure 4D Figure 4E Figure 4F ppm benzene"}]
    s = cmp.score_frame("f1", expected, got, raw)
    assert (s.expected, s.kind_correct, s.document_text_leaked) == (3, 2, True)
    assert cmp.summarize([s])["kind_accuracy"] == round(2 / 3, 3)


def test_compare_runs_each_candidate_through_productions_request():
    class Fake:
        def __init__(self):
            self.messages, self.calls = self, 0

        def create(self, **kw):
            self.calls += 1
            assert kw["tools"][0]["name"] == "report_on_screen_text"
            n = sum(1 for b in kw["messages"][0]["content"] if b["type"] == "image")
            labels = [int(b["text"].split()[1].rstrip(":")) for b in kw["messages"][0]["content"]
                      if b["type"] == "text" and b["text"].startswith("Frame ")]
            frames = [{"index": i, "boxes": [{"kind": CARD, "text": f"card {i}"}]} for i in labels]
            assert len(frames) == n
            return SimpleNamespace(stop_reason="tool_use", usage=None,
                                   content=[SimpleNamespace(type="tool_use", input={"frames": frames})])

    frames = [{"frame_id": f"f{i}", "time": float(i), "jpeg": b"\xff\xd8",
               "expected": [{"kind": CARD, "text": f"card {i}"}]} for i in range(6)]
    out = cmp.compare(frames, {"a": Fake()})
    assert out["a"]["kind_accuracy"] == 1.0 and out["a"]["mean_text_similarity"] == 1.0


def test_openai_adapter_translates_the_request_and_reply():
    seen = {}

    def create(**kw):
        seen.update(kw)
        call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps({"frames": [{"index": 0, "boxes": []}]})))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="tool_calls",
                                                        message=SimpleNamespace(tool_calls=[call]))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    resp = cmp.OpenAIVisionAdapter(sdk, reasoning=True).create(
        model="m", max_tokens=100, system="sys", tools=[{"name": "t", "description": "d", "input_schema": {}}],
        tool_choice={"type": "tool", "name": "t"},
        messages=[{"role": "user", "content": [{"type": "text", "text": "Frame 0:"}, {"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": "AA=="}}]}])
    assert seen["max_completion_tokens"] == 100 and "max_tokens" not in seen
    assert seen["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert resp.content[0].input == {"frames": [{"index": 0, "boxes": []}]} and resp.stop_reason == "tool_use"
