"""Model-assisted adjudication of the blind sample (2026-11-24).

The blind Claude re-label (blind/model_relabel_*.csv, blind_model_pass_v1) was
compared with the first pass (blind/model_relabel_comparison.md); the project
lead adjudicated every disagreement. build_csvs.py applies this file on top of
the labels in labels*.py, so a rebuild keeps the decisions.

Rules (README.md / REVIEW.md "Guideline clarifications"):
  A1 literal reading      A2 on-screen claims count
  A3 "removes/detoxes X" is efficacy      A4 directness for product claims
  B  individual calls     C  follow the comparison report's lean

Model-model agreement is not human inter-annotator agreement. A row is never
marked verified on model agreement alone: rows where both passes agreed stay
pending with the note AGREED_NOTE.
"""
import csv
from pathlib import Path

REVIEWER = "PranavCR01"
TAG = "model-assisted adjudication"
AGREED_NOTE = "agreed by blind model pass"
BLIND = Path(__file__).resolve().parents[1] / "blind"

# (video, claim) -> (field changes, reason). Empty changes = confirmed (verified).
CLAIMS = {
    ("v11", "c2"): ({}, "C: first pass kept (model SUPPORTED, first MIXED; first pass had the 2025 meta-analysis)."),
    ("v11", "c3"): ({"claim_verdict": "MIXED", "evidence_contradicting": "PMID:23386268"},
                    "B: SUPPORTED -> MIXED; added PMID:23386268 (recovered Sydney Diet Heart RCT, more deaths with linoleic acid) as contradicting."),
    ("v21", "c2"): ({"claim_text": "Almonds are rich in unsaturated fats that promote good cholesterol",
                     "claim_verdict": "CONTRADICTED", "evidence_contradicting": "PMID:27752301",
                     "confidence": "medium"},
                    "A1: split from 'protect your heart' (now c7); 'good cholesterol' read literally as HDL; RCT meta-analysis PMID:27752301 finds HDL-C not affected, so INSUFFICIENT_EVIDENCE -> CONTRADICTED (replaces PMID:38967674, which moves to c7)."),
    ("v21", "c3"): ({}, "C: first pass kept (INSUFFICIENT_EVIDENCE; appetite evidence low certainty)."),
    ("v22", "c1"): ({"claim_verdict": "SUPPORTED", "evidence_supporting": "PMID:39703894;PMID:33133540"},
                    "C: model taken; INSUFFICIENT_EVIDENCE -> SUPPORTED with DIAAS papers retrieved by the blind pass ('best' is a superlative)."),
    ("v22", "c6"): ({}, "C: first pass kept (one small crossover trial is too weak)."),
    ("v23", "c1"): ({"claim_text": "[gluten] can cause everything from osteoporosis to autism",
                     "claim_verdict": "INSUFFICIENT_EVIDENCE", "evidence_contradicting": ""},
                    "C: referent [vaccines] -> [gluten] (on-screen caption at 2 s reads 'gluten can cause everything from osteoporosis to autism'); CONTRADICTED -> INSUFFICIENT_EVIDENCE; vaccine-autism citations removed as they do not test a gluten claim."),
    ("v23", "c3"): ({}, "C: first pass kept (CONTRADICTED)."),
    ("v24", "c1"): ({}, "C: reviewer call, first pass kept (proposition 'Cheerios carry harmful glyphosate residues')."),
    ("v68", "c1"): ({}, "C: first pass kept; stance difference was a polarity artefact."),
    ("v69", "c4"): ({}, "C: first pass kept (INSUFFICIENT_EVIDENCE for 'about half')."),
    ("v71", "c1"): ({}, "C: first pass kept (MIXED)."),
    ("v71", "c6"): ({"claim_verdict": "INSUFFICIENT_EVIDENCE", "evidence_contradicting": ""},
                    "C: model taken; MIXED -> INSUFFICIENT_EVIDENCE; PMID:30374900 (topical photoprotection) removed as it does not contradict the NO claim."),
    ("v109", "c5"): ({}, "C: first pass kept (SUPPORTED; the blind pass mis-cited PMID:40437949)."),
    ("v109", "c6"): ({"claim_verdict": "CONTRADICTED"},
                     "B: INSUFFICIENT_EVIDENCE -> CONTRADICTED; both cited meta-analyses find no increase in pancreatitis."),
    ("v109", "c7"): ({}, "C: first pass kept (CONTRADICTED, target-trial emulation)."),
    ("v109", "c11"): ({}, "C: reviewer call, first pass kept."),
    ("v113", "c2"): ({}, "A4/C: first pass kept (UNSUPPORTED; deep-sea-water evidence is a different intervention)."),
    ("v113", "c3"): ({}, "A4/C: first pass kept (UNSUPPORTED)."),
    ("v113", "c4"): ({}, "A4/C: first pass kept (UNSUPPORTED; Dead Sea bathing is a different route)."),
    ("v120", "c1"): ({"claim_verdict": "UNSUPPORTED",
                      "notes": "UNSUPPORTED (treatment_efficacy): Claims drinking seawater removes heavy metals from the body; no study of it was found by either pass. "},
                     "A3: removing heavy metals from the body is a specific therapeutic (efficacy) effect; INSUFFICIENT_EVIDENCE -> UNSUPPORTED."),
    ("v135", "c2"): ({}, "C: first pass kept (FDA limit unchecked)."),
    ("v135", "c4"): ({}, "C: first pass kept (absorption varies by vehicle)."),
    ("v135", "c6"): ({}, "C: first pass kept (NHANES study found by first pass)."),
    ("v149", "c2"): ({}, "A4: first pass kept (UNSUPPORTED; ingredient evidence does not bear on the untested product)."),
    ("v176", "c2"): ({}, "C: first pass kept (NOT_VERIFIABLE)."),
    ("v177", "c1"): ({}, "C: first pass kept (split from 'multiple personality')."),
    ("v177", "c2"): ({}, "C: first pass kept (CONTRADICTED; the blind pass merged it into c1)."),
}

NEW_CLAIMS = [
    dict(video_id="v21", claim_id="c7", claim_text="[Almonds] protect your heart", claim_source="both",
         claim_kind="research_question", start_seconds="12.8", end_seconds="18.1", speaker_stance="ENDORSES",
         claim_verdict="INSUFFICIENT_EVIDENCE", evidence_supporting="", evidence_contradicting="PMID:38967674",
         confidence="medium",
         notes="Split from c2. Keeps the first pass's verdict and citation for the heart half: no cardiovascular-outcome trial of almonds was retrieved, and the systematic review of nuts in secondary prevention found no change in lipid or inflammatory profiles.",
         why="A1: split from c2 (one assertion per row); keeps the first pass's verdict for the heart half."),
    dict(video_id="v36", claim_id="c6", claim_text="Irish Sea Moss: Cures Thyroid Issues", claim_source="screen",
         claim_kind="research_question", start_seconds="34.0", end_seconds="40.0", speaker_stance="ENDORSES",
         claim_verdict="UNSUPPORTED", evidence_supporting="", evidence_contradicting="", confidence="medium",
         notes="UNSUPPORTED (treatment_efficacy): no trial of sea moss for thyroid disease was found; retrieved sources concern iodine excess causing thyroid dysfunction, not treatment. On-screen infographic, stated as fact.",
         why="A2: screen-only infographic claim, ENDORSES; extracted by the blind pass."),
    dict(video_id="v36", claim_id="c7", claim_text="Burdock Root: Rids Kidney & Gallbladder Stones", claim_source="screen",
         claim_kind="research_question", start_seconds="28.0", end_seconds="32.0", speaker_stance="ENDORSES",
         claim_verdict="UNSUPPORTED", evidence_supporting="", evidence_contradicting="", confidence="medium",
         notes="UNSUPPORTED (treatment_efficacy): no study of burdock for kidney or gallbladder stones was found. On-screen infographic, stated as fact.",
         why="A2: screen-only infographic claim, ENDORSES; extracted by the blind pass."),
    dict(video_id="v36", claim_id="c8", claim_text="Burdock Root: Lowers Blood-Sugar levels", claim_source="screen",
         claim_kind="research_question", start_seconds="28.0", end_seconds="32.0", speaker_stance="ENDORSES",
         claim_verdict="INSUFFICIENT_EVIDENCE", evidence_supporting="PMID:28348972", evidence_contradicting="",
         confidence="medium", notes="Rodent studies only (too weak). On-screen infographic, stated as fact.",
         why="A2: screen-only infographic claim, ENDORSES; extracted by the blind pass."),
]

# video -> reason; these video rows were decided (label confirmed or changed).
VIDEOS = {
    "v11": "B: v11 c3 SUPPORTED -> MIXED leaves no judged claim, so the label is re-derived.",
    "v21": "A1: v21 c2 split; HDL row CONTRADICTED; label re-derived.",
    "v22": "C: v22 c1 -> SUPPORTED; label re-derived.",
    "v23": "C: v23 c1 referent [gluten], INSUFFICIENT_EVIDENCE; label re-derived.",
    "v36": "A2: screen-only infographic claims added (c6-c8); label re-derived.",
    "v47": "C: first pass kept (out_of_scope; the lobster/telomere claim is not a health assertion).",
    "v69": "C: first pass kept (the 'cancer proof' title is not judged as CONTRADICTED).",
    "v71": "C: first pass kept on c1 (MIXED); c6 -> INSUFFICIENT_EVIDENCE; label re-derived.",
    "v109": "B/C: c6 -> CONTRADICTED, c5/c7 kept; label re-derived.",
    "v113": "A4: first pass kept (UNSUPPORTED claims).",
    "v120": "A3: c1 -> UNSUPPORTED; label re-derived.",
    "v149": "A4: first pass kept (c2 UNSUPPORTED).",
}


def agreed_sets():
    """(video, claim) pairs and videos where the blind pass agreed with the
    first pass, computed from the committed blind files with the same matcher
    as compare_blind.py, against the first-pass labels (pre-adjudication)."""
    import compare_blind as cb
    with open(BLIND / "model_relabel_videos.csv", encoding="utf-8") as f:
        mv = {r["video_id"]: r for r in csv.DictReader(f)}
    return cb, mv


def apply(claim_rows, video_rows_fn=None):
    """Called by build_csvs.py with the first-pass claim rows (all videos).
    Returns the adjusted claim rows. Agreement is computed on the first-pass
    rows before any change."""
    cb, mv = agreed_sets()
    vids = set(mv)
    first = [r for r in claim_rows if r["video_id"] in vids]
    with open(BLIND / "model_relabel_claims.csv", encoding="utf-8") as f:
        model = [r for r in csv.DictReader(f)]
    pairs, _uf, _um = cb.match(first, model)
    agreed = {(f_["video_id"], f_["claim_id"]) for f_, m, _s, _h in pairs
              if f_["speaker_stance"] == m["speaker_stance"]
              and f_["claim_verdict"] == m["claim_verdict"]}
    out = []
    for r in claim_rows:
        key = (r["video_id"], r["claim_id"])
        if key in CLAIMS:
            changes, why = CLAIMS[key]
            changed = [k for k, v in changes.items() if r.get(k, "") != v]
            for k, v in changes.items():
                if k == "notes":
                    r["notes"] = (v + r["notes"]).strip()
                else:
                    r[k] = v
            r["reviewer"] = REVIEWER
            r["review_status"] = "corrected" if changed else "verified"
            r["reviewer_notes"] = "%s (%s)" % (why, TAG)
        elif key in agreed:
            r["reviewer_notes"] = AGREED_NOTE
        out.append(r)
    for n in NEW_CLAIMS:
        row = {k: v for k, v in n.items() if k != "why"}
        row.update(annotator="blind_model_pass_v1", review_status="corrected",
                   reviewer=REVIEWER, reviewer_notes="%s New row. (%s)" % (n["why"], TAG))
        out.append(row)
    return out, agreed


def apply_video(row, first_label_basis):
    """row: the re-derived video row. first_label_basis: (label, basis) the
    first pass's claims gave before adjudication."""
    vid = row["video_id"]
    with open(BLIND / "model_relabel_videos.csv", encoding="utf-8") as f:
        mv = {r["video_id"]: r for r in csv.DictReader(f)}
    if vid in VIDEOS:
        now = (row["video_level_label"], row["misinfo_basis"])
        row["reviewer"] = REVIEWER
        row["review_status"] = "corrected" if now != first_label_basis else "verified"
        extra = "" if now == first_label_basis else " Label %s%s -> %s%s." % (
            first_label_basis[0], "/" + first_label_basis[1] if first_label_basis[1] else "",
            now[0], "/" + now[1] if now[1] else "")
        row["reviewer_notes"] = "%s%s (%s)" % (VIDEOS[vid], extra, TAG)
        if extra:
            row["notes"] = ("[Adjudicated 2026-11-24:%s The text below was "
                            "written for the first-pass label.] %s" % (extra, row["notes"]))
    elif vid in mv and (mv[vid]["video_level_label"], mv[vid]["misinfo_basis"]) == first_label_basis:
        row["reviewer_notes"] = AGREED_NOTE
    return row
