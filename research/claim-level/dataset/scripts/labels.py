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
    {
        "video_id": "v20",
        "topic": "home remedies / respiratory infection",
        "case_tags": ["missing_evidence"],
        "confidence": "high",
        "notes": "A 27-second recipe video: onion, garlic, lemon, ginger and "
                 "cinnamon boiled in two litres of water, claimed to relieve "
                 "five separate respiratory conditions. One sentence carrying "
                 "five therapeutic claims, split into five rows per the "
                 "section 4 rule. Nothing in the literature tests this "
                 "preparation, and the closest thing to a direct test -- the "
                 "Cochrane review of garlic for the common cold -- concludes "
                 "there is insufficient trial evidence. So every row is "
                 "INSUFFICIENT_EVIDENCE and the video is CANNOT_RECOGNIZE, "
                 "against the collectors' MISINFO. The same pattern as v12, "
                 "v13 and v17: unevidenced folk remedies are not CONTRADICTED "
                 "under section 7, they are unproven.",
        "claims": [
            {
                "text": "a remedy capable of relieving dry cough",
                "start": 10.6, "end": 17.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "No trial of this preparation. The honey the video "
                         "offers as an optional sweetener does have Cochrane "
                         "evidence for acute cough in children, but that tests "
                         "honey, not this decoction, so it is not cited here.",
            },
            {
                "text": "a remedy capable of ... [relieving] bronchitis",
                "start": 10.6, "end": 17.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Searches for herbal treatment of acute bronchitis "
                         "return trials of Pelargonium sidoides extract, a "
                         "different preparation entirely, so nothing tests "
                         "this claim.",
            },
            {
                "text": "a remedy capable of ... expelling mucus stuck in the "
                        "lungs",
                "start": 10.6, "end": 17.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A search for ginger as a respiratory expectorant "
                         "returned nothing at all; the empty search is in "
                         "evidence_cache/.",
            },
            {
                "text": "a remedy capable of ... improving sinusitis",
                "start": 17.3, "end": 22.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Nothing retrieved tests any of these ingredients "
                         "against sinusitis.",
            },
            {
                "text": "a remedy capable of ... easing cold symptoms",
                "start": 17.3, "end": 22.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:25386977"],
                "confidence": "high",
                "notes": "The closest direct test available: the Cochrane "
                         "review of garlic for the common cold concludes there "
                         "is insufficient clinical trial evidence for garlic "
                         "in preventing or treating colds, resting on a single "
                         "trial. Cited as the nearest evidence while the "
                         "verdict stays insufficient, because the review "
                         "itself reports an absence of evidence rather than a "
                         "demonstrated lack of effect.",
            },
        ],
    },
    {
        "video_id": "v21",
        "topic": "nutrition / nuts",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A six-benefit listicle about eating almonds daily, ending in "
                 "a 'natural medicine' subscribe prompt. A useful contrast "
                 "with v20: same listicle format, but one of the six claims is "
                 "backed by a 37-trial meta-analysis, so the video comes out "
                 "NO_MISINFO rather than CANNOT_RECOGNIZE. The weaker half of "
                 "the video leans on nutrient-to-outcome reasoning (magnesium "
                 "therefore mood, tryptophan therefore sleep, vitamin E "
                 "therefore less stress) that no retrieved trial tests. "
                 "Collectors filed it under NO_MISINFO, which agrees.",
        "claims": [
            {
                "text": "You'll reduce abdominal fat. Studies show that "
                        "almonds can help you lose weight, especially in the "
                        "stomach area",
                "start": 3.8, "end": 10.9,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:38351580"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "A meta-analysis of 37 randomised trials finds "
                         "significant reductions in body weight (-0.45 kg) and "
                         "waist circumference (-0.66 cm) with moderate GRADE "
                         "certainty. Two caveats a reviewer should weigh: the "
                         "effects are small, and the 'especially in the "
                         "stomach area' part is not established -- certainty "
                         "for visceral adipose tissue specifically was rated "
                         "very low.",
            },
            {
                "text": "Almonds are rich in unsaturated fats that promote "
                        "good cholesterol and protect your heart",
                "start": 12.8, "end": 18.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:38967674"],
                "confidence": "medium",
                "notes": "No cardiovascular-outcome trial of almonds was "
                         "retrieved, and the systematic review of nuts in "
                         "secondary cardiovascular prevention found no change "
                         "in lipid or inflammatory profiles. Not enough to "
                         "call the claim false, well short of supporting it.",
            },
            {
                "text": "Thanks to their fiber and protein content, almonds "
                        "make you feel full. This makes them an ideal snack "
                        "for controlling your appetite",
                "start": 19.8, "end": 28.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:36305961", "PMID:34682735"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Individual trials point this way (almonds improve "
                         "appetite-regulating hormones; snacking on almonds "
                         "lowers energy intake against a high-carbohydrate "
                         "snack), but the 37-trial meta-analysis rates the "
                         "certainty of the appetite evidence very low on "
                         "GRADE. Section 7's 'what exists is too weak' applies.",
            },
            {
                "text": "Almonds are an excellent source of magnesium, which "
                        "plays an essential role in mood regulation and stress "
                        "management",
                "start": 31.5, "end": 37.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Every trial the search returned tests magnesium "
                         "inside a multi-ingredient supplement (with B "
                         "vitamins, green tea, rhodiola), so none isolates "
                         "magnesium's effect on mood or stress.",
            },
            {
                "text": "Almonds are naturally rich in tryptophan, an amino "
                        "acid that plays a key role in the production of "
                        "serotonin, the sleep hormone",
                "start": 40.1, "end": 47.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing retrieved tests almond tryptophan against "
                         "sleep in people -- the only hit was a study in ring "
                         "doves. Worth a reviewer's attention separately: "
                         "calling serotonin 'the sleep hormone' is wrong "
                         "(melatonin is the one usually meant), but that is a "
                         "mislabel inside the reasoning rather than a separate "
                         "testable claim, and no retrieved source states it, "
                         "so it is noted rather than cited.",
            },
            {
                "text": "Almonds are rich in antioxidants like vitamin E, "
                        "which help fight oxidative stress and reduce daily "
                        "stress",
                "start": 49.6, "end": 56.5,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Conflates oxidative stress with psychological "
                         "stress. Nothing retrieved tests vitamin E or almonds "
                         "against perceived daily stress.",
            },
        ],
    },
    {
        "video_id": "v22",
        "topic": "nutrition / eggs",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A two-week-of-eggs listicle, delivered in clinical language. "
                 "The best-evidenced of the three listicles (v20, v21, v22): "
                 "the HDL claim is directly supported by a meta-analysis of "
                 "randomised trials, though the same meta-analysis shows eggs "
                 "raise LDL as well, which the video does not mention. That "
                 "omission is the most interesting thing in the video and is "
                 "recorded on the claim rather than treated as a separate "
                 "claim, since the speaker never asserts anything about LDL. "
                 "Collectors filed it under NO_MISINFO, which agrees.",
        "claims": [
            {
                "text": "You're going to be consuming the best quality "
                        "protein. Your muscles, your connective tissue will "
                        "get the highest quality amino acids",
                "start": 3.2, "end": 10.2,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "A search for egg protein quality scores (DIAAS, "
                         "biological value) returned nothing. Egg protein "
                         "scoring well is uncontroversial nutrition-textbook "
                         "material, but PubMed returned no source for it and "
                         "section 7 does not allow filling the gap from "
                         "background knowledge. A reviewer with a food "
                         "composition reference should expect to upgrade this.",
            },
            {
                "text": "Eggs are high in antioxidants, which is really good "
                        "to prevent something called macular degeneration as "
                        "well as cataracts",
                "start": 10.2, "end": 16.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:35215476"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The retrieved review covers lutein and zeaxanthin in "
                         "age-related macular degeneration, not egg intake as "
                         "a prevention strategy, and says nothing retrievable "
                         "about cataracts. Indirect on both halves of the "
                         "claim.",
            },
            {
                "text": "Eggs are also high in something called choline, "
                        "which is really good to prevent a fatty liver",
                "start": 16.8, "end": 20.8,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39424072", "PMID:37634048"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The Framingham analysis finds dietary choline intake "
                         "strongly inversely associated with incident NAFLD "
                         "risk, which is the claim as stated. But the same "
                         "cohort found no association between egg intake "
                         "itself and NAFLD risk, so the nutrient link holds "
                         "while the food-level effect does not. A reviewer "
                         "could reasonably call this MIXED; recorded as "
                         "SUPPORTED because the sentence is a claim about "
                         "choline.",
            },
            {
                "text": "[choline is] really good to ... support your brain, "
                        "better focus, concentration, and memory",
                "start": 20.8, "end": 24.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Split from the fatty-liver claim in the same "
                         "sentence. Nothing retrieved tests choline or eggs "
                         "against focus, concentration or memory.",
            },
            {
                "text": "Even though eggs are high in cholesterol, you're "
                        "going to find that your HDL, the good cholesterol "
                        "will go up if you consume eggs",
                "start": 24.8, "end": 33.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:29111915", "PMID:32635569"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Directly supported: the meta-analysis of randomised "
                         "trials concludes that egg consumption increases "
                         "total cholesterol, LDL-C and HDL-C against low-egg "
                         "control diets. Supported exactly as stated -- and "
                         "worth a reviewer's note that the same result "
                         "includes the LDL rise the video leaves out, so a "
                         "true claim is being used to carry a one-sided "
                         "impression.",
            },
            {
                "text": "if you eat eggs for breakfast, you're going to find "
                        "your blood sugars are going to be very stabilized",
                "start": 28.8, "end": 36.2,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:29313753"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "A search for egg breakfasts and postprandial "
                         "glycaemia returned nothing; the nearest trial "
                         "compares two eggs a day with an oatmeal breakfast "
                         "and reports carotenoids and choline, not glucose "
                         "stability.",
            },
        ],
    },
    {
        "video_id": "v26",
        "topic": "exercise / fasted walking",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A timeline listicle (@asmrsounding) about a 20-minute fasted "
                 "morning walk: effects claimed immediately, after one week "
                 "and after 20 days. The specific timelines are invented -- "
                 "nothing retrieved tests a 20-day immune effect -- but the "
                 "two claims that map onto a real literature (blood pressure, "
                 "sleep) are supported, so the video is NO_MISINFO. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "Since your glycogen stores are depleted overnight, "
                        "your body switches to burning fat more quickly",
                "start": 5.1, "end": 9.9,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:23723099"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Higher fat oxidation during fasted exercise is the "
                         "well-described part of this topic. Cited to the "
                         "fed-versus-fasted interval training trial; note it "
                         "is fat oxidation during exercise, which is not the "
                         "same as losing more fat.",
            },
            {
                "text": "your metabolism gets activated, helping you burn fat "
                        "more efficiently, which makes weight loss easier and "
                        "faster",
                "start": 10.7, "end": 20.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:23723099"],
                "confidence": "medium",
                "notes": "This is the step the video takes without support: "
                         "greater fat oxidation during a fasted walk does not "
                         "make weight loss faster. The trial that compares fed "
                         "with fasted training found body-composition "
                         "improvements in both states. Not a clean "
                         "contradiction of the claim as worded, so "
                         "insufficient, but this is the row a reviewer should "
                         "look at first in this video.",
            },
            {
                "text": "Your cortisol level, the stress hormone, gets "
                        "regulated. This helps you feel more relaxed and calm "
                        "throughout the day",
                "start": 20.9, "end": 25.0,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "'Regulated' is not a direction, and nothing "
                         "retrieved tests morning fasted walking against "
                         "cortisol or self-reported calmness.",
            },
            {
                "text": "After just one week, your circulation improves. This "
                        "helps regulate blood pressure and strengthens your "
                        "cardiovascular system",
                "start": 35.6, "end": 40.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39444461", "PMID:25601182"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The systematic review concludes brisk walking "
                         "significantly reduces blood pressure in people with "
                         "hypertension. Two qualifications: the evidence is in "
                         "hypertensive populations rather than everyone, and "
                         "nothing establishes the 'after just one week' "
                         "timeline the video asserts.",
            },
            {
                "text": "After 20 days, your immune system becomes stronger",
                "start": 46.4, "end": 51.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "The exercise-immunology literature that the search "
                         "returned concerns infection susceptibility in "
                         "athletes and training loads; none of it tests a "
                         "20-day immune effect from a daily 20-minute walk. "
                         "The precise-sounding timeline has no source.",
            },
            {
                "text": "Your sleep also improves. You fall asleep faster and "
                        "wake up feeling more refreshed",
                "start": 51.8, "end": 54.9,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:34163383", "PMID:25596964"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The meta-analysis of randomised trials finds "
                         "exercise improves subjective sleep quality, insomnia "
                         "severity and daytime sleepiness. Noted limitation "
                         "from the review itself: the improvements are in "
                         "subjective rather than physiological sleep measures.",
            },
        ],
    },
    {
        "video_id": "v19",
        "topic": "nutrition / dietary fat",
        "case_tags": ["debunking", "uncertain_science"],
        "confidence": "medium",
        "notes": "A careful seed-oil debunk that explicitly separates "
                 "correlation from causation, cites controlled feeding trials "
                 "and the Japan counter-example, and ends on obesity being "
                 "multifactorial. Pairs with v11 (same topic, a doctor "
                 "defending seed oils) and against the rest of the bundle's "
                 "seed-oil content. Comes out DEBUNKING because the myth it "
                 "refutes is contradicted by the linoleic-acid literature. "
                 "Two of its claims are national-statistics assertions that "
                 "PubMed cannot settle. This collector's folder carried no "
                 "label.",
        "claims": [
            {
                "text": "seed oils are horrible for you",
                "start": 0.0, "end": 3.2,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:25161045", "PMID:37513547"],
                "confidence": "medium",
                "notes": "The myth the video exists to refute, stated in its "
                         "opening line. The systematic review and "
                         "meta-analysis of prospective cohorts finds dietary "
                         "linoleic acid inversely associated with coronary "
                         "heart disease risk in a dose-response manner, which "
                         "contradicts 'horrible for you'. Observational "
                         "evidence, hence medium confidence.",
            },
            {
                "text": "In every single human study done, the people eating "
                        "more seed oils either saw the same or actually better "
                        "health outcomes than the groups eating less",
                "start": 47.2, "end": 55.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:32428300", "PMID:40416032",
                               "PMID:25161045"],
                "confidence": "medium",
                "contradicting": [],
                "notes": "Unusually, the hedge inside the claim ('the same or "
                         "better') is what makes it hold: the Cochrane review "
                         "finds benefit from replacing saturated fat and the "
                         "2025 meta-analysis finds no difference, and both "
                         "fall inside 'same or better'. 'Every single human "
                         "study done' is an absolute that cannot be verified "
                         "exhaustively, which is why this is medium confidence "
                         "rather than high.",
            },
            {
                "text": "researchers locked people in a metabolic ward and fed "
                        "them two diets matched for the calories in sugar, "
                        "fat, fiber, and sodium ... On the processed diet, "
                        "people ate 500 calories more a day and gained weight",
                "start": 107.2, "end": 120.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:31105044"],
                "contradicting": [],
                "confidence": "high",
                "notes": "An accurate description of a real trial, down to the "
                         "effect size: Hall et al., 'Ultra-Processed Diets "
                         "Cause Excess Calorie Intake and Weight Gain: An "
                         "Inpatient Randomized Controlled Trial of Ad Libitum "
                         "Food Intake'. The most precisely sourced claim in "
                         "the bundle that the speaker did not show on screen.",
            },
            {
                "text": "Since the 1960s, Japan has quadrupled its vegetable "
                        "oil intake in the form of canola and soybean ... "
                        "Their obesity rate is under 5%, and they live longer "
                        "than almost anyone on the earth",
                "start": 65.4, "end": 78.5,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Three national statistics (oil intake, obesity "
                         "prevalence, life expectancy). All are checkable, but "
                         "against OECD or WHO country data rather than the "
                         "biomedical literature, and nothing retrievable "
                         "through PubMed or a WHO/CDC page tests them. A "
                         "structural gap in the evidence sources rather than a "
                         "weakness in the claim -- see the PR description.",
            },
            {
                "text": "We eat about 500 or more calories a day than we did "
                        "in 1970",
                "start": 92.3, "end": 96.5,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Same kind of claim as the Japan one: a national "
                         "food-availability statistic, not a biomedical "
                         "finding.",
            },
        ],
    },
    {
        "video_id": "v25",
        "topic": "nutrition / sugar",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "@andydoeshealthy plays a news clip of someone claiming the "
                 "body cannot break down high fructose corn syrup, then "
                 "refutes it on composition and metabolism. The cleanest "
                 "debunking case in the bundle: both refuted claims are "
                 "contradicted by retrievable evidence, so the section 9 rules "
                 "return DEBUNKING on solid ground rather than on a single "
                 "thin verdict the way v07 does. Also a good test of the "
                 "section 5 distinction between QUOTES and REFUTES -- the "
                 "claims are someone else's words, played as a clip, but the "
                 "speaker takes a clear position against them, so the stance "
                 "is REFUTES, not QUOTES. This collector's folder carried no "
                 "label.",
        "claims": [
            {
                "text": "High fructose corn syrup, our body doesn't really "
                        "know what to do with it, it doesn't have the proper "
                        "enzymes or stuff to break it down",
                "start": 2.9, "end": 9.0,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:28241431"],
                "confidence": "medium",
                "notes": "Quoted from the news clip and then refuted. Human "
                         "fructose metabolism via intestinal and hepatic "
                         "fructolysis is characterised in the retrieved "
                         "review, so the enzymes plainly exist. The review "
                         "describes the pathway rather than setting out to "
                         "rebut this claim, hence medium confidence.",
            },
            {
                "text": "by adding cane sugar instead of high fructose corn "
                        "syrup, it wouldn't be as overwhelming to the liver "
                        "and wouldn't have as high of blood sugar spikes",
                "start": 9.0, "end": 15.0,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:3891268"],
                "confidence": "high",
                "notes": "Directly tested and directly refuted: in patients "
                         "with non-insulin-dependent diabetes, plasma glucose "
                         "responses after sucrose and HFCS test meals 'did not "
                         "differ', and the integrated areas under the glucose "
                         "curves were not statistically different. Swapping "
                         "one for the other does not reduce the spike.",
            },
            {
                "text": "a beverage that is basically liquid sugar "
                        "substituting one type of sugar for a very similar "
                        "type of sugar is probably not gonna do a whole lot in "
                        "the realm of making people healthier",
                "start": 39.0, "end": 49.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:3891268"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The speaker's own positive claim, supported by the "
                         "same trial that refutes the clip. Appropriately "
                         "hedged ('probably not gonna do a whole lot'), and "
                         "the evidence is a small 1985 study in a diabetic "
                         "population, so medium confidence.",
            },
        ],
    },
    {
        "video_id": "v28",
        "topic": "diabetes / fruit",
        "case_tags": ["clearly_false"],
        "confidence": "high",
        "notes": "@doctorbodyhealthtips telling diabetics to avoid four "
                 "fruits, interleaved with follow prompts. The best-evidenced "
                 "MISINFO case in the bundle so far, and the inverse of the "
                 "pattern in v12, v13, v17 and v20: these claims are specific "
                 "enough to test, and the evidence contradicts them. A "
                 "meta-analysis of nineteen randomised trials recommends the "
                 "opposite of the video's headline advice, and the "
                 "international glycemic-index tables contradict the "
                 "high-GI claims about apples and bananas. Note the "
                 "watermelon claim survives as insufficient rather than "
                 "contradicted, because watermelon is a genuine exception "
                 "among fruits and no value for it could be read. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "All diabetics must avoid eating these four fruits",
                "start": 0.0, "end": 3.8,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:37214237", "PMID:23990623"],
                "confidence": "high",
                "notes": "Contradicted head-on. The meta-analysis of nineteen "
                         "randomised controlled trials (888 participants) "
                         "finds fruit consumption significantly lowers fasting "
                         "blood glucose and concludes: 'we recommend that "
                         "patients with diabetes eat more fruits while "
                         "ensuring that their total energy intake remains "
                         "unchanged'. The claim is the opposite of the "
                         "evidence-based advice, and it is the claim that "
                         "makes this video MISINFO under section 9.",
            },
            {
                "text": "Watermelon has a very high glycemic index ... That "
                        "means it raises blood sugar quickly, even in small "
                        "portions",
                "start": 6.0, "end": 15.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Deliberately not lumped in with the apple and "
                         "banana rows. Watermelon is the one fruit here with a "
                         "genuinely high glycemic index, and the tables are "
                         "not open access so no specific value could be read. "
                         "The 'even in small portions' half is also "
                         "questionable, since glycemic load accounts for "
                         "portion and watermelon's is low -- but nothing "
                         "retrieved states that, so it stays insufficient.",
            },
            {
                "text": "Ripe bananas have a high glycemic index and sugar "
                        "content, which can rapidly elevate blood sugar levels",
                "start": 29.0, "end": 40.1,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:34258626"],
                "confidence": "medium",
                "notes": "The 2021 international tables of glycemic index and "
                         "glycemic load report that fruits are usually low-GI "
                         "foods, at or below 55 on the 100-point glucose "
                         "scale, with consistent values worldwide. Medium "
                         "rather than high confidence because the tables are "
                         "not open access, so this rests on the review's "
                         "summary statement about fruits as a class rather "
                         "than on the banana row itself.",
            },
            {
                "text": "Mangos, especially when ripe, contain a lot of sugar "
                        "that can cause quick blood sugar spikes",
                "start": 45.3, "end": 55.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "No mango-specific value or trial was retrieved. The "
                         "claim is also softer than the others ('can cause'), "
                         "and it is paired with sensible portion advice.",
            },
            {
                "text": "Apple has a high glycemic index and can sharply raise "
                        "blood glucose",
                "start": 56.9, "end": 62.8,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:34258626"],
                "confidence": "medium",
                "notes": "Apples are a standard example of a low-GI fruit, and "
                         "the 2021 international tables report fruits as "
                         "usually low-GI (at or below 55). Same limitation as "
                         "the banana row: the summary statement about fruits "
                         "as a class is readable, the per-food table is not.",
            },
        ],
    },
    {
        "video_id": "v29",
        "topic": "cancer / alternative remedies",
        "case_tags": ["satire"],
        "confidence": "medium",
        "notes": "@dr_elisa108, speaking as someone living with cancer, "
                 "relays a 'miracle cure' she has just heard -- blending three "
                 "or four Venus flytraps and eating them daily -- and asks "
                 "whether anyone else has come across it. The reason this "
                 "video is in the set is the stance, not the verdict: the "
                 "delivery is wry throughout ('I'm not easily surprised', "
                 "'Kind of fun', 'Let me know if you've tried it and it "
                 "works'), which reads as irony rather than either endorsement "
                 "or correction. Section 5 says hard cases of sarcasm and "
                 "irony go to UNCLEAR rather than a guess, and UNCLEAR is a "
                 "section 11 review trigger, so that is how it is recorded. "
                 "Tagged 'satire' as the nearest section 14 category for "
                 "ironic delivery, though it is wryness rather than parody. A "
                 "second labeller could defensibly call this QUOTES, and this "
                 "is exactly the kind of row the blind subset exists to "
                 "measure. This collector's folder carried no label.",
        "claims": [
            {
                "text": "Venus fly trap[s] ... you blend up three to four of "
                        "them and eat[] them every day ... And that kills your "
                        "cancer",
                "start": 16.9, "end": 31.1,
                "stance": "UNCLEAR", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A search for Dionaea muscipula or Venus flytrap "
                         "extract against cancer returned nothing at all; the "
                         "empty search is in evidence_cache/. Section 7 is "
                         "explicit that this is insufficient evidence and not "
                         "CONTRADICTED, however implausible the claim sounds. "
                         "The verdict is the easy part here; the stance is the "
                         "judgement call.",
            },
        ],
    },
    {
        "video_id": "v23",
        "topic": "vaccines / media literacy",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "@abbeyskitchen on the BBC World Service report into Steven "
                 "Bartlett's Diary of a CEO podcast. Structurally unusual and "
                 "useful for the stance step: the video opens cold on a clip "
                 "of someone else's claims, with no framing until several "
                 "seconds later, so a system reading only the first lines "
                 "would see vaccine-autism and anti-COVID-vaccine assertions "
                 "presented flat. The framing that makes it REFUTES arrives "
                 "afterwards. All three refuted claims are contradicted by "
                 "retrievable evidence, so DEBUNKING rests on solid ground. "
                 "The claims about what the BBC report found are claims about "
                 "a document rather than health assertions, so they are not "
                 "rows. This collector's folder carried no label.",
        "claims": [
            {
                "text": "[vaccines] can cause everything from osteoporosis to "
                        "autism",
                "start": 0.4, "end": 3.8,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:24814559", "PMID:32309885"],
                "confidence": "high",
                "notes": "Played as a clip and rejected by the framing that "
                         "follows. The evidence-based meta-analysis of "
                         "case-control and cohort studies is titled 'Vaccines "
                         "are not associated with autism'. The osteoporosis "
                         "half of the claim is not separately tested by "
                         "anything retrieved, but the autism half is squarely "
                         "contradicted.",
            },
            {
                "text": "The COVID vaccine introduction has had a catastrophic "
                        "negative effect",
                "start": 3.8, "end": 9.2,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:40711778"],
                "confidence": "high",
                "notes": "The global estimate finds more than 2.5 million "
                         "deaths averted by COVID-19 vaccination over "
                         "2020-2024 (one death averted per 5400 doses), with "
                         "sensitivity analyses between 1.4 and 4.0 million "
                         "lives saved. A net catastrophic negative effect is "
                         "the opposite of that.",
            },
            {
                "text": "you can reverse autism through diet",
                "start": 50.3, "end": 55.8,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:28612113", "PMID:24789114"],
                "confidence": "medium",
                "notes": "The systematic review of six randomised trials (214 "
                         "participants) of gluten- and casein-free diets finds "
                         "no statistically significant differences in autism "
                         "core symptoms between groups, with one exception on "
                         "a single communication subdomain. That refutes "
                         "reversal through diet; medium confidence because the "
                         "trials test one dietary approach rather than every "
                         "possible one.",
            },
        ],
    },
    {
        "video_id": "v24",
        "topic": "pesticide residues / food safety",
        "case_tags": ["debunking", "uncertain_science"],
        "confidence": "medium",
        "notes": "@andydoeshealthy rebutting a creator who told people to "
                 "avoid Cheerios over glyphosate residues. The most "
                 "instructive case in the bundle for the section 9 rules: it "
                 "is unmistakably a debunking video, but it comes out "
                 "NO_MISINFO rather than DEBUNKING, because the claim it "
                 "refutes lands on MIXED and section 9's second rule fires "
                 "only on CONTRADICTED. Glyphosate carcinogenicity is "
                 "genuinely contested -- the Agricultural Health Study found "
                 "no association overall, a 2019 meta-analysis found increased "
                 "non-Hodgkin lymphoma risk, and IARC and the regulatory "
                 "agencies reached different conclusions. The debunker is also "
                 "one-sided himself: he quotes the cohort's null result "
                 "accurately but omits the raised acute myeloid leukaemia risk "
                 "in its highest exposure quartile. Written up in the PR "
                 "description. This collector's folder carried no label.",
        "claims": [
            {
                "text": "[Cheerios carry harmful] glyphosate residues ... your "
                        "cereal is a spawn of Satan",
                "start": 25.2, "end": 31.2,
                "stance": "REFUTES", "verdict": "MIXED",
                "supporting": ["PMID:31342895", "PMID:26941213"],
                "contradicting": ["PMID:29136183", "PMID:27552246"],
                "confidence": "medium",
                "notes": "The myth being refuted. Evidence genuinely points "
                         "both ways on glyphosate and cancer, so MIXED. Note "
                         "that the columns read against the claim, not against "
                         "the speaker: papers supporting glyphosate harm sit "
                         "in evidence_supporting because the claim asserts "
                         "harm.",
            },
            {
                "text": "when research actually studied this further and "
                        "looked at glyphosate independently, it wasn't "
                        "significantly associated with cancer at any site in a "
                        "study of 54,000 people",
                "start": 152.6, "end": 162.8,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:29136183"],
                "contradicting": [],
                "confidence": "high",
                "notes": "An accurate description of a real study, down to the "
                         "cohort size: among 54,251 applicators, glyphosate "
                         "was not statistically significantly associated with "
                         "cancer at any site in unlagged analyses. What he "
                         "leaves out, and a reviewer should see, is the same "
                         "paper's finding of increased acute myeloid leukaemia "
                         "risk in the highest exposure quartile (RR 2.44).",
            },
            {
                "text": "a look at 15 government agencies and their consensus "
                        "on glyphosate. Not genotoxic, doesn't represent a "
                        "risk of cancer, not carcinogenic, not neurotoxic",
                "start": 157.1, "end": 173.6,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:27552246"],
                "contradicting": ["PMID:26941213", "PMID:31342895"],
                "confidence": "medium",
                "notes": "'Consensus' overstates the position. The retrieved "
                         "literature is explicitly about the disagreement "
                         "between IARC, which classified glyphosate as a "
                         "probable human carcinogen, and the regulatory "
                         "agencies that did not. Papers exist arguing each "
                         "way, which is MIXED, not consensus.",
            },
            {
                "text": "an 150 pound adult would have to eat over 5,000 cups "
                        "a day for a prolonged period of time for glyphosate "
                        "to become an issue",
                "start": 125.6, "end": 137.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A dose calculation against EPA tolerance levels. "
                         "Checkable in principle, but against a regulatory "
                         "tolerance document rather than the biomedical "
                         "literature, and nothing retrievable through PubMed "
                         "or a WHO/CDC page tests it.",
            },
        ],
    },
    {
        "video_id": "v27",
        "topic": "cancer / alternative remedies",
        "case_tags": ["clearly_false"],
        "confidence": "medium",
        "notes": "A ten-minute lecture recording (@botanicalburr) on what "
                 "'cancer loves and hates': sugar, acidity and the absence of "
                 "oxygen, with approving mentions of intravenous vitamin C and "
                 "apricot kernel seeds. The longest video in the bundle and the "
                 "most potentially harmful, since it points at stopping sugar "
                 "and alkalising the body as ways to conquer cancer at 'no "
                 "matter what stage'. It lands on MISINFO through the "
                 "acid/alkaline claims, which are specific enough to be "
                 "contradicted. Worth noting how close it came to escaping: "
                 "its framing claim, that cancer favours an acidic "
                 "environment, is actually SUPPORTED at the level of the "
                 "tumour microenvironment, and the video then slides from that "
                 "real biology into a dietary conclusion that does not follow. "
                 "That slide, not any single false sentence, is where the harm "
                 "lives. This collector's folder carried no label.",
        "claims": [
            {
                "text": "cancer loves sugar ... a cancer cell consumes 15 "
                        "times the glucose of any other cell",
                "start": 19.3, "end": 37.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:19460998", "PMID:39284669"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Elevated glucose uptake by tumour cells (the Warburg "
                         "effect) is real and well described in the retrieved "
                         "reviews, but the specific figure of 15 times any "
                         "other cell is not supported by anything retrieved, "
                         "and the reviews describe aerobic glycolysis as a "
                         "requirement of proliferation rather than a feeding "
                         "relationship with dietary sugar.",
            },
            {
                "text": "Cancer also loves an acid environment",
                "start": 108.2, "end": 118.8,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:31730395"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Supported as stated, and deliberately labelled that "
                         "way: 'The Acidic Tumor Microenvironment as a Driver "
                         "of Cancer' is exactly this claim. The acidity is "
                         "produced by the tumour's own metabolism inside the "
                         "tumour, not set by what the person eats -- which is "
                         "the step the next two claims take without support. "
                         "A reviewer should read this row together with them.",
            },
            {
                "text": "what is the most acid substance you can put into "
                        "your body? Refined sugar ... when they extract the "
                        "sugar out of the sugarcane plant it becomes a pure "
                        "acid",
                "start": 118.8, "end": 141.6,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:38282081"],
                "confidence": "medium",
                "notes": "Dietary acid load is determined by protein, "
                         "potassium, phosphorus, calcium and magnesium, plus "
                         "organic acids that are metabolised to bicarbonate "
                         "and so alkalinise. Refined sucrose contributes none "
                         "of those, so it cannot be the most acidifying thing "
                         "a person can eat. Medium confidence because the "
                         "review defines the measure rather than naming sugar; "
                         "a reviewer should check the PRAL framing in section "
                         "'What is acid-base status?' of PMC11006742.",
            },
            {
                "text": "Cancer is not happy when you create an alkaline "
                        "environment in the ... body",
                "start": 167.4, "end": 190.8,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:38282081", "PMID:27297008"],
                "confidence": "medium",
                "notes": "Contradicted on the premise and unsupported on the "
                         "outcome. Human acid-base equilibrium is, in the "
                         "retrieved review's words, 'a tightly regulated "
                         "physiological system that aims to maintain blood pH "
                         "between 7.35 and 7.45', managed by the kidneys and "
                         "lungs, so a diet cannot make the body alkaline. The "
                         "systematic review of dietary acid load, alkaline "
                         "water and cancer located no studies at all examining "
                         "alkaline diet or alkaline water for cancer "
                         "treatment, and the single included cohort found no "
                         "association. This is the claim that makes the video "
                         "MISINFO.",
            },
            {
                "text": "Cancer hates it when you stop the sugar or stop all "
                        "glucose",
                "start": 167.4, "end": 176.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:39639257"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Glucose restriction as cancer therapy is still at "
                         "the stage of proposing a clinical research framework "
                         "(the retrieved paper is a framework proposal for "
                         "ketogenic metabolic therapy in glioblastoma), so "
                         "nothing yet tests the claim in patients. Not false, "
                         "not established -- and dangerous as advice at 'no "
                         "matter what stage', which is a materiality point for "
                         "the reviewer rather than a verdict.",
            },
            {
                "text": "remember genetics loads the gun, lifestyle pulls the "
                        "trigger",
                "start": 101.1, "end": 108.2,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "An aphorism, not a testable proposition. Kept as a "
                         "row because it is doing argumentative work in the "
                         "video, and NOT_VERIFIABLE is the honest verdict for "
                         "it.",
            },
            {
                "text": "Some do IV vitamin C, some do apricot kernel seeds "
                        "[among doctors, specialists and naturopaths who are "
                        "conquering cancer]",
                "start": 203.4, "end": 212.4,
                "stance": "QUOTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:35929990", "PMID:39369582"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "A QUOTES row: the speaker reports what the authors "
                         "of books in his library do, without asserting it "
                         "himself in this sentence. Intravenous vitamin C has "
                         "reached randomised phase 3 trials in combination "
                         "chemotherapy, so it is being studied rather than "
                         "established; a search for amygdalin, laetrile or "
                         "apricot kernels against cancer returned nothing at "
                         "all.",
            },
        ],
    },
    {
        "video_id": "v30",
        "topic": "vaccines / cancer statistics",
        "case_tags": ["debunking"],
        "confidence": "medium",
        "notes": "@drjessicaknurick taking apart a claim that Australian "
                 "prostate cancer rates in 30-to-40-year-olds rose 500% in "
                 "five years because of vaccine mandates, by showing the "
                 "underlying data spans 2000-2024. The second clear instance "
                 "of the section 9 gap that v24 shows: a competent debunk that "
                 "comes out NO_MISINFO rather than DEBUNKING, because the "
                 "claim being refuted is a data-provenance error that no paper "
                 "tests, so it lands on INSUFFICIENT_EVIDENCE rather than "
                 "CONTRADICTED. The video's own supporting claims about "
                 "early-onset cancer drivers, trans fat and lead are "
                 "supported, which is what carries the label. This collector's "
                 "folder carried no label.",
        "claims": [
            {
                "text": "Over the last five years and typically healthy 30 to "
                        "40-year-olds, prostate cancer is up a whopping 500 "
                        "percent",
                "start": 19.5, "end": 25.5,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:25251195"],
                "confidence": "medium",
                "notes": "The speaker's correction is about the time window, "
                         "not the biology: she says the figure comes from 25 "
                         "years of data (2000-2024), not five. Settling that "
                         "needs the Australian cancer registry rather than a "
                         "paper, and nothing retrieved tests it. The closest "
                         "retrievable item is a report on rising early-onset "
                         "cancer in Australia described explicitly 'over two "
                         "decades', which is consistent with her correction "
                         "but does not verify the 500% figure.",
            },
            {
                "text": "Scientists from around the world who are actually "
                        "studying these trends point to things like improved "
                        "screening, obesity trends, infections, and "
                        "environmental exposures",
                "start": 52.9, "end": 60.9,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33219329", "PMID:40781551",
                               "PMID:40674064"],
                "confidence": "medium",
                "contradicting": [],
                "notes": "The early-onset cancer literature does attribute "
                         "rising incidence to screening changes, metabolic and "
                         "obesity trends and environmental exposures. Medium "
                         "confidence because the retrieved reviews are "
                         "concentrated on gastrointestinal and colorectal "
                         "cancers rather than prostate cancer.",
            },
            {
                "text": "when evidence showed that trans fat increased heart "
                        "disease risk, independent scientists globally said it",
                "start": 102.8, "end": 110.9,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:21427742", "PMID:26268692"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The systematic review and meta-analysis of "
                         "industrial and ruminant trans fatty acids and "
                         "coronary heart disease supports the premise of the "
                         "analogy.",
            },
            {
                "text": "If vaccines were causing increased cancer rates, "
                        "independent researchers worldwide would say so",
                "start": 83.8, "end": 89.7,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A claim about how science behaves, not about health. "
                         "No study could test it as stated, so NOT_VERIFIABLE. "
                         "Kept as a row because it is the load-bearing "
                         "argument of the video.",
            },
        ],
    },
    {
        "video_id": "v31",
        "topic": "supplements / dermatology",
        "case_tags": ["debunking"],
        "confidence": "medium",
        "notes": "@drmichaelsays, an OBGYN, stitching a supplement-claims "
                 "video and rebutting four claims in turn. Notable for the "
                 "stance step because the refutation is often tonal rather "
                 "than propositional -- 'Really?', 'the hair transplant "
                 "surgeons in Turkey are really shaking in the boots with this "
                 "one' -- so a system that keys on explicit negation would "
                 "read sarcasm as agreement. He also says outright that for "
                 "these claims he does not need to produce studies, which is "
                 "the honest position and the reason three of the four rows "
                 "are INSUFFICIENT_EVIDENCE. This collector's folder carried "
                 "no label.",
        "claims": [
            {
                "text": "Tea tree reduces all acne by 512 percent",
                "start": 16.2, "end": 22.3,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:2145499", "PMID:27416314"],
                "confidence": "medium",
                "notes": "Tea tree oil does have a measured effect on acne, "
                         "and that is what contradicts the claim: the "
                         "comparative trial against benzoyl peroxide reports a "
                         "modest effect with slower onset, nothing like a "
                         "512% reduction -- a figure that cannot describe a "
                         "reduction at all, as the speaker points out himself.",
            },
            {
                "text": "Macker [maca] root. Three times your pencil size in "
                        "30 days",
                "start": 46.7, "end": 50.7,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Nothing retrieved tests maca root against genital "
                         "size. Refuted by incredulity rather than by "
                         "evidence, which is a stance-detection case as much "
                         "as a verdict one.",
            },
            {
                "text": "Beat root [beetroot] spikes muscle growth in 30 days",
                "start": 54.8, "end": 57.8,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Refuted with a joke about Ronnie Coleman. Nothing "
                         "retrieved tests beetroot against muscle growth over "
                         "30 days.",
            },
            {
                "text": "Batana oil adds three inches of hair to your scalp ... "
                        "Reverses you're balding completely",
                "start": 69.6, "end": 76.5,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Nothing retrieved tests batana oil for hair growth "
                         "or androgenetic alopecia.",
            },
            {
                "text": "It [tea tree] can actually be quite damaging to your "
                        "skin if you apply it directly and don't dilute it "
                        "down",
                "start": 41.7, "end": 45.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:31780027"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The speaker's own positive claim. The systematic "
                         "review of essential oils as topical anti-infectives "
                         "was retrieved but nothing readable in it addresses "
                         "undiluted tea tree oil causing skin damage.",
            },
        ],
    },
    {
        "video_id": "v33",
        "topic": "appetite / circadian rhythm",
        "case_tags": ["accurate"],
        "confidence": "high",
        "notes": "@footdocdana explaining why morning hunger is low, in four "
                 "sentences. The most straightforwardly accurate video in the "
                 "bundle: every claim maps onto the circadian-appetite "
                 "literature, there is no product, and the mechanism is "
                 "described without overreach. Worth keeping as a "
                 "NO_MISINFO anchor -- a set made only of hard cases cannot "
                 "measure false positives. This collector's folder carried no "
                 "label.",
        "claims": [
            {
                "text": "Your body has a natural circadian rhythm that makes "
                        "hunger hit its lowest point around 8AM",
                "start": 8.4, "end": 13.3,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:32463976", "PMID:30232416"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Supported in direction by the circadian "
                         "substrate-oxidation and ghrelin literature. The "
                         "specific clock time of 8 a.m. is more precise than "
                         "the retrieved studies state, which is why this is "
                         "medium rather than high confidence.",
            },
            {
                "text": "Growl in [ghrelin], your hunger hormone is naturally "
                        "suppressed in the morning hours",
                "start": 13.3, "end": 17.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:30232416"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Directly supported: ghrelin is shown to be governed "
                         "by the endogenous circadian system in humans. Note "
                         "the transcript renders 'ghrelin' as 'growl in' -- a "
                         "transcription artefact worth keeping for the "
                         "extraction track, since a claim extractor reading "
                         "the raw transcript loses the hormone's name.",
            },
            {
                "text": "hunger and appetite peak later in the evening",
                "start": 17.0, "end": 21.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:32463976", "PMID:41622791"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Consistent with the chrononutrition literature on "
                         "diurnal appetite variation.",
            },
            {
                "text": "poor sleep messes with your hunger hormones "
                        "completely",
                "start": 23.9, "end": 27.5,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:30232416"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The retrieved paper covers circadian misalignment "
                         "rather than sleep deprivation as such, and "
                         "'completely' is not a testable magnitude.",
            },
        ],
    },
    {
        "video_id": "v34",
        "topic": "cancer / diet",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "Sixteen seconds, one piece of advice, aimed squarely at "
                 "people who have just been diagnosed with cancer: cut out "
                 "processed sugar to starve the cancer. The shortest video in "
                 "the bundle and among the most consequential, and it ends "
                 "CANNOT_RECOGNIZE because glucose restriction as cancer "
                 "therapy is still at the stage of proposed research "
                 "frameworks rather than tested in patients. Section 7 says "
                 "untested is insufficient, not false. This is the clearest "
                 "argument in the whole set for a materiality signal separate "
                 "from the verdict: advice this dangerous should reach a human "
                 "reviewer whatever the evidence column says, and section 9's "
                 "materiality note is the right place for it. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "the first word of advice I would give is to cut out "
                        "any form of processed sugar. Starving cancer to death "
                        "by removing one food in particular, refined sugars, "
                        "could end up saving your life",
                "start": 5.2, "end": 15.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:39639257", "PMID:40428567"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The retrieved work is a proposed clinical research "
                         "framework for ketogenic metabolic therapy in "
                         "glioblastoma and a review of diet in cancer "
                         "development and management -- that is, the question "
                         "is open and being formalised, not answered. Nothing "
                         "tests whether removing refined sugar starves a "
                         "tumour or extends survival. Flagged for review on "
                         "materiality rather than on verdict.",
            },
        ],
    },
    {
        "video_id": "v35",
        "topic": "radiation / food folklore",
        "case_tags": ["missing_evidence"],
        "confidence": "high",
        "notes": "@healingartsapothecary retelling the Hiroshima miso story "
                 "and concluding that you should have miso soup before an "
                 "X-ray. An instructive INSUFFICIENT_EVIDENCE case rather "
                 "than an empty one: there really is a radioprotection study, "
                 "and it is in mice, so the directness test in section 7 "
                 "decides the row. The speaker is also careful in one respect "
                 "worth noting -- he says explicitly that it did not work as "
                 "treatment after exposure -- which makes this a claim with "
                 "a real qualifier that must be preserved per section 4. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "Japanese doctors during World War 2 accidentally "
                        "discovered that miso soup was a preventative and a "
                        "way to stop radiation exposure and radiation "
                        "poisoning",
                "start": 0.0, "end": 11.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A historical claim about a wartime discovery. "
                         "Nothing retrieved documents it; the firsthand "
                         "accounts the speaker appeals to are not in the "
                         "biomedical literature.",
            },
            {
                "text": "they discovered that miso soup carried binders that "
                        "would actually remove any form of radiation from the "
                        "human body or the bloodstream",
                "start": 36.4, "end": 44.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:11833659"],
                "contradicting": [],
                "confidence": "high",
                "notes": "There is a real radioprotection study -- "
                         "'Radioprotective effects of miso (fermented soy bean "
                         "paste) against radiation in B6C3F1 mice' -- but it "
                         "is in mice, and it reports radioprotection rather "
                         "than binders removing radiation from the "
                         "bloodstream. Fails directness twice over: wrong "
                         "species and wrong mechanism.",
            },
            {
                "text": "it demonstrated the potential for miso to prevent "
                        "radiation poisoning ... So why not have a bowl of "
                        "miso soup before getting any kind of X-rays?",
                "start": 49.2, "end": 57.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:11833659"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The claim is hedged to 'potential', which the mouse "
                         "study arguably supports, but the recommendation it "
                         "carries -- miso before diagnostic X-rays -- is not "
                         "tested by anything retrieved.",
            },
        ],
    },
    {
        "video_id": "v36",
        "topic": "supplements / minerals",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "@healingartsapothecary on getting '102 minerals' from "
                 "burdock root, Irish moss, bladderwrack and moringa, ending "
                 "in 'we can buy it'. Every claim here is sweeping and "
                 "unevidenced, and the video still comes out "
                 "CANNOT_RECOGNIZE, which is the sharpest illustration in the "
                 "set of the gap described in the PR: a claim can be plainly "
                 "false and still not be CONTRADICTED, because no researcher "
                 "has bothered to test it. The Linus Pauling attribution row "
                 "is the starkest -- 'every sickness, every disease and every "
                 "ailment' traced to mineral deficiency is contradicted by the "
                 "existence of infectious and genetic disease, but no "
                 "retrieved paper states that, and section 7 does not permit "
                 "filling the gap from background knowledge. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "our entire physical makeup is comprised of 102 of "
                        "these minerals in trace amounts",
                "start": 6.5, "end": 14.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing retrieved states an element count for the "
                         "human body. A reviewer with a biochemistry "
                         "reference should expect to correct the figure.",
            },
            {
                "text": "according to two-time Nobel Prize winning chemist Dr. "
                        "Linus Pauling, you can trace every sickness, every "
                        "disease and every ailment to a mineral deficiency. I "
                        "happen to agree with them",
                "start": 14.8, "end": 25.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "Recorded as ENDORSES, not QUOTES: he attributes it "
                         "to Pauling and then says he agrees, which is "
                         "adopting the claim. Nothing retrieved tests it or "
                         "documents the attribution. THE ROW WHERE THE RUBRIC "
                         "IS MOST VISIBLY TOO CAUTIOUS -- a sweeping claim "
                         "refuted by the whole of infectious and genetic "
                         "medicine still lands on insufficient because no "
                         "paper bothers to say so.",
            },
            {
                "text": "Burdock root contains all 102 of those minerals",
                "start": 25.9, "end": 32.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "No composition analysis of burdock root was "
                         "retrieved.",
            },
            {
                "text": "Iris Seamos [Irish moss] is a gelatinous sea algae "
                        "that contains 92 of those 102 minerals, and it's "
                        "actually in concentrated amounts",
                "start": 32.1, "end": 41.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "No composition analysis retrieved.",
            },
            {
                "text": "moranga [moringa] powder ... has just about the "
                        "highest concentration of vitamins of any plant on the "
                        "earth",
                "start": 49.1, "end": 58.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:39759372", "PMID:25190880"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Moringa leaf composition studies were retrieved and "
                         "they do profile vitamins and minerals, but none "
                         "ranks moringa against all other plants, which is "
                         "what the superlative claims.",
            },
        ],
    },
    {
        "video_id": "v37",
        "topic": "diabetes / supplements",
        "case_tags": ["clearly_false"],
        "confidence": "high",
        "notes": "@healingartsapothecary claiming Ozempic contains berberine, "
                 "that berberine is 'nature's metformin', and inviting people "
                 "with diabetes to talk to their doctor about getting off "
                 "prescription medication -- while selling barberry capsules "
                 "and extract. MISINFO on a cleanly contradicted "
                 "pharmacology claim, and the most dangerous advice in the "
                 "bundle after v34. A good case for the set because the video "
                 "mixes a flatly false premise with a partially supported "
                 "claim: berberine really does lower glucose in trials, which "
                 "is what makes the false premise persuasive. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "there's an ingredients in the drug ozembic "
                        "[Ozempic] called berberine",
                "start": 0.0, "end": 5.0,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:26308095", "PMID:40281304"],
                "confidence": "high",
                "notes": "Flatly false and the claim that makes this video "
                         "MISINFO. Semaglutide is an acylated GLP-1 analogue, "
                         "a peptide, as the discovery paper sets out; "
                         "berberine is a plant alkaloid and is not a "
                         "component of it. The video's entire argument rests "
                         "on this.",
            },
            {
                "text": "berberine is actually nature's metformin",
                "start": 19.0, "end": 28.0,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:34956436", "PMID:23118793"],
                "contradicting": ["PMID:34407851"],
                "confidence": "medium",
                "notes": "Berberine does improve glycaemic measures in "
                         "randomised trials, which is the supporting side. The "
                         "comparative analysis of oral insulin sensitizers "
                         "places metformin and berberine differently, so "
                         "equating them is not supported. MIXED rather than "
                         "CONTRADICTED because the glucose-lowering half is "
                         "real.",
            },
            {
                "text": "the benefits of berberine, barberry are so "
                        "astounding that even doctors are getting off the "
                        "drug [metformin]",
                "start": 33.1, "end": 38.5,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "An unquantified claim about what unnamed doctors "
                         "do. No study could test it as stated.",
            },
            {
                "text": "berberine is amazing because it has a multitude of "
                        "health benefits, one of which is it helps to "
                        "eliminate arterial plaque",
                "start": 38.5, "end": 44.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A search for berberine against atherosclerosis or "
                         "arterial plaque regression returned nothing at all; "
                         "the empty search is in evidence_cache/.",
            },
        ],
    },
    {
        "video_id": "v39",
        "topic": "nutrition / multiple myths",
        "case_tags": ["debunking", "uncertain_science"],
        "confidence": "medium",
        "notes": "@jacbfoods refuting five nutrition myths in 86 seconds, "
                 "naming the composition fallacy explicitly. Pairs with v19 "
                 "and v11 as the third seed-oil video in the set, and with "
                 "v42 which argues the opposite. Comes out DEBUNKING on the "
                 "seed-oil row. Note that his own position on saturated fat "
                 "('fine to eat in moderation ... probably not optimal to "
                 "increase to extreme amounts') is more carefully hedged than "
                 "v11's 'totally fine', and the hedging is what moves it from "
                 "MIXED to a claim the evidence can live with. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "seed oils are unhealthy, leads to inflammation, "
                        "heart disease, obesity",
                "start": 3.6, "end": 7.4,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:25161045", "PMID:37513547"],
                "confidence": "medium",
                "notes": "Same myth and same contradicting evidence as v19: "
                         "dietary linoleic acid is inversely associated with "
                         "coronary heart disease risk in a dose-response "
                         "meta-analysis of prospective cohorts.",
            },
            {
                "text": "that carbs make you fat",
                "start": 21.4, "end": 23.0,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Searches for isocaloric low-carbohydrate against "
                         "low-fat comparisons returned trials in specific "
                         "clinical populations rather than a test of the "
                         "general claim, so nothing retrieved settles it.",
            },
            {
                "text": "butter should be eaten as a snack and it is healthy "
                        "for you to do so",
                "start": 36.1, "end": 38.4,
                "stance": "REFUTES", "verdict": "MIXED",
                "supporting": ["PMID:40416032"],
                "contradicting": ["PMID:32428300"],
                "confidence": "medium",
                "notes": "The same saturated-fat split as v11: Cochrane finds "
                         "benefit from reducing saturated fat, a 2025 "
                         "meta-analysis finds none. The evidence does not "
                         "settle whether eating butter as a snack is healthy, "
                         "so the refutation lands on MIXED.",
            },
            {
                "text": "You can gain fat in a calorie deficit due to "
                        "hormonal problems or endocrine dysfunction",
                "start": 46.9, "end": 50.0,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing retrieved tests this. The speaker's "
                         "counter-argument is from first principles ('you are "
                         "still bound to the laws of physics') rather than "
                         "from a study, which is a reasonable argument and "
                         "still not retrievable evidence.",
            },
            {
                "text": "that vegetables are bad for you",
                "start": 58.7, "end": 62.6,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:28338764", "PMID:33641343"],
                "confidence": "high",
                "notes": "Contradicted by the systematic review and "
                         "dose-response meta-analysis of fruit and vegetable "
                         "intake against cardiovascular disease, total cancer "
                         "and all-cause mortality, and by the two-cohort "
                         "mortality analysis.",
            },
        ],
    },
    {
        "video_id": "v40",
        "topic": "hydration / supplements",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A 24-second sales-funnel opener (@nutritiouslyeasy): day one "
                 "of a 30-day tips series, recommending electrolytes in water "
                 "every morning. Short, and a good test of how the rubric "
                 "handles a claim whose first half is supported and whose "
                 "second half is a 'long laundry list of health benefits' with "
                 "no content. This collector's folder carried no label.",
        "claims": [
            {
                "text": "Electrolytes help you properly retain fluid, keeping "
                        "you way more hydrated",
                "start": 12.5, "end": 16.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:34578811", "PMID:9760324"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The Beverage Hydration Index work shows electrolyte "
                         "content influences fluid retention, and the sodium "
                         "rehydration trial supports the mechanism. Both are "
                         "in exercise-rehydration settings rather than healthy "
                         "people adding electrolytes to morning water, which "
                         "is a directness limitation.",
            },
            {
                "text": "So think better, energy levels, immune health, and "
                        "no more headaches",
                "start": 16.0, "end": 19.5,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Three separate outcomes asserted in one breath with "
                         "no mechanism and no magnitude. Nothing retrieved "
                         "tests electrolyte supplementation against energy, "
                         "immune function or headaches in this population. "
                         "Kept as one row because it is one list in one "
                         "clause, not three developed claims.",
            },
        ],
    },
    {
        "video_id": "v41",
        "topic": "hand hygiene / food safety",
        "case_tags": ["accurate"],
        "confidence": "high",
        "notes": "A food-service handwashing instructional (@partstown, a "
                 "catering-equipment supplier). Procedural rather than "
                 "persuasive, and accurate. Included deliberately as a second "
                 "NO_MISINFO anchor alongside v33: the set needs content a "
                 "classifier should leave alone, or false-positive rate cannot "
                 "be measured. Also the clearest case in the bundle of a video "
                 "whose claims are instructions -- 'scrub for 20 seconds' is "
                 "an imperative that carries an implicit efficacy assertion, "
                 "and it is recorded as the assertion. This collector's "
                 "folder carried no label.",
        "claims": [
            {
                "text": "Scrub your entire hands up to just above your wrists "
                        "for 20 seconds",
                "start": 12.5, "end": 17.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:25836392"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The quantification study reports a 1.7 log CFU "
                         "reduction for a 20-second wash with soap against 1.0 "
                         "log for a 5-second wash without, so the 20-second "
                         "duration with soap is the better-supported "
                         "procedure. Medium confidence because the same paper "
                         "finds some comparisons not statistically "
                         "significant.",
            },
            {
                "text": "Use a piece of paper towel to turn off the faucet",
                "start": 26.1, "end": 28.9,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Standard food-safety practice, but nothing "
                         "retrieved tests recontamination from taps or the "
                         "paper-towel step specifically.",
            },
        ],
    },
    {
        "video_id": "v32",
        "topic": "obesity pharmacotherapy / GLP-1",
        "case_tags": ["debunking", "uncertain_science"],
        "confidence": "medium",
        "notes": "A stitch with two speakers who disagree: roughly the first "
                 "95 seconds is an influencer arguing against GLP-1 drugs, "
                 "then @drspencer rebuts her point by point. The most "
                 "important video in the set for the stance step, because "
                 "stance cannot be read off the words alone -- the same video "
                 "contains assertions from both sides, and which speaker is "
                 "talking decides the label. One row is deliberately UNCLEAR: "
                 "the weight-regain claim is the influencer's, and the doctor "
                 "never contests it, so neither REFUTES nor ENDORSES fits the "
                 "video as a whole. Section 5 names 'two speakers with "
                 "different views' as an UNCLEAR trigger. Comes out DEBUNKING. "
                 "This collector's folder carried no label.",
        "claims": [
            {
                "text": "If you go to get off of it, you gain all the weight "
                        "back",
                "start": 1.7, "end": 5.4,
                "stance": "UNCLEAR", "verdict": "SUPPORTED",
                "supporting": ["PMID:35441470", "PMID:41399474"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Stance UNCLEAR because this is the influencer's "
                         "claim and the doctor never addresses it, so the "
                         "video takes no position. The verdict is the "
                         "interesting part: her claim is the best-supported "
                         "one in the exchange. The STEP 1 trial extension "
                         "found weight regain after semaglutide withdrawal, "
                         "and a 2025 meta-analysis documents metabolic rebound "
                         "after discontinuation. 'All the weight' overstates "
                         "it -- STEP 1 participants regained about two thirds "
                         "-- hence medium confidence.",
            },
            {
                "text": "Ozympic [Ozempic] kills hunger. And that's one of the "
                        "reasons it's causing people to lose weight",
                "start": 28.5, "end": 32.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:28266779", "PMID:40466247"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The one claim both speakers accept, so ENDORSES is "
                         "safe. Directly supported: the trial of once-weekly "
                         "semaglutide measured effects on appetite, energy "
                         "intake and control of eating.",
            },
            {
                "text": "We don't know what it does to the microbiome ... If "
                        "we destroy our microbiome, you destroy your body and "
                        "you destroy your mind",
                "start": 39.6, "end": 55.6,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:40284168"],
                "confidence": "medium",
                "notes": "Refuted by the doctor and contradicted by the "
                         "evidence: a systematic review of thirty-eight "
                         "studies describes GLP-1 analogues' effects on gut "
                         "microbiota composition, richness and diversity, with "
                         "liraglutide promoting beneficial genera. 'We don't "
                         "know' is no longer true. Medium confidence because "
                         "much of that review is animal work.",
            },
            {
                "text": "a fasting lifestyle will give you the same weight "
                        "loss result and save you money as ozempic",
                "start": 78.2, "end": 89.6,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:38740993", "PMID:40961952"],
                "confidence": "medium",
                "notes": "The SELECT long-term analysis and the STEP UP phase "
                         "3b trial put semaglutide weight loss well above what "
                         "fasting achieves, which contradicts equivalence. A "
                         "search for intermittent-fasting weight-loss "
                         "magnitude returned nothing, so the fasting side of "
                         "the comparison rests on the absence of comparable "
                         "results rather than on a retrieved number.",
            },
            {
                "text": "we should look at hard outcomes meaning improved "
                        "cardiovascular health. We reduce risk of heart "
                        "attacks",
                "start": 121.8, "end": 130.3,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39181597", "PMID:38796653"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The doctor's own claim, supported by the SELECT "
                         "cardiovascular and kidney outcome analyses.",
            },
            {
                "text": "You get less than a 10% total body weight loss with "
                        "any type of fasting ... Whereas these medicines we're "
                        "looking at 15 to 20 or higher percent total body "
                        "weight loss",
                "start": 147.6, "end": 159.7,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:38740993", "PMID:40961952"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The drug half of the comparison is well supported. "
                         "The 'less than 10% with any type of fasting' half is "
                         "not backed by anything retrieved, so a reviewer "
                         "could reasonably split this row in two and mark the "
                         "fasting half insufficient.",
            },
        ],
    },
    {
        "video_id": "v42",
        "topic": "nutrition / dietary fat",
        "case_tags": ["clearly_false"],
        "confidence": "high",
        "notes": "The fourth and final seed-oil video, and the one that "
                 "argues the opposite of v11, v19 and v39. MISINFO: the "
                 "inflammation claim is contradicted head-on by a "
                 "meta-analysis of randomised trials. Structurally "
                 "interesting because the argument is built out of "
                 "processing steps (hexane, heat, sodium hydroxide, bleaching) "
                 "where individual factual fragments are true or near-true and "
                 "the health conclusion drawn from them is not -- the same "
                 "shape as v27. These four videos together are the most "
                 "valuable cluster in the set: one topic, four creators, "
                 "labels spanning MISINFO, DEBUNKING and NO_MISINFO, which is "
                 "exactly what section 14 means by covering the hard cases on "
                 "purpose.",
        "claims": [
            {
                "text": "What are the most harmful foods that people "
                        "constantly eat? Seed oils",
                "start": 0.0, "end": 3.1,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:25161045", "PMID:37513547"],
                "confidence": "medium",
                "notes": "The dose-response meta-analysis of prospective "
                         "cohorts finds dietary linoleic acid inversely "
                         "associated with coronary heart disease risk, which "
                         "contradicts seed oils being the most harmful food "
                         "people eat.",
            },
            {
                "text": "you de-gum it with hexane, which is a known "
                        "neurotoxin",
                "start": 13.0, "end": 17.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39536137", "PMID:11724159"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Deliberately labelled SUPPORTED. n-hexane really is "
                         "a neurotoxin -- occupational exposure causes "
                         "peripheral neuropathy, as the toxicity review and "
                         "the automotive-technician cluster report show. The "
                         "claim as stated is true; the inference the video "
                         "draws from it, that refined seed oil is therefore "
                         "harmful to eat, is a separate claim and is the one "
                         "the evidence contradicts. A reviewer should read "
                         "this row next to the inflammation row -- this is how "
                         "true fragments carry a false conclusion.",
            },
            {
                "text": "You need to deodorize it with sodium hydroxide, "
                        "which is a very powerful carcinogen",
                "start": 22.0, "end": 26.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A search for sodium hydroxide toxicity and "
                         "carcinogenicity returned nothing at all; the empty "
                         "search is in evidence_cache/. Sodium hydroxide is "
                         "handled as a corrosive rather than a carcinogen, but "
                         "no retrieved source says so, so this stays "
                         "insufficient rather than contradicted. Another row a "
                         "reviewer with a toxicology reference should expect "
                         "to upgrade.",
            },
            {
                "text": "These are pro-inflammatory that cause massive amount "
                        "of inflammation in the body",
                "start": 45.4, "end": 49.6,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:28752873", "PMID:22889633"],
                "confidence": "high",
                "notes": "The claim that makes this video MISINFO, and the "
                         "best-evidenced contradiction in the bundle. The "
                         "systematic review and meta-analysis of randomised "
                         "trials found no significant effect of higher "
                         "linoleic acid intake on tumour necrosis factor, "
                         "interleukin-6, adiponectin or monocyte "
                         "chemoattractant protein 1, and a second systematic "
                         "review of randomised trials in healthy people agrees.",
            },
            {
                "text": "in your kitchen, you need five oils. You need a "
                        "grass-fed butter, butter, grass-fed tallow, coconut "
                        "oil, and an olive oil",
                "start": 51.9, "end": 59.3,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:32428300"],
                "confidence": "medium",
                "notes": "A recommendation rather than a mechanism claim, and "
                         "nothing retrieved tests this specific set of five "
                         "fats. Cited against is the Cochrane review on "
                         "reducing saturated fat, since four of the five "
                         "recommended fats are saturated-fat-dominant, but "
                         "that bears on the recommendation rather than "
                         "testing it.",
            },
        ],
    },
    {
        "video_id": "v43",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A long-form practical demonstration of the Earth's "
                 "curvature, renting a high floor to watch a boat hull "
                 "reappear. Science communication, no health content. "
                 "Collectors filed it under NO_MISINFO.",
        "claims": [],
    },
    {
        "video_id": "v44",
        "topic": "water safety / infection",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "A narrated scare story: a tourist drinks Antarctic glacial "
                 "water and dies three days later from ancient bacteria and "
                 "parasites humans have no immunity to, ending with a prompt "
                 "to search TikTok for the clip. Collectors filed it under "
                 "NO_MISINFO, which the section 9 rules do not reproduce -- it "
                 "comes out CANNOT_RECOGNIZE, because the death is an "
                 "unverifiable anecdote and nothing retrievable tests the "
                 "ancient-pathogen claim. Recorded as a collector "
                 "disagreement.",
        "claims": [
            {
                "text": "This girl makes the last mistake of her life, "
                        "drinking this clear glacial water in Antarctica. And "
                        "three days later, she was urgently taken to the "
                        "hospital, where she died",
                "start": 0.0, "end": 9.6,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "An unidentified individual, no date, no location, no "
                         "cause of death, and the video itself switches the "
                         "subject's gender mid-story ('what happened to him'). "
                         "There is no version of this a study could test.",
            },
            {
                "text": "you can see ancient bacteria and parasites there, "
                        "which are also older than those very dinosaurs, and "
                        "people just don't have immunity from these ancient "
                        "organisms",
                "start": 43.1, "end": 51.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A search for ancient microorganisms in glacial ice "
                         "and permafrost and their viability returned nothing "
                         "at all; the empty search is in evidence_cache/. The "
                         "claim also contains a false premise about glacier "
                         "ages that is geological rather than medical and so "
                         "is not a row here.",
            },
        ],
    },
    {
        "video_id": "v45",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A game-theory thought experiment about a million people "
                 "competing to win. No health content. Collectors filed it "
                 "under NO_MISINFO.",
        "claims": [],
    },
    {
        "video_id": "v46",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "An economics explainer on the seven stages by which global "
                 "reserve currencies collapse. No health content. Collectors "
                 "filed it under NO_MISINFO.",
        "claims": [],
    },
    {
        "video_id": "v47",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A natural-history explainer on lobsters being "
                 "'biologically immortal' and why they die anyway. Biology, "
                 "not human health, so no checkable health assertion. "
                 "Collectors filed it under NO_MISINFO. Borderline: a "
                 "reviewer could argue senescence claims are health-adjacent, "
                 "and this is in the blind subset, so the disagreement will be "
                 "measured.",
        "claims": [],
    },
    {
        "video_id": "v48",
        "topic": "none (non-health)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A two-person conversation disputing the Great Wall of "
                 "China's stated length. History, no health content. "
                 "Collectors filed it under MISINFO, which is plausible for "
                 "the historical claims but outside this dataset's scope; the "
                 "section 9 rules give CANNOT_RECOGNIZE. Recorded as a "
                 "collector disagreement.",
        "claims": [],
    },
    {
        "video_id": "v49",
        "topic": "vaccines / immunology",
        "case_tags": ["accurate", "neutral_discussion"],
        "confidence": "medium",
        "notes": "An interview with a pharmacology and immunology PhD "
                 "explaining how vaccines generate antibodies. The most "
                 "valuable row in this video is the last one: asked whether a "
                 "strong vaccine reaction predicts how badly you would have "
                 "had COVID, the scientist says he does not know of data "
                 "either way, and the interviewer praises him for it. That is "
                 "a speaker explicitly declining to take a position, which is "
                 "what section 5's NEUTRAL is for, sitting on top of a "
                 "section 7 INSUFFICIENT_EVIDENCE verdict -- the two "
                 "abstentions agreeing. Collectors filed it under NO_MISINFO, "
                 "which agrees.",
        "claims": [
            {
                "text": "You get the injection in your arm ... Most often "
                        "little pieces of the pathogen",
                "start": 18.6, "end": 28.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:22481438"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "An accurate description of subunit vaccine "
                         "principles. The retrieved immunological-memory "
                         "review supports the mechanism in general terms "
                         "rather than this sentence specifically.",
            },
            {
                "text": "before COVID ever existed, you had in your body T "
                        "cells and B cells that recognized COVID ... all of "
                        "those cells were randomly generated in advance",
                "start": 76.0, "end": 93.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:22481438", "PMID:34126625"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The pre-existing randomly generated repertoire is "
                         "standard immunology and the retrieved papers are "
                         "consistent with it, but neither tests this claim "
                         "head-on, so medium confidence.",
            },
            {
                "text": "that same process happens whether you've been "
                        "[infected] with a virus. It still takes the piece of "
                        "virus and goes to the lymph node and activates the B "
                        "and T cells",
                "start": 124.3, "end": 130.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:22481438"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The equivalence between infection-induced and "
                         "vaccine-induced priming, which is the video's "
                         "central point.",
            },
            {
                "text": "If the severity of your vaccine response is "
                        "predictive [of how severe COVID would have been]",
                "start": 141.5, "end": 146.7,
                "stance": "NEUTRAL", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "The best NEUTRAL example in the set. The scientist "
                         "says in terms 'I don't know of data to say one way "
                         "or the other', so he discusses the claim without "
                         "taking a position -- section 5's NEUTRAL, not "
                         "UNCLEAR, because there is nothing ambiguous about "
                         "his meaning. Nothing retrieved tests it either, so "
                         "the verdict abstains for the same reason the speaker "
                         "does.",
            },
        ],
    },
    {
        "video_id": "v50",
        "topic": "smoking / respiratory health",
        "case_tags": ["accurate"],
        "confidence": "medium",
        "notes": "A 32-second clip on smoke inhalation from tobacco, "
                 "marijuana and hookah damaging the lungs. Short and "
                 "accurate, with the transcript garbling 'pneumothoraces' as "
                 "'pneumothoracies' -- another transcription artefact worth "
                 "keeping for the extraction track. Collectors filed it under "
                 "NO_MISINFO, which agrees.",
        "claims": [
            {
                "text": "it makes your lungs more susceptible to "
                        "pneumothoracies [pneumothoraces] ... This makes your "
                        "lungs decreased in terms of its function. Yeah, even "
                        "with marijuana",
                "start": 11.2, "end": 26.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:37728136"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The systematic review of marijuana smoking and the "
                         "respiratory system supports both halves, including "
                         "the specific point that cannabis smoke is not benign "
                         "for the lungs. Medium confidence because the claim "
                         "bundles three exposures (tobacco, marijuana, hookah) "
                         "and the retrieved review covers one.",
            },
        ],
    },
    {
        "video_id": "v51",
        "topic": "cannabis / cardiovascular health",
        "case_tags": ["accurate"],
        "confidence": "medium",
        "notes": "A heart surgeon on regular marijuana smoking and coronary "
                 "risk, explicitly answering the 'it's natural so it must be "
                 "safe' argument. He gives a quantified risk estimate, which "
                 "is unusual in this bundle and makes the claim properly "
                 "checkable. Collectors filed it under NO_MISINFO, which "
                 "agrees.",
        "claims": [
            {
                "text": "smoking marijuana regularly increases your risk of "
                        "coronary disease and acute heart attack by 1.3 to two "
                        "times those that don't smoke marijuana regularly",
                "start": 19.4, "end": 33.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:40686207"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The cohort of veterans with coronary artery disease "
                         "supports an association between cannabis smoking and "
                         "cardiovascular events. Medium confidence because "
                         "nothing retrieved pins the effect size to the 1.3-2x "
                         "range he quotes.",
            },
            {
                "text": "That's the same increased risk as high blood pressure "
                        "or increased cholesterol",
                "start": 33.0, "end": 38.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A comparative magnitude claim across three risk "
                         "factors. Nothing retrieved puts them on the same "
                         "scale, so the comparison is untested.",
            },
            {
                "text": "I have operated on multiple patients over the years "
                        "that smoke marijuana regularly and I can tell you "
                        "that their lungs are totally black ... these are "
                        "folks that have never smoked a cigarette in their "
                        "lives",
                "start": 38.8, "end": 55.0,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Clinical anecdote from his own operating theatre. "
                         "Not the kind of claim a study tests, and recorded as "
                         "NOT_VERIFIABLE rather than dismissed, since "
                         "unverifiable testimony from a credible speaker is "
                         "exactly what makes health content persuasive.",
            },
        ],
    },
    {
        "video_id": "v52",
        "topic": "glycaemic control / activity",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A 64-year-old creator recommending ten minutes of light "
                 "movement after dinner, with a weight-loss credential and an "
                 "'I'm not AI' disclaimer. The mechanism she describes is "
                 "real and well studied, which makes this a NO_MISINFO video "
                 "built on a sales-style hook. Collectors filed it under "
                 "NO_MISINFO, which agrees.",
        "claims": [
            {
                "text": "10 minutes after your meal, glucose starts flooding "
                        "your bloodstream. If you sit down, that sugar just "
                        "sits there forcing your body to pump out excess "
                        "insulin",
                "start": 16.7, "end": 27.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:22374636", "PMID:36728338"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Breaking up prolonged sitting does reduce "
                         "postprandial glucose and insulin responses, which is "
                         "the claim's substance. The 'ten minutes' timing is "
                         "more precise than the trials specify.",
            },
            {
                "text": "if you keep your legs moving, just 15 chair squats "
                        "or calf raises while washing dishes or march in place "
                        "your muscles will act like a sponge and soak up that "
                        "sugar",
                "start": 27.6, "end": 39.3,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:27208318", "PMID:35147898"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Brief bouts of light walking or simple resistance "
                         "activity improve glucose handling in type 2 "
                         "diabetes, which supports the mechanism. The specific "
                         "prescription of 15 chair squats is not itself "
                         "tested.",
            },
        ],
    },
    {
        "video_id": "v53",
        "topic": "dermatology / hydration myths",
        "case_tags": ["accurate", "debunking"],
        "confidence": "medium",
        "notes": "A dermatologist correcting four common beliefs. Contains "
                 "the set's neatest logical wrinkle: he claims there is no "
                 "evidence-based daily water target, and a claim that "
                 "asserts an absence of evidence cannot be SUPPORTED by "
                 "retrieving nothing -- absence of evidence is the verdict "
                 "INSUFFICIENT_EVIDENCE, which is not the same as agreeing "
                 "with him. That row is flagged in the PR description as a "
                 "case the section 7 vocabulary does not cover. It also "
                 "corroborates this annotator's own INSUFFICIENT_EVIDENCE "
                 "verdicts on the hydration claims in v07 and v12. Collectors "
                 "filed it under NO_MISINFO, which agrees.",
        "claims": [
            {
                "text": "Washing your hands with antibacterial soap doesn't "
                        "present any advantage over using regular soap for "
                        "regular hand washing",
                "start": 11.8, "end": 21.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:17683018"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The retrieved review of consumer antibacterial "
                         "soaps supports the claim and also the speaker's "
                         "follow-up about antibiotic resistance concerns "
                         "driving US regulatory changes.",
            },
            {
                "text": "This idea of just drink more water to have nice "
                        "skin, total BS. Drinking excessive amounts of water "
                        "will not make your skin look different",
                "start": 50.0, "end": 64.0,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing retrieved tests water intake against skin "
                         "appearance in people with normal fluid balance. Note "
                         "that he qualifies the claim carefully himself "
                         "('assuming normal fluid balance'), which per section "
                         "4 has to be preserved in the claim text.",
            },
            {
                "text": "we don't know like what the optimal amount of water "
                        "a standard adult human should be drinking every day "
                        "is ... three liters or eight eight ounce glasses or "
                        "what like that's not evidence-based",
                "start": 85.5, "end": 105.0,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A claim ABOUT the absence of evidence. Retrieving "
                         "nothing is consistent with him being right, but "
                         "section 7's INSUFFICIENT_EVIDENCE means 'we cannot "
                         "say', so the verdict cannot express agreement with a "
                         "negative claim. Independently, this is the third "
                         "video in the set (with v07 and v12) to turn on the "
                         "same hydration-rule evidence gap, from a third "
                         "direction.",
            },
            {
                "text": "Acne is not infectious, it's not something that you "
                        "just wash away, it's a chronic inflammatory condition "
                        "of the skin",
                "start": 142.1, "end": 152.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:27416314"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Consistent with the retrieved review of "
                         "over-the-counter acne treatment, which treats acne "
                         "as an inflammatory condition rather than an "
                         "infection.",
            },
        ],
    },
    {
        "video_id": "v54",
        "topic": "nutrition / nuts",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A dermatologist-adjacent creator arguing nuts and seeds "
                 "are unfairly demonised, citing a University of Michigan "
                 "analysis of 5,800 foods. Comes out CANNOT_RECOGNIZE: the "
                 "study he describes could not be retrieved, and his other "
                 "two statements are an unquantified benefit claim and an "
                 "aphorism. A useful example of a video that is probably "
                 "right and still unjudgeable. Collectors filed it under "
                 "NO_MISINFO.",
        "claims": [
            {
                "text": "when the University of Michigan looked at 5,800 "
                        "foods to see how many minutes they add or take away "
                        "from your life ... there was one category that did "
                        "significantly better than all the others [nuts and "
                        "seeds]",
                "start": 6.3, "end": 30.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A search for nut consumption against all-cause "
                         "mortality and life expectancy returned nothing, and "
                         "the specific Michigan analysis was not retrieved. "
                         "Checkable in principle -- it is a named study -- "
                         "which makes this a retrieval failure rather than an "
                         "evidence gap, and a good test case for the "
                         "retrieval track.",
            },
            {
                "text": "they have so many amazing things for your health, "
                        "but because they're high calorie, people think "
                        "they're unhealthy",
                "start": 39.9, "end": 44.2,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:36904160"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The retrieved review of nuts, energy balance and "
                         "body weight is adjacent but does not test an "
                         "unquantified 'so many amazing things'.",
            },
            {
                "text": "low calorie and healthy aren't the same thing",
                "start": 44.2, "end": 49.2,
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A definitional point rather than an empirical "
                         "claim.",
            },
        ],
    },
    {
        "video_id": "v56",
        "topic": "smoking / cardiovascular health",
        "case_tags": ["accurate"],
        "confidence": "high",
        "notes": "A heart surgeon asked what he avoids, answering smoking, "
                 "with an explicit causal claim about lung cancer and a "
                 "deliberate note that he passes no judgement on smokers. The "
                 "most clearly SUPPORTED video in the whole set, and worth "
                 "having for exactly that reason -- a classifier that flags "
                 "this has a false-positive problem. Collectors filed it "
                 "under NO_MISINFO, which agrees.",
        "claims": [
            {
                "text": "I cannot come up with one single thing that does as "
                        "much damage to every organ in the body as smoking "
                        "cigarettes",
                "start": 6.6, "end": 17.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:30800285", "PMID:36727839"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Supported in substance by the systematic review of "
                         "smoking against lung cancer, COPD, ischaemic heart "
                         "disease and stroke, and by the Mendelian "
                         "randomisation analysis across 24 gastrointestinal "
                         "diseases. The superlative ('one single thing ... as "
                         "much damage') is a ranking nothing retrieved tests, "
                         "hence medium.",
            },
            {
                "text": "the causal relationship with lung cancer",
                "start": 35.8, "end": 38.8,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:11165392", "PMID:30800285"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The meta-analysis of cigarette smoking across major "
                         "histological types of lung cancer. As directly "
                         "supported as a claim in this set gets.",
            },
        ],
    },
    {
        "video_id": "v57",
        "topic": "measles / vaccination",
        "case_tags": ["accurate"],
        "confidence": "medium",
        "notes": "A PBS News segment with a physician on measles "
                 "transmissibility and herd protection. Broadcast journalism "
                 "rather than creator content, which makes it a useful "
                 "out-of-distribution item: the register, pacing and the "
                 "closing PressPass sponsorship read nothing like the rest of "
                 "the bundle. Collectors filed it under NO_MISINFO, which "
                 "agrees.",
        "claims": [
            {
                "text": "it is the most contagious virus that we know",
                "start": 10.1, "end": 23.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:39156354"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Measles' extreme transmissibility is well "
                         "established and the retrieved airborne-transmission "
                         "modelling study is consistent with it, but a "
                         "superlative across all known viruses is a ranking "
                         "claim that nothing retrieved tests.",
            },
            {
                "text": "a person who is shedding breathes out the measles "
                        "virus[,] can leave the room[,] and if a susceptible "
                        "person comes into that room up to two hours later "
                        "they can still inhale the few viral particles ... and "
                        "become infected",
                "start": 23.7, "end": 37.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39156354"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The retrieved study models airborne measles "
                         "transmission in indoor spaces, supporting persistent "
                         "infectious aerosol. The specific two-hour figure is "
                         "standard public-health guidance rather than "
                         "something the retrieved paper states.",
            },
            {
                "text": "there are little babies who could get measles and "
                        "they have high mortality associated with that who "
                        "can't be vaccinated yet ... we create a cocoon of "
                        "protection around them",
                "start": 60.4, "end": 88.0,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:32309885"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The Cochrane review of measles, mumps, rubella and "
                         "varicella vaccines in children was retrieved and "
                         "supports vaccine effectiveness, but nothing "
                         "retrieved tests infant measles mortality or the "
                         "cocooning mechanism specifically.",
            },
        ],
    },
    {
        "video_id": "v58",
        "topic": "home remedies / constipation",
        "case_tags": ["missing_evidence"],
        "confidence": "high",
        "notes": "A 27-second remedy clip: a navel orange coated in cayenne "
                 "and cinnamon, eaten skin and all, said to relieve "
                 "constipation in about five minutes, with the science "
                 "promised in a description that the video does not contain. "
                 "Same shape as v20 and lands the same way. This collector's "
                 "folder carried no label.",
        "claims": [
            {
                "text": "[if you're] constipated, this works every time in "
                        "about five minutes. Grab a navel orange, it must be "
                        "navel ... Generously coat with cayenne pepper and "
                        "cinnamon ... eat the entire wedge, skin and all",
                "start": 0.0, "end": 21.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:35816465", "PMID:41081513"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Nothing tests this preparation, and the "
                         "five-minute onset is implausible on any mechanism. "
                         "Cited as the nearest evidence are the fibre "
                         "supplementation meta-analysis and the British "
                         "Dietetic Association constipation guidelines, which "
                         "support dietary fibre generally -- orange peel is "
                         "fibre -- while testing nothing about this recipe or "
                         "its timing.",
            },
        ],
    },
    {
        "video_id": "v59",
        "topic": "cancer / muscle mass",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A creator arguing that muscle mass built before a cancer "
                 "diagnosis is the best protection during treatment. The "
                 "underlying science is real -- sarcopenia predicts "
                 "chemotherapy toxicity and worse survival -- and the video "
                 "pushes it one step past the evidence by calling muscle your "
                 "'best fighting chance against cancer'. Collectors filed it "
                 "under NO_MISINFO, which the rules reproduce.",
        "claims": [
            {
                "text": "What's your best fighting chance against cancer? "
                        "It's actually muscle mass",
                "start": 0.0, "end": 6.2,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:18539529"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "A superlative ranking muscle mass above all other "
                         "protective factors, including screening and not "
                         "smoking. Nothing retrieved supports that ranking, "
                         "though the sarcopenia literature supports the "
                         "weaker claim underneath it.",
            },
            {
                "text": "chemotherapy drugs deplete skeletal muscle. And if "
                        "you don't start off with a good muscle mass, then "
                        "you're already starting your tank on zero",
                "start": 36.2, "end": 47.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:18539529", "PMID:31842559",
                               "PMID:41206817"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Supported in substance: sarcopenia and sarcopenic "
                         "obesity in cancer patients carry clinical "
                         "implications including treatment toxicity and "
                         "survival. The retrieved work is observational and "
                         "concentrated in gastrointestinal and colorectal "
                         "cancers.",
            },
        ],
    },
    {
        "video_id": "v60",
        "topic": "endocrine disruptors / everyday exposure",
        "case_tags": [],
        "confidence": "high",
        "notes": "A creator advising people not to handle thermal-paper "
                 "receipts because of BPA and BPS skin absorption. One of the "
                 "most useful collector disagreements in the set: filed under "
                 "MISINFO, but the claims are well supported -- thermal "
                 "receipts do carry BPA and BPS and these are absorbed "
                 "through skin, with a measured 25% absorbed dose for BPA "
                 "over 24 hours. The video is also notably measured for this "
                 "genre, saying outright that touching one occasionally 'isn't "
                 "the end of the world'. Recorded as NO_MISINFO against the "
                 "collectors' MISINFO and listed in the PR description.",
        "claims": [
            {
                "text": "These thermal paper receipts contain BPA and BPS",
                "start": 11.8, "end": 15.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:26407846", "PMID:32608004"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Directly supported by measurement studies of "
                         "bisphenol A and bisphenol S levels in thermal paper "
                         "receipts.",
            },
            {
                "text": "These are endocrine disrupting chemicals that can "
                        "actually be absorbed through your skin",
                "start": 15.5, "end": 20.2,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33313651", "PMID:28570582"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The skin-absorption study reports an absorbed dose "
                         "after 24 hours of exposure of 25% for BPA and 17% "
                         "for one alternative, with the handling study "
                         "addressing dermal exposure from thermal paper "
                         "directly. This is the row that makes the collectors' "
                         "MISINFO label look wrong.",
            },
            {
                "text": "if you are touching a lot of receipts ... Don't "
                        "touch the thermal paper receipts and you will "
                        "decrease your exposure",
                "start": 37.8, "end": 44.5,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:28570582"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Follows from the handling study's exposure "
                         "implications. Note what the video does not claim: "
                         "no disease outcome is asserted, which is why nothing "
                         "here is overreach.",
            },
        ],
    },
    {
        "video_id": "v61",
        "topic": "water safety / fluoride",
        "case_tags": ["clearly_false", "uncertain_science"],
        "confidence": "medium",
        "notes": "'Stop drinking water, it is actually quite dangerous' -- "
                 "three claims about tap water (prescription drugs, "
                 "glyphosate, fluoride) ending in a recommendation to drink "
                 "reverse osmosis or distilled water. MISINFO on the fluoride "
                 "claim, and a good example of the directness test doing real "
                 "work: the Chinese studies the speaker invokes are from "
                 "endemic-fluorosis areas with fluoride well above community "
                 "water fluoridation levels, and the meta-analyses restricted "
                 "to fluoridation-relevant concentrations find no association "
                 "with IQ. Generalising from one exposure range to the other "
                 "is the error. The glyphosate claim is genuinely partly true, "
                 "which is what makes the package persuasive. This "
                 "collector's folder filed it under MISINFO, which agrees.",
        "claims": [
            {
                "text": "A lot of city water has prescription drugs in it ... "
                        "a lot of people flush their unused medications down "
                        "the toilet",
                "start": 14.3, "end": 23.6,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35112470", "PMID:21139869"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Pharmaceutical residues in water bodies are real "
                         "and measured. What the video omits, and the "
                         "retrieved risk assessments address, is that "
                         "detection at trace concentrations is not the same as "
                         "a health risk. Supported as literally stated.",
            },
            {
                "text": "roundup [glyphosate] is actually in our rainwater ... "
                        "it's in our groundwater, it's in our well water, and "
                        "it's in our tap water. So you don't wanna drink tap "
                        "water because it likely has glyphosate in it. That is "
                        "a neurotoxin",
                "start": 28.1, "end": 41.1,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:40684482"],
                "contradicting": ["PMID:29136183", "PMID:27552246"],
                "confidence": "medium",
                "notes": "Occurrence in drinking water is documented by the "
                         "monitoring study, so the first half holds. Calling "
                         "it a neurotoxin at those concentrations is not "
                         "supported, and the Agricultural Health Study found "
                         "no overall cancer association even in occupationally "
                         "exposed applicators. Split claim, hence MIXED. Note "
                         "this is the second glyphosate video in the set, "
                         "arguing the opposite side from v24.",
            },
            {
                "text": "Big studies in China show that children who drink "
                        "fluoridated tap water actually have lower IQ. So it "
                        "actually lowers IQ in children",
                "start": 44.9, "end": 52.3,
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": ["PMID:36639015"],
                "contradicting": ["PMID:37120936", "PMID:41941356"],
                "confidence": "medium",
                "notes": "The claim that makes this video MISINFO, and a "
                         "textbook directness failure. The meta-analysis "
                         "restricted to low fluoride exposure relevant to "
                         "community water fluoridation found no statistically "
                         "significant IQ difference (SMD 0.07, 95% CI -0.02 to "
                         "0.17), and the 2026 update concludes there is no "
                         "association at fluoridation-relevant concentrations "
                         "while criticising the endemic-area studies the "
                         "speaker relies on. The dose-response meta-analysis "
                         "is cited on the supporting side because associations "
                         "do appear at high exposures -- which is precisely "
                         "the distinction the claim erases.",
            },
            {
                "text": "It can harm the pineal gland. It can even harm the "
                        "teeth and the bones",
                "start": 52.3, "end": 55.2,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:31254856"],
                "contradicting": ["PMID:41941356"],
                "confidence": "low",
                "notes": "Dental and skeletal fluorosis are real at high "
                         "exposures, as the groundwater-contamination review "
                         "documents, so the teeth and bones half has support "
                         "in that exposure range; the pineal gland claim has "
                         "nothing retrieved behind it. Three outcomes bundled "
                         "in one sentence, which is why confidence is low and "
                         "a reviewer may want to split the row.",
            },
        ],
    },
    {
        "video_id": "v64",
        "topic": "vaccines / immunisation schedules",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "A paediatrician going country by country through "
                 "immunisation schedules to show that an official White House "
                 "/ HHS graphic claiming '11 injections in European countries, "
                 "72 in the United States' is wrong, and explaining how the 72 "
                 "is constructed (splitting combination shots and counting "
                 "annual flu and COVID doses for eighteen years). The third "
                 "competent debunk in the set to come out CANNOT_RECOGNIZE, "
                 "and the most clear-cut: every claim on both sides is a count "
                 "from a published national schedule, which is checkable in "
                 "minutes and not checkable against PubMed or WHO/CDC pages. "
                 "Collectors filed it under DEBUNKING. This is the single best "
                 "argument in the set for widening the evidence sources in "
                 "section 6, and it is written up in the PR description.",
        "claims": [
            {
                "text": "in European countries they get 11 injections[,] in "
                        "the United States we give 72",
                "start": 9.9, "end": 18.7,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "The claim the whole video exists to refute, and it "
                         "cannot be adjudicated here. Settling it needs the "
                         "AAP, CDC and European national schedules, none of "
                         "which is a paper. Under section 9 that leaves a "
                         "thorough, numerate debunk labelled "
                         "CANNOT_RECOGNIZE.",
            },
            {
                "text": "there's about 24 vaccines that children will receive "
                        "by the age of two[, and] in said 24 injections, "
                        "you'll get protection from 16 different diseases",
                "start": 36.3, "end": 53.1,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "His own count from the AAP schedule. Same problem: "
                         "a schedule document, not a study.",
            },
            {
                "text": "the only way they get there is by separating out the "
                        "DTAP shots and MMR shots as if those were separate "
                        "injections, which they're not. And combines that with "
                        "a yearly flu shot and a yearly COVID shot for all 18 "
                        "years of life",
                "start": 120.3, "end": 134.5,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "An explanation of how the disputed figure was "
                         "constructed. Arithmetic over schedule documents, so "
                         "again outside the allowed evidence sources. Note "
                         "this is the most useful claim in the video for a "
                         "reader and the least verifiable for the pipeline.",
            },
        ],
    },
    {
        "video_id": "v66",
        "topic": "vaccines / mercury",
        "case_tags": ["debunking"],
        "confidence": "medium",
        "notes": "A clinician answering a 'mercury in vaccines' post by "
                 "distinguishing methylmercury from ethylmercury, with the "
                 "methanol-versus-ethanol analogy. DEBUNKING on solid "
                 "ground. Good material for the stance step because the video "
                 "opens on the opposing claim with no framing at all -- the "
                 "first eight seconds are the other person's words -- exactly "
                 "the trap v23 sets. Collectors filed it under DEBUNKING, "
                 "which agrees.",
        "claims": [
            {
                "text": "you want to give my daughter moments after her "
                        "arrival into this world vaccines with copious amounts "
                        "of mercury",
                "start": 4.8, "end": 8.3,
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:15121295", "PMID:18049924",
                                  "PMID:18482737"],
                "confidence": "medium",
                "notes": "Contradicted on both the amount and the compound. "
                         "The review of thiomersal safety in newborn and "
                         "infant vaccines and the review of thimerosal and its "
                         "ethylmercury breakdown product address exactly this "
                         "claim, and the medical-records study found no link "
                         "with neurodevelopmental disorders.",
            },
            {
                "text": "metal [methyl] mercury[,] which is the compound found "
                        "in certain seafood, can accumulate within the body "
                        "and be toxic at relatively low doses ... whereas "
                        "epimercary [ethylmercury] is a different compound "
                        "that's rapidly excreted and is not toxic at low doses",
                "start": 23.8, "end": 41.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:18049924", "PMID:15121295"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The distinction is the substance of the "
                         "thimerosal safety literature. Note the transcript "
                         "mangles both compound names ('metal mercury', "
                         "'epimercary'), so a claim extractor working from "
                         "raw transcript text would lose the two chemicals "
                         "the entire argument turns on -- a concrete "
                         "extraction-track finding.",
            },
            {
                "text": "[thimerosal] hasn't been used in routine childhood "
                        "vaccinations since 2001 and only remained in a "
                        "multi-dose version of flu vaccine given to less than "
                        "6% of the population and even now has been replaced "
                        "with another preservative",
                "start": 54.8, "end": 70.7,
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:15121295"],
                "contradicting": ["PMID:29895363"],
                "confidence": "low",
                "notes": "The US removal timeline is a regulatory fact rather "
                         "than a study finding, and a 2018 paper is titled "
                         "'Low-dose Thimerosal (ethyl-mercury) is still used "
                         "in infants' vaccines', which at least complicates "
                         "the 'even now has been replaced' half globally. "
                         "Recorded MIXED with low confidence; a reviewer "
                         "should narrow the claim to the US and may well "
                         "move it.",
            },
        ],
    },
    {
        "video_id": "v68",
        "topic": "water safety / endocrine disruptors",
        "case_tags": ["debunking"],
        "confidence": "medium",
        "notes": "A creator showing how a chain of individually-true Google "
                 "answers (tap water contains atrazine; atrazine is an "
                 "endocrine disruptor; endocrine disruptors lower "
                 "testosterone) builds a false conclusion, then supplying the "
                 "dose: the rat studies used 50 mg/kg, which he converts to "
                 "1.2 million litres of tap water a day. The mirror image of "
                 "v42 and v27 -- same 'true fragments, false conclusion' "
                 "shape, but with a speaker pointing at the fallacy instead of "
                 "committing it. Lands on CANNOT_RECOGNIZE: the refuted claim "
                 "has no human test, and his dose arithmetic is not itself a "
                 "retrievable finding. In the blind subset. Collectors filed "
                 "it under DEBUNKING.",
        "claims": [
            {
                "text": "does tap water lower testosterone ... [because it "
                        "contains atrazine, an endocrine disruptor, and] do "
                        "endocrine disruptors lower testosterone",
                "start": 4.2, "end": 28.6,
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:11053540", "PMID:24758756"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "No human study tests tap-water atrazine against "
                         "testosterone. The retrieved rat work does show "
                         "reproductive and pubertal effects, which is why the "
                         "fearmongering chain is persuasive -- but it is in "
                         "rats and at doses orders of magnitude above drinking "
                         "water, so it fails directness. Cited on the "
                         "supporting side because the papers do support the "
                         "claim's premise at high dose, which is the "
                         "distinction the video is about.",
            },
            {
                "text": "Atrazine, a common pesticide that's found in tap "
                        "water, has a regulatory limit of three parts per "
                        "billion",
                "start": 37.1, "end": 44.8,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A regulatory limit, checkable against the EPA and "
                         "not against the literature. The same gap as v24's "
                         "tolerance figure and v64's schedules.",
            },
            {
                "text": "they filled up those rats at 50 milligrams per "
                        "kilogram, which in humans you would need to drink 1.2 "
                        "million liters of tap water a day to have it affect "
                        "your testosterone",
                "start": 44.8, "end": 67.6,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:11053540"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The dose in the rat protocol is the kind of detail "
                         "the retrieved puberty study would carry, but the "
                         "conversion to litres of tap water is the speaker's "
                         "own arithmetic and is not a retrievable finding. The "
                         "reasoning is sound; the claim is still unverified "
                         "here.",
            },
        ],
    },
    {
        "video_id": "v69",
        "topic": "cancer prevention",
        "case_tags": ["accurate"],
        "confidence": "high",
        "notes": "A functional-medicine doctor giving three cancer-prevention "
                 "recommendations -- cut alcohol, lose visceral fat, raise "
                 "fibre and drop processed meat -- and then recommending "
                 "colonoscopy, with the aside 'I'm a functional medicine "
                 "doctor and I will still tell you to get one done'. Kept "
                 "deliberately as a counterexample to a tempting shortcut: "
                 "speaker credentials and genre are not evidence of anything. "
                 "This is the best-evidenced NO_MISINFO video in the bundle, "
                 "from the professional category most associated elsewhere in "
                 "the set with v34, v36 and v37. In the blind subset. This "
                 "collector's folder carried no label.",
        "claims": [
            {
                "text": "Alcohol is a group one carcinogen, same category as "
                        "tobacco and asbestos. It's actually linked to at "
                        "least seven different cancers including breast cancer "
                        "and colon cancer",
                "start": 11.9, "end": 33.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:25422909", "PMID:37905315"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The comprehensive dose-response meta-analysis of "
                         "alcohol and site-specific cancer risk supports both "
                         "the multi-site claim and the named sites.",
            },
            {
                "text": "There's no amount [of alcohol] that's been shown to "
                        "be protective. Less is better, and none is better "
                        "than less",
                "start": 33.7, "end": 50.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:37905315", "PMID:25422909"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Supported for cancer risk specifically, which is "
                         "what he is talking about. Medium confidence because "
                         "the broader cardiovascular literature has argued "
                         "about low-dose effects, and the claim as phrased "
                         "('no amount ... protective') is about cancer.",
            },
            {
                "text": "Excess body fat is second only to smoking as a "
                        "modifiable cause of cancer. And it's linked to 13 of "
                        "them",
                "start": 41.6, "end": 59.0,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:26205840", "PMID:25719336",
                               "PMID:41634393"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The European Code against Cancer chapter on "
                         "obesity and body fatness and the obesity-and-cancer "
                         "review support the multi-site link; the global "
                         "modifiable-risk-factor analysis supports the "
                         "ranking. The exact count of 13 sites is a "
                         "specific figure the retrieved abstracts do not "
                         "state.",
            },
            {
                "text": "Most adults get about half the fiber they actually "
                        "need",
                "start": 84.3, "end": 88.7,
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A population intake statistic, checkable against "
                         "dietary survey data rather than the literature.",
            },
            {
                "text": "fiber feeds the bacteria that produce something "
                        "called butyrate, which is what the cells lining your "
                        "colon run on",
                "start": 96.8, "end": 105.7,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:41305603", "PMID:40331741"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The short-chain-fatty-acid and colorectal cancer "
                         "review supports the mechanism. The retrieved "
                         "tumorigenesis work is in animals, so the mechanism "
                         "rather than a clinical outcome is what is "
                         "supported.",
            },
            {
                "text": "gotta cut out the processed meat, the bacon, the hot "
                        "dogs, the deli meat, the summer sausages, that's one "
                        "group as well",
                "start": 112.4, "end": 120.7,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:40210826", "PMID:33838606",
                               "PMID:34455534"],
                "contradicting": [],
                "confidence": "high",
                "notes": "The comprehensive meta-analysis and umbrella review "
                         "of red and processed meat and cancer outcomes "
                         "support the colorectal association and the group 1 "
                         "classification he alludes to.",
            },
            {
                "text": "a colonoscopy ... is one of the only tests in "
                        "medicine that doesn't just find cancer, it actually "
                        "can prevent it. Many times they'll go in there, "
                        "they'll take out a polyp before it even moves into "
                        "the next state",
                "start": 126.1, "end": 142.4,
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:37737817", "PMID:26257272"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Polypectomy during screening colonoscopy removing "
                         "precursor lesions is exactly what the clinical "
                         "practice update on screening and post-polypectomy "
                         "surveillance covers. The superlative ('one of the "
                         "only tests') is not itself tested.",
            },
        ],
    },
]
