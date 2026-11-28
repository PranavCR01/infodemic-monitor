"""T68 (g): frame-level vision-OCR model comparison. PROPOSED ONLY.

Compares candidate vision models on 20-30 saved, hand-labelled frames: does each model
give every text box the right kind (subtitle / document_or_chart / title_or_claim_card
/ interface), copy card and subtitle text faithfully, and never copy a document's text?
The request is production's (``vision_ocr.SYSTEM``, ``OCR_TOOL``, batches of
``OCR_BATCH_SIZE``), so the result transfers to the pipeline.

Nothing here spends money unless a person runs ``run --live --approved-by <name>
--max-usd <cap>``; the lead has not approved a run. The default command is the cost
estimate:

    python -m app.evaluation.vision_ocr_compare estimate [--frames 30]
    python -m app.evaluation.vision_ocr_compare extract --videos <dir> --ids v36,v135 --out <frames dir>
    python -m app.evaluation.vision_ocr_compare run --frames-file <frames.jsonl> --live \\
        --approved-by <name> --max-usd 2

Token estimates: Anthropic images ~ width*height/750 tokens; OpenAI high-detail images
85 + 170 per 512-px tile after scaling the short side to 768 px. Text: characters / 3.5
plus 350 tokens of tool scaffolding (``routing_experiment.cost``). These are estimates,
not provider tokenizers; the upper bound assumes every request writes its full
``OCR_MAX_TOKENS``.
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import yaml

from app.core.config import settings
from app.core.extraction import vision_ocr
from app.core.extraction.vision_ocr import CARD, DOCUMENT, SUBTITLE, TextBox
from app.evaluation.routing_experiment.cost import CHARS_PER_TOKEN, TOOL_OVERHEAD_TOKENS

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "evals" / "reports" / "T68" / "vision_compare.yaml"


# ------------------------------------------------------------------ config and cost


def load_config(path: Path = CONFIG) -> dict:
    return yaml.safe_load(Path(path).read_text())


def image_tokens(provider: str, width: int, height: int) -> int:
    if provider == "openai":
        w, h = width, height
        if max(w, h) > 2048:  # fit in 2048 x 2048, then the short side down to 768
            f = 2048 / max(w, h)
            w, h = w * f, h * f
        if min(w, h) > 768:
            f = 768 / min(w, h)
            w, h = w * f, h * f
        return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)
    w, h = width, height
    if max(w, h) > 1568:  # Anthropic resizes the long edge to 1568
        f = 1568 / max(w, h)
        w, h = int(w * f), int(h * f)
    return math.ceil(w * h / 750)


def request_text_tokens(frames_in_request: int) -> int:
    text = vision_ocr.SYSTEM + json.dumps(vision_ocr.OCR_TOOL) + "Frame 00:" * frames_in_request \
        + "Report the on-screen text of every frame with the tool."
    return math.ceil(len(text) / CHARS_PER_TOKEN) + TOOL_OVERHEAD_TOKENS


def price_for(model: str, routing_pricing: dict, assumed: dict) -> tuple[Optional[dict], str]:
    if model in routing_pricing:
        p = routing_pricing[model]
        return {"input": p["input"], "output": p["output"]}, "config/routing.yaml"
    if model in assumed:
        return {"input": assumed[model]["input"], "output": assumed[model]["output"]}, \
            f"ASSUMED (proxy: {assumed[model].get('proxy_for', '?')} prices)"
    return None, "unpriced"


def estimate(cfg: dict, n_frames: int, routing_pricing: dict) -> dict:
    batch = int(cfg.get("batch_size") or settings.OCR_BATCH_SIZE)
    requests = math.ceil(n_frames / batch)
    out_per_frame = int(cfg.get("expected_output_tokens_per_frame", 250))
    runs = int(cfg.get("runs", 1))
    rows = []
    for c in cfg["candidates"]:
        img = image_tokens(c["provider"], cfg["frame_width"], cfg["frame_height"])
        inp = n_frames * img + sum(request_text_tokens(min(batch, n_frames - i * batch)) for i in range(requests))
        reasoning = requests * int(cfg.get("reasoning_allowance_per_request", 0)) if c.get("reasoning") else 0
        out_exp = n_frames * out_per_frame + reasoning
        out_max = requests * settings.OCR_MAX_TOKENS + reasoning
        price, source = price_for(c["model"], routing_pricing, cfg.get("assumed_pricing") or {})

        def usd(i, o):
            return None if price is None else round(runs * (i * price["input"] + o * price["output"]) / 1e6, 4)

        rows.append({"id": c["id"], "model": c["model"], "provider": c["provider"], "requests": requests * runs,
                     "image_tokens_per_frame": img, "input_tokens": inp * runs, "output_tokens_expected": out_exp * runs,
                     "output_tokens_upper": out_max * runs, "usd_expected": usd(inp, out_exp),
                     "usd_upper": usd(inp, out_max), "price_source": source})
    priced = [r for r in rows if r["usd_expected"] is not None]
    return {"frames": n_frames, "batch_size": batch, "runs": runs, "candidates": rows,
            "total_usd_expected": round(sum(r["usd_expected"] for r in priced), 4),
            "total_usd_upper": round(sum(r["usd_upper"] for r in priced), 4),
            "unpriced": [r["id"] for r in rows if r["usd_expected"] is None]}


# ------------------------------------------------------------------ scoring


def _norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", (text or "").casefold()))


def text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


@dataclass
class FrameScore:
    frame_id: str
    expected: int
    kind_correct: int
    text_similarity: list[float]
    document_text_leaked: bool
    interface_text_kept: bool


def score_frame(frame_id: str, expected: list[dict], got: list[TextBox], raw_boxes: list[dict]) -> FrameScore:
    """Greedy match of expected boxes to the model's boxes (by text, or by kind for
    documents and interface), then: kind right? verbatim text close? A document whose
    raw reply carried more than 20 characters of text counts as a leak (the parser drops
    it, but the model did not follow the instruction)."""
    pool = list(got)
    kinds, sims = 0, []
    for e in expected:
        kind = e.get("kind")
        if kind in (CARD, SUBTITLE):
            best = max(pool, key=lambda b: text_similarity(e.get("text", ""), b.text), default=None)
            if best is not None and text_similarity(e.get("text", ""), best.text) >= 0.5:
                pool.remove(best)
                kinds += best.kind == kind
                sims.append(text_similarity(e.get("text", ""), best.text))
            else:
                sims.append(0.0)
        else:
            best = next((b for b in pool if b.kind == kind), None)
            if best is not None:
                pool.remove(best)
                kinds += 1
    leak = any(b.get("kind") == DOCUMENT and len(str(b.get("text") or "")) > 20 for b in raw_boxes)
    ui_kept = any(b.kind in (CARD, SUBTITLE) and re.fullmatch(r"@?\w+|tiktok|pinterest", b.text.casefold().strip())
                  for b in got if b.text) and not any(e.get("kind") in (CARD, SUBTITLE) and
                                                      e.get("text", "").startswith("@") for e in expected)
    return FrameScore(frame_id, len(expected), kinds, sims, leak, ui_kept)


def summarize(scores: list[FrameScore]) -> dict:
    n = sum(s.expected for s in scores)
    sims = [x for s in scores for x in s.text_similarity]
    return {"frames": len(scores), "boxes": n,
            "kind_accuracy": round(sum(s.kind_correct for s in scores) / n, 3) if n else None,
            "mean_text_similarity": round(sum(sims) / len(sims), 3) if sims else None,
            "frames_with_document_text_leak": sum(s.document_text_leaked for s in scores),
            "frames_with_interface_kept": sum(s.interface_text_kept for s in scores)}


# ------------------------------------------------------------------ clients (live only)


class OpenAIVisionAdapter:
    """Exposes ``messages.create(**anthropic_kwargs)`` over OpenAI chat completions, so
    ``vision_ocr._ask_model_boxes`` sends the same request to either provider."""

    def __init__(self, sdk: Any, reasoning: bool = False):
        self.sdk, self.reasoning = sdk, reasoning
        self.messages = self

    def create(self, *, model, max_tokens, system, tools, tool_choice, messages):
        parts = []
        for b in messages[0]["content"]:
            if b["type"] == "text":
                parts.append({"type": "text", "text": b["text"]})
            else:
                parts.append({"type": "image_url", "image_url": {
                    "url": f"data:{b['source']['media_type']};base64,{b['source']['data']}", "detail": "high"}})
        tool = tools[0]
        kwargs = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": parts}],
                  "tools": [{"type": "function", "function": {"name": tool["name"], "description": tool["description"],
                                                               "parameters": tool["input_schema"]}}],
                  "tool_choice": {"type": "function", "function": {"name": tool_choice["name"]}}}
        kwargs["max_completion_tokens" if self.reasoning else "max_tokens"] = max_tokens
        resp = self.sdk.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        calls = getattr(choice.message, "tool_calls", None) or []
        content = [SimpleNamespace(type="tool_use", input=json.loads(c.function.arguments or "{}")) for c in calls]
        stop = "max_tokens" if choice.finish_reason == "length" else "tool_use"
        usage = SimpleNamespace(input_tokens=getattr(resp.usage, "prompt_tokens", None),
                                output_tokens=getattr(resp.usage, "completion_tokens", None))
        return SimpleNamespace(stop_reason=stop, usage=usage, content=content)


class RecordingClient:
    """Wraps a client and keeps each raw tool input, to score leaks the parser hides."""

    def __init__(self, inner: Any):
        self.inner, self.raw = inner, []
        self.messages = self

    def create(self, **kw):
        resp = self.inner.messages.create(**kw)
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use":
                self.raw.append(b.input)
        return resp


def raw_boxes_by_frame(raw_inputs: list[Any]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for raw in raw_inputs:
        frames = raw.get("frames") if isinstance(raw, dict) else None
        for f in frames if isinstance(frames, list) else []:
            if isinstance(f, dict) and isinstance(f.get("boxes"), list):
                try:
                    out[int(f.get("index"))] = [b for b in f["boxes"] if isinstance(b, dict)]
                except (TypeError, ValueError):
                    continue
    return out


def compare(frames: list[dict], clients: dict[str, Any]) -> dict:
    """Run each candidate on the frames (``frames``: dicts with ``frame_id``, ``jpeg``
    bytes and ``expected``) and score it. ``clients``: candidate id -> vision client."""
    images = [(float(f.get("time", 0.0)), f["jpeg"]) for f in frames]
    out = {}
    for cid, client in clients.items():
        rec = RecordingClient(client)
        boxes = vision_ocr._ask_model_boxes(images, rec)
        raw = raw_boxes_by_frame(rec.raw)
        scores = [score_frame(f["frame_id"], f["expected"], boxes.get(i, []), raw.get(i, []))
                  for i, f in enumerate(frames)]
        out[cid] = summarize(scores)
    return out


# ------------------------------------------------------------------ CLI


def _load_frames(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for r in rows:
        r["jpeg"] = (path.parent / r["path"]).read_bytes()
    return rows


def _extract(videos: Path, ids: list[str], out: Path) -> None:
    import csv
    import tempfile

    index = {r["video_id"]: r for r in csv.DictReader((REPO / "research/claim-level/dataset/video_index.csv").open())}
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for vid in ids:
        rel = index.get(vid, {}).get("relative_path") or index.get(vid, {}).get("filename") or ""
        video = videos / rel
        dur = vision_ocr._duration(str(video))
        times, _ = vision_ocr.frame_times(str(video), dur, settings.OCR_MAX_FRAMES)
        with tempfile.TemporaryDirectory() as tmp:
            for j, (t, jpg) in enumerate(vision_ocr._grab_frames(str(video), times, tmp)):
                name = f"{vid}_{j:02d}.jpg"
                (out / name).write_bytes(jpg)
                lines.append(json.dumps({"frame_id": f"{vid}_{j:02d}", "video_id": vid, "time": t, "path": name,
                                         "expected": []}))
    (out / "frames.jsonl").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} frames to {out}; label 'expected' by hand, keep 20-30 frames")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("estimate")
    e.add_argument("--frames", type=int, default=30)
    x = sub.add_parser("extract")
    x.add_argument("--videos", required=True)
    x.add_argument("--ids", required=True)
    x.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--frames-file", required=True)
    r.add_argument("--live", action="store_true")
    r.add_argument("--approved-by")
    r.add_argument("--max-usd", type=float)
    args = ap.parse_args(argv)
    cfg = load_config()
    from app.core.routing.config import load_routing

    pricing = {k: v.model_dump() for k, v in load_routing().pricing.items()}
    if args.cmd in (None, "estimate"):
        print(json.dumps(estimate(cfg, getattr(args, "frames", 30), pricing), indent=1))
        return 0
    if args.cmd == "extract":
        _extract(Path(args.videos), [s.strip() for s in args.ids.split(",") if s.strip()], Path(args.out))
        return 0
    # run: paid. Refuse unless explicitly approved, capped, and every model priced in routing.yaml.
    if not (args.live and args.approved_by and args.max_usd):
        print("refused: a live run needs --live --approved-by <name> --max-usd <cap> (lead's direct approval)")
        return 2
    frames = _load_frames(Path(args.frames_file))
    est = estimate(cfg, len(frames), pricing)
    if any(c["price_source"] != "config/routing.yaml" for c in est["candidates"]):
        print("refused: price every candidate in config/routing.yaml first (assumed prices can't hold a cap)")
        return 2
    if est["total_usd_upper"] > args.max_usd:
        print(f"refused: upper-bound cost ${est['total_usd_upper']} exceeds --max-usd {args.max_usd}")
        return 2
    import anthropic
    import openai

    clients = {}
    for c in cfg["candidates"]:
        if c["provider"] == "anthropic":
            clients[c["id"]] = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            clients[c["id"]] = OpenAIVisionAdapter(openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY")),
                                                   bool(c.get("reasoning")))
    results = {}
    for c in cfg["candidates"]:
        settings.OCR_VISION_MODEL = c["model"]  # this process only
        results[c["id"]] = compare(frames, {c["id"]: clients[c["id"]]})[c["id"]]
    print(json.dumps({"approved_by": args.approved_by, "estimate": est, "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
