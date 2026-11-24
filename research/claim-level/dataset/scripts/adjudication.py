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
        entry, tag = None, TAG
        if key in SWEEP_CLAIMS:
            entry, tag = SWEEP_CLAIMS[key], SWEEP_TAG
        elif key in CLAIMS:
            entry = CLAIMS[key]
        if entry:
            changes, why = entry
            changed = [k for k, v in changes.items() if r.get(k, "") != v]
            for k, v in changes.items():
                if k == "notes":
                    r["notes"] = (v + r["notes"]).strip()
                else:
                    r[k] = v
            r["reviewer"] = REVIEWER
            r["review_status"] = "corrected" if changed else "verified"
            r["reviewer_notes"] = "%s (%s)" % (why, tag)
        elif key in agreed:
            r["reviewer_notes"] = AGREED_NOTE
        out.append(r)
    for news, tag, ann in ((NEW_CLAIMS, TAG, "blind_model_pass_v1"),
                           (SWEEP_NEW, SWEEP_TAG, "labelling_pipeline_v1")):
        for n in news:
            row = {k: v for k, v in n.items() if k != "why"}
            row.update(annotator=ann, review_status="corrected", reviewer=REVIEWER,
                       reviewer_notes="%s New row. (%s)" % (n["why"], tag))
            out.append(row)
    return out, agreed


def apply_video(row, first_label_basis):
    """row: the re-derived video row. first_label_basis: (label, basis) the
    first pass's claims gave before adjudication."""
    vid = row["video_id"]
    with open(BLIND / "model_relabel_videos.csv", encoding="utf-8") as f:
        mv = {r["video_id"]: r for r in csv.DictReader(f)}
    if vid in VIDEOS or vid in SWEEP_VIDEOS:
        now = (row["video_level_label"], row["misinfo_basis"])
        row["reviewer"] = REVIEWER
        row["review_status"] = "corrected" if now != first_label_basis else "verified"
        extra = "" if now == first_label_basis else " Label %s%s -> %s%s." % (
            first_label_basis[0], "/" + first_label_basis[1] if first_label_basis[1] else "",
            now[0], "/" + now[1] if now[1] else "")
        parts = []
        if vid in VIDEOS:
            parts.append("%s (%s)" % (VIDEOS[vid], TAG))
        if vid in SWEEP_VIDEOS:
            parts.append("%s (%s)" % (SWEEP_VIDEOS[vid], SWEEP_TAG))
        row["reviewer_notes"] = " ".join(parts) + extra
        if extra:
            row["notes"] = ("[Adjudicated 2026-11-24:%s The text below was "
                            "written for the first-pass label.] %s" % (extra, row["notes"]))
    elif vid in mv and (mv[vid]["video_level_label"], mv[vid]["misinfo_basis"]) == first_label_basis:
        row["reviewer_notes"] = AGREED_NOTE
    return row


# ---------------------------------------------------------------------------
# Rule sweep (blind/rule_sweep.md), approved by the lead on 2026-11-24.
SWEEP_TAG = "rule sweep, lead-approved 2026-11-24"

SWEEP_CLAIMS = {
    ("v22", "c2"): ({"claim_verdict": "UNSUPPORTED", "evidence_supporting": "",
                     "notes": "UNSUPPORTED (prevention): Nothing retrieved tests egg intake against macular degeneration or cataract incidence; the lutein/zeaxanthin review (PMID:35215476) and egg-MPOD trials concern a nutrient or a pigment marker, not the outcome. "},
                    "A4: evidence on a nutrient (lutein) and a marker (macular pigment) does not bear on 'eggs prevent macular degeneration and cataracts'; INSUFFICIENT_EVIDENCE -> UNSUPPORTED (prevention); PMID:35215476 removed."),
    ("v35", "c2"): ({"claim_verdict": "UNSUPPORTED", "evidence_supporting": "",
                     "notes": "UNSUPPORTED (treatment_efficacy): No study tests miso removing radiation from the human body or bloodstream. "},
                    "A3 + A4. Judgement call: the only citation (PMID:11833659) is a mouse study of radioprotection, a different outcome from 'removing radiation from the body', so under A4 it does not bear on the claim. Removed; INSUFFICIENT_EVIDENCE -> UNSUPPORTED (treatment_efficacy)."),
    ("v139", "c5"): ({"claim_verdict": "UNSUPPORTED", "evidence_contradicting": "",
                      "notes": "UNSUPPORTED (treatment_efficacy): No study tests a fungal 'cleanse' against migraine. "},
                     "A3 + A4. Judgement call: PMID:2247104 (nystatin vs placebo for the 'candidiasis hypersensitivity syndrome') did not measure migraine, so it neither tests nor contradicts the claim. Removed; not CONTRADICTED. INSUFFICIENT_EVIDENCE -> UNSUPPORTED (treatment_efficacy)."),
    ("v139", "c6"): ({"claim_verdict": "UNSUPPORTED", "evidence_contradicting": "",
                      "notes": "UNSUPPORTED (treatment_efficacy): No study tests a fungal 'cleanse' against skin itching. "},
                     "A3 + A4. Judgement call as v139 c5: PMID:2247104 did not measure skin itching. Removed; INSUFFICIENT_EVIDENCE -> UNSUPPORTED (treatment_efficacy)."),
    ("v161", "c6"): ({"claim_verdict": "UNSUPPORTED",
                      "notes": "UNSUPPORTED (treatment_efficacy): No study of lemon for liver detoxification was found (search 'lemon liver detoxification' returned a herbal detox-tea liver-injury case and citrus-pectin reviews). "},
                     "A3: 'detoxing the liver' is a specific therapeutic effect. Judgement call: 'the best fruit' is read as a comparative wrapper around that efficacy claim, not as vague wellness. INSUFFICIENT_EVIDENCE -> UNSUPPORTED (treatment_efficacy)."),
}

def _new(vid, cid, text, start, end, verdict, sup="", con="", notes="", why=""):
    return dict(video_id=vid, claim_id=cid, claim_text=text, claim_source="screen",
                claim_kind="research_question", start_seconds=start, end_seconds=end,
                speaker_stance="ENDORSES", claim_verdict=verdict, evidence_supporting=sup,
                evidence_contradicting=con, confidence="medium", notes=notes, why=why)

_A2 = "A2: screen-only infographic claim stated as fact, ENDORSES."
SWEEP_NEW = [
    _new("v36", "c9", "Irish Sea Moss: Boost Mens Sexual Wellness", "34.0", "40.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:34220241", notes="One rat study of Chondrus crispus reports improved testicular function and sperm motility; animal data on the same seaweed, so too weak rather than absent.", why=_A2),
    _new("v36", "c10", "Irish Sea Moss: Building Muscles Mass", "34.0", "40.0", "UNSUPPORTED",
         notes="UNSUPPORTED (treatment_efficacy): No study of sea moss and muscle mass was found (search 'sea moss seaweed muscle mass': 0 hits).", why=_A2),
    _new("v36", "c11", "Irish Sea Moss: Reduces Diseases Risk", "34.0", "40.0", "INSUFFICIENT_EVIDENCE",
         notes="No disease named; vague wellness, so INSUFFICIENT_EVIDENCE rather than UNSUPPORTED.", why=_A2),
    _new("v36", "c12", "Burdock Root: Fights Infections", "28.0", "32.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:16521107", notes="In vitro antibacterial activity of an Arctium lappa extract (endodontic bacteria); no human infection trial.", why=_A2),
    _new("v36", "c13", "Burdock Root: Soothes Eczema", "28.0", "32.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:41111517", notes="Review of mostly experimental evidence on Arctium lappa in immune-mediated skin disease; no adequate eczema trial.", why=_A2),
    _new("v36", "c14", "Burdock Root: Assists with PMS Symptoms", "28.0", "32.0", "UNSUPPORTED",
         notes="UNSUPPORTED (treatment_efficacy): No study of burdock for premenstrual symptoms was found (search 'burdock premenstrual syndrome': 0 hits).", why=_A2),
    _new("v36", "c15", "Moringa: Promotes Liver Protection", "50.0", "56.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:37765399", notes="Cell-culture (HepG2) review of hepatoprotection; no human data.", why=_A2),
    _new("v36", "c16", "Moringa: Treats Urinary Disorders", "50.0", "56.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:27437504", notes="One small open Ayurvedic trial of moringa stem bark in UTI (66.7% cured vs 46.7% on standard drugs); too weak, and 'urinary disorders' is broader than UTI.", why=_A2),
    _new("v36", "c17", "Moringa: Anti-Ulcer", "50.0", "56.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:23972244", notes="Rat gastric-ulcer models only.", why=_A2),
    _new("v81", "c2", "[Legs up the wall:] Improved sleep", "38.0", "40.0", "INSUFFICIENT_EVIDENCE",
         notes="Nothing retrieved tests the pose against sleep (search 'legs up the wall sleep' returned case reports only). Judgement call: 'improved sleep' read as vague wellness, so INSUFFICIENT_EVIDENCE rather than UNSUPPORTED.", why=_A2),
    _new("v81", "c3", "[Legs up the wall:] Reduce swelling", "38.0", "40.0", "INSUFFICIENT_EVIDENCE",
         sup="PMID:2794965", notes="Legs up the wall is leg elevation. One small study (31 women) found leg elevation reduces lower-leg oedema after prolonged standing: the same intervention, so the claim is not UNSUPPORTED, but a single small study is too weak to call it SUPPORTED. The sweep had predicted UNSUPPORTED; retrieval found this study.", why=_A2),
    _new("v81", "c4", "[Legs up the wall:] Support lymph flow", "38.0", "40.0", "INSUFFICIENT_EVIDENCE",
         notes="Mechanism claim; nothing retrieved tests leg elevation against lymph flow.", why=_A2),
]

SWEEP_VIDEOS = {
    "v22": "A4 (rule sweep): c2 eggs/AMD -> UNSUPPORTED.",
    "v35": "A3/A4 (rule sweep): c2 miso/radiation -> UNSUPPORTED.",
    "v36": "A2 (rule sweep): nine more infographic claims added (c9-c17).",
    "v81": "A2 (rule sweep): three on-screen claims added (c2-c4); none is UNSUPPORTED, so the label does not change.",
    "v139": "A3/A4 (rule sweep): c5 and c6 -> UNSUPPORTED.",
    "v161": "A3 (rule sweep): c6 lemon/liver detox -> UNSUPPORTED.",
}
