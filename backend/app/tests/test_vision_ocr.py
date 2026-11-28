"""Vision OCR (app.core.extraction.vision_ocr): off by default, never fails a job,
timed captions reach the graph as OcrSegments."""
from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.extraction import multimodal, vision_ocr
from app.core.inference.providers.graph_provider import segments_from_fusion


class FakeClient:
    """Answers each request with the texts of the frames it was shown ("Frame N:" labels).
    ``overflow_over``: a request with more frames than this hits max_tokens with an empty input."""

    def __init__(self, texts=None, exc=None, overflow_over=None):
        self.texts, self.exc, self.calls, self.overflow_over = texts or {}, exc, [], overflow_over
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        shown = [int(b["text"].split()[1].rstrip(":")) for b in kw["messages"][0]["content"]
                 if b["type"] == "text" and b["text"].startswith("Frame ")]
        usage = SimpleNamespace(input_tokens=100, output_tokens=10)
        if self.overflow_over is not None and len(shown) > self.overflow_over:
            return SimpleNamespace(stop_reason="max_tokens", usage=usage,
                                   content=[SimpleNamespace(type="tool_use", input={})])
        frames = [{"index": i, "text": self.texts[i]} for i in shown if i in self.texts]
        return SimpleNamespace(stop_reason="tool_use", usage=usage,
                               content=[SimpleNamespace(type="tool_use", input={"frames": frames})])


def fake_grab(video, times, tmp):
    return [(t, b"\xff\xd8jpeg") for t in times]


def test_sample_times_capped_and_spaced():
    ts = vision_ocr.sample_times(60.0, 16)
    assert len(ts) <= 16 and ts[0] == 0.5 and all(b - a >= 2.0 - 1e-9 for a, b in zip(ts, ts[1:]))
    assert len(vision_ocr.sample_times(6.0, 16)) == 3  # 2 s minimum spacing
    assert vision_ocr.sample_times(0.0, 16) == [0.0]


def test_collapse_merges_repeats_and_skips_empty():
    segs = vision_ocr.collapse([0.5, 2.5, 4.5, 6.5], {0: "El Cáncer es un hongo", 1: "El  Cáncer es un hongo",
                                                      2: "", 3: "Jugo verde"}, 8.0)
    assert [(s.start, s.end, s.text) for s in segs] == [(0.5, 4.5, "El Cáncer es un hongo"), (6.5, 8.0, "Jugo verde")]


def test_extract_reads_frames_and_returns_timed_segments():
    client = FakeClient({0: "Cúrate del cáncer matándolo de hambre", 1: "Cúrate del cáncer matándolo de hambre", 2: ""})
    segs = vision_ocr.extract_on_screen_text("v.mp4", client=client, grab=fake_grab, duration=6.0)
    assert [s.text for s in segs] == ["Cúrate del cáncer matándolo de hambre"]
    call = client.calls[0]
    assert call["model"] == settings.OCR_VISION_MODEL
    assert call["tool_choice"]["name"] == vision_ocr.OCR_TOOL["name"]
    assert sum(1 for b in call["messages"][0]["content"] if b["type"] == "image") == 3


@pytest.mark.parametrize("exc", [RuntimeError("api down"), TimeoutError("slow")])
def test_failure_never_raises(exc):
    assert vision_ocr.extract_on_screen_text("v.mp4", client=FakeClient(exc=exc), grab=fake_grab, duration=6.0) == []


def test_bad_video_never_raises(tmp_path):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"nope")
    assert vision_ocr.extract_on_screen_text(str(bad), client=FakeClient({0: "x"})) == []


def test_off_by_default_fusion_unchanged(monkeypatch):
    assert settings.OCR_PROVIDER == "none" and not vision_ocr.enabled()
    monkeypatch.setattr(multimodal, "transcribe", lambda p: "hello world")
    called = []
    monkeypatch.setattr(vision_ocr, "extract_on_screen_text", lambda p: called.append(p) or [])
    r = multimodal.MultimodalFusion().fuse("v.mp4")
    assert called == [] and r.visual_text == "" and r.combined_content == "[AUDIO TRANSCRIPT]\nhello world"
    assert r.metadata["ocr_disabled"] is True and "ocr_segments" not in r.metadata


def test_on_fusion_adds_timed_captions_and_graph_gets_them(monkeypatch):
    monkeypatch.setattr(settings, "OCR_PROVIDER", "vision")
    monkeypatch.setattr(multimodal.transcription, "transcribe_segments",
                        lambda p: ("We're gonna starve that cancer.", [{"start": 0.0, "end": 3.0, "text": "We're gonna starve that cancer."}]))
    monkeypatch.setattr(vision_ocr, "extract_on_screen_text",
                        lambda p: [vision_ocr.TimedText(0.5, 10.0, "El Cáncer es un hongo"),
                                   vision_ocr.TimedText(10.0, 20.0, "El Bicarbonato es bueno")])
    r = multimodal.MultimodalFusion().fuse("v.mp4", keep_segments=True)
    assert "[ON-SCREEN TEXT]\nEl Cáncer es un hongo\nEl Bicarbonato es bueno" in r.combined_content
    transcript, ocr, estimated = segments_from_fusion(r)
    assert [(o.segment_id, o.start, o.end, o.text) for o in ocr] == [
        ("o1", 0.5, 10.0, "El Cáncer es un hongo"), ("o2", 10.0, 20.0, "El Bicarbonato es bueno")]
    assert estimated is False


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_real_ffmpeg_frame_grab(tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=5",
                    "-pix_fmt", "yuv420p", "-y", str(video)], check=True, timeout=60)
    client = FakeClient({0: "caption"})
    segs = vision_ocr.extract_on_screen_text(str(video), client=client)
    imgs = [b for b in client.calls[0]["messages"][0]["content"] if b["type"] == "image"]
    assert len(imgs) >= 2 and all(b["source"]["media_type"] == "image/jpeg" for b in imgs)
    assert segs and segs[0].text == "caption"


@pytest.mark.parametrize("raw", [
    {"frames": [{"index": 0, "text": "El Cáncer es un hongo"}, {"index": 1, "text": ""}]},
    {"frames": '[{"index": 0, "text": "El Cáncer es un hongo"}, {"index": 1, "text": ""}]'},
    {"frames": [{"index": "0", "text": "El Cáncer es un hongo"}]},
    {"frames": {"0": "El Cáncer es un hongo", "1": ""}},
    {"frames": ["El Cáncer es un hongo", ""]},
    '{"frames": [{"index": 0, "text": "El Cáncer es un hongo"}]}',
])
def test_parse_frames_tolerates_model_shapes(raw):
    assert vision_ocr.parse_frames(raw)[0] == "El Cáncer es un hongo"


def test_parse_frames_garbage_is_empty():
    assert vision_ocr.parse_frames(None) == {} and vision_ocr.parse_frames("not json") == {}


def test_frames_are_asked_in_batches_with_global_labels(monkeypatch):
    monkeypatch.setattr(settings, "OCR_BATCH_SIZE", 4)
    texts = {i: f"card {i}" for i in range(10)}
    client = FakeClient(texts)
    got = vision_ocr._ask_model([(float(i), b"j") for i in range(10)], client)
    assert got == texts
    assert [sum(1 for b in c["messages"][0]["content"] if b["type"] == "image") for c in client.calls] == [4, 4, 2]
    assert all(c["max_tokens"] == settings.OCR_MAX_TOKENS for c in client.calls)


def test_overflowing_reply_is_split_and_retried(monkeypatch):
    # Production job f85f2daa: 16 text-dense frames in one request came back as '{}'.
    monkeypatch.setattr(settings, "OCR_BATCH_SIZE", 4)
    texts = {i: f"page {i}" for i in range(4)}
    client = FakeClient(texts, overflow_over=1)
    assert vision_ocr._ask_model([(float(i), b"j") for i in range(4)], client) == texts
    assert client.calls[0]["messages"][0]["content"][0]["text"] == "Frame 0:"
    assert len(client.calls) == 1 + 2 + 4  # 4 overflows -> 2+2 overflow -> 1+1+1+1


def test_single_frame_overflow_gives_nothing_for_it_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "OCR_BATCH_SIZE", 2)
    client = FakeClient({0: "a", 1: "b"}, overflow_over=0)
    assert vision_ocr._ask_model([(0.0, b"j"), (1.0, b"j")], client) == {}


def test_batch_numbered_from_zero_is_mapped_to_global_frames(monkeypatch):
    monkeypatch.setattr(settings, "OCR_BATCH_SIZE", 2)

    class LocalIndexClient(FakeClient):
        def create(self, **kw):
            self.calls.append(kw)
            n = sum(1 for b in kw["messages"][0]["content"] if b["type"] == "image")
            return SimpleNamespace(stop_reason="tool_use", usage=None, content=[SimpleNamespace(
                type="tool_use", input={"frames": [f"text {len(self.calls)}-{j}" for j in range(n)]})])

    got = vision_ocr._ask_model([(float(i), b"j") for i in range(4)], LocalIndexClient())
    assert got == {0: "text 1-0", 1: "text 1-1", 2: "text 2-0", 3: "text 2-1"}
