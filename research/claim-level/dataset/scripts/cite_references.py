"""Write reference_citations.csv: the section 6 citation record for every
authoritative reference (a URL, not a PMID) cited in claims.csv.

Section 6: each reference is "cited like papers", with an evidence_id built by
code (ref_<hash>), the URL, the date retrieved and the quoted passage, and "a
snapshot of the fetched text is stored with its hash". The snapshot lives in
evidence_cache/reference/ (written by evidence.py fetch_reference); this script
refuses to write a row whose passage is not actually in that snapshot.

  python cite_references.py          # write reference_citations.csv
"""
import csv
import hashlib
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import (load_reference, snapshot_text,  # noqa: E402
                      passage_found, reference_org)

DATASET = Path(__file__).resolve().parents[1]
OUT = DATASET / "reference_citations.csv"
COLS = ["evidence_id", "video_id", "claim_id", "side", "url", "source_org",
        "retrieved_at", "snapshot_sha256", "quoted_passage"]

FDC = "https://api.nal.usda.gov/fdc/v1/food/%d?api_key=DEMO_KEY"
FDA_THIMEROSAL = ("https://www.fda.gov/vaccines-blood-biologics/"
                  "safety-availability-biologics/thimerosal-and-vaccines")

# (video_id, claim_id, side, url, quoted passage). " ... " separates fragments
# with words elided between them.
CITATIONS = [
    ("v03", "c18", "supporting", FDC % 170277,
     "Sweetener, syrup, agave ... Glucose: 12.43 g ... Fructose: 55.6 g"),
    ("v38", "c1", "supporting",
     "https://www.fda.gov/vaccines-blood-biologics/"
     "safety-availability-biologics/fda-approves-required-updated-warning-"
     "labeling-mrna-covid-19-vaccines-regarding-myocarditis-and",
     "The warning on myocarditis and pericarditis in the Prescribing "
     "Information for Comirnaty and Spikevax has been updated to convey that "
     "the observed risk of myocarditis and pericarditis following vaccination "
     "with mRNA COVID-19 vaccines has been highest in males 12 through 24 "
     "years of age"),
    ("v41", "c2", "supporting",
     "https://www.nhs.uk/live-well/best-way-to-wash-your-hands/",
     "10. Dry your hands completely with a disposable towel. 11. Use the "
     "disposable towel to turn off the tap."),
    ("v57", "c2", "supporting",
     "https://www.who.int/news-room/fact-sheets/detail/measles",
     "The virus remains active and contagious in the air or on infected "
     "surfaces for up to two hours."),
    ("v63", "c6", "supporting",
     "https://www.who.int/initiatives/behealthy/physical-activity",
     "Adults aged 18–64 years Should do at least 150 minutes of "
     "moderate-intensity physical activity throughout the week, or do at "
     "least 75 minutes of vigorous-intensity physical activity, or an "
     "equivalent combination of both."),
    ("v66", "c3", "supporting", FDA_THIMEROSAL,
     "All vaccines routinely recommended for children 6 years of age and "
     "younger in the U.S. are available in formulations that do not contain "
     "thimerosal."),
    ("v66", "c3", "contradicting", FDA_THIMEROSAL,
     "Thimerosal Content of Available FDA-Approved Seasonal Influenza "
     "Vaccines ... Afluria (multi-dose presentation) Seqirus Pty Ltd 0.01% "
     "(24.5 mcg/0.5 mL dose, 12.25 mcg/0.25 mL dose)"),
    ("v68", "c2", "supporting",
     "https://wwwn.cdc.gov/tsp/PHS/PHS.aspx?phsid=336&toxid=59",
     "The EPA has set a maximum amount of atrazine allowable in drinking "
     "water of 3 µg/L."),
    ("v70", "c2", "supporting", FDC % 174832,
     "Beverages, almond milk, unsweetened, shelf stable ... Calcium, Ca: "
     "184.0 mg ... Vitamin D (D2 + D3): 1.0 µg"),
    ("v70", "c2", "supporting", FDC % 2257045,
     "Almond milk, unsweetened, plain, refrigerated ... Calcium, Ca: 157.5 mg "
     "... Vitamin D (D2 + D3): 1.59 µg"),
    ("v70", "c2", "supporting", FDC % 2257046,
     "Oat milk, unsweetened, plain, refrigerated ... Calcium, Ca: 148.5 mg "
     "... Vitamin D (D2 + D3): 1.7 µg"),
    ("v70", "c2", "supporting", FDC % 171265,
     "Milk, whole, 3.25% milkfat, with added vitamin D ... Calcium, Ca: 113.0 "
     "mg ... Vitamin D (D2 + D3): 1.3 µg"),
]


def evidence_id(url):
    """Section 6: ref_<hash>, built by code from the URL."""
    return "ref_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def main():
    rows, problems = [], []
    for vid, cid, side, url, passage in CITATIONS:
        rec = load_reference(url)
        if not rec or not rec.get("ok"):
            problems.append("%s/%s: %s was never retrieved" % (vid, cid, url))
            continue
        if not passage_found(passage, snapshot_text(rec)):
            problems.append("%s/%s: passage not in the snapshot of %s"
                            % (vid, cid, url))
            continue
        rows.append({
            "evidence_id": evidence_id(url),
            "video_id": vid, "claim_id": cid, "side": side, "url": url,
            "source_org": reference_org(url),
            "retrieved_at": rec["_retrieved_at"],
            "snapshot_sha256": rec["text_sha256"],
            "quoted_passage": passage,
        })
    if problems:
        for p in problems:
            print("FAIL ", p)
        sys.exit(1)
    rows.sort(key=lambda r: (r["video_id"], int(r["claim_id"][1:]),
                             r["side"], r["url"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print("wrote %d reference citations -> %s" % (len(rows), OUT.name))


if __name__ == "__main__":
    main()
