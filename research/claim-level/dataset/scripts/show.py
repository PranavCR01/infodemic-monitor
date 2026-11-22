"""Print a compact review sheet for one or more videos: speech segments with
timestamps, plus the on-screen captions worth reading.

Labelling aid only -- it writes nothing. Captions are deduplicated across the
whole video (OCR re-reads the same overlay on every sampled frame) and the
noisiest fragments are held back behind --all so the real text is legible.
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DATASET = Path(__file__).resolve().parents[1]
TRANSCRIPTS = DATASET / "transcripts"


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def interesting(text):
    """Hold back OCR fragments that carry no readable content."""
    t = text.strip()
    if len(t) < 3:
        return False
    letters = sum(c.isalpha() for c in t)
    if letters < 3:
        return False
    if letters / max(1, len(t)) < 0.5:
        return False
    # platform furniture
    if re.fullmatch(r"(?i)(follow|like|share|subscribe|for more|fyp|tiktok|"
                    r"reels|shorts|original sound|sound|music)\W*", t):
        return False
    return True


def show(vid, show_all=False, max_caps=60):
    p = TRANSCRIPTS / ("%s.json" % vid)
    if not p.exists():
        print("%s: no transcript yet" % vid)
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    t = d.get("transcript", {})
    osd = d.get("on_screen", {})
    print("=" * 78)
    print("%s  %s" % (d["video_id"], d["filename"]))
    print("  collector=%s  collector_label=%s  handle=%s"
          % (d.get("collector", "-"), d.get("collector_label") or "-",
             d.get("creator_handle") or "-"))
    print("  duration=%.0fs  lang=%s (p=%.2f)  segments=%d  captions=%d"
          % (t.get("duration_seconds", 0) or 0, t.get("language"),
             t.get("language_probability", 0) or 0,
             len(t.get("segments", [])), len(osd.get("captions", []))))
    if t.get("error"):
        print("  TRANSCRIPT ERROR: %s" % t["error"])
    if osd.get("error"):
        print("  OCR ERROR: %s" % osd["error"])

    print("--- SPEECH ---")
    if not t.get("segments"):
        print("  (none)")
    for s in t.get("segments", []):
        print("  %s [%6.1f-%6.1f] %s" % (s["id"], s["start"], s["end"],
                                         s["text"]))

    print("--- ON-SCREEN (deduplicated) ---")
    caps = osd.get("captions", [])
    best = {}
    for c in caps:
        if not show_all and not interesting(c["text"]):
            continue
        k = norm(c["text"])
        if not k:
            continue
        if k not in best:
            best[k] = {"text": c["text"], "start": c["start"],
                       "end": c["end"], "n": 1,
                       "confidence": c["confidence"]}
        else:
            b = best[k]
            b["end"] = max(b["end"], c["end"])
            b["start"] = min(b["start"], c["start"])
            b["n"] += 1
            b["confidence"] = max(b["confidence"], c["confidence"])
    items = sorted(best.values(), key=lambda x: x["start"])
    if not items:
        print("  (none)")
    for c in items[:max_caps]:
        print("  [%6.1f-%6.1f] x%-2d %s" % (c["start"], c["end"], c["n"],
                                            c["text"]))
    if len(items) > max_caps:
        print("  ... %d more unique captions" % (len(items) - max_caps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="video_ids, or empty for all")
    ap.add_argument("--all", action="store_true",
                    help="include noisy OCR fragments")
    ap.add_argument("--max-caps", type=int, default=60)
    args = ap.parse_args()
    ids = args.ids or sorted(p.stem for p in TRANSCRIPTS.glob("*.json"))
    for vid in ids:
        show(vid, args.all, args.max_caps)


if __name__ == "__main__":
    main()
