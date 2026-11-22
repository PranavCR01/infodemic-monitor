"""Build video_index.csv: filename -> video_id, plus any signal carried by the
folder layout and filenames of the delivered bundle.

No media is read or copied here; this writes filenames only.
"""
import csv
import os
import re
import sys
# Windows consoles default to cp1252 and cannot print em-dashes or Greek letters.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

# Collector folder names -> the production MisinfoLabel they were sorting into.
# These are the *collectors'* priors, not our labels. We record them so our own
# labelling can be cross-checked against them (and disagreements surfaced).
COLLECTOR_LABEL = {
    "misinfo": "MISINFO",
    "misinformation": "MISINFO",
    "no-misinfo": "NO_MISINFO",
    "no misinfo": "NO_MISINFO",
    "no_misinformation": "NO_MISINFO",
    "debunking": "DEBUNKING",
    "no info": "CANNOT_RECOGNIZE",
}

HANDLE_RE = re.compile(r"ssstik\.io_@([A-Za-z0-9_.]+)_\d+", re.I)
FILE_LABEL_RE = re.compile(r"^(Misinformation|No_Misinformation)_\d+$", re.I)


def collector_label(rel: Path, stem: str) -> str:
    for part in rel.parts[:-1]:
        hit = COLLECTOR_LABEL.get(part.strip().lower())
        if hit:
            return hit
    m = FILE_LABEL_RE.match(stem)
    if m:
        return COLLECTOR_LABEL[m.group(1).lower()]
    return ""


def collector(rel: Path) -> str:
    """The student whose subfolder the video came from, where the layout says."""
    parts = list(rel.parts[:-1])
    for p in parts:
        if p.strip().lower() in COLLECTOR_LABEL:
            continue
        if p.startswith("Dataset-") or p.startswith("Misinfo Dataset"):
            continue
        return p
    return parts[0] if parts else ""


def main(root: str, out: str) -> None:
    root_p = Path(root)
    files = [
        p for p in root_p.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXT
    ]
    # Stable order: by lowercased basename, tie-broken by full relative path.
    files.sort(key=lambda p: (p.name.lower(), str(p.relative_to(root_p)).lower()))

    rows = []
    for i, p in enumerate(files, start=1):
        rel = p.relative_to(root_p)
        stem = p.stem
        handle = ""
        m = HANDLE_RE.search(p.name)
        if m:
            handle = "@" + m.group(1)
        rows.append({
            "video_id": f"v{i:02d}",
            "filename": p.name,
            "relative_path": str(rel).replace("\\", "/"),
            "collector": collector(rel),
            "collector_label": collector_label(rel, stem),
            "creator_handle": handle,
            "platform": "tiktok" if handle or "ssstik" in p.name.lower() else "unknown",
            "size_mb": round(p.stat().st_size / (1024 * 1024), 1),
        })

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")
    # quick summary
    from collections import Counter
    print("collector_label:", dict(Counter(r["collector_label"] or "(none)" for r in rows)))
    print("collector:", dict(Counter(r["collector"] for r in rows)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
