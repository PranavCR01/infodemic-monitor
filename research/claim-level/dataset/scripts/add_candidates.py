"""Append rows to candidates.csv, one fact-checked video per row.

Every video_url here is a link the fact-check article itself gives. Nothing is
constructed, guessed, or pattern-filled. Where an article gives no playable
platform URL, video_url is left EMPTY and the notes say so -- the row is still
useful as a lead, but it is not a downloadable video.

Rows come from two places: ROWS below (the first-pass batch, kept for
provenance) and every candidate_batches/*.jsonl file (one JSON object per line,
same keys as COLS). Add a new batch by dropping a new .jsonl file there.

De-duplicates on video_url (query string and trailing slash ignored). Rows with
an empty video_url are de-duplicated on (fact_check_url, dataset_video_id in
notes, or claim_summary). Rows whose video_url or creator handle is already in
the 82-video set (videos.csv / video_index.csv) are rejected. Safe to re-run.

Run:  .\\.venv\\Scripts\\python.exe research\\claim-level\\dataset\\scripts\\add_candidates.py
"""
import csv
import glob
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "candidates.csv")

COLS = ["video_url", "platform", "language", "fact_check_url", "fact_checker",
        "fact_checker_verdict", "claim_summary", "topic", "candidate_tags",
        "published_date", "notes"]

SF = "Health Feedback / Science Feedback"

ROWS = [
    # ---- the one article of 12 checked that gave a usable platform URL ----
    {
        "video_url": "https://www.tiktok.com/@drone721xxx/video/7284274028485938462",
        "platform": "tiktok", "language": "en",
        "fact_check_url": "https://science.feedback.org/review/viral-video-inaccurate-claims-sugar-causes-medical-conditions-cancer-adhd",
        "fact_checker": SF,
        "fact_checker_verdict": "Misleading",
        "claim_summary": "Sugar directly causes ADHD in babies, dementia and Alzheimer disease in adults, cancer and glaucoma; sugar addiction is eight times more powerful than cocaine.",
        "topic": "nutrition / sugar",
        "candidate_tags": "clearly_false;multi_claim",
        "published_date": "2023-10-27",
        "notes": "URL taken verbatim from the web.archive.org wrapper the article links: web.archive.org/web/20231023192146/https://www.tiktok.com/@drone721xxx/video/7284274028485938462 . Not constructed. The article also links a Twitter/X copy and a perma.cc Facebook capture. Live status of the TikTok not verified.",
    },

    # ---- verified fact-checks whose articles give NO platform video URL ----
    {
        "video_url": "", "platform": "tiktok", "language": "en",
        "fact_check_url": "https://fullfact.org/health/Amish-cancer-cure/",
        "fact_checker": "Full Fact",
        "fact_checker_verdict": "Partly false",
        "claim_summary": "A product called TO-MOR-GONE made by an Amish man cured cancer, tumours, skin disorders and infections and was suppressed by authorities.",
        "topic": "cancer / alternative remedies",
        "candidate_tags": "clearly_false",
        "published_date": "2022-07-29",
        "notes": "reported removed - Full Fact states the original TikTok no longer appears to be available on the platform; it was reshared to Facebook. Article gives no video URL, so video_url is empty.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "en",
        "fact_check_url": "https://science.feedback.org/review/tiktok-outdated-inaccurate-claims-depression-gary-brecka/",
        "fact_checker": SF,
        "fact_checker_verdict": "Inaccurate",
        "claim_summary": "Depression is defined as having low serotonin, and increasing serotonin in the gut ends depression.",
        "topic": "mental health / depression",
        "candidate_tags": "clearly_false;multi_claim",
        "published_date": "2025-06-19",
        "notes": "Creator: Gary Brecka. The article links four videos only through mvau.lt archive redirects, which do not expose the original TikTok URLs. video_url left empty rather than constructed.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "en",
        "fact_check_url": "https://science.feedback.org/review/vitamin-k-shot-doesnt-stop-stem-cells-from-circulating-or-change-blood-thickness/",
        "fact_checker": SF,
        "fact_checker_verdict": "Inaccurate",
        "claim_summary": "The vitamin K injection given at birth thickens a newborn blood and prevents stem cells from circulating.",
        "topic": "newborn care / vitamin K",
        "candidate_tags": "clearly_false",
        "published_date": "2026-10-13",
        "notes": "Creator named as chiropractor Daniel Pompa; the article cites a TikTok with 174,000 views but gives no platform URL. Most recent item found in this pass. video_url empty.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "en",
        "fact_check_url": "https://science.feedback.org/review/social-media-claims-urine-therapy-benefits-not-backed-scientific-evidence/",
        "fact_checker": SF,
        "fact_checker_verdict": "Unsupported",
        "claim_summary": "Drinking or applying urine provides health benefits, including from its urea content and urine-derived stem cells.",
        "topic": "alternative remedies / urine therapy",
        "candidate_tags": "clearly_false",
        "published_date": "2025-06-07",
        "notes": "Creators named: Daniel Pompa, KT The Arch Degree, Troy Casey. All videos linked via mvau.lt archive wrappers only. video_url empty.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "en",
        "fact_check_url": "https://science.feedback.org/review/no-evidence-chiropractor-bryan-ardis-claim-nicotine-cures-parkinsons-other-diseases/",
        "fact_checker": SF,
        "fact_checker_verdict": "Unsupported",
        "claim_summary": "Nicotine patches cure Parkinson disease, Alzheimer disease, autism and multiple sclerosis.",
        "topic": "neurology / nicotine",
        "candidate_tags": "clearly_false;multi_claim",
        "published_date": "2025-05-07",
        "notes": "Creator: Bryan Ardis. The article links web.archive.org wrappers that do not expose original platform URLs. video_url empty.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "en",
        "fact_check_url": "https://science.feedback.org/review/no-scientific-evidence-supporting-claims-of-diatomaceous-earths-detox-benefits",
        "fact_checker": SF,
        "fact_checker_verdict": "Unsupported",
        "claim_summary": "The silica in diatomaceous earth absorbs minerals and vitamins and removes parasites and heavy metals from the body.",
        "topic": "detox / supplements",
        "candidate_tags": "clearly_false",
        "published_date": "2024-10-18",
        "notes": "The article references the videos only through perma.cc captures; no playable URL is given. video_url empty.",
    },
    {
        "video_url": "https://www.facebook.com/ChrisDNeale/posts/1107295370206060/",
        "platform": "facebook reel (article says reposted from TikTok)",
        "language": "en",
        "fact_check_url": "https://leadstories.com/hoax-alert/2022/08/fact-check-video-does-not-prove-rife-machines-cure-cancer.html",
        "fact_checker": "Lead Stories",
        "fact_checker_verdict": "Not A Cure",
        "claim_summary": "Rife machines cure cancer through resonant frequency therapy, and the cure for cancer has already been found.",
        "topic": "cancer / devices",
        "candidate_tags": "clearly_false;speech_screen_disagree",
        "published_date": "2022-08-25",
        "notes": "STRONGEST speech_screen_disagree LEAD: Lead Stories notes an on-screen numerical correction appearing over the audio, changing 1.58 billion dollars to 158 billion dollars - on-screen text correcting what is said. The only URL the article gives is this Facebook post of the reel, not the original TikTok, and it is recorded exactly as given. Platform sits outside the TikTok/Reels/Shorts preference.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "es",
        "fact_check_url": "https://chequeado.com/el-explicador/es-enganoso-el-video-que-afirma-que-las-vacunas-contra-el-coronavirus-danan-el-corazon-de-los-jovenes/",
        "fact_checker": "Chequeado",
        "fact_checker_verdict": "Enganoso",
        "claim_summary": "Coronavirus vaccines permanently damage young people hearts (destruyen el corazon de por vida) and cause sudden death.",
        "topic": "vaccines / myocarditis",
        "candidate_tags": "clearly_false;other_language",
        "published_date": "2021-09-01",
        "notes": "Spanish. Verdict is Enganoso with a tilde on the n in the original. The article reports 220k views and 230k likes but gives no video URL. video_url empty.",
    },
    {
        "video_url": "", "platform": "tiktok", "language": "es",
        "fact_check_url": "https://chequeado.com/el-explicador/chequeo-a-un-video-de-tik-tok-sobre-la-vacuna-de-astrazeneca-contra-el-coronavirus/",
        "fact_checker": "Chequeado",
        "fact_checker_verdict": "Enganoso",
        "claim_summary": "An Oxford study showed the AstraZeneca vaccine carries a cerebral thrombosis risk similar to the Pfizer and Moderna vaccines.",
        "topic": "vaccines / thrombosis",
        "candidate_tags": "clearly_false;other_language;speech_screen_disagree",
        "published_date": "2021-09-08",
        "notes": "Spanish. Verdict is Enganoso with a tilde on the n. The article quotes on-screen text from an RT report shown inside the video, so this is also a speech_screen_disagree candidate. Over 430,000 views at publication; no video URL given. video_url empty.",
    },
]


DATASET = os.path.dirname(HERE)
BATCHES = os.path.join(DATASET, "candidate_batches")


def norm_url(u):
    return u.strip().split("?")[0].split("#")[0].rstrip("/").lower()


def key(r):
    u = r["video_url"].strip()
    if u:
        return ("url", norm_url(u))
    m = re.search(r"dataset_video_id=([\w-]+)", r.get("notes", ""))
    return ("lead", r["fact_check_url"].strip().rstrip("/"),
            m.group(1) if m else r["claim_summary"].strip().lower())


def golden_set():
    """URLs and creator handles already in the 82-video golden set."""
    urls, handles = set(), set()
    for name, col in (("videos.csv", "source_url"),
                      ("video_index.csv", "creator_handle")):
        path = os.path.join(DATASET, name)
        if not os.path.exists(path):
            continue
        with io.open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                v = (r.get(col) or "").strip()
                if v and col == "source_url":
                    urls.add(norm_url(v))
                elif v:
                    handles.add(v.lstrip("@").lower())
    return urls, handles


def batch_rows():
    rows = list(ROWS)
    for path in sorted(glob.glob(os.path.join(BATCHES, "*.jsonl"))):
        with io.open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except ValueError as e:
                        raise SystemExit("%s:%d: %s" % (path, n, e))
    return rows


def main():
    existing, seen = [], set()
    if os.path.exists(OUT):
        with io.open(OUT, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                existing.append({c: r.get(c, "") for c in COLS})
                seen.add(key(r))
    gold_urls, gold_handles = golden_set()
    added = rejected = 0
    for r in batch_rows():
        missing = [c for c in COLS if c not in r]
        if missing:
            raise SystemExit("row %r missing columns %s"
                             % (r.get("video_url"), missing))
        r = {c: (r[c] if r[c] is not None else "") for c in COLS}
        u = r["video_url"].strip()
        h = re.search(r"/@?([\w.\-]+)/(?:video|reel|p)/", u)
        if u and (norm_url(u) in gold_urls or
                  (h and h.group(1).lower() in gold_handles)):
            print("rejected (already in the golden set):", u)
            rejected += 1
            continue
        k = key(r)
        if k in seen:
            continue
        existing.append(r)
        seen.add(k)
        added += 1
    existing.sort(key=lambda r: (r["language"], r["fact_checker"],
                                 r["fact_check_url"]))
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(existing)

    from collections import Counter
    with_url = sum(1 for r in existing if r["video_url"].strip())
    print("added %d, rejected %d, total %d -> %s" % (added, rejected, len(existing),
                                        os.path.basename(OUT)))
    print("rows with a usable video_url: %d; leads without one: %d"
          % (with_url, len(existing) - with_url))
    print("by language:", dict(Counter(r["language"] for r in existing)))
    print("by fact_checker:", dict(Counter(r["fact_checker"]
                                           for r in existing)))
    tags = Counter()
    for r in existing:
        for t in [x.strip() for x in r["candidate_tags"].split(";")
                  if x.strip()]:
            tags[t] += 1
    print("by tag:", dict(tags.most_common()))


if __name__ == "__main__":
    main()
