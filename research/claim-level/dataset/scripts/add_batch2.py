"""Batch 2: map the new_* files to their sources, select the balanced subset,
and append the selected videos to video_index.csv as v83 onwards.

    python add_batch2.py --check   # print the mapping and selection only
    python add_batch2.py           # also write batch2_selection.csv and
                                   # append to video_index.csv (idempotent)

Inputs, all under sources/batch2/ (copies of the lists the files were
downloaded from; URLs only, no media):

  download_urls.txt, batch2_factcheck_urls.txt
      creator videos named in fact-check articles, plus @malditobulo's own
  batch2_m4health_tiktok_v2.txt, batch2_dataset_links.csv
      M4Health (TikTok) and MHMisinfo-Gold (YouTube), with each dataset's label
  candidates_full.csv
      candidates.csv from origin/data/fact-checked-candidates (321 rows):
      the fact-checker, its verdict word for word, and the article URL

Each file is matched to its source by the platform's native id in the
filename (new_<platform>_<id>.<ext>). Nothing is matched on handle or title.

Selection (recorded in PLAN.md, seed below):
  - every fact-checked creator video
  - 5 of the @malditobulo videos, tagged fact_checker_produced
  - every M4Health video (non-health ones are labelled out_of_scope later)
  - 10 of the MHMisinfo-Gold videos
  - nothing longer than 3 minutes, applied before sampling
"""
import argparse
import csv
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DATASET = Path(__file__).resolve().parents[1]
SOURCES = DATASET / "sources" / "batch2"
VIDEOS = DATASET / "videos"
INDEX = DATASET / "video_index.csv"
SELECTION = DATASET / "sources" / "batch2_selection.csv"

SELECTION_SEED = 20261123
MAX_SECONDS = 180
N_MALDITO = 5
N_MHMISINFO = 10
FIRST_ID = 83

# One file whose native id is not the id in the list it came from. yt-dlp
# names an X/Twitter download after the tweet that carries the media, which
# here is not the status that was linked. Resolved with
#   yt-dlp --skip-download --print "%(id)s %(webpage_url)s" <status url>
# which prints 1859626307996512256 for the linked status below.
RESOLVED = {
    "1859626307996512256":
        "https://x.com/sherryontopp/status/1859626801611305413",
}

INDEX_COLS = ["video_id", "filename", "relative_path", "collector",
              "collector_label", "creator_handle", "platform", "size_mb",
              "source", "source_label", "source_url", "external_label",
              "external_source", "external_url", "duration_seconds"]

PATTERNS = [
    r"tiktok\.com/(?:@[^/]*/video|embed)/([A-Za-z0-9_-]+)",
    r"instagram\.com/(?:[^/]+/)?(?:reel|p)/([A-Za-z0-9_-]+)",
    r"facebook\.com/(?:reel|[^/]+/videos|[^/]+/posts)/(\d+)",
    r"(?:twitter|x)\.com/[^/]+/status/(\d+)",
    r"youtube\.com/(?:shorts|live)/([A-Za-z0-9_-]{11})",
    r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
]


def native_id(url):
    for pat in PATTERNS:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def read_list(name):
    p = SOURCES / name
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def handle_of(url):
    m = re.search(r"tiktok\.com/(@[^/]+)/video", url)
    if m and m.group(1) != "@_":
        return m.group(1)
    m = re.search(r"instagram\.com/([^/]+)/reel", url)
    if m and m.group(1) not in ("reel", "p"):
        return "@" + m.group(1)
    m = re.search(r"(?:twitter|x)\.com/([^/]+)/status", url)
    if m:
        return "@" + m.group(1)
    return ""


def duration(path):
    ffprobe = (Path(__file__).resolve().parents[5]
               / "ffmpeg-7.1.1-essentials_build" / "bin" / "ffprobe.exe")
    exe = str(ffprobe) if ffprobe.exists() else "ffprobe"
    out = subprocess.run([exe, "-v", "error", "-show_entries",
                          "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    return round(float(json.loads(out)["format"]["duration"]), 1)


def load_verdicts():
    """platform video id -> candidates.csv row, for rows with a video URL.

    Matched on the platform id only, never on the full URL string, so a
    tracking parameter or a different URL form cannot break the match."""
    out = {}
    with open(SOURCES / "candidates_full.csv", encoding="utf-8",
              newline="") as f:
        for r in csv.DictReader(f):
            vid = native_id(r.get("video_url", ""))
            if vid and "(dataset)" not in r["fact_checker"]:
                out.setdefault(vid, r)
    return out


def build():
    urls = {}       # native id -> (list name, url)
    for name in ("download_urls.txt", "batch2_factcheck_urls.txt"):
        for u in read_list(name):
            urls.setdefault(native_id(u), (name, u))
    datasets = {r["dataset_video_id"]: r for r in csv.DictReader(
        open(SOURCES / "batch2_dataset_links.csv", encoding="utf-8"))}
    yt = {native_id(u): u for u in read_list("batch2_mhmisinfo_youtube.txt")}
    verdicts = load_verdicts()

    rows = []
    files = [p for p in VIDEOS.glob("new_*")
             if p.suffix.lower() in (".mp4", ".webm")]
    for p in sorted(files, key=lambda p: p.name.lower()):
        m = re.match(r"new_([A-Za-z]+)_(.+)\.(?:mp4|webm)$", p.name)
        platform, nid = m.group(1).lower(), m.group(2)
        url = RESOLVED.get(nid, "")
        list_name = "batch2_factcheck_urls.txt" if url else ""
        if nid in urls:
            list_name, url = urls[nid]
        ds = datasets.get(nid)
        ext_source = ext_url = ext_note = ext_tags = ""
        if ds:
            source = ds["dataset"]
            # M4Health labels every video FALSE and adds a category; both are
            # kept verbatim. MHMisinfo-Gold's label is kept as the raw value.
            label = ds["dataset_label"] + (
                " / " + ds["category"] if source == "M4Health" else "")
            ext_source = source
            url = (yt.get(nid, ds["built_url"]) if source == "MHMisinfo-Gold"
                   else ds["built_url"])
        else:
            source = ("" if not url else "fact_checker_produced"
                      if "malditobulo" in url else "fact_checked_creator")
            v = verdicts.get(nid) or verdicts.get(native_id(url) or "")
            label = v["fact_checker_verdict"] if v else ""
            if v:
                ext_source, ext_url = v["fact_checker"], v["fact_check_url"]
                ext_tags = v["candidate_tags"]
            elif source:
                ext_note = ("no row in candidates_full.csv carries this "
                            "video's platform id")
        rows.append({
            "filename": p.name, "platform": platform, "native_id": nid,
            "source": source, "source_label": label, "source_url": url,
            "external_label": label, "external_source": ext_source,
            "external_url": ext_url, "external_note": ext_note,
            "external_tags": ext_tags,
            "source_list": list_name if not ds else "batch2_dataset_links.csv",
            "creator_handle": handle_of(url),
            "size_mb": round(p.stat().st_size / (1024 * 1024), 1),
            "duration_seconds": duration(p),
        })

    rng = random.Random(SELECTION_SEED)
    for r in rows:
        r["selected"], r["skip_reason"] = "no", ""
        if not r["source"]:
            r["skip_reason"] = "source not found"
        elif r["duration_seconds"] > MAX_SECONDS:
            r["skip_reason"] = "longer than 3 minutes"

    def eligible(src):
        return sorted((r for r in rows
                       if r["source"] == src and not r["skip_reason"]),
                      key=lambda r: r["filename"].lower())

    picked = []
    picked += eligible("fact_checked_creator")
    picked += rng.sample(eligible("fact_checker_produced"), N_MALDITO)
    picked += eligible("M4Health")
    picked += rng.sample(eligible("MHMisinfo-Gold"), N_MHMISINFO)
    chosen = {r["filename"] for r in picked}
    for r in rows:
        if r["filename"] in chosen:
            r["selected"] = "yes"
        elif not r["skip_reason"]:
            r["skip_reason"] = "not sampled"

    sel = sorted((r for r in rows if r["selected"] == "yes"),
                 key=lambda r: r["filename"].lower())
    for i, r in enumerate(sel, start=FIRST_ID):
        r["video_id"] = "v%02d" % i
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rows = build()
    print("files: %d" % len(rows))
    print(Counter((r["source"] or "(none)", r["selected"], r["skip_reason"])
                  for r in rows))
    sel = [r for r in rows if r["selected"] == "yes"]
    print("selected: %d, %s-%s" % (len(sel), sel[0]["video_id"],
                                   sel[-1]["video_id"]))
    for src in ("fact_checked_creator", "fact_checker_produced",
                "M4Health", "MHMisinfo-Gold"):
        xs = [r for r in sel if r["source"] == src]
        print("  %-22s selected %3d, external_label matched %3d"
              % (src, len(xs), sum(1 for r in xs if r["external_label"])))
    if args.check:
        return

    cols = ["filename", "video_id", "selected", "skip_reason", "source",
            "source_label", "source_url", "external_label",
            "external_source", "external_url", "external_note",
            "external_tags", "source_list", "platform",
            "native_id", "creator_handle", "duration_seconds", "size_mb"]
    with open(SELECTION, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    with open(INDEX, encoding="utf-8-sig", newline="") as f:
        existing = list(csv.DictReader(f))
    keep = [r for r in existing if int(r["video_id"][1:]) < FIRST_ID]
    for r in keep:
        for c in INDEX_COLS:
            r.setdefault(c, "")
        if not r["source"]:
            r["source"] = "collector_bundle"
            r["source_label"] = r["collector_label"]
    for r in sel:
        keep.append({
            "video_id": r["video_id"], "filename": r["filename"],
            "relative_path": r["filename"], "collector": "",
            "collector_label": "", "creator_handle": r["creator_handle"],
            "platform": r["platform"], "size_mb": r["size_mb"],
            "source": r["source"], "source_label": r["source_label"],
            "source_url": r["source_url"],
            "external_label": r["external_label"],
            "external_source": r["external_source"],
            "external_url": r["external_url"],
            "duration_seconds": r["duration_seconds"],
        })
    with open(INDEX, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(keep)
    print("wrote %s and %d index rows" % (SELECTION.name, len(keep)))


if __name__ == "__main__":
    main()
