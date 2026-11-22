"""Append rows to candidates.csv, one fact-checked video per row.

Every video_url here is a link the fact-check article itself gives. Nothing is
constructed, guessed, or pattern-filled. Where an article gives no playable
platform URL, video_url is left EMPTY and the notes say so -- the row is still
useful as a lead, but it is not a downloadable video.

Appends and de-duplicates on video_url, so it is safe to re-run and safe to use
incrementally across sessions. Rows with an empty video_url are always appended
(they cannot be de-duplicated), so add them once.

Run:  .\\.venv\\Scripts\\python.exe research\\claim-level\\dataset\\scripts\\add_candidates.py
"""
import csv
import io
import os

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


def main():
    existing, seen = [], set()
    if os.path.exists(OUT):
        with io.open(OUT, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                existing.append(r)
                u = r["video_url"].strip()
                if u:
                    seen.add(u)
    added = 0
    for r in ROWS:
        u = r["video_url"].strip()
        if u and u in seen:
            continue
        missing = [c for c in COLS if c not in r]
        if missing:
            raise SystemExit("row %r missing columns %s" % (u, missing))
        existing.append({c: r.get(c, "") for c in COLS})
        if u:
            seen.add(u)
        added += 1
    existing.sort(key=lambda r: (r["language"], r["fact_checker"],
                                 r["fact_check_url"]))
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(existing)

    from collections import Counter
    with_url = sum(1 for r in existing if r["video_url"].strip())
    print("added %d, total %d -> %s" % (added, len(existing),
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
