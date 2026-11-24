"""Batch 2, part d: v158-v181. Rules and format as labels.py; see
labels_batch2.py for the batch-2 additions (EN: glosses, external_reason).

Every PMID below was returned by evidence.py (searches and abstracts cached
under evidence_cache/) and its abstract was read before it was cited.
"""

LABELS = [
    {
        "video_id": "v158",
        "topic": "none (non-health)",
        "case_tags": ["out_of_scope"],
        "confidence": "medium",
        "notes": "No speech and no on-screen text: Whisper and EasyOCR both "
                 "return nothing. Frames sampled every 4 seconds show "
                 "AI-generated-looking models in sportswear posing in a gym, "
                 "with no caption, product or assertion. Nothing in the video "
                 "makes a health statement, so it is out of scope rather than "
                 "a health video with no claims. Medium confidence only "
                 "because audio-free imagery could be read as implicit body "
                 "or fitness messaging.",
        "claims": [],
    },
    {
        "video_id": "v159",
        "external_reason": (
            "The vibration-plate equivalence is almost certainly false, "
            "but nothing retrieved tests it or gives a running figure to "
            "set against the measured VO2, so it is INSUFFICIENT."),
        "topic": "exercise / fitness equipment advert",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "A sales video for a vibration plate (on-screen brand "
                 "'ROTAI'), voiced like a deal alert. One health claim, an "
                 "equivalence between ten minutes on the plate and an hour of "
                 "jogging. The rest is price, accessories and portability.",
        "claims": [
            {
                "text": "just practicing for 10 minutes a day is equivalent "
                        "to jogging for an hour",
                "start": 14.2, "end": 17.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Almost certainly false, but nothing retrieved tests "
                         "the equivalence. Rittweger 2001 (PMID:11822476) and "
                         "2002 (PMID:12215962) measured whole-body vibration "
                         "raising oxygen uptake by about 4.5 ml/min/kg over "
                         "the same posture without vibration, and Kang 2016 "
                         "(PMID:25942015) found only high-amplitude vibration "
                         "raised VO2 at all. That is a small fraction of what "
                         "running costs, but no retrieved source gives a "
                         "running figure to set against it (the 2024 "
                         "Compendium's open full text, PMID:38242596, does "
                         "not list running METs in its body text), so under "
                         "section 7 this stays INSUFFICIENT rather than "
                         "CONTRADICTED. The PMIDs are left out of the "
                         "evidence columns because none of them is evidence "
                         "for or against the equivalence as stated.",
            },
        ],
    },
    {
        "video_id": "v160",
        "external_reason": (
            "No assertion is made in speech or on screen (a tongue close-"
            "up over a song lyric), so there is no claim to judge."),
        "topic": "oral health (tongue shown, no assertion)",
        "case_tags": [],
        "confidence": "medium",
        "notes": "Seven seconds: a close-up of a person's tongue with a "
                 "fissured, patchy surface (it looks like geographic tongue) "
                 "over a song lyric ('Love it and fight it, accuse it and "
                 "deny it'). Health content, a visible oral condition, but "
                 "nothing is asserted about it in speech or on screen. No "
                 "checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v161",
        "topic": "nutrition / fruit health benefits",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "A 'best fruit for X' list read over burned-in captions, "
                 "ending 'Let food be your medicine'. Six claims, each a "
                 "superlative ('the best fruit for'). The superlative is "
                 "the claim (section 4: keep the qualifiers), and no "
                 "retrieved study compares fruits head to head for any of "
                 "these outcomes. So every claim is INSUFFICIENT, even where "
                 "the fruit itself has some evidence (blueberries and "
                 "cognition, pomegranate and blood pressure).",
        "claims": [
            {
                "text": "The best fruit for boosting immunity is oranges",
                "start": 0.0, "end": 5.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:23440782"],
                "confidence": "medium",
                "notes": "The vitamin C route is the obvious reading. The "
                         "Cochrane review (PMID:23440782) found regular "
                         "supplementation did not reduce cold incidence in "
                         "the general population, with a modest effect on "
                         "duration. That weighs against an immunity benefit "
                         "but tests vitamin C supplements, not oranges, and "
                         "nothing compares fruits. Cited on the "
                         "contradicting side because it is the closest "
                         "direct test, and it is not enough for "
                         "CONTRADICTED.",
            },
            {
                "text": "The best fruit for digestion is pineapple",
                "start": 5.7, "end": 10.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Searched pineapple/bromelain and digestion: only a "
                         "mouse study of pineapple protease (PMID:36355110) "
                         "and an in-vitro digestion model (PMID:34387509). "
                         "Animal and in-vitro only, so INSUFFICIENT "
                         "(labels.py rule 1). Not cited as support because "
                         "neither tests digestion in people.",
            },
            {
                "text": "The best fruit for brain health is blueberries",
                "start": 5.7, "end": 10.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:30999017"], "contradicting": [],
                "confidence": "medium",
                "notes": "A systematic review of RCTs (PMID:30999017) found "
                         "blueberries 'may improve some measures of cognitive "
                         "performance', with heterogeneous designs and doses. "
                         "That supports blueberries helping, not their being "
                         "the best fruit for it.",
            },
            {
                "text": "The best fruit for reducing stress is bananas",
                "start": 10.7, "end": 16.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Searched bananas and stress: the only relevant hit "
                         "is about plasma oxidative stress (PMID:18264767), "
                         "a different meaning of 'stress'. Nothing tests "
                         "psychological stress.",
            },
            {
                "text": "The best fruit for heart health is pomegranate",
                "start": 10.7, "end": 16.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:37461211"], "contradicting": [],
                "confidence": "medium",
                "notes": "A meta-analysis of 14 trials (PMID:37461211) "
                         "found pomegranate juice lowered systolic blood "
                         "pressure by about 5 mmHg, with the benefit lost "
                         "after two months. That is a surrogate marker for "
                         "juice, not heart outcomes for the fruit, and "
                         "nothing ranks it against other fruits.",
            },
            {
                "text": "The best fruit for detoxing the liver is lemon",
                "start": 16.6, "end": 21.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Searched lemon and liver detoxification: nothing "
                         "tests it in people. The hits are drug-interaction "
                         "and modified-pectin reviews. 'Detoxing the liver' "
                         "is also too vague to test as stated.",
            },
        ],
    },
    {
        "video_id": "v162",
        "external_reason": (
            "A chemist explains why cheese substitutes char; his "
            "nutritional-difference claim is SUPPORTED and he refutes "
            "nothing, so the rules see accurate content, not a debunk."),
        "topic": "nutrition / cheese analogues",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "Spanish. A chemistry communicator (@breakingvlad) explains "
                 "a viral clip in which real cheese melts under a flame and a "
                 "cheese substitute chars: casein softens on heating, while "
                 "substitutes rely on starches and oils. The food-chemistry "
                 "explanation itself is not a health claim; the two claims "
                 "kept are about what substitutes contain and how they "
                 "differ nutritionally.",
        "claims": [
            {
                "text": "los sucedáneos de queso suelen llevar una parte "
                        "proporcional de queso, pero se le añaden almidones "
                        "y otros aditivos para abaratar los costes",
                "start": 20.9, "end": 29.4,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:40807638"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: cheese substitutes usually contain some "
                         "cheese, but starches and other additives are added "
                         "to cut costs. A benchmarking study of retail "
                         "plant-based cheese analogues (PMID:40807638) found "
                         "them 'stabilized largely by solid fats, starch, and "
                         "hydrocolloids', which backs the starch half. But "
                         "those products contain no dairy cheese, and nothing "
                         "retrieved describes dairy-based substitutes with "
                         "'a proportional part of cheese'. Partial, so "
                         "INSUFFICIENT.",
            },
            {
                "text": "su composición es bastante diferente y su aporte "
                        "nutricional también",
                "start": 42.1, "end": 51.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:40807638"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: their composition is quite different, and so "
                         "is their nutritional contribution. PMID:40807638: "
                         "plant-based analogues had 0.1-1.7 g protein per "
                         "100 g against 25 g in cheddar and 12.9-18.2 g in "
                         "processed cheese. Medium confidence because those "
                         "are one kind of substitute (plant-based) and the "
                         "video means substitutes in general.",
            },
        ],
    },
    {
        "video_id": "v163",
        "external_reason": (
            "The brain-tumour cluster link is promoted but untested in "
            "anything retrievable; a dismissal by the hospital and union "
            "is not a section 6 source."),
        "topic": "occupational health / cancer cluster",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "A nurse-creator (@aprnbeauty_81) celebrating that her post "
                 "about brain tumours among nurses at Newton-Wellesley "
                 "Hospital went viral. The on-screen text runs the whole "
                 "video: 'Nurse Gang we made the Story about the Brain "
                 "Tumors Go Viral! Now the hospital can't sweep this under "
                 "the Rug!!' The health claim is implicit but plain: the "
                 "tumours are linked to working there. Nothing in PubMed "
                 "touches this cluster. An environmental investigation is "
                 "the kind of record that settles it, and it is outside "
                 "the section 6 allow-list.",
        "claims": [
            {
                "text": "I worked there, I developed this brain tumor. I had "
                        "no idea that there was a connection here",
                "start": 97.1, "end": 103.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "She is relaying nurses' messages, but she adopts "
                         "the link ('the hospital can't get away with this "
                         "now'; 'Those nurses deserve Answers!' on screen), "
                         "so ENDORSES. Searched 'Newton-Wellesley brain "
                         "tumor nurses' and 'Newton-Wellesley Hospital brain "
                         "tumors': nothing relevant. Whether workplace "
                         "exposure caused the tumours is untested here, so "
                         "INSUFFICIENT.",
            },
        ],
    },
    {
        "video_id": "v164",
        "topic": "nutrition / carnivore diet",
        "case_tags": ["other_language", "uncertain_science"],
        "confidence": "medium",
        "notes": "French. A day-by-day account of eating only meat for a "
                 "week, from feeling great on day one to less inflammation, "
                 "focus and joint relief by day seven. Every claim is about "
                 "a specific day in a one-week meat-only diet, and nothing "
                 "retrieved tests that. The ketogenic-diet literature is "
                 "indirect (weeks to months, and a ketogenic diet is not a "
                 "meat-only one), so it is cited but does not decide any "
                 "claim. Whisper heard 'en ces thoses' for 'en cétose'; "
                 "the caption reads 'CETOSE'.",
        "claims": [
            {
                "text": "Au troisième jour, tu entres en cétose. Ton corps "
                        "commence à brûler les graisses pour produire de "
                        "l'énergie au lieu du sucre",
                "start": 16.1, "end": 22.8,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: on the third day you enter ketosis; your body "
                         "starts burning fat for energy instead of sugar. "
                         "Speech is misheard ('en ces thoses'); the caption "
                         "'CETOSE' confirms the word. Ketosis within a few "
                         "days of near-zero carbohydrate is textbook "
                         "physiology, but searches for its time course "
                         "returned nothing usable, and no section 6 "
                         "reference was retrieved, so the day-3 figure "
                         "stays INSUFFICIENT.",
            },
            {
                "text": "Résultat, la perte de poids devient plus facile",
                "start": 22.8, "end": 26.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:23651522", "PMID:34934897"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: as a result, weight loss becomes easier. A "
                         "meta-analysis of very-low-carbohydrate ketogenic "
                         "versus low-fat diets (PMID:23651522) found about "
                         "0.9 kg more weight loss over a year or more, and a "
                         "self-selected survey of 2029 carnivore-diet "
                         "followers (PMID:34934897) reported lower BMI. "
                         "Neither tests one week of meat only, and the "
                         "survey is self-report with no comparison group.",
            },
            {
                "text": "Le quatrième jour, l'inflammation dans ton corps "
                        "diminue",
                "start": 26.0, "end": 29.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:38219223"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: on the fourth day, inflammation in your body "
                         "decreases. A meta-analysis of RCTs (PMID:38219223) "
                         "found ketogenic diets lowered TNF-alpha and IL-6 "
                         "but not other markers, over weeks. Nothing tests "
                         "day four, or a meat-only diet.",
            },
            {
                "text": "même les douleurs dans les articulations commencent "
                        "à disparaître",
                "start": 29.1, "end": 35.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "UNSUPPORTED",
                "claim_category": "treatment_efficacy",
                "unsupported_reason": "Claims a meat-only diet makes joint pain disappear; nothing retrieved tests it.",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: even joint pains begin to disappear. Nothing "
                         "retrieved tests joint pain on a carnivore or "
                         "ketogenic diet.",
            },
            {
                "text": "ton organisme s'adapte complètement et tire enfin "
                        "profit des nutriments biodisponibles de la viande",
                "start": 35.1, "end": 42.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: your body fully adapts and finally benefits "
                         "from the bioavailable nutrients in meat. 'Fully "
                         "adapts' and 'finally benefits' name no measurable "
                         "outcome.",
            },
        ],
    },
    {
        "video_id": "v165",
        "external_reason": (
            "'Acne is autoimmune' is only 'not classified as', which "
            "section 7 keeps INSUFFICIENT; his diet-triggers-acne claim "
            "is SUPPORTED."),
        "topic": "dermatology / acne and diet",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "A podcast clip (@paulsaladinomd2): acne is 'absolutely "
                 "autoimmune' and food elimination can find the trigger. The "
                 "kale/thyroid, spinach/joint-pain and almond/acne lines are "
                 "explicitly 'examples that are random', so they are not "
                 "recorded as claims. The autoimmune claim is the "
                 "questionable one, but the retrieved literature describes "
                 "acne as a chronic inflammatory disease without saying it "
                 "is not autoimmune. Section 7 does not let that silence "
                 "count as contradiction. The diet-triggers-acne claim is "
                 "supported, so the rules give NO_MISINFO.",
        "claims": [
            {
                "text": "acne is absolutely autoimmune",
                "start": 0.0, "end": 4.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Repeated at 55.7s ('it is an autoimmune thing'), "
                         "recorded once. The pathogenesis review retrieved "
                         "(PMID:35468121) calls acne 'a "
                         "chronic inflammatory disease of the pilosebaceous "
                         "unit' and list hyperkeratinisation, sebum and "
                         "Cutibacterium acnes, with no autoimmune mechanism, "
                         "and a search for 'acne autoimmune disease' found "
                         "nothing that tests it. That is 'not classified "
                         "as', which section 7 keeps INSUFFICIENT. Not cited "
                         "in either column because the review does not "
                         "address autoimmunity.",
            },
            {
                "text": "there are foods that can trigger acne in people",
                "start": 53.6, "end": 55.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35373155", "PMID:29778512"],
                "contradicting": [],
                "confidence": "high",
                "notes": "A systematic review (PMID:35373155) found high "
                         "glycemic index and glycemic load diets "
                         "pro-acnegenic, supported by RCTs, with mixed "
                         "evidence for dairy. A meta-analysis of "
                         "observational studies (PMID:29778512) found "
                         "higher dairy and milk intake associated with "
                         "acne.",
            },
        ],
    },
    {
        "video_id": "v166",
        "external_reason": (
            "He debunks AI deepfakes of himself, not a health claim; the "
            "one health line shown is NOT_VERIFIABLE, which no section 9 "
            "rule can score."),
        "topic": "health misinformation / AI deepfakes of clinicians",
        "case_tags": ["other_language", "debunking"],
        "confidence": "medium",
        "notes": "Spanish. A pharmacist (@farmaceuticofernandez) warns that "
                 "AI-generated fake accounts use his face and voice to give "
                 "false health advice and sell products, and plays one: 'Si "
                 "tu mujer duerme de lado ... dormir de lado no es una "
                 "coincidencia' (screen: 'Nunca Ignores Si Tu Mujer Duerme "
                 "De Lado'; another fake is titled 'Por qué dormir con "
                 "ventilador es peligroso'). A real debunk, but of the "
                 "source rather than of a checkable health claim. The one "
                 "health assertion shown is not testable, so the rules give "
                 "CANNOT_RECOGNIZE without a review flag (the "
                 "possible-debunk rule needs MIXED or INSUFFICIENT, not "
                 "NOT_VERIFIABLE). Worth a reviewer's look as a debunking "
                 "video the rules cannot see.",
        "claims": [
            {
                "text": "Si tu mujer duerme de lado, valora[la] más de lo "
                        "que te das cuenta, porque dormir de lado no es una "
                        "coincidencia",
                "start": 24.2, "end": 29.6,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: if your wife sleeps on her side, value her "
                         "more than you realise, because sleeping on her "
                         "side is no coincidence. This is the deepfake's "
                         "line, played as an example of advice that is 'not "
                         "true' ('no son ciertos'), so REFUTES. Low "
                         "confidence: he refutes the fake accounts' advice "
                         "in general, not this sentence specifically. "
                         "Whisper has 'valora la' for 'valórala'. The claim "
                         "itself implies some unstated meaning in a sleeping "
                         "position and cannot be tested.",
            },
        ],
    },
    {
        "video_id": "v167",
        "external_reason": (
            "The stage-four cure-in-40-days and sugar-starving claims are"
            " untested (ketogenic and fasting reviews find insufficient "
            "evidence), and the Hindi transcript is too garbled for "
            "confident claims."),
        "topic": "cancer / diet and alternative remedies",
        "case_tags": ["other_language", "noisy_audio"],
        "confidence": "low",
        "notes": "Hindi, with English phrases. A man at a press conference "
                 "says a stage-four metastatic cancer given a 3% chance came "
                 "back (was cured) within forty days on a diet: no sugar and "
                 "no carbohydrates ('starve' the cancer), neem leaves, raw "
                 "turmeric, lemon and apple cider vinegar, and eating before "
                 "evening then not until 10 the next morning. He adds that "
                 "the same treatment works for fatty liver, and that his own "
                 "fatty liver went and he lost 25 kg. Whisper's Hindi is "
                 "badly garbled. The claims are quoted from the transcript "
                 "as transcribed (so the Devanagari is often misspelt), "
                 "with the reading in each EN gloss. All confidence is low "
                 "for that reason. EasyOCR is English-only, so any "
                 "Devanagari captions are missing; only one English "
                 "fragment ('Cutt') was read.",
        "claims": [
            {
                "text": "स्तेज फोर कंसर, मेटास्टिसिस, दोक्तर्स गिविंगर "
                        "त्रीपर्सें चान्स ... चालिस दिन में वापिस",
                "start": 27.0, "end": 35.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:38923748"],
                "confidence": "low",
                "notes": "EN: stage four cancer, metastasis, doctors giving "
                         "a three percent chance ... back in forty days [on "
                         "the diet]. Repeated at 74.8-78.6s ('स्केड फोर से "
                         "... चालिस लिन में'). A meta-analysis of ketogenic "
                         "diets in cancer (PMID:38923748) found 'insufficient "
                         "evidence to establish a definitive link' with "
                         "cancer outcomes, and the CA review of fasting "
                         "(PMID:34383300) says effects on prognosis 'remain "
                         "unknown'. Nothing tests a forty-day diet cure of "
                         "metastatic disease. Absence of evidence, so "
                         "INSUFFICIENT, not CONTRADICTED. The ketogenic "
                         "meta-analysis is cited on the contradicting side "
                         "because it is the closest test and found no "
                         "benefit on the variables it pooled.",
            },
            {
                "text": "कंसर को अगर गआप दो खाने में, शुगर नहीं दो ... "
                        "काबोईढरेट्ट्ट नहीं दो रोटी, तो की सैल खुदब खुदम "
                        "रहने लिए निंगात",
                "start": 47.0, "end": 58.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:38923748"],
                "confidence": "low",
                "notes": "EN: if you don't give the cancer sugar in your "
                         "food ... don't give carbohydrates, roti, then the "
                         "[cancer] cells [die] by themselves. The end of the "
                         "sentence is garbled; 'die by themselves' is the "
                         "evident sense. PMID:38923748: ketogenic diets "
                         "lowered glucose in cancer patients but showed no "
                         "significant improvement in the cancer-related "
                         "variables pooled. Not a test of cells dying, so "
                         "INSUFFICIENT.",
            },
            {
                "text": "नीम के पत्तों के पैसेल, कची हल्दी के पैसेल, "
                        "नीम्पू और सेप के सिरके पेक्या पैसेल",
                "start": 38.0, "end": 44.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: [it costs] the price of neem leaves, raw "
                         "turmeric, lemon and apple cider vinegar, i.e. "
                         "these were the cancer treatment. A systematic "
                         "review of RCTs of curcumin in cancer "
                         "(PMID:37111761) concludes the evidence is 'not "
                         "strong enough to support the therapeutic use of "
                         "curcumin in cancer'. The neem search returned "
                         "only reviews and extract studies with no human "
                         "trial in their titles. Not cited in the columns: "
                         "nothing tests the regimen, and curcumin is not raw "
                         "turmeric.",
            },
            {
                "text": "जो ईलाज कन्सर का है, वही पैटी लिवर का है",
                "start": 86.4, "end": 88.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: the treatment for cancer is the same as for "
                         "fatty liver. An equivalence between treatments "
                         "for two different diseases, with 'treatment' "
                         "undefined. Not testable as stated.",
            },
        ],
    },
    {
        "video_id": "v168",
        "external_reason": (
            "Of the four herbs, lemon balm's anxiety effect is SUPPORTED "
            "by a meta-analysis and none is contradicted; the others are "
            "INSUFFICIENT."),
        "topic": "mental health / herbal remedies for anxiety",
        "case_tags": ["multi_claim"],
        "confidence": "medium",
        "notes": "A naturopath ('Janine' on screen) recommending valerian, "
                 "skullcap, lemon balm and passionflower as 'anxiety "
                 "lowering herbs they don't want you to know about'. One "
                 "claim per herb (section 4: compound claims split). Lemon "
                 "balm has a supportive meta-analysis. Valerian and "
                 "passionflower have Cochrane reviews that find too little "
                 "to conclude, and skullcap has one null trial. Because one "
                 "claim is supported and none is contradicted, the rules "
                 "give NO_MISINFO. The misleading frame ('they don't want "
                 "you to know', 'without negative side effects') is not "
                 "something the claim rules can score.",
        "claims": [
            {
                "text": "[valerian is] known in the literature to really help "
                        "to decrease that nervousness and anxiety",
                "start": 20.9, "end": 36.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:17054208"],
                "confidence": "high",
                "notes": "Cochrane (PMID:17054208): one small RCT, no "
                         "difference from placebo on HAM-A; 'insufficient "
                         "evidence to draw any conclusions'. A null pilot "
                         "trial is not a contradiction, so INSUFFICIENT.",
            },
            {
                "text": "[skullcap is] known in the literature to really help "
                        "to decrease that nervousness and anxiety",
                "start": 20.9, "end": 36.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:23878109"],
                "confidence": "medium",
                "notes": "A placebo-controlled crossover trial in 43 mostly "
                         "non-anxious adults (PMID:23878109) found no "
                         "difference on the Beck Anxiety Inventory, though "
                         "mood improved. One small null trial in the wrong "
                         "population. INSUFFICIENT.",
            },
            {
                "text": "[lemon balm is] known in the literature to really "
                        "help to decrease that nervousness and anxiety",
                "start": 20.9, "end": 36.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:34449930"], "contradicting": [],
                "confidence": "medium",
                "notes": "Meta-analysis of RCTs (PMID:34449930): lemon balm "
                         "improved anxiety scores versus placebo (SMD -0.98), "
                         "with high heterogeneity and few trials. Supported, "
                         "with the authors' own caution. Medium confidence.",
            },
            {
                "text": "[passionflower is] known in the literature to really "
                        "help to decrease that nervousness and anxiety",
                "start": 20.9, "end": 36.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Cochrane (PMID:17253512): RCTs 'too few in number "
                         "to permit any conclusions'. The 2022 network "
                         "meta-analysis (PMID:35378276) found passionflower "
                         "did not reduce HAM-A significantly. Neither says "
                         "it does not work.",
            },
            {
                "text": "herbal medicines ... decrease that nervousness and "
                        "anxiety without negative side effects",
                "start": 26.5, "end": 36.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:34449930"], "contradicting": [],
                "confidence": "medium",
                "notes": "The lemon balm meta-analysis reports no serious "
                         "side effects, and the valerian Cochrane review "
                         "found no difference in side-effect reports, but "
                         "both rest on few small trials. 'Without negative "
                         "side effects' across all four herbs is not "
                         "established.",
            },
        ],
    },
    {
        "video_id": "v169",
        "external_reason": (
            "The study on screen supports his account of stopping "
            "moisturiser and contradicts 'everyone must moisturise "
            "daily', which he refutes; his 'skin becomes dependent' claim"
            " is MIXED, not contradicted."),
        "topic": "dermatology / facial moisturisers",
        "case_tags": ["other_language", "uncertain_science"],
        "confidence": "medium",
        "notes": "Spanish, captioned 'Dermatólogo:'. Claims your skin becomes "
                 "'addicted' to moisturiser and shows a real paper on "
                 "screen: the Maul et al. split-face pilot study "
                 "(PMID:33026578; the caption misspells the author 'Yuki "
                 "Chen'). The study supports what he says happened after "
                 "stopping. But it concludes the skin 'regain[s] normal "
                 "levels quickly without continuation', which is the "
                 "opposite of dependency. He also refutes 'everyone must "
                 "moisturise daily', which that same finding contradicts. "
                 "The rules give DEBUNKING. The 'addiction' framing is "
                 "MIXED rather than contradicted, because a separate RCT "
                 "found some moisturisers do weaken the barrier of normal "
                 "skin.",
        "claims": [
            {
                "text": "En personas que llevaban mucho tiempo utilizando "
                        "crema hidratante tras un día sin usarlo, la piel "
                        "mostró sequedad, enrojecimiento y descamación y "
                        "después tardó en recuperarse hasta tres semanas",
                "start": 16.4, "end": 26.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33026578"], "contradicting": [],
                "confidence": "high",
                "notes": "EN: in long-term moisturiser users, one day after "
                         "stopping, the skin showed dryness, redness and "
                         "scaling, and then took up to three weeks to "
                         "recover. PMID:33026578: symptoms rose within 1 day "
                         "of discontinuation; recovery 1-3 weeks in young "
                         "women. Accurate to the paper, which studied only "
                         "women.",
            },
            {
                "text": "eso de que todas las personas tienen que usar "
                        "cremas hidratantes faciales todos los días es un "
                        "mito",
                "start": 28.7, "end": 35.8,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:33026578"],
                "confidence": "medium",
                "notes": "EN: the idea that everyone has to use facial "
                         "moisturiser every day is a myth. The claim refuted "
                         "is 'everyone needs daily facial moisturiser'. "
                         "PMID:33026578 found healthy young and older women "
                         "'regain normal levels quickly without continuation "
                         "of moisturizers', a direct finding against a "
                         "universal need. Medium confidence: healthy women "
                         "only, and 'tienen que' (have to) is a norm as much "
                         "as a fact.",
            },
            {
                "text": "El uso constante de cremas hidratantes podría hacer "
                        "que tu piel se vuelva dependiente, debilitando su "
                        "capacidad natural para mantenerse hidratada desde "
                        "dentro",
                "start": 35.8, "end": 43.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:17300239"],
                "contradicting": ["PMID:33026578"],
                "confidence": "medium",
                "notes": "EN: constant use of moisturisers could make your "
                         "skin dependent, weakening its natural ability to "
                         "stay hydrated. Same assertion as the opening line "
                         "'Tu piel se vuelve adicta a la crema hidratante' "
                         "(0.0-6.4s, said and shown), recorded once. A "
                         "7-week RCT on normal skin (PMID:17300239) found "
                         "simple creams increased water loss and irritant "
                         "susceptibility while an ordinary cream did the "
                         "opposite. The study he shows (PMID:33026578) found "
                         "recovery without moisturiser within 1-3 weeks, "
                         "which argues against dependency. Good studies, "
                         "different directions: MIXED.",
            },
            {
                "text": "aplicar un exceso de cremas hidratantes puede "
                        "agravar problemas como la rosácea",
                "start": 55.7, "end": 59.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: applying too much moisturiser can aggravate "
                         "problems like rosacea. Whisper has 'grabar' for "
                         "'agravar'; the caption reads 'PUEDE AGRAVAR'. The "
                         "rosacea search returned trials of moisturisers "
                         "helping rosacea (e.g. PMID:16209160), none on "
                         "excess use. Untested.",
            },
        ],
    },
    {
        "video_id": "v170",
        "external_reason": (
            "An exorcism 'curing' autism is a supernatural claim, "
            "NOT_VERIFIABLE."),
        "topic": "mental health / autism and faith healing",
        "case_tags": [],
        "confidence": "high",
        "notes": "A deliverance clip: 'This autistic kid had a demon inside "
                 "of him', a prayer ('Every spirit of autism and mental "
                 "sickness must leave in Jesus' name') and an instant "
                 "'set free', with a '(DEMON SPEAKING)' caption. The claim "
                 "is supernatural, so not testable. The rules give "
                 "CANNOT_RECOGNIZE. The implied promise of a cure for autism "
                 "is the harm, and it has no checkable form here.",
        "claims": [
            {
                "text": "One moment this kid has a demon of autism and then "
                        "in Jesus [name] he's instantly set free",
                "start": 4.6, "end": 10.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Said and captioned. A demonic cause and an exorcism "
                         "cure are outside anything evidence can test. A "
                         "search for 'exorcism autism' found nothing "
                         "relevant.",
            },
        ],
    },
    {
        "video_id": "v171",
        "external_reason": (
            "The Callas tapeworm story is reported as a hypothesis "
            "(QUOTES), not endorsed, and is a biographical rumour no "
            "source settles."),
        "topic": "weight loss / tapeworm diet (history)",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "Spanish. A 'HISTORIA REAL' clip on Maria Callas: a critic "
                 "mocked her legs, she lost 50 kg in a season, and 'the "
                 "brutal hypothesis' was that she had swallowed a tapeworm, "
                 "'a fashion in Europe since 1900'. It ends on a vintage "
                 "'sanitized tape worms, jar packed' advert. The tapeworm "
                 "story is reported as a hypothesis, not endorsed, and it "
                 "is a historical assertion about one person, not a "
                 "testable health claim. It does not say a tapeworm is a "
                 "safe way to lose weight.",
        "claims": [
            {
                "text": "La hipótesis brutal de su transformación sostenía que "
                        "María Callas había ingerido una tenia solitaria que "
                        "se encargaba de todo",
                "start": 42.4, "end": 52.4,
                "kind": "fact_of_record",
                "stance": "QUOTES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: the brutal hypothesis for her transformation "
                         "held that Maria Callas had swallowed a tapeworm "
                         "that did all the work. Reported as someone else's "
                         "hypothesis, so QUOTES. A biographical rumour that "
                         "no medical source can settle.",
            },
        ],
    },
    {
        "video_id": "v172",
        "external_reason": (
            "A personal account of Tourette's and OCD vanishing after a "
            "spiritual awakening, NOT_VERIFIABLE."),
        "topic": "mental health / Tourette's and OCD, spiritual recovery",
        "case_tags": [],
        "confidence": "high",
        "notes": "An interview: a man says his Tourette's and severe OCD "
                 "'vanished' after a spiritual awakening and a lifestyle "
                 "'more in tune with nature', inspired by YouTubers. A "
                 "personal recovery story, not testable. Context for a "
                 "reviewer: tics often wane to clinical insignificance over "
                 "the teen years (PMID:34178575), so a remission alongside "
                 "a life change is unsurprising, but that does not test his "
                 "account.",
        "claims": [
            {
                "text": "These conditions [Tourette's and severe OCD] "
                        "vanished as soon as I had a spiritual awakening "
                        "almost, where I changed my lifestyle to one that was "
                        "more in tune with nature",
                "start": 9.6, "end": 24.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A single person's experience with no measure. "
                         "The search on tic course (PMID:34178575) is "
                         "background only and is not cited.",
            },
        ],
    },
    {
        "video_id": "v173",
        "external_reason": (
            "First-person sermon about choosing happiness despite "
            "depression, NOT_VERIFIABLE."),
        "topic": "mental health / depression, faith and choice",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A sermon clip (Life Church): even when 'the weight of "
                 "discouragement and depression' is on her, she can 'make "
                 "up my mind I'm gonna be happy today'. The implication, "
                 "that depression yields to a decision, is spoken as "
                 "personal practice, not as a general claim, so it is "
                 "NOT_VERIFIABLE.",
        "claims": [
            {
                "text": "when I get up in the morning and I feel the weight "
                        "of discouragement and depression on me I still can "
                        "make up my mind I'm gonna be happy today",
                "start": 5.7, "end": 18.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "First-person and about her own mornings. Read as "
                         "a general claim that depression can be overcome "
                         "by choosing happiness, it would be checkable, but "
                         "she does not state it that way.",
            },
        ],
    },
    {
        "video_id": "v174",
        "topic": "mental health / schizophrenia, DMT and spirits",
        "case_tags": ["speech_screen_disagree"],
        "confidence": "medium",
        "notes": "Replying to 'Can you do a video on schizophrenia when it "
                 "comes to the demons?', the speaker says people with "
                 "schizophrenia are 'extremely sensitive to the spirit "
                 "world' and that their perceptions are not hallucinations. "
                 "As proof he cites a real study (Rodnight et al. 1976, "
                 "PMID:1070024, whose abstract is on screen): DMT was found "
                 "in the urine of 47% of patients diagnosed with "
                 "schizophrenia. He quotes the figure correctly. The "
                 "abstract on screen also says 'specifically schizophrenic "
                 "symptoms did not appear to be major determinants of DMT "
                 "excretion', and 5% of normal subjects excreted it, which "
                 "undercuts his inference. Hence speech_screen_disagree. "
                 "Denying that the experiences are hallucinations is "
                 "refuting a supported claim, so the rules give MISINFO "
                 "with a review flag.",
        "claims": [
            {
                "text": "if you have schizophrenia That means that you're "
                        "really just extremely sensitive to the spirit world",
                "start": 0.0, "end": 15.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "A spiritual claim; not testable.",
            },
            {
                "text": "People will try to claim that they're hallucinations "
                        "and illusions. I do not think that's the case",
                "start": 15.8, "end": 28.8,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "SUPPORTED",
                "supporting": ["PMID:30384148", "PMID:9017111"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "The claim refuted is 'what people with "
                         "schizophrenia see and hear are hallucinations'. "
                         "PMID:30384148: 'Auditory verbal hallucinations are "
                         "common symptoms in schizophrenia patients'. "
                         "PMID:9017111 lists disturbances in perception "
                         "among the signs on which the diagnosis is made. "
                         "Repeated at 42.9-48.1s.",
            },
            {
                "text": "There was a study where scientists studied the urine "
                        "of people who had schizophrenia. They found out that "
                        "47% of them had dimethyltryptamine, also known as "
                        "DMT, within their urine",
                "start": 28.8, "end": 38.7,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:1070024"], "contradicting": [],
                "confidence": "high",
                "notes": "PMID:1070024 (Psychol Med 1976): 'DMT was detected "
                         "in the urine of 47% of those diagnosed by their "
                         "psychiatrists as schizophrenic'. The figure is "
                         "right; the inference he draws from it is not in "
                         "the paper (see video notes).",
            },
            {
                "text": "Dimethyltryptamine is a very powerful psychedelic "
                        "that allows you to see certain entities",
                "start": 38.7, "end": 42.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:34975614"], "contradicting": [],
                "confidence": "low",
                "notes": "Read as the experience: a thematic analysis of "
                         "breakthrough DMT experiences (PMID:34975614) "
                         "documents encounters with perceived entities as a "
                         "core feature. Low confidence because the speaker "
                         "means the entities are real, which is not "
                         "testable. A reviewer may prefer NOT_VERIFIABLE. "
                         "The video label does not depend on it.",
            },
            {
                "text": "If you've ever come out of a deep sleep and saw some "
                        "sort of hallucination of some sort of entity, that "
                        "was caused by the DMT in your brain",
                "start": 48.1, "end": 54.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Searched endogenous DMT and hypnopompic "
                         "hallucinations: only DMT pharmacology and a "
                         "1997 hypothesis paper (PMID:9468359). Nothing "
                         "tests endogenous DMT as the cause.",
            },
        ],
    },
    {
        "video_id": "v175",
        "external_reason": (
            "Reports that fruit 'seems' rubbery and asserts nothing about"
            " safety or composition, so there is no checkable claim."),
        "topic": "food quality / 'rubber' fruit",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "Spanish news-style clip: in the US people are buying fruit "
                 "that seems to be made of rubber, with clips of a bendy "
                 "watermelon. It reports what users showed ('parecen', "
                 "'resultó ser elástica, con poco jugo y un sabor extraño') "
                 "and asserts nothing about safety, composition or health. "
                 "The insinuation that the fruit is artificial is never "
                 "stated, so there is no checkable health claim. The "
                 "speech has a gap from 2.4 s to 21.1 s (the embedded "
                 "clips).",
        "claims": [],
    },
    {
        "video_id": "v176",
        "external_reason": (
            "Panic attacks being 'not of God' and scripture overcoming "
            "them are religious claims, NOT_VERIFIABLE."),
        "topic": "mental health / panic attacks and faith",
        "case_tags": [],
        "confidence": "high",
        "notes": "A devotional clip: panic and anxiety attacks are 'not of "
                 "God', and 2 Timothy 1:7 is the scripture 'to overcome'. "
                 "Religious claims, not testable. No medical advice is "
                 "given against treatment.",
        "claims": [
            {
                "text": "[a panic attack or an anxiety attack] that's "
                        "actually not of God",
                "start": 0.0, "end": 16.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Theological; not testable.",
            },
            {
                "text": "He gives you a scripture to overcome [it]",
                "start": 25.4, "end": 38.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Read as 'scripture overcomes panic attacks'. "
                         "Framed devotionally, with no outcome to measure.",
            },
        ],
    },
    {
        "video_id": "v177",
        "topic": "mental health / schizophrenia and demons",
        "case_tags": ["clearly_false"],
        "confidence": "medium",
        "notes": "A podcast clip: hearing voices, seeing things and multiple "
                 "personality are 'the three main signs of having a demon', "
                 "and people are 'misdiagnosed, thinking they're mentally "
                 "ill when really they just have a demon'. The checkable "
                 "error is the split-personality idea of schizophrenia, a "
                 "documented public misconception, which the speaker "
                 "endorses. So MISINFO. The demon claims are not testable. "
                 "Her point that there is no brain scan for diagnosis is "
                 "correct.",
        "claims": [
            {
                "text": "[schizophrenia] literally is hearing voices and "
                        "seeing things",
                "start": 1.3, "end": 6.7,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:30384148", "PMID:9017111"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Hallucinations are a core feature "
                         "(PMID:30384148), and the diagnosis rests on "
                         "perceptual disturbances among other signs "
                         "(PMID:9017111). 'Literally is' overstates it, "
                         "since no single symptom is pathognomonic per "
                         "PMID:9017111, hence medium.",
            },
            {
                "text": "And multiple personality. Yes, and multiple",
                "start": 6.7, "end": 8.6,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:17987546",
                                                    "PMID:23459877",
                                                    "PMID:18652789"],
                "confidence": "high",
                "notes": "The co-host offers 'multiple personality' and the "
                         "speaker agrees, then lists it as one of 'the three "
                         "main signs'. PMID:17987546 calls mistaking "
                         "schizophrenia for split personality 'an error'. "
                         "PMID:23459877 calls the split-personality belief a "
                         "'misconception'. PMID:18652789: schizophrenia and "
                         "dissociative identity disorder are 'typically "
                         "thought of as unrelated syndromes' and categorised "
                         "separately in DSM-IV.",
            },
            {
                "text": "oftentimes people are being misdiagnosed, thinking "
                        "they're mentally ill when really they just have a "
                        "demon",
                "start": 30.0, "end": 34.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Repeated at 55.0-58.1s. Supernatural; not "
                         "testable.",
            },
            {
                "text": "There's no like brain scan",
                "start": 46.8, "end": 48.1,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:9017111"], "contradicting": [],
                "confidence": "medium",
                "notes": "Said of how schizophrenia is diagnosed. "
                         "PMID:9017111: 'The diagnosis of schizophrenia is "
                         "made on the basis of a diverse set of "
                         "characteristic signs and symptoms', not imaging. "
                         "True as stated, though she uses it to argue for "
                         "demons.",
            },
        ],
    },
    {
        "video_id": "v178",
        "external_reason": (
            "The autism-transgender co-occurrence he asserts is "
            "SUPPORTED; the 'ideology preys on the vulnerable' claim is "
            "INSUFFICIENT, not contradicted."),
        "topic": "mental health / autism and gender identity",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "A commentator on parents' calls about autistic children "
                 "who come to identify as transgender. He says there is a "
                 "connection, that people with autism, anxiety and "
                 "depression are 'very vulnerable' to 'gender identity "
                 "ideology', and that 'it is false that you can become the "
                 "opposite sex'. The co-occurrence is well documented, so "
                 "the rules give NO_MISINFO. The causal claim, that the "
                 "ideology preys on vulnerable people (the rapid-onset "
                 "hypothesis), is untested and INSUFFICIENT. On-screen "
                 "Slate and NPR headlines on the autism-gender link back "
                 "the co-occurrence.",
        "claims": [
            {
                "text": "Somehow the transgender identification and the "
                        "autism thing ... what's going on with this "
                        "connection",
                "start": 22.9, "end": 31.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:32770077"], "contradicting": [],
                "confidence": "high",
                "notes": "Hedged ('I would want to be very careful that I'm "
                         "not linking the two necessarily') but asserted. "
                         "PMID:32770077 (Nat Commun 2020, 641,860 people): "
                         "transgender and gender-diverse people have higher "
                         "rates of autism.",
            },
            {
                "text": "These people who are dealing with these struggles, "
                        "not just autism, social anxiety, depression, other "
                        "psychiatric ailments and disorders, they're all "
                        "very vulnerable to this",
                "start": 31.4, "end": 40.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Continues 'it preys upon those who are already "
                         "having a really hard time ... especially autistic "
                         "people' (48.2-56.0s). This is the rapid-onset "
                         "gender dysphoria hypothesis: transgender "
                         "identification as a maladaptive response to mental "
                         "health problems under social influence. A 2024 "
                         "review (PMID:38951367) sets out to test that "
                         "theory against the evidence base; its abstract "
                         "states the hypothesis but no conclusion, and "
                         "nothing else retrieved tests causation. "
                         "INSUFFICIENT.",
            },
            {
                "text": "Not only is it false that you can become the "
                        "opposite sex",
                "start": 45.2, "end": 48.2,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "Turns on what 'sex' and 'become' mean "
                         "(chromosomes, anatomy, legal status, social "
                         "role). It is a definitional and political "
                         "claim, not one evidence settles as phrased. Low "
                         "confidence; a reviewer may read it as a narrow "
                         "biological fact.",
            },
        ],
    },
    {
        "video_id": "v179",
        "external_reason": (
            "A personal testimony about weight and faith with no general "
            "health assertion."),
        "topic": "mental health / body image, depression and faith",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A testimony: she tied her worth to her weight, got 'so "
                 "depressed that I outgrew the wedding dress', and God told "
                 "her the scale was an idol. A personal story about "
                 "disordered thinking about weight, with no general or "
                 "checkable health assertion. No checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v180",
        "external_reason": (
            "Infection is linked to new autoimmune disease and "
            "vaccination is not, so 'booster then COVID caused it' is "
            "MIXED rather than false."),
        "topic": "vaccines / COVID-19 booster and autoimmunity",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "A talk-show host (SiriusXM captions) regrets her COVID "
                 "vaccine and says a top rheumatologist agreed that her new "
                 "positive autoimmune test could be due to a booster "
                 "followed by COVID within three weeks. The evidence points "
                 "both ways on the two exposures. Infection is associated "
                 "with new autoimmune disease, with that risk lower in the "
                 "vaccinated. Vaccination shows no change in autoantibodies "
                 "in one cohort, and only scattered associations in a "
                 "national one. MIXED, so CANNOT_RECOGNIZE with a review "
                 "flag.",
        "claims": [
            {
                "text": "I regret getting the vaccine even though I'm a "
                        "52-year-old woman because I don't think I needed it. "
                        "I think I would have been fine",
                "start": 0.0, "end": 7.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A counterfactual about herself. Not testable for "
                         "one person.",
            },
            {
                "text": "do you think this [autoimmune issue] could have to "
                        "do with the fact that I got the damn booster and "
                        "then got COVID within three weeks? and she said, "
                        "yes",
                "start": 19.2, "end": 33.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:41452424"],
                "contradicting": ["PMID:37413933", "PMID:41331674"],
                "confidence": "medium",
                "notes": "She reports the rheumatologist's 'yes' approvingly, "
                         "so ENDORSES. A meta-analysis (PMID:41452424) found "
                         "SARS-CoV-2 infection raises the risk of new "
                         "autoimmune disease, attenuated by vaccination. An "
                         "autoantibody cohort after mRNA vaccination "
                         "(PMID:37413933) found no autoreactive change, and "
                         "a Norwegian cohort (PMID:41331674) found most "
                         "autoimmune disorders unassociated with either "
                         "infection or vaccination. 'Could have to do with' "
                         "is a possibility claim about the pair. Supported "
                         "for the infection arm, not the booster arm: MIXED.",
            },
        ],
    },
    {
        "video_id": "v181",
        "external_reason": (
            "The salt, magnesium and four-herb claims rest on rat "
            "studies, poor-quality reviews or nothing, so all are "
            "INSUFFICIENT."),
        "topic": "mental health / anxiety, salt and herbs",
        "case_tags": ["multi_claim", "uncertain_science"],
        "confidence": "medium",
        "notes": "The same naturopath as v168 ('Janine'): a pinch of salt "
                 "under the tongue when anxious to 'balance electrolytes', "
                 "magnesium, and the valerian, skullcap, passionflower and "
                 "lemon balm combination 'amazing for chronic anxiety'. "
                 "The salt evidence is rat studies, and they point both "
                 "ways. Magnesium's is 'suggestive' but poor. Nothing tests "
                 "the four-herb combination. All INSUFFICIENT, so "
                 "CANNOT_RECOGNIZE.",
        "claims": [
            {
                "text": "Do you ever crave salty foods when you are stressed "
                        "out and you're very anxious? Well that's because "
                        "your brain has very specific sensors for sodium",
                "start": 0.0, "end": 11.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "The brain does sense sodium, but the claim is "
                         "causal: stress-related salt craving happens "
                         "because of those sensors. Nothing retrieved tests "
                         "that in people.",
            },
            {
                "text": "just get a little bit of salt and put a pinch into "
                        "your mouth, ideally under your tongue and drink that "
                        "down with a little bit of water. You can do this "
                        "throughout the day when you are feeling anxious",
                "start": 16.9, "end": 31.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:21471383"],
                "contradicting": ["PMID:34634356"],
                "confidence": "medium",
                "notes": "Animal only, and it disagrees. Acute hypernatremia "
                         "blunted stress responses and anxiety-like behaviour "
                         "in rats (PMID:21471383). A review of preclinical "
                         "salt studies (PMID:34634356) found heightened salt "
                         "augmented stress responsivity. No human test of a "
                         "pinch of salt for anxiety: INSUFFICIENT (labels.py "
                         "rule 1). Evidence on both sides is itself a "
                         "section 11 review trigger.",
            },
            {
                "text": "magnesium is going to be really important for your "
                        "nervous system",
                "start": 31.7, "end": 41.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:28445426"], "contradicting": [],
                "confidence": "medium",
                "notes": "In context, magnesium for anxiety. A systematic "
                         "review (PMID:28445426) calls the evidence "
                         "'suggestive of a beneficial effect ... in anxiety "
                         "vulnerable samples' but of poor quality.",
            },
            {
                "text": "things like valerian, skull cat, passion flower, and "
                        "lemon balm, that combination together is amazing "
                        "for chronic anxiety",
                "start": 41.6, "end": 51.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:34449930"],
                "contradicting": ["PMID:17054208", "PMID:17253512"],
                "confidence": "medium",
                "notes": "'skull cat' is Whisper's 'skullcap'. No study of "
                         "the combination was found. Of the parts, lemon "
                         "balm has a supportive meta-analysis "
                         "(PMID:34449930), while valerian (PMID:17054208) "
                         "and passionflower (PMID:17253512) have Cochrane "
                         "reviews that find too little to conclude.",
            },
        ],
    },
]
