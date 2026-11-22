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
TRANSCRIPTS = os.path.join(os.path.dirname(HERE), "transcripts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chars", type=int, default=420,
                    help="how much opening speech to print")
    ap.add_argument("--labelled", default="",
                    help="comma-separated video_ids already done, to skip")
    args = ap.parse_args()
    done = set(s.strip() for s in args.labelled.split(",") if s.strip())

    for f in sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        vid = d["video_id"]
        if vid in done:
            continue
        t = d.get("transcript", {})
        osd = d.get("on_screen", {})
        segs = t.get("segments", [])
        speech = " ".join(s["text"] for s in segs)
        caps = osd.get("captions", [])
        print("=" * 78)
        print("%s  dur=%.0fs  lang=%s  segs=%d  caps=%d  collector_label=%s  %s"
              % (vid, t.get("duration_seconds", 0) or 0, t.get("language"),
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
