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
    def __init__(self, texts=None, exc=None):
        self.texts, self.exc, self.calls = texts or {}, exc, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        frames = [{"index": i, "text": t} for i, t in self.texts.items()]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"frames": frames})])


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
