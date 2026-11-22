"""Generate videos.csv and claims.csv from the labels in labels.py.

The point of generating rather than hand-editing: video_level_label is *derived*
by the section 9 judge rules, so it can never drift from the claims that are
supposed to justify it, and split assignment is deterministic.

  python build_csvs.py            # write the CSVs
  python build_csvs.py --check    # print what it would write, change nothing
"""
import argparse
import csv
import random
import sys
# Windows consoles default to cp1252 and cannot print em-dashes or Greek letters.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import judge, is_mixed          # noqa: E402
import enrich                              # noqa: E402
from labels import LABELS, ANNOTATOR       # noqa: E402

DATASET = Path(__file__).resolve().parents[1]
VIDEOS_CSV = DATASET / "videos.csv"
CLAIMS_CSV = DATASET / "claims.csv"
INDEX_CSV = DATASET / "video_index.csv"

SPLIT_SEED = 20261121          # same seed as the blind subset; recorded in REVIEW.md
TEST_FRACTION = 0.70           # section 14: roughly 30/70 tune/test, per video

VIDEO_COLS = ["video_id", "source_url", "platform", "topic",
              "video_level_label", "text_type", "case_tags", "split",
              "annotator", "confidence", "review_status", "reviewer",
              "reviewer_notes", "notes"]

CLAIM_COLS = ["video_id", "claim_id", "claim_text", "claim_source",
              "start_seconds", "end_seconds", "speaker_stance",
              "claim_verdict", "evidence_supporting",
              "evidence_contradicting", "annotator", "confidence",
              "review_status", "reviewer", "reviewer_notes", "notes"]


def load_index():
    with open(INDEX_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["video_id"]: r for r in csv.DictReader(f)}


def assign_splits(video_ids):
    """Deterministic per-video tune/test assignment (section 14: split by video,
    never by sentence, so no video appears in both)."""
    ids = sorted(video_ids)
    rng = random.Random(SPLIT_SEED)
    shuffled = ids[:]
    rng.shuffle(shuffled)
    n_test = round(len(shuffled) * TEST_FRACTION)
    test = set(shuffled[:n_test])
    return {v: ("test" if v in test else "tune") for v in ids}


def join(values):
    return ";".join(values)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    index = load_index()
    splits = assign_splits([v["video_id"] for v in LABELS])

    video_rows, claim_rows = [], []
    for v in LABELS:
        vid = v["video_id"]
        if vid not in index:
            raise SystemExit("%s is not in video_index.csv" % vid)
        claims = v.get("claims", [])

        doc = enrich.load(vid)
        if doc is None and claims:
            raise SystemExit(
                "%s has claims but no transcripts/%s.json; run extract.py "
                "--stage merge first" % (vid, vid))

        for i, c in enumerate(claims, start=1):
            cid = c.get("claim_id") or ("c%d" % i)
            src = c.get("source") or enrich.derive_claim_source(
                doc, float(c["start"]), float(c["end"]))
            claim_rows.append({
                "video_id": vid,
                "claim_id": cid,
                "claim_text": c["text"],
                "claim_source": src,
                "start_seconds": c["start"],
                "end_seconds": c["end"],
                "speaker_stance": c["stance"],
                "claim_verdict": c["verdict"],
                "evidence_supporting": join(c.get("supporting", [])),
                "evidence_contradicting": join(c.get("contradicting", [])),
                "annotator": ANNOTATOR,
                "confidence": c.get("confidence", "medium"),
                "review_status": "pending",
                "reviewer": "",
                "reviewer_notes": "",
                "notes": c.get("notes", ""),
            })

        judged = [{"claim_id": r["claim_id"],
                   "speaker_stance": r["speaker_stance"],
                   "claim_verdict": r["claim_verdict"],
                   "evidence_supporting": r["evidence_supporting"],
                   "evidence_contradicting": r["evidence_contradicting"]}
                  for r in claim_rows if r["video_id"] == vid]
        label, _deciding = judge(judged)

        tags = list(v.get("case_tags", []))
        if is_mixed(judged) and "mixed" not in tags:
            tags.append("mixed")
        if not judged and "no_claims" not in tags:
            tags.append("no_claims")
        if len(judged) > 1 and "multi_claim" not in tags:
            tags.append("multi_claim")
        if len(judged) == 1 and "single_claim" not in tags:
            tags.append("single_claim")

        # text_type is derived from the OCR output by the documented rule in
        # enrich.py; an explicit value in labels.py overrides it.
        text_type = v.get("text_type")
        if not text_type:
            if doc is None:
                raise SystemExit(
                    "%s has no text_type and no transcript to derive one from"
                    % vid)
            text_type = enrich.derive_text_type(doc)[0]

        idx = index[vid]
        video_rows.append({
            "video_id": vid,
            "source_url": v.get("source_url", ""),
            "platform": v.get("platform") or idx.get("platform", "unknown"),
            "topic": v["topic"],
            "video_level_label": label,
            "text_type": text_type,
            "case_tags": join(tags),
            "split": splits[vid],
            "annotator": ANNOTATOR,
            "confidence": v.get("confidence", "medium"),
            "review_status": "pending",
            "reviewer": "",
            "reviewer_notes": "",
            "notes": v.get("notes", ""),
        })

    video_rows.sort(key=lambda r: r["video_id"])
    claim_rows.sort(key=lambda r: (r["video_id"],
                                   int(r["claim_id"].lstrip("c"))))

    if args.check:
        from collections import Counter
        print("videos=%d claims=%d" % (len(video_rows), len(claim_rows)))
        print("labels:", dict(Counter(r["video_level_label"]
                                      for r in video_rows)))
        print("splits:", dict(Counter(r["split"] for r in video_rows)))
        return

    with open(VIDEOS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=VIDEO_COLS)
        w.writeheader()
        w.writerows(video_rows)
    with open(CLAIMS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CLAIM_COLS)
        w.writeheader()
        w.writerows(claim_rows)
    print("wrote %d video rows -> %s" % (len(video_rows), VIDEOS_CSV.name))
    print("wrote %d claim rows -> %s" % (len(claim_rows), CLAIMS_CSV.name))


if __name__ == "__main__":
    main()
