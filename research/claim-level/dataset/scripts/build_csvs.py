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
from judge import (judge, is_mixed, has_true_and_false,  # noqa: E402
                   review_reasons, CLAIM_KINDS, EFFICACY_CATEGORIES)
import enrich                              # noqa: E402
from blind_subset import batch_of          # noqa: E402
from labels import LABELS, ANNOTATOR       # noqa: E402
import adjudication                        # noqa: E402

DATASET = Path(__file__).resolve().parents[1]
VIDEOS_CSV = DATASET / "videos.csv"
CLAIMS_CSV = DATASET / "claims.csv"
INDEX_CSV = DATASET / "video_index.csv"

SPLIT_SEED = 20261121          # same seed as the blind subset; recorded in REVIEW.md
TEST_FRACTION = 0.70           # section 14: roughly 30/70 tune/test, per video

VIDEO_COLS = ["video_id", "source_url", "platform", "topic",
              "video_level_label", "misinfo_basis", "review_reasons", "text_type", "case_tags", "split",
              "annotator", "confidence", "review_status", "reviewer",
              "reviewer_notes", "notes", "source", "external_label",
              "external_source", "external_url"]

# Carried over from video_index.csv. external_label is the source's own label,
# verbatim: the fact-checker's verdict, or the dataset's label (batch 2).
EXTERNAL_COLS = ("source", "external_label", "external_source", "external_url")

CLAIM_COLS = ["video_id", "claim_id", "claim_text", "claim_source",
              "claim_kind",
              "start_seconds", "end_seconds", "speaker_stance",
              "claim_verdict", "evidence_supporting",
              "evidence_contradicting", "annotator", "confidence",
              "review_status", "reviewer", "reviewer_notes", "notes"]


def load_index():
    with open(INDEX_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["video_id"]: r for r in csv.DictReader(f)}


def assign_splits(video_ids):
    """Deterministic per-video tune/test assignment (section 14: split by video,
    never by sentence, so no video appears in both).

    Each batch is split on its own with the same seed, so adding a batch
    never moves a video that is already in tune or test."""
    out = {}
    for batch in sorted({batch_of(v) for v in video_ids}):
        ids = sorted(v for v in video_ids if batch_of(v) == batch)
        rng = random.Random(SPLIT_SEED)
        shuffled = ids[:]
        rng.shuffle(shuffled)
        n_test = round(len(shuffled) * TEST_FRACTION)
        test = set(shuffled[:n_test])
        out.update({v: ("test" if v in test else "tune") for v in ids})
    return out


def join(values):
    return ";".join(values)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    index = load_index()
    splits = assign_splits([v["video_id"] for v in LABELS])

    video_rows, claim_rows = [], []
    # Pass 1: first-pass claim rows for every video.
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
            if c.get("kind") not in CLAIM_KINDS:
                raise SystemExit("%s claim %d: kind must be one of %s"
                                 % (vid, i, ", ".join(CLAIM_KINDS)))
            cid = c.get("claim_id") or ("c%d" % i)
            notes = c.get("notes", "")
            if c["verdict"] == "UNSUPPORTED":
                # Section 7: only an efficacy claim can be UNSUPPORTED, and the
                # reason for the change leads the notes.
                if (c.get("claim_category") not in EFFICACY_CATEGORIES
                        or not c.get("unsupported_reason")):
                    raise SystemExit(
                        "%s claim %d: UNSUPPORTED needs claim_category (%s) "
                        "and unsupported_reason" % (
                            vid, i, " or ".join(EFFICACY_CATEGORIES)))
                notes = "UNSUPPORTED (%s): %s %s" % (
                    c["claim_category"], c["unsupported_reason"], notes)
            src = c.get("source") or enrich.derive_claim_source(
                doc, float(c["start"]), float(c["end"]))
            claim_rows.append({
                "video_id": vid,
                "claim_id": cid,
                "claim_text": c["text"],
                "claim_source": src,
                "claim_kind": c["kind"],
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
                "notes": notes.strip(),
            })

    first_rows = [dict(r) for r in claim_rows]
    claim_rows, _agreed = adjudication.apply(claim_rows)

    # Pass 2: derive each video's label from its (adjudicated) claims.
    for v in LABELS:
        vid = v["video_id"]
        doc = enrich.load(vid)
        first_judged = [r for r in first_rows if r["video_id"] == vid]
        _fl, _fb, _d, _r = judge(first_judged)
        first_label_basis = (_fl, _fb or "")
        judged = [{"claim_id": r["claim_id"],
                   "speaker_stance": r["speaker_stance"],
                   "claim_verdict": r["claim_verdict"],
                   "evidence_supporting": r["evidence_supporting"],
                   "evidence_contradicting": r["evidence_contradicting"]}
                  for r in claim_rows if r["video_id"] == vid]
        label, basis, _deciding, _reasons = judge(judged)
        reasons = review_reasons(judged)

        tags = list(v.get("case_tags", []))
        # Section 14: an out_of_scope video carries no other tag, so it can't
        # leak into any category count.
        out_of_scope = "out_of_scope" in tags
        if is_mixed(judged) and "mixed" not in tags:
            tags.append("mixed")
        if has_true_and_false(judged) and "true_and_false" not in tags:
            tags.append("true_and_false")
        if out_of_scope:
            if judged:
                raise SystemExit("%s is out_of_scope but has claims" % vid)
            tags = ["out_of_scope"]
        elif not judged and "no_claims" not in tags:
            tags.append("no_claims")
        if (index[vid].get("source") == "fact_checker_produced"
                and not out_of_scope
                and "fact_checker_produced" not in tags):
            tags.append("fact_checker_produced")
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
            "misinfo_basis": basis or "",
            "review_reasons": join(reasons),
            "text_type": text_type,
            "case_tags": join(tags),
            "split": splits[vid],
            "annotator": ANNOTATOR,
            "confidence": v.get("confidence", "medium"),
            "review_status": "pending",
            "reviewer": "",
            "reviewer_notes": "",
            "notes": v.get("notes", ""),
            **{c: idx.get(c, "") for c in EXTERNAL_COLS},
        })
        adjudication.apply_video(video_rows[-1], first_label_basis)

    video_rows.sort(key=lambda r: int(r["video_id"][1:]))
    claim_rows.sort(key=lambda r: (int(r["video_id"][1:]),
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
