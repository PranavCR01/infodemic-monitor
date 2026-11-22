"""One line per video plus the opening speech, to sort health content from the
rest quickly before labelling each video properly.

Labelling aid only -- it writes nothing and decides nothing.
"""
import argparse
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.dirname(HERE)
TRANSCRIPTS = os.path.join(DATASET, "transcripts")
SPEECH_CACHE = os.path.join(DATASET, ".cache", "speech")
INDEX = os.path.join(DATASET, "video_index.csv")


def sources(use_cache):
    """Merged transcripts first; the speech-stage cache fills the gaps so
    claim work can start while the OCR stage is still running."""
    out = {}
    for f in sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.json"))):
        out[os.path.basename(f)[:-5]] = (f, "final")
    if use_cache:
        import csv
        meta = {}
        if os.path.exists(INDEX):
            with open(INDEX, encoding="utf-8-sig", newline="") as fh:
                meta = {r["video_id"]: r for r in csv.DictReader(fh)}
        for f in sorted(glob.glob(os.path.join(SPEECH_CACHE, "*.json"))):
            vid = os.path.basename(f)[:-5]
            if vid not in out:
                out[vid] = (f, "speech-only", meta.get(vid, {}))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chars", type=int, default=420,
                    help="how much opening speech to print")
    ap.add_argument("--labelled", default="",
                    help="comma-separated video_ids already done, to skip")
    ap.add_argument("--no-cache", action="store_true",
                    help="only merged transcripts, not the speech-stage cache")
    args = ap.parse_args()
    done = set(s.strip() for s in args.labelled.split(",") if s.strip())

    for vid, entry in sorted(sources(not args.no_cache).items()):
        if vid in done:
            continue
        f, kind = entry[0], entry[1]
        d = json.load(open(f, encoding="utf-8"))
        d.setdefault("video_id", vid)
        if kind == "speech-only":
            meta = entry[2] if len(entry) > 2 else {}
            d.setdefault("collector_label", meta.get("collector_label", ""))
            d.setdefault("creator_handle", meta.get("creator_handle", ""))
            d.setdefault("collector", meta.get("collector", ""))
            d.setdefault("on_screen", {"captions": []})
        t = d.get("transcript", {})
        osd = d.get("on_screen", {})
        segs = t.get("segments", [])
        speech = " ".join(s["text"] for s in segs)
        caps = osd.get("captions", [])
        print("=" * 78)
        print("%s [%s] dur=%.0fs  lang=%s  segs=%d  caps=%d  collector_label=%s  %s"
              % (vid, kind, t.get("duration_seconds", 0) or 0,
                 t.get("language"),
                 len(segs), len(caps), d.get("collector_label") or "-",
                 d.get("creator_handle") or d.get("collector", "")))
        if t.get("error"):
            print("  TRANSCRIPT ERROR: %s" % t["error"])
        print("  SPEECH: %s" % (speech[:args.chars] if speech
                                else "(no speech)"))
        # the few longest distinct captions usually say what is on screen
        uniq, seen = [], set()
        for c in caps:
            k = " ".join(c["text"].lower().split())
            if k in seen or len(k) < 6:
                continue
            seen.add(k)
            uniq.append(c["text"])
        uniq.sort(key=len, reverse=True)
        if uniq:
            print("  SCREEN: %s" % " | ".join(uniq[:8])[:args.chars])


if __name__ == "__main__":
    main()
