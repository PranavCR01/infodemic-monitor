"""Compare the collectors' original labels with the derived video_level_label.

The collectors' labels are the Box folders they filed each video under
(MISINFO / DEBUNKING / NO-MISINFO / No info), recorded as collector_label in
video_index.csv; 55 of 82 videos have one. Videos tagged out_of_scope are
listed but left out of every number (section 14).

  python compare_collectors.py         # write collector_agreement.md
  python compare_collectors.py --check # fail if a disagreement has no reason
"""
import csv
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import VIDEO_LABELS  # noqa: E402

DATASET = Path(__file__).resolve().parents[1]
OUT = DATASET / "collector_agreement.md"

# One line per disagreement: why the section 9 label differs from the folder.
REASONS = {
    "v03": "No claim is contradicted by evidence: 8 of 18 are SUPPORTED and "
           "the weak ones (dyes and DNA damage, fructose and cancer) are "
           "INSUFFICIENT or MIXED, not false.",
    "v12": "'You pee out the fat' is almost certainly false, but the paper "
           "that settles it has no readable abstract or PMC copy and "
           "Bookshelf blocks scripted retrieval, so all three claims are "
           "INSUFFICIENT.",
    "v13": "Vague, anecdotal weight-loss advice; nothing retrieved tests or "
           "contradicts any of it, so no claim can be judged.",
    "v17": "The misinformation sits in regulatory assertions (FDA chemical "
           "counts, Texas labels) that are not health claims; the one health "
           "claim left is NOT_VERIFIABLE.",
    "v44": "The death anecdote is NOT_VERIFIABLE and nothing tests the "
           "'ancient pathogens, no immunity' claim: unjudgeable rather than "
           "accurate.",
    "v54": "Probably right, but the cited Michigan 5,800-food study could not "
           "be retrieved and the rest is unquantified or an aphorism.",
    "v60": "All three claims (BPA/BPS in receipts, skin absorption, less "
           "handling means less exposure) are SUPPORTED by measured "
           "absorption studies.",
    "v64": "Every claim is a count from immunisation schedules; CDC's "
           "schedule pages refuse scripted retrieval, so the refuted claim "
           "stays INSUFFICIENT. Now sent to review as a possible debunk.",
    "v65": "His critique of the PURE salt study is methodological; the "
           "refuted claim is MIXED in the literature, not contradicted. Now "
           "sent to review as a possible debunk.",
    "v68": "The refuted tap-water/testosterone chain has no human test; his "
           "atrazine-limit claim is SUPPORTED (ATSDR), and NO_MISINFO fires "
           "before the possible-debunk rule.",
    "v70": "The refuted 'least processed' claim is NOT_VERIFIABLE and the "
           "cancer insinuation untested; her fortification claim is "
           "SUPPORTED (FoodData Central).",
    "v75": "Sunscreen actives reaching the bloodstream after one day is "
           "SUPPORTED by FDA trials; the leap to harm is INSUFFICIENT, not "
           "contradicted.",
    "v76": "The refuted 'renamed dyes' claim is about naming intent "
           "(NOT_VERIFIABLE); her 'Allura Red is Red 40' claim is SUPPORTED.",
}


def cohen_kappa(pairs):
    n = len(pairs)
    if not n:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def load():
    with open(DATASET / "video_index.csv", encoding="utf-8-sig") as f:
        idx = {r["video_id"]: r for r in csv.DictReader(f)}
    with open(DATASET / "videos.csv", encoding="utf-8") as f:
        videos = list(csv.DictReader(f))
    rows = []
    for v in videos:
        i = idx[v["video_id"]]
        if not i["collector_label"]:
            continue
        rows.append({
            "video_id": v["video_id"],
            "collector": i["collector"],
            "collector_label": i["collector_label"],
            "label": v["video_level_label"],
            "out_of_scope": "out_of_scope" in v["case_tags"].split(";"),
            "topic": v["topic"],
            "review": v["review_reasons"],
        })
    return rows


def check(rows):
    """Problems a reader of the comparison would trip on."""
    problems = []
    for r in rows:
        if r["out_of_scope"]:
            continue
        dis = r["collector_label"] != r["label"]
        if dis and r["video_id"] not in REASONS:
            problems.append("%s disagrees with its collector label but has "
                            "no reason in compare_collectors.py" % r["video_id"])
        if not dis and r["video_id"] in REASONS:
            problems.append("%s now agrees with its collector label; drop its "
                            "stale reason" % r["video_id"])
    return problems


def main():
    rows = load()
    problems = check(rows)
    if "--check" in sys.argv or problems:
        for p in problems:
            print("FAIL ", p)
        sys.exit(1 if problems else 0)

    scoped = [r for r in rows if not r["out_of_scope"]]
    oos = [r for r in rows if r["out_of_scope"]]
    pairs = [(r["collector_label"], r["label"]) for r in scoped]
    agree = sum(a == b for a, b in pairs)
    kappa = cohen_kappa(pairs)

    L = []
    L.append("# Collector labels vs. the derived video label")
    L.append("")
    L.append("Generated by `scripts/compare_collectors.py` from "
             "`video_index.csv` (`collector_label`: the Box folder each video "
             "was filed under) and `videos.csv` (`video_level_label`, derived "
             "by the revised section 9 rules). Do not edit by hand.")
    L.append("")
    L.append("**%d** videos carry a collector label. **%d** of them are "
             "`out_of_scope` and excluded from every number below (section "
             "14), leaving **%d**." % (len(rows), len(oos), len(scoped)))
    L.append("")
    L.append("- Agreement: **%d / %d (%.0f%%)**" % (agree, len(scoped),
                                                   100.0 * agree / len(scoped)))
    L.append("- Cohen's kappa (collector folder vs. derived label): **%.2f**"
             % kappa)
    L.append("")
    L.append("The collectors judged whole videos by eye; the derived label "
             "comes from per-claim evidence. So kappa here measures how far "
             "an evidence-grounded rubric departs from a reader's impression, "
             "not inter-annotator agreement. The blind second labelling in "
             "`REVIEW.md` measures that.")
    L.append("")

    L.append("## Confusion matrix (rows: collector, columns: derived)")
    L.append("")
    labels = list(VIDEO_LABELS)
    L.append("| collector \\ derived | " + " | ".join(labels) + " | total |")
    L.append("|---|" + "---:|" * (len(labels) + 1))
    for a in labels:
        cells = [sum(1 for x, y in pairs if x == a and y == b) for b in labels]
        L.append("| %s | %s | %d |" % (a, " | ".join(str(c) for c in cells),
                                        sum(cells)))
    L.append("")

    L.append("## Per collector")
    L.append("")
    L.append("| collector | videos | agree |")
    L.append("|---|---:|---:|")
    for c in sorted({r["collector"] for r in scoped}):
        rs = [r for r in scoped if r["collector"] == c]
        L.append("| %s | %d | %d |" % (
            c, len(rs), sum(r["collector_label"] == r["label"] for r in rs)))
    L.append("")

    L.append("## Disagreements")
    L.append("")
    L.append("| video | collector label | derived label | sent to review | "
             "why |")
    L.append("|---|---|---|---|---|")
    for r in scoped:
        if r["collector_label"] != r["label"]:
            L.append("| %s | %s | %s | %s | %s |" % (
                r["video_id"], r["collector_label"], r["label"],
                "yes" if r["review"] else "no", REASONS[r["video_id"]]))
    L.append("")

    L.append("## Agreements")
    L.append("")
    L.append(", ".join("%s (%s)" % (r["video_id"], r["label"])
                       for r in scoped if r["collector_label"] == r["label"]))
    L.append("")

    L.append("## Out of scope (excluded)")
    L.append("")
    L.append("No health content, so no label is scored. The collector folder "
             "is shown for completeness.")
    L.append("")
    L.append("| video | collector label | topic |")
    L.append("|---|---|---|")
    for r in oos:
        L.append("| %s | %s | %s |" % (r["video_id"], r["collector_label"],
                                       r["topic"]))
    L.append("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("agreement %d/%d, kappa %.2f -> %s"
          % (agree, len(scoped), kappa, OUT.name))


if __name__ == "__main__":
    main()
