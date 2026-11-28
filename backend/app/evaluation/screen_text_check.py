"""T68 (f): screen-only claim recall sanity check on mocked vision replies. No spend.

Runs the real vision-OCR code (frame planning from recorded scene cuts, the tool-reply
parser, collapse by kind) and the real routing (``screen_text.route`` against the
golden Whisper transcript) on mocked vision-model replies
(``app/tests/fixtures/vision_ocr/<id>.json``, synthetic), then asks two questions of
what would reach claim extraction:

- **Screen-only input recall** (main case v36, 12 golden ``claim_source=screen``
  claims): the share of those claims whose words appear in an extraction-bound OCR
  segment shown at the claim's time (token containment >= ``CLAIM_MATCH``, time
  overlap padded by 2 s). This is a ceiling for extraction, not claim recall: no
  extraction model is run.
- **New screen content** (v135 must gain no new claims): extraction-bound OCR segments
  whose words are not already spoken in their time window. Zero means extraction gets
  nothing from the screen that the speech doesn't already give it.

Both are compared with the pre-T68 behaviour on the same replies (every box read
verbatim, documents included). A sanity check on two tune videos, not an accuracy
figure: the kinds in the mocked replies were assigned by hand.

    python -m app.evaluation.screen_text_check [--out evals/reports/T68]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from app.core.config import settings
from app.core.extraction import screen_text, vision_ocr
from app.core.extraction.vision_ocr import INTERFACE, TimedText

REPO = Path(__file__).resolve().parents[3]
DATASET = REPO / "research" / "claim-level" / "dataset"
FIXTURES = REPO / "backend" / "app" / "tests" / "fixtures" / "vision_ocr"
VIDEOS = ("v36", "v135")
CLAIM_MATCH = 0.75
TIME_PAD = 2.0


class MockVision:
    """Vision client answering each frame with the boxes of the scene it falls in."""

    def __init__(self, boxes_by_frame: dict[int, list[dict]]):
        self.boxes, self.calls = boxes_by_frame, 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        shown = [int(b["text"].split()[1].rstrip(":")) for b in kw["messages"][0]["content"]
                 if b["type"] == "text" and b["text"].startswith("Frame ")]
        frames = [{"index": i, "boxes": self.boxes.get(i, [])} for i in shown]
        return SimpleNamespace(stop_reason="tool_use", usage=None,
                               content=[SimpleNamespace(type="tool_use", input={"frames": frames})])


def load_fixture(video_id: str) -> dict:
    return json.loads((FIXTURES / f"{video_id}.json").read_text())


def frame_boxes(fx: dict, times: list[float], variant: Optional[str] = None) -> dict[int, list[dict]]:
    overrides = (fx.get("variants") or {}).get(variant or "", {})
    out: dict[int, list[dict]] = {}
    for i, t in enumerate(times):
        scene = next((s for s in fx["scenes"] if s["start"] <= t < s["end"]), fx["scenes"][-1])
        out[i] = overrides.get(f"{scene['start']:.1f}", scene["boxes"])
    return out


def golden(video_id: str) -> tuple[list[dict], dict, list[dict]]:
    """Golden claims, the video row and Whisper segments. Tune split only."""
    row = next(r for r in csv.DictReader((DATASET / "videos.csv").open()) if r["video_id"] == video_id)
    if row["split"] != "tune":
        raise SystemExit(f"{video_id} is not a tune video; the test split is never read")
    claims = [r for r in csv.DictReader((DATASET / "claims.csv").open()) if r["video_id"] == video_id]
    tx = json.loads((DATASET / "transcripts" / f"{video_id}.json").read_text())
    return claims, row, tx["transcript"]["segments"]


def before_t68(times: list[float], boxes: dict[int, list[dict]], duration: float) -> list[TimedText]:
    """Pre-T68 reading of the same replies: every non-interface box verbatim, one
    segment per frame text, all of it extraction input."""
    texts = {i: " / ".join(b["text"] for b in bs if b.get("kind") != INTERFACE and b.get("text"))
             for i, bs in boxes.items()}
    return vision_ocr.collapse(times, texts, duration)


def covered(claim: dict, segs: list[TimedText]) -> Optional[TimedText]:
    start, end = float(claim["start_seconds"] or 0), float(claim["end_seconds"] or 0)
    for s in segs:
        if s.end >= start - TIME_PAD and s.start <= end + TIME_PAD and \
                screen_text.containment(claim["claim_text"], s.text) >= CLAIM_MATCH:
            return s
    return None


def new_content(segs: list[TimedText], spoken: list[screen_text.Spoken]) -> list[TimedText]:
    return [s for s in segs if screen_text.containment(
        s.text, screen_text.speech_window(spoken, s.start, s.end)) < screen_text.SUBTITLE_MATCH]


def run_video(video_id: str, variant: Optional[str] = None) -> dict[str, Any]:
    fx = load_fixture(video_id)
    claims, row, segments = golden(video_id)
    dur = float(fx["duration_seconds"])
    times = vision_ocr.plan_frame_times(dur, fx["scene_cuts"], settings.OCR_MAX_FRAMES)
    boxes = frame_boxes(fx, times, variant)
    client = MockVision(boxes)
    segs = vision_ocr.extract_on_screen_text(f"{video_id}.mp4", client=client, duration=dur, times=times,
                                             grab=lambda v, ts, tmp: [(t, b"\xff\xd8") for t in ts])
    spoken = screen_text.spoken_from(segments)
    routed = screen_text.route(segs, spoken)
    old = before_t68(times, boxes, dur)
    screen_claims = [c for c in claims if c["claim_source"] == "screen"]

    def recall(pool: list[TimedText]) -> dict:
        hits = {c["claim_id"]: covered(c, pool) for c in screen_claims}
        return {"found": sum(1 for h in hits.values() if h), "of": len(screen_claims),
                "missed": [c for c, h in hits.items() if not h]}

    after_new, before_new = new_content(routed.to_extraction, spoken), new_content(old, spoken)
    return {
        "video_id": video_id, "variant": variant or "as_labelled", "split": row["split"],
        "golden_claims": len(claims), "golden_screen_claims": len(screen_claims),
        "frames": len(times), "frame_times": times, "vision_requests": client.calls,
        "routing": routed.counts(),
        "after": {
            "segments_to_extraction": len(routed.to_extraction),
            "chars_to_extraction": sum(len(s.text) for s in routed.to_extraction),
            "screen_only_recall": recall(routed.to_extraction),
            "new_content_segments": [{"start": s.start, "end": s.end, "kind": s.kind, "text": s.text[:200]}
                                     for s in after_new],
            "documents": [{"start": d.start, "end": d.end, "note": d.text} for d in routed.documents],
            "subtitles_dropped": len(routed.subtitles_dropped),
        },
        "before": {
            "segments_to_extraction": len(old),
            "chars_to_extraction": sum(len(s.text) for s in old),
            "screen_only_recall": recall(old),
            "new_content_segments": len(before_new),
        },
        # Notes find_study would be offered for each golden claim (near documents only;
        # a claim citing a study may also fall back to every document).
        "hints_for_golden_claims": {c["claim_id"]: screen_text.hints_for(
            float(c["start_seconds"] or 0), float(c["end_seconds"] or 0), [
                SimpleNamespace(start=d.start, end=d.end, note=d.text) for d in routed.documents])
            for c in claims} if routed.documents else {},
    }


def run() -> dict[str, Any]:
    rows = [run_video("v36"), run_video("v36", "pinterest_as_document"), run_video("v135")]
    return {"task": "T68", "synthetic_replies": True, "model_calls": 0, "cost_usd": 0.0,
            "claim_match": CLAIM_MATCH, "time_pad_seconds": TIME_PAD, "max_frames": settings.OCR_MAX_FRAMES,
            "videos": rows}


def markdown(rep: dict) -> str:
    lines = ["| video | variant | screen-only recall after (before) | segments to extraction after (before) "
             "| chars after (before) | new-content segments after (before) | subtitles dropped | documents |",
             "|---|---|---|---|---|---|---|---|"]
    for v in rep["videos"]:
        a, b = v["after"], v["before"]
        ra, rb = a["screen_only_recall"], b["screen_only_recall"]
        lines.append(f"| {v['video_id']} | {v['variant']} | {ra['found']}/{ra['of']} ({rb['found']}/{rb['of']}) "
                     f"| {a['segments_to_extraction']} ({b['segments_to_extraction']}) "
                     f"| {a['chars_to_extraction']} ({b['chars_to_extraction']}) "
                     f"| {len(a['new_content_segments'])} ({b['new_content_segments']}) "
                     f"| {a['subtitles_dropped']} | {len(a['documents'])} |")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(REPO / "evals" / "reports" / "T68"))
    args = ap.parse_args(argv)
    rep = run()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "screen_text_check.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
    print(markdown(rep))


if __name__ == "__main__":
    main()
