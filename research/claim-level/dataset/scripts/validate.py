"""Validation for the golden label set.

Checks, per docs/target-system-design.md section 10 and the dataset README:

  1. every label is drawn from its allowed set
  2. every claim's video_id exists in videos.csv, and claim_ids are unique
     and well formed within a video
  3. every video_level_label equals what the section 9 judge rules give for
     that video's claims
  4. no evidence field is empty unless the verdict is INSUFFICIENT_EVIDENCE
     or NOT_VERIFIABLE
  5. timestamps are sane, and inside the transcript's duration where known
  6. cited PMIDs and URLs were actually retrieved (present in evidence_cache/)

Exit code is non-zero if anything fails, so this can gate a commit.
"""
import csv
import json
import re
import sys
# Windows consoles default to cp1252 and cannot print em-dashes or Greek letters.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import (judge, is_mixed, VERDICTS, STANCES,  # noqa: E402
                   VIDEO_LABELS)

DATASET = Path(__file__).resolve().parents[1]
VIDEOS_CSV = DATASET / "videos.csv"
CLAIMS_CSV = DATASET / "claims.csv"
INDEX_CSV = DATASET / "video_index.csv"
TRANSCRIPTS = DATASET / "transcripts"
CACHE = DATASET / "evidence_cache"

TEXT_TYPES = ("high_text", "low_text")
SPLITS = ("tune", "test")
CONFIDENCES = ("low", "medium", "high")
REVIEW_STATUSES = ("pending", "verified", "corrected", "blind_pending")
CLAIM_SOURCES = ("speech", "screen", "both")

CASE_TAGS = {
    "debunking", "satire", "mixed", "screen_only", "uncertain_science",
    "noisy_audio", "other_language", "multi_claim", "missing_evidence",
    "prompt_injection", "clearly_false", "accurate", "neutral_discussion",
    "speech_screen_disagree", "no_claims", "single_claim",
}

PMID_RE = re.compile(r"^PMID:(\d{4,9})$")

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def split_multi(value):
    return [p.strip() for p in (value or "").split(";") if p.strip()]


def load_retrieved_ids():
    """Every PMID and URL that evidence.py actually brought back."""
    pmids, urls = set(), set()
    if not CACHE.exists():
        return pmids, urls
    for p in CACHE.rglob("*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in rec.get("records", []) or []:
            if r.get("pmid"):
                pmids.add(str(r["pmid"]))
        if rec.get("pmid"):
            pmids.add(str(rec["pmid"]))
        if rec.get("url") and rec.get("ok"):
            urls.add(rec["url"])
    return pmids, urls


def main():
    for f in (VIDEOS_CSV, CLAIMS_CSV):
        if not f.exists():
            err("missing file: %s" % f)
    if errors:
        report()
        return

    with open(VIDEOS_CSV, encoding="utf-8-sig", newline="") as f:
        videos = list(csv.DictReader(f))
    with open(CLAIMS_CSV, encoding="utf-8-sig", newline="") as f:
        claims = list(csv.DictReader(f))
    index_ids = set()
    if INDEX_CSV.exists():
        with open(INDEX_CSV, encoding="utf-8-sig", newline="") as f:
            index_ids = {r["video_id"] for r in csv.DictReader(f)}

    retrieved_pmids, retrieved_urls = load_retrieved_ids()

    # ---- videos.csv ----------------------------------------------------
    seen = set()
    for v in videos:
        vid = v["video_id"]
        if vid in seen:
            err("%s: duplicate video_id in videos.csv" % vid)
        seen.add(vid)
        if index_ids and vid not in index_ids:
            err("%s: video_id is not in video_index.csv" % vid)
        if v["video_level_label"] not in VIDEO_LABELS:
            err("%s: video_level_label %r not allowed"
                % (vid, v["video_level_label"]))
        if v["text_type"] not in TEXT_TYPES:
            err("%s: text_type %r not allowed" % (vid, v["text_type"]))
        if v["split"] not in SPLITS:
            err("%s: split %r not allowed" % (vid, v["split"]))
        if v["confidence"] not in CONFIDENCES:
            err("%s: confidence %r not allowed" % (vid, v["confidence"]))
        if v["review_status"] not in REVIEW_STATUSES:
            err("%s: review_status %r not allowed"
                % (vid, v["review_status"]))
        if not v["annotator"].strip():
            err("%s: annotator is empty" % vid)
        tags = split_multi(v["case_tags"])
        if not tags:
            err("%s: case_tags is empty" % vid)
        for t in tags:
            if t not in CASE_TAGS:
                err("%s: unknown case_tag %r" % (vid, t))

    # ---- claims.csv ----------------------------------------------------
    by_video = defaultdict(list)
    for c in claims:
        vid = c["video_id"]
        cid = c["claim_id"]
        if vid not in seen:
            err("%s/%s: claim refers to a video_id not in videos.csv"
                % (vid, cid))
        if not re.match(r"^c\d+$", cid):
            err("%s/%s: claim_id must look like c1, c2, ..." % (vid, cid))
        if any(o["claim_id"] == cid for o in by_video[vid]):
            err("%s/%s: duplicate claim_id within the video" % (vid, cid))
        by_video[vid].append(c)

        if c["speaker_stance"] not in STANCES:
            err("%s/%s: speaker_stance %r not allowed"
                % (vid, cid, c["speaker_stance"]))
        if c["claim_verdict"] not in VERDICTS:
            err("%s/%s: claim_verdict %r not allowed"
                % (vid, cid, c["claim_verdict"]))
        if c["claim_source"] not in CLAIM_SOURCES:
            err("%s/%s: claim_source %r not allowed"
                % (vid, cid, c["claim_source"]))
        if c["confidence"] not in CONFIDENCES:
            err("%s/%s: confidence %r not allowed"
                % (vid, cid, c["confidence"]))
        if c["review_status"] not in REVIEW_STATUSES:
            err("%s/%s: review_status %r not allowed"
                % (vid, cid, c["review_status"]))
        if not c["annotator"].strip():
            err("%s/%s: annotator is empty" % (vid, cid))
        if not c["claim_text"].strip():
            err("%s/%s: claim_text is empty" % (vid, cid))

        # timestamps
        try:
            s = float(c["start_seconds"])
            e = float(c["end_seconds"])
            if s < 0 or e < 0:
                err("%s/%s: negative timestamp" % (vid, cid))
            if e < s:
                err("%s/%s: end_seconds %s before start_seconds %s"
                    % (vid, cid, e, s))
            tj = TRANSCRIPTS / ("%s.json" % vid)
            if tj.exists():
                dur = (json.loads(tj.read_text(encoding="utf-8"))
                       .get("transcript", {}).get("duration_seconds"))
                if dur and e > float(dur) + 1.0:
                    err("%s/%s: end_seconds %s beyond video duration %s"
                        % (vid, cid, e, dur))
        except ValueError:
            err("%s/%s: timestamps must be numbers (got %r, %r)"
                % (vid, cid, c["start_seconds"], c["end_seconds"]))

        # evidence presence rule
        sup = split_multi(c["evidence_supporting"])
        con = split_multi(c["evidence_contradicting"])
        verdict = c["claim_verdict"]
        if not sup and not con:
            if verdict not in ("INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE"):
                err("%s/%s: no evidence but verdict is %s (only "
                    "INSUFFICIENT_EVIDENCE or NOT_VERIFIABLE may be bare)"
                    % (vid, cid, verdict))
        if verdict == "SUPPORTED" and not sup:
            err("%s/%s: SUPPORTED with no supporting evidence" % (vid, cid))
        if verdict == "CONTRADICTED" and not con:
            err("%s/%s: CONTRADICTED with no contradicting evidence"
                % (vid, cid))
        if verdict == "MIXED" and not (sup and con):
            err("%s/%s: MIXED needs evidence on both sides" % (vid, cid))

        # every cited id must have been retrieved
        for ref in sup + con:
            m = PMID_RE.match(ref)
            if m:
                if retrieved_pmids and m.group(1) not in retrieved_pmids:
                    err("%s/%s: PMID %s is not in evidence_cache -- it was "
                        "not retrieved" % (vid, cid, m.group(1)))
            elif ref.startswith("http"):
                if retrieved_urls and ref not in retrieved_urls:
                    err("%s/%s: URL %s is not in evidence_cache -- it was "
                        "not retrieved" % (vid, cid, ref))
            else:
                err("%s/%s: evidence %r is neither PMID:<digits> nor a URL"
                    % (vid, cid, ref))

    # ---- judge consistency (section 9) ---------------------------------
    for v in videos:
        vid = v["video_id"]
        cs = by_video.get(vid, [])
        expected, deciding = judge(cs)
        if v["video_level_label"] != expected:
            err("%s: video_level_label is %s but the section 9 rules give %s "
                "for its %d claim(s)"
                % (vid, v["video_level_label"], expected, len(cs)))
        if is_mixed(cs) and "mixed" not in split_multi(v["case_tags"]):
            err("%s: endorses one falsehood and refutes another but is not "
                "tagged 'mixed'" % vid)
        if not cs and "no_claims" not in split_multi(v["case_tags"]):
            warn("%s: has no claims; consider the 'no_claims' tag" % vid)

    # ---- coverage ------------------------------------------------------
    report(videos, claims, by_video)


def report(videos=None, claims=None, by_video=None):
    if videos is not None:
        print("videos: %d   claims: %d" % (len(videos), len(claims)))
        print("video_level_label:",
              dict(Counter(v["video_level_label"] for v in videos)))
        print("split:", dict(Counter(v["split"] for v in videos)))
        print("text_type:", dict(Counter(v["text_type"] for v in videos)))
        print("speaker_stance:",
              dict(Counter(c["speaker_stance"] for c in claims)))
        print("claim_verdict:",
              dict(Counter(c["claim_verdict"] for c in claims)))
        print("claim_source:",
              dict(Counter(c["claim_source"] for c in claims)))
        tag_counts = Counter()
        for v in videos:
            for t in split_multi(v["case_tags"]):
                tag_counts[t] += 1
        print("case_tags:", dict(tag_counts.most_common()))
        missing = sorted(CASE_TAGS - set(tag_counts))
        if missing:
            print("case_tags with no videos:", ", ".join(missing))
    print()
    for w in warnings:
        print("WARN  %s" % w)
    if errors:
        print()
        for e in errors:
            print("FAIL  %s" % e)
        print("\n%d error(s), %d warning(s)" % (len(errors), len(warnings)))
        sys.exit(1)
    print("OK — %d warning(s), no errors" % len(warnings))


if __name__ == "__main__":
    main()
