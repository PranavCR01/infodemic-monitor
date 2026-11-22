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
    {
        "video_id": "v07",
        "topic": "assorted health myths (hydration, joints, first aid, hair)",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "A myth-debunking listicle. Of the eleven myths it raises, "
                 "five are health assertions and are labelled here; the rest "
                 "(Einstein failing maths, Columbus, Marilyn Monroe's dress "
                 "size, undercover police having to identify themselves, "
                 "swallowing spiders in your sleep) are not health claims and "
                 "are left out. The speaker refutes all of them. Only the "
                 "knuckle-cracking myth could actually be adjudicated from "
                 "retrievable evidence, which is what makes this video "
                 "DEBUNKING rather than CANNOT_RECOGNIZE -- see the PR "
                 "description on folklore myths and section 7. Collectors "
                 "filed it under DEBUNKING, which agrees.",
        "claims": [
            {
                "text": "you need to drink eight cups of water a day",
                "start": 3.1, "end": 10.0,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Searches for the eight-glasses rule and for adult "
                         "water requirements returned nothing that tests it. "
                         "The rule having no evidence base is exactly why it "
                         "is a myth, but section 7 is explicit that absence of "
                         "evidence is not contradiction, so the verdict is "
                         "insufficient rather than CONTRADICTED.",
            },
            {
                "text": "we only use 10% of our brain",
                "start": 40.6, "end": 46.8,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "The neuromyths literature (PMID 23087664, 36470620) "
                         "was retrieved, but neither abstract names the "
                         "ten-percent claim, so citing them for it would be "
                         "citing a paper for something not shown to be in it "
                         "-- the evidence-laundering failure in section 7's "
                         "probe. Left uncited rather than loosely cited.",
            },
            {
                "text": "if you crack your knuckles you're going to get "
                        "arthritis",
                "start": 82.0, "end": 92.8,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:21383216", "PMID:30080300"],
                "confidence": "high",
                "notes": "Directly tested and directly refuted: the "
                         "case-control study concludes that a history of "
                         "habitual knuckle cracking, including total duration "
                         "and cumulative exposure, does not seem to be a risk "
                         "factor for hand osteoarthritis. The one claim in "
                         "this video the evidence can actually settle, and the "
                         "one that makes the section 9 rules return DEBUNKING.",
            },
            {
                "text": "to pee on a jellyfish sting and that that'll make it "
                        "heal",
                "start": 122.1, "end": 133.6,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:40525026"],
                "confidence": "high",
                "notes": "The 2025 systematic review of jellyfish-sting first "
                         "aid lists the treatments with any evidence "
                         "(seawater, heat, cold packs, lidocaine, vinegar, "
                         "bicarbonate) and urine is not among them -- it is "
                         "not tested at all, and the review rates the whole "
                         "evidence base very low quality. Not tested is "
                         "insufficient, not contradicted.",
            },
            {
                "text": "if you shave your hair it'll grow back thicker",
                "start": 159.8, "end": 181.8,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:5459955"],
                "confidence": "medium",
                "notes": "Lynfield and MacWilliams, 'Shaving and hair growth' "
                         "(J Invest Dermatol 1970), is exactly on the question, "
                         "but PubMed holds no abstract for it and it is not in "
                         "PMC, so its conclusion could not be read. Cited as "
                         "the on-point paper; a reviewer with journal access "
                         "should read it and will most likely upgrade this row "
                         "to CONTRADICTED.",
            },
        ],
    },
    {
        "video_id": "v08",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A narrated hide-and-seek competition show ($100,000 prize, "
                 "six people hiding in an abandoned courthouse). No health "
                 "content. Collectors filed it under 'No info', which agrees.",
        "claims": [],
    },
    {
        "video_id": "v09",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A Bill Nye thermal-conductivity demonstration: ice melting "
                 "faster on the surface that feels cooler. Physics, not "
                 "health, so there is no checkable health assertion. "
                 "Collectors filed it under NO_MISINFO.",
        "claims": [],
    },
    {
        "video_id": "v10",
        "topic": "none (non-health)",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "A debunk of a 'giants were real' video, arguing from "
                 "prehistoric oxygen levels and arthropod size. Genuine "
                 "debunking structure but the subject is palaeontology, not "
                 "health. Tagged 'debunking' for the stance track for the same "
                 "reason as v02 and v04. Collectors filed it under DEBUNKING.",
        "claims": [],
    },
    {
        "video_id": "v11",
        "topic": "nutrition / dietary fat",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "A physician replying to a commenter who attacks him for "
                 "endorsing seed oils. The most genuinely unsettled video in "
                 "the bundle so far, and a clean test of the MIXED verdict: "
                 "the seed-oil claims are supported by the observational "
                 "literature, while the aside that saturated fat is 'totally "
                 "fine' sits on top of a real disagreement between the 2020 "
                 "Cochrane review and a 2025 meta-analysis. Under section 9 "
                 "that leaves the video NO_MISINFO, but MIXED verdicts are a "
                 "section 11 review trigger, which is the intended behaviour. "
                 "This collector's folder carried no label.",
        "claims": [
            {
                "text": "people who eat a lot of saturated fats, which are "
                        "totally fine, by the way",
                "start": 15.3, "end": 19.0,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:40416032"],
                "contradicting": ["PMID:32428300"],
                "confidence": "high",
                "notes": "Good studies point in different directions. The 2020 "
                         "Cochrane review finds reducing saturated fat cuts "
                         "combined cardiovascular events by 21% (moderate "
                         "quality) though with little or no effect on "
                         "all-cause or cardiovascular mortality; a 2025 "
                         "meta-analysis of nine trials finds no significant "
                         "difference in any of those outcomes and concludes "
                         "that saturated fat reduction cannot currently be "
                         "recommended. Exactly the case MIXED exists for.",
            },
            {
                "text": "they replace some fraction of those [saturated fats] "
                        "with seed oils. And in almost every study, the people "
                        "are months later healthier",
                "start": 19.0, "end": 26.5,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:32428300", "PMID:25161045"],
                "contradicting": ["PMID:40416032"],
                "confidence": "medium",
                "notes": "The Cochrane review supports replacement with "
                         "polyunsaturated fat reducing cardiovascular events, "
                         "and the linoleic-acid meta-analysis points the same "
                         "way; the 2025 meta-analysis finds no benefit. "
                         "'Almost every study' overstates a split literature, "
                         "which is why this is MIXED rather than SUPPORTED.",
            },
            {
                "text": "seed oils are super great for your health. They're "
                        "totally fine",
                "start": 49.6, "end": 54.8,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:25161045", "PMID:37513547",
                               "PMID:39820582"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The systematic review and meta-analysis of "
                         "prospective cohorts concludes that dietary linoleic "
                         "acid intake is inversely associated with coronary "
                         "heart disease risk in a dose-response manner. "
                         "Observational, and 'super great' is stronger than "
                         "'not harmful', hence medium confidence.",
            },
        ],
    },
    {
        "video_id": "v12",
        "topic": "weight loss",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "A fitness creator explaining how she lost 15 pounds in 20 "
                 "days, selling a meal plan. Contains what is almost certainly "
                 "the clearest piece of false physiology in the bundle -- that "
                 "body fat leaves the body in urine -- but the one paper that "
                 "addresses it directly is a BMJ feature with only a "
                 "one-sentence teaser abstract and no PMC copy, so its "
                 "conclusion could not be read and the verdict has to stay "
                 "INSUFFICIENT_EVIDENCE. That leaves the video "
                 "CANNOT_RECOGNIZE where the collectors filed it under "
                 "MISINFO, and a reviewer with journal access should expect to "
                 "flip it. Written up in the PR description as a limitation of "
                 "an abstract-only evidence pipeline, not as a labelling "
                 "preference.",
        "claims": [
            {
                "text": "you need to eliminate your sugar addiction. If you "
                        "didn't know, your body runs off sugar, aka glucose. "
                        "So if you stop feeding yourself sugar, your body will "
                        "burn the sugar that is stored",
                "start": 22.2, "end": 31.0,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "Roughly describes glycogen depletion, which is "
                         "textbook physiology, but no retrieved study tests "
                         "the claim as stated and 'sugar addiction' is not "
                         "defined here. Honest insufficient rather than a "
                         "verdict propped up by background knowledge.",
            },
            {
                "text": "you need to be drinking a hundred ounces of water a "
                        "day. Really, you should be drinking your body weight "
                        "in ounces",
                "start": 31.0, "end": 38.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Same evidence gap as the eight-cups myth in v07, "
                         "from the opposite stance: nothing retrieved "
                         "establishes a body-weight-in-ounces water "
                         "requirement. Note that v07 refutes a hydration rule "
                         "and this video endorses a stricter one -- a useful "
                         "pair for the stance step.",
            },
            {
                "text": "your body actually flushes out the fat cells through "
                        "your bloodstream, and you pee it out. You don't poop "
                        "it out ... you pee out the fat",
                "start": 38.7, "end": 48.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:25516540"],
                "confidence": "low",
                "notes": "THE ROW MOST LIKELY TO CHANGE ON REVIEW. Meerman and "
                         "Brown, 'When somebody loses weight, where does the "
                         "fat go?' (BMJ 2014), is precisely on this question, "
                         "but PubMed carries only the teaser line 'explain why "
                         "the answer might not be what you expect' and the "
                         "paper has no PMCID, so nothing readable was "
                         "retrieved. Three further searches for the mass "
                         "balance of fat loss returned nothing usable. A "
                         "reviewer who reads the full text should upgrade this "
                         "to CONTRADICTED, which flips the video to MISINFO.",
            },
        ],
    },
    {
        "video_id": "v13",
        "topic": "weight loss",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "A personal weight-loss account (100 pounds in nine months, "
                 "no gym). Mostly motivational and anecdotal; the three "
                 "checkable assertions are all either too vague to test or "
                 "untested in the literature, so the video comes out "
                 "CANNOT_RECOGNIZE against the collectors' MISINFO. Same "
                 "pattern as v12: folk physiology that a human annotator reads "
                 "as obviously wrong but a retrieval-grounded rubric cannot "
                 "call false.",
        "claims": [
            {
                "text": "don't worry about being hungry. I promise you that "
                        "feeling goes away. You will stop being hungry after a "
                        "while. Probably like a week probably like two weeks",
                "start": 54.7, "end": 65.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing retrieved tests whether hunger resolves "
                         "within one to two weeks of energy restriction. The "
                         "adaptive-thermogenesis paper that the search "
                         "returned measures resting energy expenditure, not "
                         "appetite, so it does not test this.",
            },
            {
                "text": "nine times out of ten you can't ... weigh 130 pounds "
                        "and be eating pizzas and burgers",
                "start": 98.7, "end": 112.9,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "No population, no quantity and no time frame: there "
                         "is no version of this that a study could test as "
                         "stated. Section 7's NOT_VERIFIABLE rather than "
                         "INSUFFICIENT_EVIDENCE, because the problem is the "
                         "claim, not the literature.",
            },
            {
                "text": "if I go out and I eat something real dirty for me ... "
                        "I'm going to drink a lot of water, I'm gonna flush it "
                        "out",
                "start": 132.2, "end": 143.2,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "The idea that drinking water flushes out food "
                         "already eaten. No retrieved study tests it.",
            },
        ],
    },
    {
        "video_id": "v14",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A student arguing with a lecturer about an un-curved exam "
                 "averaging 47%. No health content. Collectors filed it under "
                 "'No info', which agrees.",
        "claims": [],
    },
    {
        "video_id": "v15",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A mirror/line-of-sight trick, filmed as banter. No health "
                 "content, and the speech is fragmentary. Collectors filed it "
                 "under 'No info', which agrees.",
        "claims": [],
    },
    {
        "video_id": "v16",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A natural-history explainer about the oldest animal ever "
                 "found (the quahog clam 'Ming'). Biology, not health. "
                 "Collectors filed it under NO_MISINFO.",
        "claims": [],
    },
    {
        "video_id": "v17",
        "topic": "food additives / food safety",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "A short scaremongering clip driving traffic to a bio link: "
                 "the FDA has approved 863 chemicals, Texas has supposedly "
                 "demanded 'unfit for human consumption' warning labels, and "
                 "the foods on display contain 'hundreds of dangerous "
                 "chemicals'. Two judgement calls here. First, the two "
                 "specific assertions are regulatory rather than health "
                 "claims, so under the README's definition they are not rows "
                 "in claims.csv -- but they are where the misinformation "
                 "actually lives, and neither PubMed nor WHO/CDC can settle a "
                 "claim about Texas state law. Second, what is left is a "
                 "health assertion too vague to test. The result is "
                 "CANNOT_RECOGNIZE against the collectors' MISINFO. The PR "
                 "description raises both gaps: the rubric has no home for "
                 "false regulatory claims, and vague chemical scaremongering "
                 "is unfalsifiable by construction.",
        "claims": [
            {
                "text": "all of these foods behind me literally contain "
                        "hundreds of dangerous chemicals",
                "start": 23.8, "end": 28.0,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Which foods, which chemicals, dangerous at what "
                         "dose, for what outcome -- none are specified, and "
                         "'chemicals' covers water and salt as readily as "
                         "anything else. There is no study that could test "
                         "this as stated, so NOT_VERIFIABLE rather than "
                         "INSUFFICIENT_EVIDENCE.",
            },
        ],
    },
]
