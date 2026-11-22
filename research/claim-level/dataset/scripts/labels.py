"""The golden label set, as data.

build_csvs.py turns this into videos.csv and claims.csv. video_level_label is
NOT stored here -- it is derived by the section 9 judge rules, so a label can
never contradict the claims under it.

Per video:
  video_id    v01..v82, from video_index.csv
  topic       health topic, or "none (non-health)" for off-topic videos
  text_type   high_text | low_text  (does on-screen text carry content?)
  case_tags   from the section 14 hard-case table; build_csvs.py adds
              mixed / no_claims / multi_claim / single_claim automatically
  confidence  low | medium | high -- how sure the annotator is overall
  notes       anything a reader would otherwise have to re-watch to learn
  claims      list, in the order they appear

Per claim:
  text        verbatim, one assertion, qualifiers and negation kept (section 4)
  source      speech | screen | both
  start, end  seconds, from the transcript segments
  stance      ENDORSES | REFUTES | QUOTES | NEUTRAL | UNCLEAR (section 5)
  verdict     SUPPORTED | CONTRADICTED | MIXED | INSUFFICIENT_EVIDENCE |
              NOT_VERIFIABLE (section 7)
  supporting, contradicting
              lists of "PMID:nnnnnnnn" or URLs that were actually retrieved
              through evidence.py. Absence of evidence is INSUFFICIENT_EVIDENCE,
              never CONTRADICTED.

Two labelling rules applied consistently, both from section 7:

  1. Only animal, in-vitro or mechanistic-review evidence exists for a claim
     stated about people -> INSUFFICIENT_EVIDENCE ("what exists is too weak"),
     with the study still cited and the limitation in notes. It is not
     CONTRADICTED, and it is not SUPPORTED either.
  2. A search that returns nothing relevant -> INSUFFICIENT_EVIDENCE. The empty
     search stays in evidence_cache/ as the record that it was actually run.
"""

ANNOTATOR = "pranav"

LABELS = [
    {
        "video_id": "v01",
        "topic": "none (non-health)",
        "text_type": "high_text",
        "case_tags": [],
        "confidence": "high",
        "notes": "Off-topic for this dataset: a police/retail identity dispute "
                 "with no health content. Burned-in subtitles carry the whole "
                 "dialogue, so it is high_text, but no health assertion is "
                 "made. Collectors filed it under 'No info', which agrees.",
        "claims": [],
    },
    {
        "video_id": "v02",
        "topic": "none (non-health)",
        "text_type": "high_text",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "A genuine debunking video (@dustindeanmentalist explains that "
                 "paranormal 'spirit flashlight' responses are thermal "
                 "expansion of the contacts), but the debunked claim is "
                 "paranormal, not health, so there is no checkable health "
                 "assertion to label. Tagged 'debunking' because the stance "
                 "structure is exactly what the stance step must handle. "
                 "Collectors filed it under DEBUNKING.",
        "claims": [],
    },
    {
        "video_id": "v03",
        "topic": "nutrition / food additives",
        "text_type": "high_text",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "@gabbituft (coachgabby.com) listing five food additives to "
                 "avoid. The densest claim video in the bundle: 17 separate "
                 "health assertions, several of them genuinely unsettled, and "
                 "the speaker cites study years that do not match the "
                 "literature (see per-claim notes). Collectors filed it under "
                 "MISINFO; the section 9 rules give NO_MISINFO here, because "
                 "no individual claim is contradicted by the evidence -- the "
                 "weak ones are insufficiently evidenced rather than false. "
                 "A good reviewer disagreement candidate. "
                 "This is the strongest OCR result in the bundle: the creator "
                 "displays the PubMed or PMC page for almost every claim, and "
                 "EasyOCR recovered the PMIDs and titles well enough to "
                 "retrieve the exact papers cited. Four verdicts were decided "
                 "or corrected by what the screen showed rather than what was "
                 "said, including the cancer claim, whose own on-screen source "
                 "says the human effect remains unresolved. Every claim is "
                 "therefore claim_source=both, and this video is direct "
                 "evidence for the modality track that OCR earns its cost on "
                 "citation-heavy content.",
        "claims": [
            {
                "text": "It's fine when you eat it [fructose] with fruit "
                        "because of the fiber that's associated with it",
                "source": "both", "start": 10.4, "end": 13.9,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:37019448"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "BMJ umbrella review attributes the harms to free "
                         "and added sugars and sugar-sweetened beverages, not "
                         "to whole fruit.",
            },
            {
                "text": "It drives dopamine receptors down and is highly "
                        "addictive",
                "source": "both", "start": 21.8, "end": 24.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:41794143", "PMID:17668074"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Only a narrative review and a rat reward study were "
                         "retrieved. Nothing measures dopamine receptor "
                         "downregulation or addiction in people, so this is "
                         "insufficient evidence rather than support.",
            },
            {
                "text": "It does not satiate you the same way that normal "
                        "table sugar does, keeps you hungry compared to "
                        "regular sugar",
                "source": "both", "start": 24.7, "end": 31.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:33300990"],
                "contradicting": [],
                "confidence": "low",
                "notes": "The closest retrieved trial compares sucrose with "
                         "glucose, not crystalline fructose with table sugar, "
                         "so it does not test this comparison.",
            },
            {
                "text": "[Fructose] produces more body fat",
                "source": "both", "start": 31.3, "end": 34.7,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:37019448"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Split from a compound sentence that also claimed "
                         "physical inactivity. Umbrella review finds increased "
                         "body weight and ectopic fat for sugar-sweetened "
                         "beverages.",
            },
            {
                "text": "[Fructose] produces ... physical inactivity. In other "
                        "words, it makes you more sedentary",
                "source": "both", "start": 31.3, "end": 36.6,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:25892667"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Other half of the split compound claim. The video "
                         "displays its source on screen and OCR recovered it: "
                         "a 2015 Scientific Reports study in rodents, fructose "
                         "against an isocaloric glucose diet. It does report "
                         "decreased physical activity, but in animals, so "
                         "directness fails for a claim stated about people.",
            },
            {
                "text": "[Fructose] inhibits three enzymes critical for "
                        "mitochondrial function, AMP kinase, ACADL, and CPT1",
                "source": "both", "start": 36.6, "end": 40.4,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": [],
                "confidence": "medium",
                "notes": "A targeted search for fructose with AMPK/CPT1 and "
                         "mitochondrial fatty-acid oxidation returned nothing "
                         "that tests this; the empty search is in "
                         "evidence_cache/.",
            },
            {
                "text": "It's also been shown to contribute to non-alcoholic "
                        "fatty liver disease",
                "source": "both", "start": 43.8, "end": 47.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:29408694", "PMID:35995049",
                               "PMID:32214246"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Well supported, including a mechanistic Nature paper "
                         "and two reviews in hepatology/nutrition.",
            },
            {
                "text": "When fructose is absorbed without fiber, it causes "
                        "the tight junctions in the epithelial cells ... to "
                        "start to separate and there is some permeability",
                "source": "both", "start": 47.2, "end": 61.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:33171587"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Only a mechanistic overview of dietary carbohydrates "
                         "in leaky-gut pathogenesis was retrieved. No human "
                         "study tests fructose-without-fibre against "
                         "intestinal permeability.",
            },
            {
                "text": "It [high fructose corn syrup] contributes to cancer",
                "source": "both", "start": 76.4, "end": 78.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:25965509", "PMID:37019448"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Downgraded from SUPPORTED after reading the source "
                         "the video puts on screen. OCR recovered it as the "
                         "2015 review The role of fructose in metabolism and "
                         "cancer, and the displayed page states that how "
                         "dietary fructose impacts human cancer progression "
                         "and the response to immunotherapy remains "
                         "unresolved; the tumour data shown is in mice. The "
                         "umbrella review's cancer associations are for "
                         "dietary sugar broadly, not HFCS. Nothing retrieved "
                         "tests this claim directly in people.",
            },
            {
                "text": "It can contribute to metabolic disorders ... even "
                        "without obesity being present",
                "source": "both", "start": 78.1, "end": 84.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:31935149", "PMID:37019448"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Fructose-driven hepatic insulin resistance is "
                         "documented independently of obesity.",
            },
            {
                "text": "It's been shown to contribute to diabetes",
                "source": "both", "start": 84.5, "end": 86.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:40122386", "PMID:37019448"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The 2025 dose-response meta-analysis finds the "
                         "incident-T2D association for sugar consumed as "
                         "beverages, and explicitly does not support it for "
                         "total sugar or sucrose regardless of form. HFCS is "
                         "predominantly consumed in beverages, so the claim "
                         "holds in the form that matters, with that "
                         "qualification.",
            },
            {
                "text": "it puts you at greater risk for heart disease",
                "source": "both", "start": 86.5, "end": 88.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:37019448"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Umbrella review detects harmful associations with "
                         "ten cardiovascular outcomes.",
            },
            {
                "text": "A 2023 study showed that red 40 causes DNA damage",
                "source": "both", "start": 98.0, "end": 101.6,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:37719200", "PMID:26364875"],
                "contradicting": ["PMID:28458012"],
                "confidence": "medium",
                "notes": "Genuine conflict: a 2015 in vivo genotoxicity study "
                         "of Allura Red AC reports genotoxicity, and a 2017 "
                         "OECD-guideline study run in response to EFSA "
                         "reports none. The 2017 study is industry-authored "
                         "(IACM / Coca-Cola / Colorcon), which a reviewer "
                         "should weigh. The speaker's 2023 study is real and "
                         "OCR recovered it from the screen: Toxicology Reports "
                         "2023, PMID 37719200 -- but its own title ends in "
                         "mice, so the species limitation applies to the "
                         "supporting side too.",
            },
            {
                "text": "[red 40 causes] colonic inflammation and affects the "
                        "gut microbiome",
                "source": "both", "start": 101.6, "end": 104.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:37719200", "PMID:36539404"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Both retrieved studies are in mice, including the "
                         "one the video displays, whose title ends in mice. "
                         "The Nature Communications study showing Allura Red "
                         "AC promotes colitis susceptibility via intestinal "
                         "serotonin is in mice. Directness fails for a claim "
                         "stated about people.",
            },
            {
                "text": "A 2022 study showed that synthetic food dyes are "
                        "linked to ADHD in children",
                "source": "both", "start": 104.8, "end": 108.8,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35484553", "PMID:17825405",
                               "PMID:15155391", "PMID:24217026"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The best-evidenced claim in the video. OCR recovered "
                         "the on-screen citation and it is a 2022 systematic "
                         "review of the human and animal evidence, so the "
                         "speaker's date is right here. Three randomised "
                         "placebo-controlled challenge trials back it "
                         "independently. One qualification for the reviewer: "
                         "those trials measure hyperactive behaviour in the "
                         "general child population, not a diagnosis of ADHD.",
            },
            {
                "text": "a 2015 study showed that it [synthetic food dyes] is "
                        "linked directly to cancer",
                "source": "both", "start": 108.8, "end": 112.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:25750299", "PMID:38928929"],
                "contradicting": [],
                "confidence": "high",
                "notes": "OCR recovered the speaker's 2015 study from the "
                         "screen: Anticancer Research 2015, DNA repair in "
                         "human lymphocytes exposed to tartrazine yellow. It "
                         "is an in vitro assay, it measures DNA repair rather "
                         "than cancer, and it concerns tartrazine (yellow 5) "
                         "rather than the red 40 the segment is built around, "
                         "so it does not support linked directly to cancer. "
                         "Per section 7 that makes it insufficient, not "
                         "contradicted.",
            },
            {
                "text": "A 2022 study showed that nitrates show an increased "
                        "risk of cancer when ingested",
                "source": "both", "start": 132.8, "end": 138.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35303088"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Matches the cited year: the 2022 NutriNet-Sante "
                         "analysis finds higher breast cancer risk for food "
                         "additive nitrates and higher prostate cancer risk "
                         "for additive nitrites, with no association for "
                         "natural sources -- a distinction the video does not "
                         "make.",
            },
            {
                "text": "[Agave syrup] is very high in fructose, usually about "
                        "57 to 90% fructose",
                "source": "both", "start": 163.0, "end": 166.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Searches for agave syrup / agave nectar sugar "
                         "composition returned nothing that reports a fructose "
                         "percentage. Plausible and probably checkable from a "
                         "food-composition database, but PubMed is the wrong "
                         "source and nothing was retrieved, so the honest "
                         "verdict is insufficient evidence.",
            },
        ],
    },
    {
        "video_id": "v04",
        "topic": "none (non-health)",
        "text_type": "low_text",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "Same creator as v02. Debunks a telekinesis claim by "
                 "explaining that loosely folded tinfoil catches moving air, "
                 "and offers $10,000 for a sealed-container repeat. Real "
                 "debunking structure, no health claim. On-screen text is only "
                 "a 'DEBUNK INCOMING' sting and the handle watermark, so "
                 "low_text. Collectors filed it under DEBUNKING.",
        "claims": [],
    },
    {
        "video_id": "v05",
        "topic": "none (non-health)",
        "text_type": "high_text",
        "case_tags": [],
        "confidence": "high",
        "notes": "A mentalism performance (@jakehofman, 'Fooling my Stanford "
                 "Professor'). No health content. Collectors filed it under "
                 "'No info', which agrees.",
        "claims": [],
    },
    {
        "video_id": "v06",
        "topic": "none (non-health)",
        "text_type": "high_text",
        "case_tags": [],
        "confidence": "high",
        "notes": "A 5.5-minute technical explainer on neural scaling laws in "
                 "machine learning (OpenAI's 2020 papers, GPT-3, petaflop "
                 "days). Dense on-screen text, all of it charts and axis "
                 "labels. No health content of any kind. Collectors filed it "
                 "under NO_MISINFO, which reads as 'nothing false here' rather "
                 "than a judgement that it belongs in a health dataset; the "
                 "section 9 rules give CANNOT_RECOGNIZE because there is no "
                 "checkable health claim to judge.",
        "claims": [],
    },
]
