"""Compare each batch-2 source's own label with the derived video_level_label.

external_label (videos.csv, from video_index.csv) is the source's label kept
verbatim: the fact-checker's verdict for a fact-checked creator video or one
of @malditobulo's own, M4Health's Credibility column plus its category, or
MHMisinfo-Gold's label column. Videos tagged out_of_scope are listed but left
out of every number (section 14).

The verbatim labels are not one vocabulary, so the table is given twice:
verbatim against the derived label, and mapped to the label the source
implies. The mapping is the only interpretation added here:

  fact-checked creator  by the candidates.csv curator's own candidate_tags
                        for that row, not by the verdict wording (Lead
                        Stories' "Saves Lives" is its verdict on a video
                        claiming the opposite):
                          debunking      -> DEBUNKING
                          clearly_false  -> MISINFO
                          accurate alone -> NO_MISINFO
                          anything else (mixed) -> no implied label
  fact_checker_produced the fact-checker's own debunk -> DEBUNKING
  M4Health  FALSE       low credibility                -> MISINFO
  MHMisinfo-Gold  -1    mental-health misinformation   -> MISINFO

  python compare_external.py          # write external_agreement.md
  python compare_external.py --check  # fail if a disagreement has no reason
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
from compare_collectors import cohen_kappa  # noqa: E402

DATASET = Path(__file__).resolve().parents[1]
OUT = DATASET / "external_agreement.md"
SELECTION = DATASET / "sources" / "batch2_selection.csv"
SOURCES = ("fact_checked_creator", "fact_checker_produced", "M4Health",
           "MHMisinfo-Gold")


def implied(source, label, tags):
    tags = set(t for t in tags.split(";") if t)
    if not label:
        return ""
    if source == "fact_checked_creator":
        if "debunking" in tags:
            return "DEBUNKING"
        if "clearly_false" in tags:
            return "MISINFO"
        if tags == {"accurate"}:
            return "NO_MISINFO"
        return ""
    if source == "fact_checker_produced":
        return "DEBUNKING"
    if source == "M4Health" and label.startswith("FALSE"):
        return "MISINFO"
    if source == "MHMisinfo-Gold" and label == "-1":
        return "MISINFO"
    return ""


def reasons():
    from labels_batch2 import LABELS
    return {v["video_id"]: v["external_reason"] for v in LABELS
            if v.get("external_reason")}


def load():
    with open(DATASET / "videos.csv", encoding="utf-8") as f:
        videos = list(csv.DictReader(f))
    tags = {}
    if SELECTION.exists():
        with open(SELECTION, encoding="utf-8") as f:
            tags = {r["video_id"]: r["external_tags"]
                    for r in csv.DictReader(f) if r["video_id"]}
    rows = []
    for v in videos:
        if v.get("source") not in SOURCES:
            continue
        rows.append({
            "video_id": v["video_id"],
            "source": v["source"],
            "external_label": v["external_label"],
            "external_source": v["external_source"],
            "external_tags": tags.get(v["video_id"], ""),
            "implied": implied(v["source"], v["external_label"],
                               tags.get(v["video_id"], "")),
            "label": v["video_level_label"],
            "out_of_scope": "out_of_scope" in v["case_tags"].split(";"),
            "topic": v["topic"],
            "review": v["review_reasons"],
        })
    return rows


def check(rows):
    why = reasons()
    problems = []
    for r in rows:
        if r["out_of_scope"] or not r["implied"]:
            continue
        dis = r["implied"] != r["label"]
        if dis and r["video_id"] not in why:
            problems.append("%s: derived %s, but its source implies %s and "
                            "labels_b2 gives no external_reason"
                            % (r["video_id"], r["label"], r["implied"]))
        if not dis and r["video_id"] in why:
            problems.append("%s now agrees with its source; drop its stale "
                            "external_reason" % r["video_id"])
    return problems


def md(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def main():
    rows = load()
    problems = check(rows)
    if "--check" in sys.argv or problems:
        for p in problems:
            print("FAIL ", p)
        sys.exit(1 if problems else 0)
    why = reasons()
    scoped = [r for r in rows if not r["out_of_scope"]]
    oos = [r for r in rows if r["out_of_scope"]]
    mapped = [r for r in scoped if r["implied"]]
    pairs = [(r["implied"], r["label"]) for r in mapped]
    agree = sum(a == b for a, b in pairs)
    labels = list(VIDEO_LABELS)

    L = ["# Source labels vs. the derived video label (batch 2)", "",
         "Generated by `scripts/compare_external.py` from `videos.csv` "
         "(`external_label`, the source's own label verbatim; "
         "`video_level_label`, derived by the section 9 rules) and "
         "`sources/batch2_selection.csv` (`external_tags`). Do not edit by "
         "hand. The mapping from a source label to the video label it implies "
         "is in the script's docstring.", "",
         "**%d** batch-2 videos. **%d** are `out_of_scope` and excluded from "
         "every number (section 14), leaving **%d**; **%d** of those have a "
         "source label that implies a video label."
         % (len(rows), len(oos), len(scoped), len(mapped)), ""]
    if pairs:
        L += ["- Agreement with the implied label: **%d / %d (%.0f%%)**"
              % (agree, len(pairs), 100.0 * agree / len(pairs)),
              "- Cohen's kappa (implied vs. derived): **%.2f**"
              % cohen_kappa(pairs), ""]
    L += ["The sources judged whole videos, by a fact-checker's reading or a "
          "dataset's annotation scheme; the derived label comes from "
          "per-claim evidence under section 7, where an untested claim is "
          "INSUFFICIENT_EVIDENCE rather than false. So disagreement here is "
          "mostly a measure of how often a source's 'false' rests on claims "
          "the literature has not tested, not of labelling error.", "",
          "**Not a blind comparison.** The batch-2 labellers had seen every "
          "source label before writing claims (PLAN.md, batch 2). If that "
          "biased anything it would push towards agreement, so the true "
          "agreement is unlikely to be higher than this. The batch-2 blind "
          "subset in REVIEW.md is where an independent number has to come "
          "from.", ""]

    L += ["## By source", "",
          "| source | videos in scope | with implied label | agree | "
          + " | ".join(labels) + " |",
          "|---|---:|---:|---:|" + "---:|" * len(labels)]
    for s in SOURCES:
        rs = [r for r in scoped if r["source"] == s]
        ms = [r for r in rs if r["implied"]]
        L.append("| %s | %d | %d | %d | %s |" % (
            s, len(rs), len(ms), sum(r["implied"] == r["label"] for r in ms),
            " | ".join(str(sum(r["label"] == lab for r in rs))
                       for lab in labels)))
    L.append("")

    L += ["## Confusion matrix (rows: implied by source, columns: derived)",
          "", "| implied \\ derived | " + " | ".join(labels) + " | total |",
          "|---|" + "---:|" * (len(labels) + 1)]
    for a in labels:
        cells = [sum(1 for x, y in pairs if x == a and y == b) for b in labels]
        if sum(cells):
            L.append("| %s | %s | %d |" % (
                a, " | ".join(str(c) for c in cells), sum(cells)))
    L.append("")

    L += ["## Verbatim source label vs. derived label", "",
          "| source | external_label | n | " + " | ".join(labels) + " |",
          "|---|---|---:|" + "---:|" * len(labels)]
    groups = Counter((r["source"], r["external_label"]) for r in scoped)
    for (s, lab), n in sorted(groups.items()):
        rs = [r for r in scoped
              if r["source"] == s and r["external_label"] == lab]
        L.append("| %s | %s | %d | %s |" % (
            s, md(lab) or "*(no verdict found)*", n,
            " | ".join(str(sum(r["label"] == x for r in rs))
                       for x in labels)))
    L.append("")

    L += ["## Every video", "",
          "| video | source | external_label | implied | derived | sent to "
          "review | why they differ |",
          "|---|---|---|---|---|---|---|"]
    for r in scoped:
        dis = r["implied"] and r["implied"] != r["label"]
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["video_id"], r["source"], md(r["external_label"]),
            r["implied"] or "—", r["label"], "yes" if r["review"] else "no",
            md(why.get(r["video_id"], "")) if dis else ""))
    L.append("")

    L += ["## Out of scope (excluded)", "",
          "No health content, so no label is scored.", "",
          "| video | source | external_label | topic |", "|---|---|---|---|"]
    for r in oos:
        L.append("| %s | %s | %s | %s |" % (
            r["video_id"], r["source"], md(r["external_label"]), md(r["topic"])))
    L.append("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("implied-label agreement %d/%d -> %s"
          % (agree, len(pairs), OUT.name))


if __name__ == "__main__":
    main()
