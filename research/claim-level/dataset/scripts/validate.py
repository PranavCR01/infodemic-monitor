"""Validation for the golden label set.

Checks, per docs/target-system-design.md section 10 and the dataset README:

  1. every label is drawn from its allowed set
  2. every claim's video_id exists in videos.csv, and claim_ids are unique
     and well formed within a video
  3. every video_level_label equals what the section 9 judge rules give for
     that video's claims
  4. no evidence field is empty unless the verdict is INSUFFICIENT_EVIDENCE,
     UNSUPPORTED or NOT_VERIFIABLE; an UNSUPPORTED claim cites nothing, is
     endorsed, and its notes open with its efficacy category and reason
  5. timestamps are sane, and inside the transcript's duration where known
  6. cited PMIDs and URLs were actually retrieved (present in evidence_cache/)
  7. the judge itself applies the revised section 9 rules in the doc's order
     (a self-test on synthetic claims), and each video's review_reasons equal
     what the rules and the section 11 triggers derive
  8. every claim has a claim_kind (section 4)
  9. every cited URL is a section 6 reference on a fact_of_record claim, with a
     reference_citations.csv row whose quoted passage is in the stored
     snapshot and whose hash matches it
 10. out_of_scope videos (section 14) have no claims and no other tag, and are
     left out of every count this script reports
 11. every collector-label disagreement has a written reason
 12. every video in video_index.csv is labelled; batch 2's source columns
     match video_index.csv; every disagreement with a source's own label
     (compare_external.py) has a written reason

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
from judge import (judge, is_mixed, has_true_and_false,  # noqa: E402
                   review_reasons, reason_kind, VERDICTS, STANCES,
                   VIDEO_LABELS, MISINFO_BASES, CLAIM_KINDS,
                   EFFICACY_CATEGORIES, JUDGE_REASONS)
from evidence import (load_reference, snapshot_text,  # noqa: E402
                      passage_found, reference_org)
import compare_collectors  # noqa: E402
import compare_external  # noqa: E402

DATASET = Path(__file__).resolve().parents[1]
VIDEOS_CSV = DATASET / "videos.csv"
CLAIMS_CSV = DATASET / "claims.csv"
INDEX_CSV = DATASET / "video_index.csv"
REFS_CSV = DATASET / "reference_citations.csv"
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
    "true_and_false", "out_of_scope", "fact_checker_produced",
}
OUT_OF_SCOPE = "out_of_scope"


def judge_self_test():
    """The section 9 rules on synthetic claims, one case per branch plus the
    order-sensitive combinations. If judge.py drifts from the doc, this fails
    before any real row is checked."""
    def c(stance, verdict, i=1):
        return {"claim_id": "c%d" % i, "speaker_stance": stance,
                "claim_verdict": verdict}
    E, R = "ENDORSES", "REFUTES"
    M = "MISINFO"
    cases = [
        ("endorsed false", [c(E, "CONTRADICTED")], M, "contradicted", []),
        ("denies a true claim", [c(R, "SUPPORTED")], M, "denies_supported",
         ["denies_supported:c1"]),
        ("rule 1 before rule 2",
         [c(E, "CONTRADICTED"), c(R, "SUPPORTED", 2)], M, "contradicted",
         ["denies_supported:c2"]),
        ("unproven efficacy", [c(E, "UNSUPPORTED")], M, "unproven",
         ["unproven_claim:c1"]),
        ("rule 2 before unproven",
         [c(E, "UNSUPPORTED"), c(R, "SUPPORTED", 2)], M, "denies_supported",
         ["denies_supported:c2", "unproven_claim:c1"]),
        ("unproven before debunking",
         [c(R, "CONTRADICTED"), c(E, "UNSUPPORTED", 2)], M, "unproven",
         ["unproven_claim:c2", "mixed_video"]),
        ("rule 2 before debunking",
         [c(R, "SUPPORTED"), c(R, "CONTRADICTED", 2)], M,
         "denies_supported", ["denies_supported:c1"]),
        ("debunk", [c(R, "CONTRADICTED")], "DEBUNKING", None, []),
        ("mixed video is MISINFO",
         [c(R, "CONTRADICTED"), c(E, "CONTRADICTED", 2)], M, "contradicted",
         ["mixed_video"]),
        ("refuted unsupported is not unproven",
         [c(R, "UNSUPPORTED")], "CANNOT_RECOGNIZE", None, []),
        ("judged, nothing false endorsed", [c(E, "SUPPORTED")],
         "NO_MISINFO", None, []),
        ("possible debunk raised under NO_MISINFO",
         [c(E, "SUPPORTED"), c(R, "INSUFFICIENT_EVIDENCE", 2)],
         "NO_MISINFO", None, ["possible_debunk:c2"]),
        ("any MIXED claim is a reason",
         [c(E, "SUPPORTED"), c(E, "MIXED", 2)], "NO_MISINFO", None,
         ["mixed_evidence:c2"]),
        ("refutes insufficient", [c(R, "INSUFFICIENT_EVIDENCE")],
         "CANNOT_RECOGNIZE", None, ["possible_debunk:c1"]),
        ("refutes mixed", [c(R, "MIXED")], "CANNOT_RECOGNIZE", None,
         ["possible_debunk:c1", "mixed_evidence:c1"]),
        ("refutes not verifiable", [c(R, "NOT_VERIFIABLE")],
         "CANNOT_RECOGNIZE", None, []),
        ("endorses insufficient", [c(E, "INSUFFICIENT_EVIDENCE")],
         "CANNOT_RECOGNIZE", None, ["nothing_judged"]),
        ("insufficient beside not verifiable",
         [c(E, "NOT_VERIFIABLE"), c("QUOTES", "INSUFFICIENT_EVIDENCE", 2)],
         "CANNOT_RECOGNIZE", None, ["nothing_judged"]),
        ("only not verifiable", [c(E, "NOT_VERIFIABLE")],
         "CANNOT_RECOGNIZE", None, []),
        ("refuted open is not nothing_judged",
         [c(R, "INSUFFICIENT_EVIDENCE"), c(E, "INSUFFICIENT_EVIDENCE", 2)],
         "CANNOT_RECOGNIZE", None, ["possible_debunk:c1"]),
        ("no claims", [], "CANNOT_RECOGNIZE", None, []),
    ]
    for name, claims, label, basis, reasons in cases:
        got_label, got_basis, _, got_reasons = judge(claims)
        if (got_label, got_basis, got_reasons) != (label, basis, reasons):
            err("judge self-test %r: expected %s %s %s, got %s %s %s"
                % (name, label, basis, reasons, got_label, got_basis,
                   got_reasons))

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
    index_ids, index = set(), {}
    if INDEX_CSV.exists():
        with open(INDEX_CSV, encoding="utf-8-sig", newline="") as f:
            index = {r["video_id"]: r for r in csv.DictReader(f)}
        index_ids = set(index)
    for vid in sorted(index_ids - {v["video_id"] for v in videos},
                      key=lambda v: int(v[1:])):
        err("%s: in video_index.csv but not labelled in videos.csv" % vid)
    for v in videos:
        for col in compare_external_cols():
            if index and v.get(col, "") != index.get(v["video_id"], {}).get(
                    col, ""):
                err("%s: %s differs from video_index.csv" % (v["video_id"],
                                                            col))

    retrieved_pmids, retrieved_urls = load_retrieved_ids()
    judge_self_test()

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
        if OUT_OF_SCOPE in tags and tags != [OUT_OF_SCOPE]:
            err("%s: out_of_scope must be the only tag, or the video leaks "
                "into category counts (has %s)" % (vid, ";".join(tags)))

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
        if c.get("claim_kind") not in CLAIM_KINDS:
            err("%s/%s: claim_kind %r not allowed (section 4: %s)"
                % (vid, cid, c.get("claim_kind"), " or ".join(CLAIM_KINDS)))
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
            if verdict not in ("INSUFFICIENT_EVIDENCE", "UNSUPPORTED",
                               "NOT_VERIFIABLE"):
                err("%s/%s: no evidence but verdict is %s (only "
                    "INSUFFICIENT_EVIDENCE, UNSUPPORTED or NOT_VERIFIABLE "
                    "may be bare)" % (vid, cid, verdict))
        if verdict == "UNSUPPORTED":
            if sup or con:
                err("%s/%s: UNSUPPORTED means nothing for or against, but "
                    "evidence is cited" % (vid, cid))
            if c["speaker_stance"] != "ENDORSES":
                err("%s/%s: UNSUPPORTED is only used on endorsed claims"
                    % (vid, cid))
            m = re.match(r"^UNSUPPORTED \((\w+)\): \S", c["notes"])
            if not m or m.group(1) not in EFFICACY_CATEGORIES:
                err("%s/%s: UNSUPPORTED notes must open with 'UNSUPPORTED "
                    "(<%s>): <reason>'"
                    % (vid, cid, "|".join(EFFICACY_CATEGORIES)))
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
                if not reference_org(ref):
                    err("%s/%s: URL %s is not on the section 6 reference "
                        "allow-list" % (vid, cid, ref))
                if c.get("claim_kind") != "fact_of_record":
                    err("%s/%s: cites reference %s but is not a "
                        "fact_of_record claim (section 6 picks references "
                        "from claim_kind)" % (vid, cid, ref))
            else:
                err("%s/%s: evidence %r is neither PMID:<digits> nor a URL"
                    % (vid, cid, ref))

    # ---- judge consistency (section 9) ---------------------------------
    for v in videos:
        vid = v["video_id"]
        cs = by_video.get(vid, [])
        expected, basis, deciding, _ = judge(cs)
        if v["video_level_label"] != expected:
            err("%s: video_level_label is %s but the section 9 rules give %s "
                "for its %d claim(s)"
                % (vid, v["video_level_label"], expected, len(cs)))
        if v.get("misinfo_basis", "") != (basis or ""):
            err("%s: misinfo_basis is %r but the rules give %r"
                % (vid, v.get("misinfo_basis"), basis or ""))
        if basis and basis not in MISINFO_BASES:
            err("%s: misinfo_basis %r not allowed" % (vid, basis))
        want = review_reasons(cs)
        if split_multi(v.get("review_reasons")) != want:
            err("%s: review_reasons are %r but the rules give %r"
                % (vid, v.get("review_reasons"), ";".join(want)))
        if OUT_OF_SCOPE in split_multi(v["case_tags"]) and cs:
            err("%s: tagged out_of_scope but has %d claim(s)" % (vid, len(cs)))
        if is_mixed(cs) and "mixed" not in split_multi(v["case_tags"]):
            err("%s: endorses one falsehood and refutes another but is not "
                "tagged 'mixed'" % vid)
        if has_true_and_false(cs) and                 "true_and_false" not in split_multi(v["case_tags"]):
            err("%s: carries both supported and contradicted claims but is "
                "not tagged 'true_and_false'" % vid)
        if not cs and not ({"no_claims", OUT_OF_SCOPE}
                           & set(split_multi(v["case_tags"]))):
            warn("%s: has no claims; tag it 'no_claims', or 'out_of_scope' "
                 "if it has no health content" % vid)

    check_reference_citations(claims)

    # ---- collector comparison -------------------------------------------
    for p in compare_collectors.check(compare_collectors.load()):
        err(p)
    for p in compare_external.check(compare_external.load()):
        err(p)

    # ---- coverage ------------------------------------------------------
    # Section 14: out_of_scope videos are left out of every count and metric.
    scoped = [v for v in videos
              if OUT_OF_SCOPE not in split_multi(v["case_tags"])]
    excluded = len(videos) - len(scoped)
    scoped_ids = {v["video_id"] for v in scoped}
    report(scoped, [c for c in claims if c["video_id"] in scoped_ids],
           by_video, excluded)


def compare_external_cols():
    return ("source", "external_label", "external_source", "external_url")


def check_reference_citations(claims):
    """Section 6: every reference URL cited in claims.csv has a citation row
    (evidence_id, retrieval date, quoted passage, snapshot hash), the passage
    is really in the stored snapshot, and no row cites something unused."""
    cited = set()
    for c in claims:
        for side, col in (("supporting", "evidence_supporting"),
                          ("contradicting", "evidence_contradicting")):
            for ref in split_multi(c[col]):
                if ref.startswith("http"):
                    cited.add((c["video_id"], c["claim_id"], side, ref))
    if not REFS_CSV.exists():
        if cited:
            err("reference_citations.csv is missing but %d reference(s) are "
                "cited; run scripts/cite_references.py" % len(cited))
        return
    with open(REFS_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    import hashlib
    have = set()
    for r in rows:
        key = (r["video_id"], r["claim_id"], r["side"], r["url"])
        tag = "%s/%s %s" % (r["video_id"], r["claim_id"], r["url"])
        if key in have:
            err("reference_citations: duplicate row %s" % tag)
        have.add(key)
        if key not in cited:
            err("reference_citations: %s (%s) is not cited in claims.csv"
                % (tag, r["side"]))
        want_id = "ref_" + hashlib.sha256(
            r["url"].encode("utf-8")).hexdigest()[:12]
        if r["evidence_id"] != want_id:
            err("reference_citations: %s evidence_id %s, expected %s"
                % (tag, r["evidence_id"], want_id))
        if r["source_org"] != reference_org(r["url"]):
            err("reference_citations: %s source_org %r does not match the "
                "allow-list" % (tag, r["source_org"]))
        rec = load_reference(r["url"])
        if not rec or not rec.get("ok"):
            err("reference_citations: %s has no stored snapshot" % tag)
            continue
        if rec.get("text_sha256") != r["snapshot_sha256"] or \
                hashlib.sha256(rec["text"].encode("utf-8")).hexdigest() \
                != r["snapshot_sha256"]:
            err("reference_citations: %s snapshot hash does not match" % tag)
        if rec.get("_retrieved_at") != r["retrieved_at"]:
            err("reference_citations: %s retrieved_at %s, snapshot says %s"
                % (tag, r["retrieved_at"], rec.get("_retrieved_at")))
        if not r["quoted_passage"].strip():
            err("reference_citations: %s has no quoted passage" % tag)
        elif not passage_found(r["quoted_passage"], snapshot_text(rec)):
            err("reference_citations: %s quoted passage is not in the "
                "snapshot" % tag)
    for key in sorted(cited - have):
        err("%s/%s: reference %s (%s) has no row in reference_citations.csv"
            % (key[0], key[1], key[3], key[2]))


def report(videos=None, claims=None, by_video=None, excluded=0):
    if videos is not None:
        print("videos: %d   claims: %d   (out_of_scope, excluded from every "
              "count: %d)" % (len(videos), len(claims), excluded))
        print("claim_kind:", dict(Counter(c["claim_kind"] for c in claims)))
        print("review reasons added by section 9 (videos):", {
            r: sum(any(reason_kind(x) == r
                       for x in split_multi(v["review_reasons"]))
                   for v in videos)
            for r in JUDGE_REASONS})
        print("misinfo_basis:", dict(Counter(
            v["misinfo_basis"] for v in videos if v["misinfo_basis"])))
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
        missing = sorted(CASE_TAGS - set(tag_counts) - {OUT_OF_SCOPE})
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
