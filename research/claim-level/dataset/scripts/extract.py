"""Transcribe (faster-whisper) and OCR (EasyOCR) every video in video_index.csv.

Writes text only to research/claim-level/dataset/transcripts/<video_id>.json.
No media is copied or committed. Per-video caching makes the run resumable:
a video whose transcript JSON already exists is skipped.

Device: CUDA when the CUDA runtime actually loads, else CPU.
  faster-whisper: model "small", int8 on CPU / float16 on GPU.
  EasyOCR: English only, 0.5 frames per second, longest side <= 960 px.
"""
import argparse
import csv
import json
import os
import time
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1]
VIDEOS = DATASET / "videos"
TRANSCRIPTS = DATASET / "transcripts"
INDEX = DATASET / "video_index.csv"

OCR_FPS = 0.5          # one frame every 2 seconds
OCR_MAX_SIDE = 960     # resize so the longest side is at most this
OCR_MIN_CONF = 0.5     # design doc section 2: drop detections below 0.5


def _add_cuda_dll_dirs():
    """Pip-installed nvidia wheels put DLLs under site-packages/nvidia/*/bin.
    ctranslate2 only finds them if those dirs are on the DLL search path."""
    try:
        import nvidia
        base = Path(nvidia.__file__).parent
        for sub in base.iterdir():
            for d in (sub / "bin", sub / "lib"):
                if d.is_dir():
                    try:
                        os.add_dll_directory(str(d))
                    except OSError:
                        pass
    except Exception:
        pass
    try:
        import torch
        td = Path(torch.__file__).parent / "lib"
        if td.is_dir():
            os.add_dll_directory(str(td))
    except Exception:
        pass


def pick_whisper_device(force):
    if force == "cpu":
        return "cpu", "int8"
    _add_cuda_dll_dirs()
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            from faster_whisper import WhisperModel
            WhisperModel("tiny", device="cuda", compute_type="float16")
            return "cuda", "float16"
    except Exception as e:
        print("[device] CUDA unavailable for whisper (%s: %s); using CPU"
              % (type(e).__name__, str(e)[:90]), flush=True)
    return "cpu", "int8"


def ocr_gpu_available():
    _add_cuda_dll_dirs()
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def transcribe(model, path):
    segments, info = model.transcribe(
        str(path), beam_size=5, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        # Whisper's repetition loop: with the previous text fed back in, a
        # music-heavy or repetitive clip can emit the same phrase until the
        # window ends. One video in this bundle ran ~15x longer than a clip of
        # the same length before this was turned off. Costs a little
        # cross-segment coherence, which claim extraction does not rely on.
        condition_on_previous_text=False,
        # drop segments the decoder itself thinks are silence/garbage
        no_speech_threshold=0.6,
        compression_ratio_threshold=2.4,
    )
    segs = [
        {"id": "t%d" % i, "start": round(s.start, 2), "end": round(s.end, 2),
         "text": s.text.strip()}
        for i, s in enumerate(segments, start=1)
    ]
    return {
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "duration_seconds": round(float(info.duration), 2),
        "segments": segs,
    }


def ocr_video(reader, path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"error": "could not open video for OCR", "detections": []}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / OCR_FPS)))
    dets, idx, sampled = [], 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            sampled += 1
            # real timestamp from the decoder, not idx/fps (avoids drift)
            ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            t = round((ms / 1000.0) if ms and ms > 0 else idx / fps, 2)
            h, w = frame.shape[:2]
            scale = OCR_MAX_SIDE / float(max(h, w))
            if scale < 1.0:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_AREA)
            try:
                # batch_size batches the recognition pass over the detected
                # text regions. Caption-heavy frames carry dozens of regions and
                # recognising them one at a time is the run's real bottleneck.
                for _box, text, conf in reader.readtext(frame, batch_size=16):
                    if conf >= OCR_MIN_CONF and text.strip():
                        dets.append({"time": t, "text": text.strip(),
                                     "confidence": round(float(conf), 3)})
            except Exception as e:
                dets.append({"time": t,
                             "error": "%s: %s" % (type(e).__name__, e)})
        idx += 1
    cap.release()
    return {"frames_sampled": sampled, "detections": dets}


def collapse(dets):
    """Section 3 step 1: consecutive identical captions become one timed entry."""
    out = []
    for d in dets:
        if "text" not in d:
            continue
        key = " ".join(d["text"].lower().split())
        if out and out[-1]["_key"] == key:
            out[-1]["end"] = d["time"]
            out[-1]["confidence"] = max(out[-1]["confidence"], d["confidence"])
            continue
        out.append({"_key": key, "text": d["text"], "start": d["time"],
                    "end": d["time"], "confidence": d["confidence"]})
    for i, o in enumerate(out, start=1):
        o["id"] = "o%d" % i
        del o["_key"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", choices=["auto", "cpu"], default="auto")
    ap.add_argument("--only", default="", help="comma-separated video_ids")
    ap.add_argument("--skip", default="",
                    help="comma-separated video_ids to leave out, so one "
                         "pathological video cannot block the batch")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-ocr", action="store_true")
    args = ap.parse_args()

    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    with open(INDEX, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.only:
        want = set(s.strip() for s in args.only.split(","))
        rows = [r for r in rows if r["video_id"] in want]
    if args.skip:
        drop = set(s.strip() for s in args.skip.split(",") if s.strip())
        rows = [r for r in rows if r["video_id"] not in drop]
    if args.limit:
        rows = rows[: args.limit]

    todo = [r for r in rows
            if not (TRANSCRIPTS / ("%s.json" % r["video_id"])).exists()]
    print("[plan] %d selected, %d cached, %d to process"
          % (len(rows), len(rows) - len(todo), len(todo)), flush=True)
    if not todo:
        return

    dev, ct = pick_whisper_device(None if args.device == "auto" else args.device)
    print("[device] whisper: %s/%s" % (dev, ct), flush=True)
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device=dev, compute_type=ct)

    reader = None
    if not args.no_ocr:
        import easyocr
        gpu = ocr_gpu_available() and args.device != "cpu"
        print("[device] easyocr gpu=%s" % gpu, flush=True)
        reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)

    for n, r in enumerate(todo, start=1):
        vid = r["video_id"]
        path = VIDEOS / r["relative_path"]
        t0 = time.time()
        print("[%d/%d] %s %s" % (n, len(todo), vid, r["filename"][:58]),
              flush=True)
        rec = {
            "video_id": vid,
            "filename": r["filename"],
            "relative_path": r["relative_path"],
            "collector": r["collector"],
            "collector_label": r["collector_label"],
            "creator_handle": r["creator_handle"],
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "whisper": {"model": "small", "device": dev, "compute_type": ct},
            "ocr": {"engine": "easyocr", "lang": "en", "fps": OCR_FPS,
                    "max_side": OCR_MAX_SIDE, "min_confidence": OCR_MIN_CONF},
        }
        try:
            rec["transcript"] = transcribe(model, path)
            print("      speech: %d segs, %.0fs, lang=%s (%.0fs)"
                  % (len(rec["transcript"]["segments"]),
                     rec["transcript"]["duration_seconds"],
                     rec["transcript"]["language"], time.time() - t0),
                  flush=True)
        except Exception as e:
            rec["transcript"] = {"error": "%s: %s" % (type(e).__name__, e),
                                 "segments": []}
            print("      speech FAILED: %s: %s" % (type(e).__name__, e),
                  flush=True)

        if reader is not None:
            t1 = time.time()
            try:
                raw = ocr_video(reader, path)
                raw["captions"] = collapse(raw.get("detections", []))
                rec["on_screen"] = raw
                print("      ocr: %d captions from %d frames (%.0fs)"
                      % (len(raw["captions"]), raw.get("frames_sampled", 0),
                         time.time() - t1), flush=True)
            except Exception as e:
                rec["on_screen"] = {"error": "%s: %s" % (type(e).__name__, e),
                                    "detections": [], "captions": []}
                print("      ocr FAILED: %s: %s" % (type(e).__name__, e),
                      flush=True)
        else:
            rec["on_screen"] = {"skipped": True, "detections": [],
                                "captions": []}

        # write atomically so an interrupted run never leaves a half file
        out = TRANSCRIPTS / ("%s.json" % vid)
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(out)
        print("      -> %s (%.0fs total)" % (out.name, time.time() - t0),
              flush=True)


if __name__ == "__main__":
    main()
