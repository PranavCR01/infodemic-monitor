"""Summary statistics for the golden label set, for the PR description and for
the check-in log. Reads the generated CSVs, so it reports what was actually
written rather than what labels.py intended.

  python stats.py
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DATASET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import CASE_TAGS, split_multi   # noqa: E402

# The section 14 hard-case table, mapped onto the tag vocabulary.
SECTION_14 = {
    "Clearly false claims": "clearly_false",
    "Accurate information": "accurate",
    "Debunking videos": "debunking",
    "Neutral discussion": "neutral_discussion",
    "Satire and sarcasm": "satire",
    "Mixed videos (true and false claims)": "true_and_false",
    "Claims only on screen": "screen_only",
    "Speech and screen disagreeing": "speech_screen_disagree",
    "Noisy audio": "noisy_audio",
    "Other languages": "other_language",
    "Real scientific uncertainty": "uncertain_science",
    "Missing or irrelevant evidence": "missing_evidence",
    "Prompt-injection attempts": "prompt_injection",
    "Several claims per video": "multi_claim",
}

# Not a section 14 row: section 9's narrower judge-policy edge case.
SECTION_9_MIXED = "mixed"


def load(name):
    with open(DATASET / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    videos = load("videos.csv")
    claims = load("claims.csv")
    index = {r["video_id"]: r for r in load("video_index.csv")}

    print("## Counts\n")
    print("- videos: %d" % len(videos))
    print("- claims: %d" % len(claims))
    vids_with = len({c["video_id"] for c in claims})
    print("- videos with at least one claim: %d (%d with none)"
          % (vids_with, len(videos) - vids_with))
    print()

    for col, title in (("video_level_label", "video_level_label"),
                       ("split", "split"),
                       ("text_type", "text_type"),
                       ("confidence", "video confidence")):
        c = Counter(v[col] for v in videos)
        print("- %s: %s" % (title, ", ".join(
            "%s %d" % (k, n) for k, n in c.most_common())))
    print()
    for col, title in (("speaker_stance", "speaker_stance"),
                       ("claim_verdict", "claim_verdict"),
                       ("claim_source", "claim_source"),
                       ("confidence", "claim confidence")):
        c = Counter(x[col] for x in claims)
        print("- %s: %s" % (title, ", ".join(
            "%s %d" % (k, n) for k, n in c.most_common())))
    print()

    print("## case_tags coverage against section 14\n")
    tag_counts = Counter()
    for v in videos:
        for t in split_multi(v["case_tags"]):
            tag_counts[t] += 1
    missing = []
    for label, tag in SECTION_14.items():
        n = tag_counts.get(tag, 0)
        print("- %-38s %-24s %s" % (label, tag,
                                    n if n else "MISSING"))
        if not n:
            missing.append((label, tag))
    extra = sorted(set(tag_counts) - set(SECTION_14.values()))
    if extra:
        print("\n- other tags in use: %s" % ", ".join(
            "%s %d" % (t, tag_counts[t]) for t in extra))
    if missing:
        print("\n- NOT COVERED: %s" % "; ".join(
            "%s (%s)" % (lab, tag) for lab, tag in missing))
    print()

    print("## Collector folder label vs derived label\n")
    agree, disagree, unlabelled = 0, [], 0
    for v in videos:
        cl = (index.get(v["video_id"], {}) or {}).get("collector_label", "")
        if not cl:
            unlabelled += 1
            continue
        if cl == v["video_level_label"]:
            agree += 1
        else:
            disagree.append((v["video_id"], cl, v["video_level_label"]))
    print("- collector label present: %d; agree %d; disagree %d; "
          "no folder label %d"
          % (agree + len(disagree), agree, len(disagree), unlabelled))
    for vid, cl, ours in sorted(disagree):
        print("  - %s: collectors %s -> derived %s" % (vid, cl, ours))
    print()

    print("## Evidence\n")
    pmids, urls = set(), set()
    for x in claims:
        for ref in split_multi(x["evidence_supporting"]) + \
                split_multi(x["evidence_contradicting"]):
            (pmids if ref.startswith("PMID:") else urls).add(ref)
    cited = sum(1 for x in claims
                if split_multi(x["evidence_supporting"])
                or split_multi(x["evidence_contradicting"]))
    print("- claims citing at least one source: %d of %d"
          % (cited, len(claims)))
    print("- distinct PMIDs cited: %d" % len(pmids))
    print("- distinct URLs cited: %d" % len(urls))
    cache = DATASET / "evidence_cache"
    for kind in ("search", "abstract", "fulltext", "page"):
        d = cache / kind
        if d.exists():
            print("- cached %s responses: %d" % (kind,
                                                 len(list(d.glob("*.json")))))
    print()

    print("## Claims per video (top 10)\n")
    per = Counter(x["video_id"] for x in claims)
    for vid, n in per.most_common(10):
        print("- %s: %d" % (vid, n))
    print()

    print("## Review load (section 11 triggers present in the data)\n")
    trig = defaultdict(list)
    for x in claims:
        if x["claim_verdict"] in ("INSUFFICIENT_EVIDENCE", "MIXED"):
            trig[x["claim_verdict"]].append(x["video_id"])
        if x["speaker_stance"] == "UNCLEAR":
            trig["UNCLEAR stance"].append(x["video_id"])
        if split_multi(x["evidence_supporting"]) and \
                split_multi(x["evidence_contradicting"]):
            trig["both sides cited"].append(x["video_id"])
        if x["confidence"] == "low":
            trig["low confidence"].append(x["video_id"])
    for k, v in sorted(trig.items()):
        print("- %s: %d claim(s) across %d video(s)"
              % (k, len(v), len(set(v))))


if __name__ == "__main__":
    main()
