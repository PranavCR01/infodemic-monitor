"""Batch 2, part a: v83-v107. Same rules as labels.py; see labels_batch2.py.

Labelled from transcripts/<video_id>.json (speech and OCR read together).
Every PMID below was returned by scripts/evidence.py (cached under
evidence_cache/) and its abstract read before it was cited.
"""

LABELS = [
    {
        "video_id": "v83",
        "topic": "vitamin D / sun exposure",
        "case_tags": ["other_language"],
        "confidence": "low",
        "notes": "no checkable claims. An 8-second meme: one spoken line in "
                 "Spanish ('¡Este para vosotros!') over a French caption that "
                 "OCR reads as 'enFin Te CReeR De La vITaMIne D' (roughly "
                 "'finally making vitamin D'). Vitamin D is health-adjacent, "
                 "so it is not out_of_scope, but nothing is asserted that "
                 "could be checked. Low confidence because the caption is "
                 "garbled and the picture, which carries the joke, is not in "
                 "the transcript.",
        "claims": [],
    },
    {
        "video_id": "v84",
        "topic": "COVID-19 / home remedies (ginger)",
        "case_tags": ["missing_evidence", "uncertain_science"],
        "confidence": "medium",
        "notes": "A speaker on an Indian news channel recommending dry ginger "
                 "powder sniffed into each nostril morning and evening "
                 "against Omicron, with a pH rationale. Every claim is "
                 "untested: PubMed returns nothing on intranasal ginger and "
                 "SARS-CoV-2 beyond in-silico docking and a herbal-use "
                 "survey. Under section 7 that is INSUFFICIENT_EVIDENCE, not "
                 "CONTRADICTED, so a plainly unfounded remedy comes out "
                 "CANNOT_RECOGNIZE -- the batch-1 v12/v20 pattern. Whisper "
                 "heard 'sonth' (Hindi for dry ginger) as 'soint'.",
        "claims": [
            {
                "text": "take a bit of this [dry ginger powder] ... put it in "
                        "your nostril snot put it in the other nostril snot "
                        "... So from the nostril itself ... if we take care "
                        "of it, we'll be perfectly fine",
                "start": 32.9, "end": 99.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "The deciding claim: nasal dry-ginger powder "
                         "prevents COVID-19 (Omicron). Searches 'ginger "
                         "nasal COVID-19' and 'intranasal ginger powder "
                         "SARS-CoV-2' found no study testing it; the only "
                         "ginger hit is in-silico docking (PMID 33457429), "
                         "which tests nothing in people.",
            },
            {
                "text": "Dry ginger is highly alkaline and it has a high pH "
                        "value",
                "start": 59.0, "end": 66.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A food-composition claim. 'dry ginger alkaline pH' "
                         "returned nothing, and no allow-listed reference "
                         "gives the pH of ginger powder.",
            },
            {
                "text": "the infections which you have are all acidic and "
                        "have low pH. They get killed instantly",
                "start": 70.5, "end": 76.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing retrieved tests killing respiratory "
                         "viruses in the nose with an alkaline powder.",
            },
        ],
    },
    {
        "video_id": "v85",
        "topic": "environmental health / wind turbine noise",
        "case_tags": ["other_language", "uncertain_science"],
        "confidence": "medium",
        "notes": "@lecoinecolo reposting a French TV interview in which a "
                 "public figure explains his opposition to wind turbines "
                 "(concrete, rare earths, property values, 'it kills "
                 "animals'). Two health assertions: a recognised 'wind "
                 "turbine syndrome' disease, and people no longer able to "
                 "sleep. The literature on sleep genuinely splits by "
                 "measurement -- self-reported disturbance rises with noise, "
                 "objective sleep does not change -- so it is MIXED, and the "
                 "'syndrome' is untested rather than refuted. "
                 "CANNOT_RECOGNIZE with review triggers.",
        "claims": [
            {
                "text": "il y a le syndrome éolien, on s'est reconnu, c'est "
                        "une maladie",
                "start": 51.4, "end": 55.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: there is wind turbine syndrome, it has been "
                         "recognised, it is a disease. The systematic review "
                         "PMID 25474326 found dose-response evidence only for "
                         "annoyance and self-reported sleep disturbance and "
                         "'no conclusive evidence' for the other claimed "
                         "health effects. That is absence of evidence for a "
                         "distinct disease, not a test that refutes one. "
                         "'on s'est reconnu' is Whisper's reading, probably "
                         "'c'est reconnu'.",
            },
            {
                "text": "Les gens ne peuvent plus dormir, les gens sont "
                        "malades",
                "start": 51.4, "end": 60.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:25474326", "PMID:37844409"],
                "contradicting": ["PMID:33179850"],
                "confidence": "medium",
                "notes": "EN: people can no longer sleep, people are ill. "
                         "Self-reported sleep disturbance rises with turbine "
                         "noise and falls with distance (25474326; 37844409, "
                         "pooled 34% prevalence near turbines, poor-quality "
                         "evidence). The meta-analysis of polysomnography and "
                         "actigraphy (33179850) found no effect on any "
                         "objective sleep measure. Good studies pointing in "
                         "different directions: MIXED.",
            },
        ],
    },
    {
        "video_id": "v86",
        "topic": "HIV/AIDS denialism",
        "case_tags": ["clearly_false", "satire"],
        "confidence": "high",
        "notes": "HIV denialism in 90 seconds: AIDS was caused by poppers, "
                 "HIV can be 'reversed' by rebuilding the immune system, and "
                 "antiretrovirals lower immunity. The chimpanzee origin is "
                 "delivered as mockery ('Oh my goodness, this had to come "
                 "from a monkey in Africa that one person slept with'), so "
                 "its stance is UNCLEAR: sarcasm, which section 5 sends to "
                 "review rather than guessing. MISINFO on two contradicted, "
                 "endorsed claims. Tagged satire for the sarcastic "
                 "delivery, not because the video is satire.",
        "claims": [
            {
                "text": "Of course we can reverse HIV",
                "start": 0.0, "end": 1.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Shown on screen as 'Yes you can reverse HIV/AIDS'. "
                         "Nothing retrieved tests 'reversing' HIV by "
                         "rebuilding immunity without treatment, so this is "
                         "absence of evidence; the false parts of his "
                         "argument are carried by c2 and c3.",
                "source": "both",
            },
            {
                "text": "in the 1980s, the gay men were taking these party "
                        "drugs called poppers. And these poppers was "
                        "bringing down the immune system of these gay men",
                "start": 13.8, "end": 24.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:38169370", "PMID:22229120"],
                "confidence": "high",
                "notes": "The 1980s nitrite hypothesis of AIDS. The "
                         "literature review PMID 38169370: 'it was found that "
                         "poppers use was not the cause but rather a marker "
                         "associated with HIV acquisition'. AIDS is caused by "
                         "HIV-1 and HIV-2 (22229120).",
            },
            {
                "text": "this had to come from a monkey in Africa that one "
                        "person slept with, hopped on a plane and took the "
                        "whole disease around the world",
                "start": 47.2, "end": 56.5,
                "kind": "research_question",
                "stance": "UNCLEAR", "verdict": "SUPPORTED",
                "supporting": ["PMID:22229120"], "contradicting": [],
                "confidence": "medium",
                "notes": "Mocked, not asserted. The core is SUPPORTED: HIV-1 "
                         "group M arose from a cross-species transmission of "
                         "SIVcpz from chimpanzees in southeastern Cameroon "
                         "(22229120). The 'slept with' and 'one person "
                         "took it around the world' details are his "
                         "caricature. The speaker is plainly ridiculing the "
                         "account, which would make this REFUTES + SUPPORTED "
                         "(section 9 rule 2); it is left UNCLEAR because the "
                         "rejection is carried entirely by sarcasm.",
            },
            {
                "text": "if you start taking these medications, what does "
                        "this do to your immune system? It lowers your "
                        "immune system. It compromise your immune system "
                        "even more",
                "start": 68.9, "end": 76.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:9660367"],
                "confidence": "high",
                "notes": "The systematic review of immune recovery on potent "
                         "antiretroviral therapy (9660367) documents rising "
                         "CD4+ and CD8+ counts and qualitative immune "
                         "improvement after viral suppression: the opposite "
                         "of the claim.",
            },
        ],
    },
    {
        "video_id": "v87",
        "topic": "fluoride / infant drinking water",
        "case_tags": ["clearly_false", "uncertain_science"],
        "confidence": "medium",
        "notes": "A self-described neuroscientist (Robert Love) holding up "
                 "bottled 'baby' water: fluoride will cross an immature "
                 "blood-brain barrier, water fluoridation 'has basically "
                 "been disproven', so babies should drink distilled or "
                 "reverse-osmosis water. Two endorsed claims are "
                 "contradicted (the immature-barrier claim and the "
                 "disproven-benefit claim), so MISINFO. The core warning "
                 "about fluoride in infant water is genuinely contested and "
                 "is MIXED, not false.",
        "claims": [
            {
                "text": "babies' brains, the blood brain barrier is not fully "
                        "formed until six months",
                "start": 8.4, "end": 18.2,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:29528501"],
                "confidence": "medium",
                "notes": "Textbook physiology. The review 'The myth of the "
                         "immature barrier systems in the developing brain' "
                         "(29528501) presents evidence 'that fetal and "
                         "newborn brains are well protected'. Medium "
                         "confidence: barrier function does mature, but not "
                         "in the sense claimed.",
            },
            {
                "text": "do not buy this water for your babies. It is very "
                        "dangerous ... This water has fluoride ... You do "
                        "not want babies drinking water with fluoride",
                "start": 0.0, "end": 10.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:19571048", "PMID:39761023"],
                "contradicting": [],
                "confidence": "low",
                "notes": "Also on screen throughout ('Do NOT Buy This Water "
                         "for BABIES'). Infant formula made with fluoridated "
                         "water is associated with mild enamel fluorosis "
                         "(19571048, summary OR 1.8, 'weak' evidence of "
                         "causation). The 2025 IQ meta-analysis (39761023) "
                         "found inverse associations that were null below "
                         "1.5 mg/L overall but persisted in low-risk-of-bias "
                         "studies. Bottled 'baby' water is low in fluoride, "
                         "and 'very dangerous' is far stronger than any of "
                         "this. Nothing retrieved contradicts it either, "
                         "so it is not MIXED (section 7 needs good studies "
                         "pointing both ways): weak, partial support for a "
                         "much stronger claim is INSUFFICIENT_EVIDENCE "
                         "(strength of inference), with the two studies "
                         "kept as that partial support.",
                "source": "both",
            },
            {
                "text": "Some people believe that fluoride is good for your "
                        "teeth if you put in the water that's basically "
                        "been disproven",
                "start": 27.6, "end": 35.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:26092033", "PMID:39362658"],
                "confidence": "medium",
                "notes": "The Cochrane review (26092033) found water "
                         "fluoridation initiation reduced dmft by 35% and "
                         "DMFT by 26%. Its 2024 update (39362658) finds a "
                         "smaller benefit on contemporary (post-1975) "
                         "evidence, with low certainty. A smaller benefit is "
                         "not 'disproven'.",
            },
            {
                "text": "fluoride does a lot of damage to bones and teeth",
                "start": 35.0, "end": 39.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Unquantified. Dental fluorosis is real (see c2), "
                         "but 'a lot of damage' at drinking-water levels is "
                         "not tested by anything retrieved; the bone-fracture "
                         "search returned only a commentary on the York "
                         "review (12047121), not read as evidence.",
            },
        ],
    },
    {
        "video_id": "v88",
        "topic": "reproduction / sex selection (Shettles method)",
        "case_tags": ["clearly_false", "other_language"],
        "confidence": "high",
        "notes": "'How to choose your baby's sex, part 2': the Shettles "
                 "timing method. Intercourse near ovulation gives a boy, "
                 "three days before gives a girl, because X-bearing sperm "
                 "survive longer. Wilcox's prospective study of 221 women "
                 "and a meta-analysis of natural family planning data both "
                 "test exactly this, and both contradict it. The second "
                 "found fewer, not more, boys at the most fertile time. "
                 "MISINFO.",
        "claims": [
            {
                "text": "los espermatozoides que van a ser mujeres son más "
                        "resistentes que los espermatozoides que van a ser "
                        "varones",
                "start": 2.4, "end": 7.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: sperm that will be girls are more resistant "
                         "than sperm that will be boys. Whisper writes "
                         "'espermatosoides'. Nothing retrieved compares X- "
                         "and Y-bearing human sperm survival. The swim-up "
                         "study (8243684) found no motility enrichment "
                         "either way, which is related but does not test "
                         "survival, so it is not cited.",
            },
            {
                "text": "Si las relaciones ocurren muy cerca al día de la "
                        "ovulación, pues hay más probabilidades de tener un "
                        "varón",
                "start": 14.1, "end": 18.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:7477165", "PMID:1836712"],
                "confidence": "high",
                "notes": "EN: if intercourse happens very close to ovulation "
                         "a boy is more likely. Wilcox et al. (7477165): "
                         "'cycles producing male and female babies had "
                         "similar patterns of intercourse in relation to "
                         "ovulation'. The NFP meta-analysis (1836712) found "
                         "a lower proportion of male births at the most "
                         "fertile time (RR 0.90), the reverse of the claim.",
            },
            {
                "text": "si las relaciones ocurren 3 días antes de la "
                        "ovulación, la probabilidad de tener una niña es "
                        "mayor",
                "start": 18.7, "end": 24.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:7477165"],
                "confidence": "high",
                "notes": "EN: if intercourse happens 3 days before ovulation "
                         "a girl is more likely. Same Wilcox finding: timing "
                         "of intercourse did not differ between cycles "
                         "producing boys and girls.",
            },
        ],
    },
    {
        "video_id": "v89",
        "topic": "dental / cosmetic trends",
        "case_tags": ["debunking", "other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "A dental clinic's account reacting to a trend of painting "
                 "teeth with white nail polish to 'whiten' them: absurd, "
                 "could damage teeth and health, only a dentist can whiten "
                 "safely. A sensible debunk with nothing in the literature "
                 "on either side -- nobody has studied nail polish on teeth "
                 "-- so every claim is INSUFFICIENT_EVIDENCE and the video "
                 "is CANNOT_RECOGNIZE, sent to review as a possible debunk "
                 "of an unsettled claim.",
        "claims": [
            {
                "text": "\"BLANQUEAN\" los DIENTES con ESMALTE DE UÑAS",
                "start": 0.0, "end": 12.9,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: they 'whiten' teeth with nail polish. The "
                         "scare quotes on screen and 'estas modas absurdas' "
                         "in speech make this REFUTES. Untested either way.",
                "source": "both",
            },
            {
                "text": "podría llegar a dañar tus dientes y tu salud. Los "
                        "químicos que contienen estos esmaltes no están "
                        "destinados para su boca y ingerirlos podría "
                        "resultar tóxico",
                "start": 16.9, "end": 30.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: it could damage your teeth and your health; "
                         "the chemicals in these polishes are not meant for "
                         "the mouth and swallowing them could be toxic. "
                         "'nail polish ingestion toxicity' returns only nail "
                         "polish REMOVER poisonings (acetone, acetonitrile), "
                         "a different product. Not cited.",
            },
            {
                "text": "La única forma de blanquear tus dientes de forma "
                        "segura es acudir a un dentista a que te realice un "
                        "blanqueamiento dental profesional",
                "start": 25.3, "end": 36.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: the only safe way to whiten your teeth is "
                         "professional whitening at a dentist. An exclusivity "
                         "claim no study tests.",
            },
        ],
    },
    {
        "video_id": "v90",
        "topic": "vitamin D / COVID-19",
        "case_tags": ["accurate"],
        "confidence": "high",
        "notes": "A short, accurate summary of a real UK Biobank study "
                 "(Ma et al., Am J Clin Nutr 2021): habitual vitamin D "
                 "supplement use associated with a 34% lower risk of "
                 "COVID-19 infection, with the speaker's own caveat that "
                 "only large prophylactic studies could show a clinical "
                 "benefit. The figure matches the abstract exactly. "
                 "NO_MISINFO.",
        "claims": [
            {
                "text": "Habitual vitamin D use was associated with a 34% "
                        "lower risk of contracting COVID-19",
                "start": 0.0, "end": 5.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33515005"], "contradicting": [],
                "confidence": "high",
                "notes": "PMID 33515005: 'habitual use of vitamin D "
                         "supplements was significantly associated with a "
                         "34% lower risk of COVID-19 infection (OR, 0.66)'. "
                         "The authors add that residual confounding cannot "
                         "be ruled out, which the speaker's closing caveat "
                         "reflects.",
                "source": "both",
            },
            {
                "text": "This was independent of lifestyle, socioeconomic "
                        "status, or the presence of other chronic diseases",
                "start": 5.6, "end": 11.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33515005"], "contradicting": [],
                "confidence": "medium",
                "notes": "The abstract reports the association 'after "
                         "adjustment for covariates'; it does not list them, "
                         "so medium confidence.",
            },
        ],
    },
    {
        "video_id": "v91",
        "topic": "nutrition / seed oils (canola)",
        "case_tags": ["clearly_false"],
        "confidence": "high",
        "notes": "'Canola oil is toxic', walked through its manufacture: "
                 "toxic rapeseed, erucic acid, high-heat extraction, hexane, "
                 "bleaching, trans fats. The processing facts are "
                 "half-true (hexane is a neurotoxin; deodorisation forms "
                 "small amounts of trans alpha-linolenic acid), but the "
                 "conclusion is contradicted by a meta-analysis of 42 "
                 "controlled trials in which canola oil improved lipid "
                 "profiles. MISINFO. A sixth seed-oil video for the set "
                 "(batch 1 had five).",
        "claims": [
            {
                "text": "Canola oil is toxic",
                "start": 0.0, "end": 2.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:33127255"],
                "confidence": "medium",
                "notes": "PMID 33127255 (systematic review and meta-analysis "
                         "of controlled trials): canola oil significantly "
                         "reduced total cholesterol, LDL-C and apo B "
                         "compared with other edible oils. 'Toxic' is "
                         "unquantified, so medium confidence, but the direct "
                         "human evidence on eating it points the other way.",
                "source": "both",
            },
            {
                "text": "erusic acid, a toxic fatty acid strongly associated "
                        "with heart lesions",
                "start": 10.6, "end": 17.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Whisper's 'erusic' is erucic (the caption reads "
                         "ERUCIC). The heart-lesion evidence is the rat "
                         "myocardial-lipidosis literature. The review "
                         "retrieved (34924350) discusses the FDA's mustard "
                         "oil ban but reports human health benefits too. "
                         "Animal-only evidence for a claim about people: "
                         "INSUFFICIENT under rule 1. Canola is by definition "
                         "the low-erucic variety, which the speaker "
                         "acknowledges.",
                "source": "both",
            },
            {
                "text": "hexane, a known neurological toxin",
                "start": 26.4, "end": 30.3,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39536137"],
                "contradicting": [],
                "confidence": "high",
                "notes": "StatPearls (39536137): 6-carbon molecules like "
                         "n-hexane 'are notorious for their significant "
                         "neurologic toxicity'; it also notes n-hexane's use "
                         "in vegetable-oil extraction. (31445054, on "
                         "low-level exposure in automotive technicians, "
                         "found only limited evidence of neuropathy; it "
                         "speaks to dose, not to whether hexane is a "
                         "neurotoxin, so it is not cited.) True as stated; "
                         "the implication that residues in oil are a dose "
                         "that matters is not claimed in words.",
                "source": "both",
            },
            {
                "text": "the canola oil is left oxidized, contaminated with "
                        "solvents, and containing significant levels of "
                        "trans fatty acids",
                "start": 35.0, "end": 47.6,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Deodorised rapeseed oil does contain trans "
                         "alpha-linolenic acid (11299084 calls the amounts "
                         "'significant' and found a small LDL:HDL effect at "
                         "1.4 g/day). Nothing retrieved quantifies solvent "
                         "residue or oxidation in retail canola oil, and "
                         "the compound claim cannot be judged as a whole.",
                "source": "both",
            },
        ],
    },
    {
        "video_id": "v92",
        "topic": "grounding / earthing",
        "case_tags": ["missing_evidence"],
        "confidence": "high",
        "notes": "'You can heal any kind of disease that you have for free' "
                 "by grounding your feet, with the caption 'Inflammation is "
                 "the ROOT CAUSE of every disease known to man'. The "
                 "grounding literature retrieved is narrative reviews by its "
                 "proponents and a rat study; nothing tests the claims in "
                 "people with a control group. All INSUFFICIENT, so "
                 "CANNOT_RECOGNIZE. A clear example of an untestable "
                 "panacea claim that section 7 rightly refuses to call "
                 "false.",
        "claims": [
            {
                "text": "You can heal any kind of disease that you have for "
                        "free. Basically, all you have to do is get your "
                        "feet grounded",
                "start": 8.5, "end": 12.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Retrieved: 25848315, 31831261 and 36528336 "
                         "(narrative reviews advocating earthing) and "
                         "39337279 (rats). None is a controlled human trial "
                         "of disease outcomes, and the reviews are not "
                         "evidence of efficacy. Not cited.",
                "source": "both",
            },
            {
                "text": "A body that is consistently grounded cannot sustain "
                        "chronic inflammation",
                "start": 12.7, "end": 17.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Same search; same absence of controlled evidence.",
                "source": "both",
            },
            {
                "text": "Inflammation is the ROOT CAUSE Of every disease "
                        "known to man",
                "start": 14.0, "end": 18.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Screen-only caption stated as fact. Sweeping "
                         "enough that no study tests it as stated.",
                "source": "screen",
            },
        ],
    },
    {
        "video_id": "v93",
        "topic": "COVID-19 vaccines / mortality statistics",
        "case_tags": ["other_language", "clearly_false",
                      "speech_screen_disagree"],
        "confidence": "medium",
        "notes": "Spanish TV-style segment: 'Health ministry now admits more "
                 "than 35,000 vaccinated people died of COVID', then a legal "
                 "complaint about informed consent and the COVID pass. The "
                 "spoken claims are ministry statistics framed to imply "
                 "vaccine failure; they are facts of record not reachable "
                 "through the allow-list, so INSUFFICIENT. The deciding "
                 "claim is ON SCREEN ONLY, a persistent banner never spoken: "
                 "COVID vaccines cause immunosuppression and more doses meant "
                 "more ICU admissions and deaths. Contradicted by booster "
                 "effectiveness against ICU and death. MISINFO comes from "
                 "OCR; v94 is the same clip without the banner and comes out "
                 "CANNOT_RECOGNIZE. The pair is the cleanest OCR "
                 "ablation in the set.",
        "claims": [
            {
                "text": "Sanidad admite ahora que sí, que más de 35.000 "
                        "vacunados murieron a causa del coronavirus",
                "start": 0.0, "end": 4.9,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: the health ministry now admits more than "
                         "35,000 vaccinated people died of the coronavirus. "
                         "Also the on-screen headline. A government "
                         "statistic; the Spanish ministry is not on the "
                         "section 6 allow-list. A count of deaths among the "
                         "vaccinated says nothing about vaccine effect "
                         "without the denominator, which is the misleading "
                         "part, but the number itself cannot be checked "
                         "here.",
                "source": "both",
            },
            {
                "text": "7 millones y medio de personas vacunadas se "
                        "terminaron contagiando del COVID y fallecieron más "
                        "de 31.000 personas",
                "start": 21.6, "end": 28.2,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: 7.5 million vaccinated people caught COVID and "
                         "more than 31,000 died. On screen as 'Casos entre "
                         "vacunados ... 31.967 fallecidos'. Same reasoning "
                         "as c1.",
                "source": "both",
            },
            {
                "text": "Las vacunas cOvid generan inmunosupresion, Y dieron "
                        "lugar a mas admisiones en cuidados intensivos y mas "
                        "muertes por cOvid-19 cuantas mas dosis",
                "start": 0.0, "end": 111.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:37884492"],
                "confidence": "high",
                "notes": "EN: COVID vaccines cause immunosuppression, and "
                         "the more doses, the more ICU admissions and COVID "
                         "deaths. Screen-only banner for the whole video, "
                         "stated as fact. The Chilean national cohort of "
                         "3.75 million (37884492): a second mRNA booster was "
                         "88.2% effective against ICU admission and 90.5% "
                         "against death. More doses meant fewer, not more.",
                "source": "screen",
            },
        ],
    },
    {
        "video_id": "v94",
        "topic": "COVID-19 vaccines / mortality statistics",
        "case_tags": ["other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "The same segment as v93, reposted with a different overlay "
                 "(no immunosuppression banner; football and Real Madrid "
                 "headlines from the source broadcast leak into OCR). "
                 "Without the banner, only the ministry statistics remain, "
                 "and they are INSUFFICIENT for the reasons in v93. So it "
                 "comes out CANNOT_RECOGNIZE where v93 is MISINFO: the same "
                 "speech, a different label, decided entirely by on-screen "
                 "text.",
        "claims": [
            {
                "text": "Sanidad admite ahora que sí que más de 35.000 "
                        "vacunados murieron a causa del coronavirus",
                "start": 0.0, "end": 4.7,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: the health ministry now admits more than "
                         "35,000 vaccinated people died of the coronavirus. "
                         "As v93 c1.",
                "source": "both",
            },
            {
                "text": "7,5 millones de personas vacunadas se terminaron "
                        "contagiando del COVID y fallecieron más de 31.000 "
                        "personas",
                "start": 15.0, "end": 28.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: 7.5 million vaccinated people caught COVID and "
                         "more than 31,000 died. As v93 c2.",
                "source": "both",
            },
        ],
    },
    {
        "video_id": "v95",
        "topic": "oncology / brain tumour cluster",
        "case_tags": ["accurate", "neutral_discussion"],
        "confidence": "high",
        "notes": "@ladyspinedoc, a board-certified neurosurgeon, discussing "
                 "the reported cluster of brain tumours among nurses on one "
                 "Massachusetts maternity unit. She explains which benign "
                 "tumours are most common, that ionizing radiation is the "
                 "established environmental risk factor, and that a single "
                 "cause is hard to find. She ends speculating that there is "
                 "'some type of commonality in an environmental exposure'. "
                 "Nothing in speech or on screen mentions vaccines. "
                 "Measured and accurate where checkable: NO_MISINFO.",
        "claims": [
            {
                "text": "At least 10 nurses from one maternity ward at a "
                        "Massachusetts hospital have been diagnosed with "
                        "brain tumors",
                "start": 0.5, "end": 7.8,
                "kind": "fact_of_record",
                "stance": "QUOTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A news report she relays (headline on screen: "
                         "'Nurses Sound Alarm Over Brain Tumor Cluster'). Not "
                         "checkable against PubMed or the allow-list.",
                "source": "both",
            },
            {
                "text": "The most common types of benign brain tumors include "
                        "meningiomas ... pituitary macroadenomas ... as well "
                        "as schwannomas",
                "start": 40.7, "end": 60.8,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39371035"], "contradicting": [],
                "confidence": "medium",
                "notes": "CBTRUS 2017-2021 (39371035): meningioma is 'the "
                         "most common predominantly non-malignant "
                         "histopathology' (41.7% of all tumours). The "
                         "abstract does not rank pituitary tumours and "
                         "schwannomas, hence medium confidence.",
            },
            {
                "text": "The most common environmental risk factor for these "
                        "types of tumors is ionizing radiation",
                "start": 72.7, "end": 83.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:22952197", "PMID:25249493"],
                "contradicting": [],
                "confidence": "high",
                "notes": "22952197: ionizing radiation 'is the only "
                         "established environmental risk factor for brain "
                         "and CNS tumors', more strongly for meningioma. "
                         "25249493: for meningioma 'a causal link has been "
                         "established only for ionising radiation'.",
            },
            {
                "text": "I do think that there is some type of commonality in "
                        "an environmental exposure that may or may not be "
                        "identified",
                "start": 120.7, "end": 129.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Her own hedged speculation about this cluster. "
                         "Nothing retrieved addresses the cluster itself.",
            },
        ],
    },
    {
        "video_id": "v96",
        "topic": "nutrition / heavy metals in canned fish",
        "case_tags": ["other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "A nutrition communicator giving up the oil from canned "
                 "fish because 'heavy metals dissolve in fat', citing "
                 "on screen an Italian food-science paper (2011) on canning "
                 "and heavy-metal extraction from tuna. PubMed returns "
                 "nothing on metals in the packing oil itself. Mercury in "
                 "tuna is mostly methylmercury bound in muscle, and the "
                 "packing medium did not change its form (7185899), but "
                 "neither result tests the claim. CANNOT_RECOGNIZE.",
        "claims": [
            {
                "text": "los metales pesados se disuelven en la grasa",
                "start": 17.4, "end": 23.8,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: heavy metals dissolve in fat. 7185899 found "
                         "methylmercury predominant in canned tuna "
                         "regardless of packing medium (water or oil) and "
                         "measured only the water-extractable fraction. "
                         "27672045 found higher total Hg in olive-oil-packed "
                         "tuna meat. Neither measures metal partitioning "
                         "into the oil. Not cited.",
                "source": "both",
            },
            {
                "text": "Comer el aceite de las conservas ... va a ser comer "
                        "una concentración más alta de estos metales "
                        "pesados",
                "start": 23.8, "end": 36.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: eating the oil from canned fish means eating "
                         "a higher concentration of these heavy metals. "
                         "Searches 'mercury canned tuna oil covering liquid' "
                         "and 'heavy metals canned fish oil migration' "
                         "returned nothing. The cited Italian journal is not "
                         "indexed in PubMed.",
                "source": "both",
            },
        ],
    },
    {
        "video_id": "v97",
        "topic": "nutrition / ketogenic diet and cardiovascular risk",
        "case_tags": ["accurate", "other_language"],
        "confidence": "high",
        "notes": "Cardiologist Aurelio Rojas summarising the UK Biobank "
                 "analysis of low-carbohydrate high-fat diets (Iatan et al., "
                 "JACC Adv 2024). Higher LDL-C and apoB, over double the "
                 "risk of major cardiovascular events over ~12 years, "
                 "severe hypercholesterolaemia almost twice as common. "
                 "Every number matches the abstract, and he closes on the "
                 "Mediterranean diet, which PREDIMED supports. A clean "
                 "accurate Spanish-language anchor: NO_MISINFO.",
        "claims": [
            {
                "text": "las personas que seguían una dieta queto, baja en "
                        "carbohidratos y alta en grasas presentaron ... un "
                        "aumento significativo del colesterol LDL, un "
                        "aumento de APOB",
                "start": 36.2, "end": 48.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39081652"], "contradicting": [],
                "confidence": "high",
                "notes": "EN: people on a keto, low-carb high-fat diet had a "
                         "significant rise in LDL cholesterol and in apoB. "
                         "Whisper writes 'carboidratos' and 'colecerol'; the "
                         "captions confirm 'carbohidratos' and "
                         "'colesterol LDL'. 39081652: LDL-C and apoB "
                         "'significantly increased in the LCHF vs SD group'.",
                "source": "both",
            },
            {
                "text": "más del doble de riesgo de infarto, ictus u otros "
                        "problemas cardiovasculares durante casi 12 años de "
                        "seguimiento",
                "start": 48.6, "end": 59.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39081652"], "contradicting": [],
                "confidence": "high",
                "notes": "EN: more than double the risk of heart attack, "
                         "stroke or other cardiovascular problems over almost "
                         "12 years. 39081652: after 11.8 years, MACE in 9.8% "
                         "vs 4.3%, adjusted HR 2.18. Observational, which "
                         "the claim's wording ('presentaron') respects.",
            },
            {
                "text": "la hipercolesterolemia severa fue casi el doble de "
                        "frecuente",
                "start": 59.8, "end": 67.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39081652"], "contradicting": [],
                "confidence": "high",
                "notes": "EN: severe hypercholesterolaemia was almost twice "
                         "as frequent. 39081652: 11.1% vs 6.2% with LDL-C "
                         "above 5 mmol/L.",
            },
            {
                "text": "Para todos es la dieta mediterránea ... exactamente "
                        "lo que tu corazón quiere",
                "start": 97.3, "end": 105.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:29897866"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: for everyone, it is the Mediterranean diet, "
                         "exactly what your heart wants. PREDIMED "
                         "(29897866): lower incidence of major "
                         "cardiovascular events with a Mediterranean diet "
                         "supplemented with olive oil or nuts. 'For "
                         "everyone' goes beyond the trial population, hence "
                         "medium.",
            },
        ],
    },
    {
        "video_id": "v98",
        "topic": "cardiology / pacemakers and magnets (V16 beacons)",
        "case_tags": ["accurate", "other_language"],
        "confidence": "high",
        "notes": "A cardiologist on Spain's new mandatory V16 roadside "
                 "beacons. The magnet that holds them to the car roof can "
                 "put a pacemaker or ICD into magnet mode if placed on the "
                 "chest; the device is not damaged, the effect is "
                 "temporary, and keeping it 20-30 cm away is enough. "
                 "Device-interference studies support both the risk and "
                 "the distance. He opens on an alarming line ('pueden ... "
                 "anular el efecto de los marcapasos') and spends the rest "
                 "of the video defusing it, so it reads as an explainer "
                 "rather than a debunk: NO_MISINFO.",
        "claims": [
            {
                "text": "estos imanes, si se colocan cerca del pecho del "
                        "paciente, donde están implantados los marcapasos, "
                        "pueden activar ese modo",
                "start": 57.9, "end": 66.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:18334784", "PMID:35538270"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: these magnets, if placed near the chest where "
                         "the pacemaker is implanted, can trigger that "
                         "[magnet] mode. 18334784: household NdFeB magnets "
                         "influenced a pacemaker at 1-24 cm. 35538270: "
                         "consumer-product magnets triggered magnet mode in "
                         "all CIEDs at the surface.",
            },
            {
                "text": "mantengas la baliza en todo momento alejada del "
                        "pecho a unos 20 a 30 centímetros por si acaso es "
                        "más que suficiente",
                "start": 83.0, "end": 96.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35538270", "PMID:18334784"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: keep the beacon 20-30 cm from the chest at all "
                         "times; that is more than enough. 35538270: no "
                         "interaction at 15 cm. 18334784: strong NdFeB "
                         "magnets reached 24 cm, so '20-30 cm' is about "
                         "right rather than generous. Medium because the "
                         "beacon magnets themselves were not measured.",
            },
        ],
    },
    {
        "video_id": "v99",
        "topic": "COVID-19 vaccines / cancer",
        "case_tags": ["other_language", "uncertain_science", "multi_claim"],
        "confidence": "medium",
        "notes": "'If you got the COVID vaccine you need to know this': a "
                 "review of 69 studies and 333 patients who developed "
                 "cancer after vaccination, Italian and South Korean "
                 "population studies, three mechanisms, never tested for "
                 "cancer risk. The two population-study numbers are "
                 "reported correctly (Pescara HR 1.23 for cancer "
                 "hospitalisation; Korean 1-year HRs for thyroid, lung, "
                 "prostate, gastric). But the video omits that the Pescara "
                 "association reversed with a 12-month lag, came with lower "
                 "all-cause mortality, and was called preliminary because "
                 "of healthy-vaccinee bias. Under section 9 the two "
                 "SUPPORTED study descriptions decide: NO_MISINFO, with no "
                 "review trigger on the deciding claims. This is the rules' "
                 "known blind spot (true numbers, misleading frame), the "
                 "same pattern as batch-1 v68/v70, and the strongest case "
                 "in this part for a framing check in the critic (section "
                 "8).",
        "claims": [
            {
                "text": "en la prestigiosa revista médica Onco Target, se "
                        "acaba de publicar un análisis ... ha revisado más "
                        "de 69 estudios internacionales ... 333 pacientes "
                        "en 27 países desarrollaron cáncer poco después de "
                        "vacunarse",
                "start": 10.6, "end": 34.4,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Oncotarget just published an analysis "
                         "reviewing 69+ studies; 333 patients in 27 "
                         "countries developed cancer shortly after "
                         "vaccination. The Oncotarget search found no such "
                         "review; the nearest hit is a case report with a "
                         "literature review on haematopoietic cancers "
                         "(41954969), which is not this paper. Case reports "
                         "cannot establish causation in any case.",
            },
            {
                "text": "Los estudios poblacionales confirman la señal que "
                        "muchos de nosotros informamos",
                "start": 62.9, "end": 67.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:41013858"],
                "contradicting": ["PMID:40881928"],
                "confidence": "medium",
                "notes": "EN: population studies confirm the signal many of "
                         "us reported. The Korean cohort (41013858) reports "
                         "raised 1-year HRs for several cancers. The Pescara "
                         "cohort (40881928) found the cancer-hospitalisation "
                         "association 'was reversed when the minimum time "
                         "between vaccination and cancer hospitalization was "
                         "set to 12 months', with lower all-cause mortality, "
                         "and calls its findings preliminary. Studies point "
                         "both ways.",
            },
            {
                "text": "en Italia, analizando a 296.000 personas, se dieron "
                        "cuenta de que las hospitalizaciones por cáncer eran "
                        "un 23% más en vacunados",
                "start": 67.8, "end": 77.3,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:40881928"], "contradicting": [],
                "confidence": "high",
                "notes": "EN: in Italy, among 296,000 people, cancer "
                         "hospitalisations were 23% higher in the "
                         "vaccinated. 40881928: 296,015 residents, HR 1.23 "
                         "(1.11-1.37) for >=1 dose. The figure is right; "
                         "what it omits is in c2. The breast (54%) and "
                         "bladder (62%) figures said next are not in the "
                         "abstract and are not part of this row.",
            },
            {
                "text": "en Corea del Sur, analizando a 8.4 millones de "
                        "personas, descubrieron aumentos significativos en "
                        "cáncer de tiroides, de pulmón, de próstata y de "
                        "estómago",
                "start": 83.8, "end": 95.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:41013858"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: in South Korea, among 8.4 million people, "
                         "significant increases in thyroid, lung, prostate "
                         "and stomach cancer. 41013858 reports raised 1-year "
                         "HRs for thyroid, gastric, lung and prostate "
                         "cancers. The cohort size is not in the part of "
                         "the abstract read, hence medium.",
            },
            {
                "text": "la proteína [spike] de la vacuna persista en meses "
                        "en el cuerpo y puede dañar el ADN",
                "start": 106.7, "end": 111.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: the vaccine's spike protein persists for months "
                         "and can damage DNA. Whisper's 'al país' is "
                         "'spike'. The search found a tissue-persistence "
                         "report (38867495) and a hypothesis review "
                         "(40869200); nothing tests DNA damage in people.",
            },
            {
                "text": "Los fragmentos de ARN en las vacunas podrían "
                        "integrarse o alterar nuestros genes de forma "
                        "desconocida",
                "start": 111.3, "end": 118.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: RNA fragments in the vaccines could integrate "
                         "into or alter our genes. The only direct study "
                         "(35723296) is in a human liver cancer cell line in "
                         "vitro. In-vitro only for a claim about people: "
                         "INSUFFICIENT under rule 1.",
            },
            {
                "text": "estas nuevas vacunas nunca se testearon por riesgo "
                        "de cáncer. No hay seguimiento a largo plazo, no hay "
                        "seguimiento de más de 42 días",
                "start": 123.8, "end": 134.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: these new vaccines were never tested for "
                         "cancer risk; there is no long-term follow-up, none "
                         "beyond 42 days. A regulatory fact of record "
                         "(licensing studies) not retrieved here.",
                "source": "both",
            },
        ],
    },
    {
        "video_id": "v100",
        "topic": "diabetes / stem-cell therapy",
        "case_tags": ["screen_only", "other_language"],
        "confidence": "medium",
        "notes": "Five seconds with no speech: a news card reading '¿ADIÓS A "
                 "LA INSULINA? Logran revertir la diabetes tipo 1 y tipo 2 "
                 "mediante reprogramación celular. Científicos chinos logran "
                 "que el páncreas vuelva a funcionar de forma natural.' The "
                 "type 1 half refers to a real first-in-human case: one "
                 "patient insulin-independent a year after chemically "
                 "induced iPSC islets. The type 2 half was not retrieved. "
                 "'The pancreas works again' misdescribes a graft placed "
                 "under the abdominal rectus sheath. Overstated headline, "
                 "but its checkable core is supported: NO_MISINFO. Without "
                 "OCR there is nothing to label at all.",
        "claims": [
            {
                "text": "Logran revertir la diabetes tipo 1 ... mediante "
                        "reprogramacion celular",
                "start": 0.0, "end": 4.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39326417"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: they have reversed type 1 diabetes by cellular "
                         "reprogramming. 39326417 (Cell 2024): one patient "
                         "given autologous chemically induced "
                         "pluripotent-stem-cell islets 'achieved sustained "
                         "insulin independence starting 75 days "
                         "post-transplantation'. One patient in a phase I "
                         "trial, so medium: the headline's 'logran revertir' "
                         "is true of that case and no more.",
                "source": "screen",
            },
            {
                "text": "Logran revertir la diabetes ... tipo 2 mediante "
                        "reprogramacion celular",
                "start": 0.0, "end": 4.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: ...and type 2. The search for stem-cell islet "
                         "transplantation in type 2 diabetes did not return "
                         "the case it presumably refers to.",
                "source": "screen",
            },
            {
                "text": "Cientificos chinos logran que el pancreas vuelva a "
                        "funcionar de forma natural",
                "start": 0.0, "end": 4.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Chinese scientists get the pancreas working "
                         "again naturally. In 39326417 the islets were "
                         "transplanted beneath the abdominal anterior rectus "
                         "sheath, so in that case the patient's pancreas did "
                         "not resume function. The headline may refer to "
                         "the unretrieved type 2 case, so this is left "
                         "INSUFFICIENT rather than CONTRADICTED.",
                "source": "screen",
            },
        ],
    },
    {
        "video_id": "v101",
        "topic": "food safety / insects in strawberries",
        "case_tags": ["debunking", "other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "@malditobulo answering the TikTok trend of soaking "
                 "strawberries in salt water to make 'bugs' come out: no "
                 "monster bugs, at most a fly larva, and harmless if eaten. "
                 "A fact-checker's own debunk with no PubMed evidence on "
                 "either side (the only retrievable literature on "
                 "spotted-wing drosophila is agricultural). "
                 "CANNOT_RECOGNIZE, sent to review as a possible debunk.",
        "claims": [
            {
                "text": "salen todo tipo de bicho de ellas ... pero no van a "
                        "salir cien pies como en esta clase de vídeos",
                "start": 17.4, "end": 36.3,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: all kinds of bugs come out of them ... but "
                         "centipedes are not going to come out like in "
                         "these videos. The trend's claim, quoted and then "
                         "refuted ('No saldrán bichos monstruosos' on "
                         "screen). Nothing retrieved addresses it.",
                "source": "both",
            },
            {
                "text": "Si las comes, tranquil@ ¡No es peligroso!",
                "start": 44.0, "end": 50.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: if you eat them, relax, it is not dangerous. "
                         "Screen caption, said in other words in speech "
                         "('puedes estar tranquilo'). 'Drosophila suzukii "
                         "larvae fruit consumption' returned only pest-"
                         "control papers.",
                "source": "both",
            },
        ],
    },
    {
        "video_id": "v102",
        "topic": "alcohol / hangover myths",
        "case_tags": ["debunking", "other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "@malditobulo on hangover myths, rapid-fire: more alcohol "
                 "means a worse hangover (yes); the only prevention is not "
                 "drinking; eat first and alternate with water; the beer "
                 "the next day, greasy food and coffee do not help; "
                 "ibuprofen if anything. The refuted remedies are untested "
                 "rather than shown false, so DEBUNKING cannot fire. The "
                 "dose-response claim is SUPPORTED, so NO_MISINFO fires "
                 "before the possible-debunk rule -- the batch-1 v68/v70 "
                 "pattern.",
        "claims": [
            {
                "text": "¿Es eso cierto de que cuanto más alcohol se tome, "
                        "peor cuerpo se tendrá el día siguiente? ¡Afirmativo!",
                "start": 6.9, "end": 13.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:26280593"], "contradicting": [],
                "confidence": "high",
                "notes": "EN: is it true that the more alcohol you drink, the "
                         "worse you feel the next day? Affirmative. Pooled "
                         "EMA data from 274 drinkers (26280593): 'Participants "
                         "who consumed a greater quantity of alcohol the "
                         "prior day reported more severe hangover symptoms'.",
                "source": "both",
            },
            {
                "text": "intenta hacerlo con el estómago lleno, alternar "
                        "vasos de agua antes, durante y después de las copas",
                "start": 16.8, "end": 26.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: try to drink on a full stomach and alternate "
                         "glasses of water before, during and after. "
                         "39069212: water during or after drinking had 'only "
                         "a modest effect in preventing next-day hangover' "
                         "(survey data); nothing retrieved tests the full "
                         "stomach. Too weak and indirect to support.",
                "source": "both",
            },
            {
                "text": "¿la cerveza nivela el pH?",
                "start": 28.0, "end": 31.8,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: [does] beer [the next day] balance your pH? "
                         "Caption plus 'ir de cañas al día siguiente ... "
                         "¿verdad? NOOOO'. 'Hair of the dog' search returned "
                         "nothing.",
                "source": "both",
            },
            {
                "text": "¿Te va a aprecier comida grasiente al día siguiente? "
                        "Si ¿Que te vas a sentar bien? ¡Que nooo!",
                "start": 31.8, "end": 36.8,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: you'll crave greasy food the next day - yes; "
                         "will it do you good? No! Whisper's 'aprecier' and "
                         "'grasiente' are 'apetecer' and 'grasienta'. "
                         "34431182 (daily hangover severity and food intake) "
                         "was retrieved but not read as testing relief.",
                "source": "both",
            },
            {
                "text": "El café sí, ya que sí ... TAMPOCO!",
                "start": 36.8, "end": 39.3,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: coffee does [help], surely? Not that either! "
                         "The 2005 systematic review of hangover RCTs "
                         "(16373736) tested no caffeine arm.",
            },
            {
                "text": "Ante la duda mejor ibuprofeno",
                "start": 39.3, "end": 41.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: when in doubt, ibuprofen. Whisper: 'y "
                         "bufrofeno'. 16373736: 'No compelling evidence "
                         "exists to suggest that any conventional or "
                         "complementary intervention is effective'; "
                         "ibuprofen itself was not among the trials, and "
                         "'ibuprofen hangover' returned nothing.",
            },
        ],
    },
    {
        "video_id": "v103",
        "topic": "nutrition / aphrodisiac foods",
        "case_tags": ["debunking", "other_language"],
        "confidence": "medium",
        "notes": "@malditobulo (Maldita Ciencia): chocolate is not an "
                 "aphrodisiac, and aphrodisiac foods are an urban legend. "
                 "The chocolate claim is tested directly by a study of 163 "
                 "women whose higher sexual-function scores among "
                 "chocolate eaters vanished after adjusting for age, so the "
                 "refuted claim is CONTRADICTED and the video is DEBUNKING. "
                 "The blanket 'no food has any such property' goes further "
                 "than the evidence and is INSUFFICIENT.",
        "claims": [
            {
                "text": "el chocolate es afrodisiaco y aumenta nuestro deseo "
                        "sexual",
                "start": 0.0, "end": 9.2,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:16681473"],
                "confidence": "medium",
                "notes": "EN: chocolate is an aphrodisiac and increases our "
                         "sexual desire. Asked and answered 'Pues no, no es "
                         "cierto'. 16681473: 'when data are adjusted for age "
                         "FSFI scores are similar, regardless of chocolate "
                         "consumption'. One cross-sectional study in women, "
                         "hence medium.",
                "source": "both",
            },
            {
                "text": "no hay evidencias de que el chocolate ni ningún otro "
                        "alimento tenga propiedades relacionadas con nuestro "
                        "apetito sexual",
                "start": 9.2, "end": 19.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: there is no evidence that chocolate or any "
                         "other food has properties related to sexual "
                         "appetite. Whisper's 'fetito' is 'apetito'. The "
                         "review 30255750 concludes nutritional factors 'may "
                         "affect' sexual health with weak evidence for "
                         "supplements; that neither confirms nor refutes a "
                         "claim about every food.",
            },
        ],
    },
    {
        "video_id": "v104",
        "topic": "nutrition / vitamin C in orange juice",
        "case_tags": ["debunking", "other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "@malditobulo answering a comment: the idea that orange "
                 "juice must be drunk at once or its vitamins 'escape' is "
                 "a hoax; vitamin C stays intact up to 12 hours. Plausible, "
                 "but PubMed returned nothing on freshly squeezed juice at "
                 "home (only high-pressure-processed juice in cold "
                 "storage). Every claim is INSUFFICIENT: CANNOT_RECOGNIZE, "
                 "sent to review as a possible debunk.",
        "claims": [
            {
                "text": "el zumo de naranja hay que tomarlo rápido, al "
                        "instante, porque si no se [van] las vitaminas",
                "start": 0.0, "end": 12.4,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: you have to drink orange juice immediately "
                         "or the vitamins go. Whisper's 'se elevan' is 'se "
                         "van' (the comment on screen: 'que si no te lo "
                         "bebes se van'). 'es un bulo' makes it REFUTES. "
                         "12537436 covers high-pressure-processed juice in "
                         "refrigerated storage, not this.",
                "source": "both",
            },
            {
                "text": "hasta 12 horas después de exprimirlo, puedes "
                        "tomártelo tranquilamente porque la vitamina va a "
                        "seguir intacta",
                "start": 12.4, "end": 22.2,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: up to 12 hours after squeezing you can drink "
                         "it calmly because the vitamin stays intact. Two "
                         "searches on ascorbic acid in fresh juice over "
                         "hours returned nothing.",
                "source": "both",
            },
        ],
    },
    {
        "video_id": "v105",
        "topic": "nutrition / ultra-processed snacks",
        "case_tags": ["debunking", "other_language"],
        "confidence": "medium",
        "notes": "@malditobulo: corn puffs ('gusanitos') burn because they "
                 "are hollow, dry, starch and fat, not because they are "
                 "made of petroleum. Safe ingredients, but ultra-processed "
                 "and not recommended. The refuted petroleum claim cannot "
                 "be checked against the allowed sources. The "
                 "ultra-processed-food claim is SUPPORTED by an umbrella "
                 "review, so NO_MISINFO fires first.",
        "claims": [
            {
                "text": "Los gusanitos y otros aperitivos están hechos de "
                        "petróleo",
                "start": 1.2, "end": 15.4,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: corn puffs and similar snacks are made of "
                         "petroleum. A food-composition fact of record; "
                         "corn puffs are not in FoodData Central's "
                         "foundation set and no reference was fetched.",
            },
            {
                "text": "son productos ultra procesados que no nos aportan "
                        "demasiado ... así que recomendables tampoco son",
                "start": 31.1, "end": 41.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:38363072"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: they are ultra-processed products that don't "
                         "give us much, so they are not recommended either. "
                         "38363072 (umbrella review, GRADE): moderate-"
                         "certainty associations of ultra-processed food "
                         "with all-cause mortality, cardiovascular disease, "
                         "type 2 diabetes and colorectal cancer.",
            },
        ],
    },
    {
        "video_id": "v106",
        "topic": "gynaecology / home remedies (vaginal garlic)",
        "case_tags": ["other_language", "missing_evidence"],
        "confidence": "high",
        "notes": "Instructions to insert a raw, unwashed, peeled garlic clove "
                 "into the vagina for five nights to end odours and "
                 "'parasites', because 'garlic is a natural antibiotic'. "
                 "Potentially harmful, but untested: the systematic review "
                 "of complementary therapies for vaginitis finds garlic "
                 "has only in-vitro potential and no in-vivo studies. "
                 "INSUFFICIENT throughout, so CANNOT_RECOGNIZE. A clear case "
                 "where section 7's rule leaves a harmful remedy unflagged.",
        "claims": [
            {
                "text": "usted coja un diente de ajo ... crudo sin lavar y "
                        "pelado por cinco noches se le introduce en su "
                        "vagina ... y usted me va a decir a mí si funciona",
                "start": 22.1, "end": 46.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "EN: take a raw, unwashed, peeled garlic clove and "
                         "insert it into your vagina for five nights... you "
                         "tell me whether it works. The screen supplies what "
                         "it is for: 'Remedio ... adiós ... mal olor ... "
                         "parásito'. 12719677: garlic shows 'some in vitro "
                         "potential for the treatment of vaginitis, but the "
                         "lack of in vivo studies preclude their "
                         "recommendation'. In-vitro only: INSUFFICIENT.",
                "source": "both",
            },
            {
                "text": "Ya q el ajo es un antibiotico Natural",
                "start": 22.0, "end": 26.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: since garlic is a natural antibiotic. "
                         "Screen-only. 34394014 reviews antibacterial "
                         "organosulfur compounds in vitro; no clinical "
                         "antibiotic effect in this use was retrieved.",
                "source": "screen",
            },
        ],
    },
    {
        "video_id": "v107",
        "topic": "ophthalmology / cosmetic laser iris depigmentation",
        "case_tags": ["accurate", "other_language", "uncertain_science"],
        "confidence": "medium",
        "notes": "An ophthalmologist warning against the laser procedure "
                 "that changes eye colour by removing iris pigment. It is "
                 "not endorsed by ophthalmology bodies and can cause "
                 "complications that endanger vision. The approval claim "
                 "is SUPPORTED. The risk claim is MIXED: a 2026 case report "
                 "of sight-threatening pressure rise against a 1,176-eye "
                 "series from the procedure's own developer reporting no "
                 "change in vision or pressure. NO_MISINFO. The warning "
                 "frames no myth to refute, so it is not a debunk.",
        "claims": [
            {
                "text": "este procedimiento no está avalado por los "
                        "organismos internacionales de oftalmología",
                "start": 8.1, "end": 15.7,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35061240"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: this procedure is not endorsed by "
                         "international ophthalmology bodies. Whisper: "
                         "'ortalmología'. 35061240: laser iris "
                         "depigmentation 'has been used clinically for "
                         "aesthetic purposes without receiving official "
                         "approval or licensing'. Approval, not professional "
                         "endorsement, hence medium.",
            },
            {
                "text": "Utilizan un láser para remover el pigmento que "
                        "tenemos en el iris, pudiendo producir muchas "
                        "complicaciones para nuestros ojos, incluso poniendo "
                        "en riesgo nuestra visión",
                "start": 15.7, "end": 26.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:41982480"],
                "contradicting": ["PMID:33484383"],
                "confidence": "medium",
                "notes": "EN: they use a laser to remove the iris pigment, "
                         "which can cause many complications, even "
                         "endangering vision. 41982480: laser iris "
                         "depigmentation 'may be associated with serious, "
                         "sight-threatening complications, including "
                         "significant increases in IOP'. 33484383: 1,176 "
                         "eyes, no significant change in corrected vision or "
                         "pressure, self-limited iritis in 25%. A case "
                         "report against a large uncontrolled series from "
                         "one centre: genuinely unsettled.",
            },
        ],
    },
]

# Why the derived label differs from the label the source implies
# (compare_external.py). Written after the claims above were labelled.
_EXTERNAL_REASONS = {
    "v84": "Nasal dry-ginger powder against COVID-19 has never been tested, "
           "so every claim is INSUFFICIENT_EVIDENCE, not false.",
    "v85": "No study establishes or refutes a 'wind turbine syndrome', and "
           "the sleep claim is MIXED (self-reported disturbance vs. no "
           "objective effect).",
    "v89": "The nail-polish trend it refutes has never been studied, so the "
           "refuted claim is INSUFFICIENT; sent to review as a possible "
           "debunk.",
    "v92": "Grounding has no controlled human trials on either side; "
           "untested panacea claims are INSUFFICIENT, not CONTRADICTED.",
    "v94": "Same clip as v93 without the on-screen immunosuppression banner; "
           "only ministry statistics remain, and they are not checkable "
           "against the allowed sources.",
    "v95": "The fact-check concerns claims linking the cluster to vaccines; "
           "this video never mentions vaccines, and its checkable claims "
           "(common tumour types, ionizing radiation) are SUPPORTED.",
    "v96": "Nothing retrieved measures heavy metals in the packing oil "
           "itself, so the claims are INSUFFICIENT rather than false.",
    "v98": "The cardiologist explains rather than refutes: his claims about "
           "magnet mode and safe distance are SUPPORTED, and no false claim "
           "is refuted.",
    "v99": "The two study figures it quotes (Pescara HR 1.23, Korean 1-year "
           "HRs) are reported correctly, so NO_MISINFO fires; the "
           "misleading frame (omitted reversal at 12 months, lower "
           "mortality) is beyond the section 9 rules.",
    "v101": "Neither the refuted 'bugs in strawberries' claim nor 'harmless "
            "if eaten' has any PubMed evidence; sent to review as a "
            "possible debunk.",
    "v102": "The refuted hangover remedies are untested rather than shown "
            "false, and the supported dose-response claim makes it "
            "NO_MISINFO before the possible-debunk rule.",
    "v104": "No study of vitamin C in freshly squeezed juice over hours was "
            "retrieved, so the refuted claim is INSUFFICIENT; sent to "
            "review as a possible debunk.",
    "v105": "The refuted 'made of petroleum' claim is a composition fact no "
            "allowed source covers; the supported ultra-processed-food "
            "claim gives NO_MISINFO.",
    "v106": "Vaginal garlic has only in-vitro evidence and no human "
            "studies, so the remedy is INSUFFICIENT, not CONTRADICTED.",
    "v107": "A warning rather than a refutation: the approval claim is "
            "SUPPORTED and the risk claim MIXED, with no false claim "
            "refuted.",
}
for _v in LABELS:
    if _v["video_id"] in _EXTERNAL_REASONS:
        _v["external_reason"] = _EXTERNAL_REASONS[_v["video_id"]]
