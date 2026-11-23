"""Batch 2, part C: v133-v157. Rules as in labels.py and labels_batch2.py."""

LABELS = [
    {
        "video_id": "v133",
        "external_reason": "The refuted urine-eye-drop claims are untested in PubMed, so "
                           "they are INSUFFICIENT and the debunk goes to review as a "
                           "possible debunk of an unsettled claim.",
        "topic": "eye health / urine therapy",
        "case_tags": ["debunking", "other_language"],
        "confidence": "medium",
        "notes": "A pharmacist (@farmaceuticofernandez) stitching clips of a "
                 "woman who puts her own urine in her eyes every day and says "
                 "it cured her myopia and astigmatism, and mocking it: urine "
                 "is chemicals too, and it can irritate, infect or blind you. "
                 "A competent debunk that comes out CANNOT_RECOGNIZE: nothing "
                 "in PubMed tests urine eye drops either way (two searches, "
                 "both empty; the only hit is a historical article listing "
                 "urine eye drops among folk urine therapies, PMID:10213804), "
                 "and his own risk claim has no retrieved case series. The "
                 "refuted claims are INSUFFICIENT, so section 9 sends it to "
                 "review as a possible debunk of an unsettled claim. The "
                 "speaker's stance is carried by sarcasm ('la constancia en "
                 "los tratamientos es algo que los profesionales admiramos'), "
                 "which a stance model has to read as REFUTES, not ENDORSES. "
                 "The last segment ('Subtítulos realizados por la comunidad "
                 "de Amara.org') is a whisper hallucination on silence.",
        "claims": [
            {
                "text": "Lo mejor que te puedes echar en tu vida en los ojos es "
                        "la orina, olvídate de los colídeos [colirios] de la "
                        "farmacia que llevan cosas químicas",
                "source": "both",
                "start": 0.2, "end": 7.3,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: The best thing you can ever put in your eyes is "
                         "urine; forget pharmacy eye drops, which contain "
                         "chemicals. The quoted woman's claim, which he "
                         "mocks. Searches for urine instilled in the eye "
                         "returned nothing that tests it; absence of evidence, "
                         "so INSUFFICIENT, not CONTRADICTED. Whisper wrote "
                         "'colídeos' for 'colirios' (eye drops).",
            },
            {
                "text": "No hay nada mejor para tus ojos ... que la orina[;] "
                        "hace muchos años, cur[é] el astigmatismo y la miopía "
                        "con la constancia de echarme orina cada día de mi vida",
                "start": 28.9, "end": 41.5,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Nothing is better for your eyes than urine; "
                         "years ago I cured my astigmatism and myopia by "
                         "putting urine in them every day. Again the quoted "
                         "speaker; he refutes it. Refractive error is an "
                         "optical property of the eye, which makes the claim "
                         "implausible, but no study tests it, so it cannot be "
                         "CONTRADICTED under section 7.",
            },
            {
                "text": "la orina es algo completamente natural, el 95% es "
                        "agua y el resto es urea, cloruro de sodio, [fosfatos], "
                        "sulfatos, sales de amonio",
                "start": 15.2, "end": 23.3,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Urine is natural; 95% is water and the rest is "
                         "urea, sodium chloride, phosphates, sulphates and "
                         "ammonium salts. Textbook physiology and almost "
                         "certainly right, but no reference was retrieved: a "
                         "PubMed search for urine composition returned only "
                         "off-topic papers, and Bookshelf blocks scripted "
                         "retrieval. Whisper wrote 'josfatos'.",
            },
            {
                "text": "tú te echas orina en los ojos, se te puede ni irritar, "
                        "se te puede producir una infección, lo mismo te "
                        "quedas ciego",
                "start": 44.8, "end": 54.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Put urine in your eyes and they can get "
                         "irritated, infected, maybe you go blind. His own "
                         "warning. Plausible, but no case report or series was "
                         "retrieved, so it is not SUPPORTED either.",
            },
        ],
    },
    {
        "video_id": "v134",
        "topic": "sun protection / skin cancer",
        "case_tags": ["debunking", "other_language", "accurate"],
        "confidence": "high",
        "notes": "A dermatologist (Dra. Paloma Borregón, Academia Española de "
                 "Dermatología) on 'callo solar', the idea that skin should "
                 "be exposed to the sun unprotected so it hardens. She grants "
                 "the true part (tanned skin stops burning) and refutes the "
                 "conclusion: the skin keeps taking chronic damage, with more "
                 "skin cancer and photoaging. A clean DEBUNKING backed by the "
                 "Nambour randomised trials of daily sunscreen. Worth noting "
                 "for the stance step: she says 'eso es verdad' about part of "
                 "the opposing view, so a model that keys on agreement words "
                 "will misread the stance.",
        "claims": [
            {
                "text": "la piel se tiene que ir exponiendo sin protección solar "
                        "al sol, ya que progresivamente se va curtiendo",
                "start": 8.4, "end": 15.1,
                "kind": "research_question",
                "stance": "REFUTES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:21135266", "PMID:20883261"],
                "confidence": "high",
                "notes": "EN: The skin has to be exposed to the sun without "
                         "sun protection, because it gradually hardens. The "
                         "'callo solar' advocates' claim, introduced with "
                         "'Quien habla del callo solar dice que'. Contradicted "
                         "on its prescriptive part: in the Nambour trial, "
                         "regular sunscreen use reduced new primary melanomas "
                         "(11 vs 22), and UV radiation is the major cause of "
                         "skin cancer, with unnecessary sun exposure an "
                         "attributable risk.",
            },
            {
                "text": "la piel, a medida que va cogiendo color, la melanina "
                        "se estimula y deja de quemarse en algún momento, pero "
                        "sigue recibiendo el daño crónico del sol",
                "start": 15.1, "end": 24.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:20979596"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: As skin tans, melanin is stimulated and it "
                         "stops burning at some point, but it keeps taking "
                         "chronic sun damage. The NCI experiment found UVB "
                         "tans give modest protection against DNA damage and "
                         "UVA tans essentially none, which supports both "
                         "halves: some protection, not enough.",
            },
            {
                "text": "[con] el callo solar ... [hay] aumento de riesgo del "
                        "cáncer de piel",
                "start": 24.2, "end": 28.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:20883261", "PMID:21135266"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: Sun-hardened skin carries a higher skin cancer "
                         "risk. UV exposure is the major aetiological agent "
                         "of skin cancer; sunscreen reduces melanoma.",
            },
            {
                "text": "si quieres tener callo solar, pues sí, tendrás más "
                        "arrugas, más flacidez, porque perderás colágeno, más "
                        "manchas, un aspecto más envejecido",
                "start": 33.2, "end": 42.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:23732711", "PMID:24417448"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: With sun-hardened skin you will have more "
                         "wrinkles, sagging from collagen loss, more spots, an "
                         "older look. The Nambour skin-ageing trial: daily "
                         "sunscreen users showed no detectable increase in "
                         "photoaging over 4.5 years, 24% less than "
                         "discretionary users.",
            },
            {
                "text": "prefieres protección solar y tener una cara más joven "
                        "y más sana para el resto de la vida",
                "start": 47.7, "end": 51.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:23732711", "PMID:24417448"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Choose sun protection and a younger, healthier "
                         "face for life. Same trial evidence as c4; 'for the "
                         "rest of your life' is rhetoric beyond the 4.5-year "
                         "trial, hence medium.",
            },
        ],
    },
    {
        "video_id": "v135",
        "external_reason": "She corrects the tone of the coverage rather than a checkable "
                           "claim, and every claim she makes that could be retrieved is "
                           "SUPPORTED, so nothing refuted decides the label.",
        "topic": "cosmetics safety / benzene in acne products",
        "case_tags": ["accurate", "uncertain_science"],
        "confidence": "medium",
        "notes": "@labmuffinbeautyscience (a cosmetic chemist) putting the "
                 "Valisure benzene-in-benzoyl-peroxide report in proportion: "
                 "some products may reach ~20 ppm, benzene is a carcinogen "
                 "with no safe level, but skin absorbs little, BPO has 60 "
                 "years of use with no recorded cancer increase, and "
                 "sunscreen users showed no higher blood benzene. Every "
                 "checkable claim that could be retrieved is SUPPORTED, so "
                 "NO_MISINFO. She does not refute a checkable claim -- her "
                 "target is the tone of coverage ('less scary than some "
                 "people are making it sound'), which is not a claim -- so "
                 "the debunking reading lives in the framing, not in any row. "
                 "High-text: the CNN headline and the report's figures are "
                 "on screen throughout, mangled by OCR.",
        "claims": [
            {
                "text": "it looks like most of them are quite low, but a few "
                        "might have about 20 parts per million",
                "source": "both",
                "start": 11.9, "end": 17.8,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39384016"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Valisure's own peer-reviewed paper reports "
                         "0.16-35.30 ppm benzene across 111 over-the-counter "
                         "BPO products kept at room temperature, which "
                         "contains her estimate. Same lab, so not independent.",
            },
            {
                "text": "This is 10 times more than a limit the FDA has used "
                        "before",
                "source": "both",
                "start": 17.8, "end": 22.2,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "A regulatory figure (FDA's 2 ppm benzene limit). "
                         "The FDA benzene-contamination alert page returned "
                         "HTTP 404 through evidence.py ref, and no other "
                         "allow-listed source was retrieved, so it stays "
                         "unchecked.",
            },
            {
                "text": "Yes, it is a known carcinogen and there's no safe "
                        "level, but that doesn't mean that any amount is "
                        "dangerous. It means that little bits will add up to "
                        "increase your risk of cancer",
                "start": 34.0, "end": 43.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:20070208"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Smith's review: benzene causes acute leukaemia, "
                         "there is no evidence of a threshold, 'probably no "
                         "safe level of exposure', and exposures add risk "
                         "linearly -- close to her wording.",
            },
            {
                "text": "Benzene doesn't get through skin easily",
                "start": 52.8, "end": 55.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:10828141"],
                "contradicting": [],
                "confidence": "low",
                "notes": "Wester and Maibach: percutaneous absorption of "
                         "benzene depends on the vehicle and varies many-fold; "
                         "where it is low it is overwhelmed by intake from "
                         "food and air. That supports the comparison she goes "
                         "on to make but does not establish 'doesn't get "
                         "through skin easily' as a general rule.",
            },
            {
                "text": "Benzoyl peroxide has been used for acne for 60 years "
                        "and there's no recorded increased cancer in people "
                        "who use it",
                "start": 72.0, "end": 78.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:39002561"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Retrospective cohort (Garate et al., JAAD 2024): "
                         "benzoyl peroxide for acne is not associated with "
                         "increased risk of malignancy. Supported by the "
                         "title and design; the record carries no abstract "
                         "text. The '60 years' is not checked.",
            },
            {
                "text": "this study didn't find higher benzene levels in people "
                        "who use sunscreen",
                "start": 83.5, "end": 90.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:34509542"],
                "contradicting": [],
                "confidence": "high",
                "notes": "NHANES 2003-2006 and 2009-2018: sunscreen use is "
                         "not associated with increased blood benzene.",
            },
        ],
    },
    {
        "video_id": "v136",
        "external_reason": "Nothing tests the salt pregnancy test, so the claim is "
                           "INSUFFICIENT rather than CONTRADICTED (section 7).",
        "topic": "pregnancy testing / home remedy",
        "case_tags": ["screen_only"],
        "confidence": "medium",
        "notes": "Fifteen seconds with no speech: on-screen text only, "
                 "instructing a home pregnancy test with morning urine and two "
                 "tablespoons of salt. Without OCR the video is unlabellable. "
                 "The method is folklore with no plausible mechanism, but "
                 "nothing in PubMed tests it (searches for salt pregnancy "
                 "tests returned nothing relevant), so under section 7 it is "
                 "INSUFFICIENT and the video CANNOT_RECOGNIZE. The same "
                 "absence-of-evidence trap as batch 1's untested remedies.",
        "claims": [
            {
                "text": "Do You Know You Can Run Pregnancy Test At Home Using "
                        "SALT ... Take your early morning Urine ... Pour 2 "
                        "tablespoons of salt Inside the morning urine",
                "source": "screen",
                "start": 0.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Screen-only, stated as fact, so ENDORSES. Validated "
                         "home pregnancy tests detect hCG with antibody "
                         "strips; nothing retrieved tests salt, and absence "
                         "of evidence is not contradiction.",
            },
        ],
    },
    {
        "video_id": "v137",
        "external_reason": "She demonstrates the salt test and asks whether it is accurate "
                           "(NEUTRAL), and nothing tests the method either way.",
        "topic": "pregnancy testing / home remedy",
        "case_tags": ["noisy_audio"],
        "confidence": "medium",
        "notes": "A creator doing the urine-and-salt pregnancy test on camera "
                 "and asking viewers 'positive or negative? is this "
                 "accurate?'. She performs the method but asks whether it "
                 "works, so the stance is NEUTRAL rather than ENDORSES: a "
                 "useful stance edge case where demonstrating is not "
                 "asserting. Music under the speech; whisper rendered "
                 "'urine plus salt' as 'During plus salt'. Same untested "
                 "claim as v136, so INSUFFICIENT and CANNOT_RECOGNIZE.",
        "claims": [
            {
                "text": "urine + salt pregnancy test after 5 minutes",
                "source": "both",
                "start": 0.0, "end": 30.0,
                "kind": "research_question",
                "stance": "NEUTRAL", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "Taken from the captions ('urine + salt', "
                         "'pregnancy test', 'after 5 minutes'); speech "
                         "repeats it, misheard. No study tests the method.",
            },
        ],
    },
    {
        "video_id": "v138",
        "external_reason": "Every alkaline-diet claim is untested; the one systematic "
                           "review found almost no research for or against, so all are "
                           "INSUFFICIENT.",
        "topic": "nutrition / alkaline diet",
        "case_tags": ["other_language", "uncertain_science"],
        "confidence": "medium",
        "notes": "A nutrition creator (@dar_nutricion) promoting the alkaline "
                 "diet: it boosts immunity, sleep, digestion and vitality, "
                 "and the more alkaline the body the more toxins it "
                 "eliminates. The core premise is widely regarded as false, "
                 "but the literature retrieved does not test these outcomes: "
                 "the one systematic review (Fenton and Huang, BMJ Open 2016, "
                 "PMID:27297008) found 'almost no actual research to either "
                 "support or disprove these ideas', for cancer. Every claim "
                 "is therefore INSUFFICIENT and the video CANNOT_RECOGNIZE -- "
                 "the textbook case of section 7's rule that absence of "
                 "evidence is not contradiction. A search for a review "
                 "stating that diet cannot change blood pH found only "
                 "Schwalfenberg's 2012 review (PMID:22013455), whose "
                 "abstract is favourable to further study and does not say "
                 "that, so it is not cited against the claims.",
        "claims": [
            {
                "text": "La dieta alcalina lo que hace es potenciar tu cuerpo "
                        "al máximo nivel. Aumentar tu sistema inmunológico",
                "source": "both",
                "start": 0.0, "end": 10.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: The alkaline diet boosts your body to the "
                         "maximum, increases your immune system. Nothing "
                         "retrieved tests alkaline diets against immune "
                         "outcomes.",
            },
            {
                "text": "La dieta alcalina ... [va a] mejorar tu sueño",
                "start": 0.0, "end": 10.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: ...improves your sleep. Split from the list per "
                         "section 4; untested.",
            },
            {
                "text": "La dieta alcalina ... [va a mejorar] tu digestión",
                "start": 0.0, "end": 10.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: ...your digestion. Untested.",
            },
            {
                "text": "La dieta alcalina ... [va a mejorar] tu nivel de "
                        "vitalidad",
                "start": 0.0, "end": 10.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: ...your vitality. Vague and untested; close to "
                         "NOT_VERIFIABLE.",
            },
            {
                "text": "En nuestro cuerpo hay un pH y cuanto más alcalino "
                        "somos, más eliminación de toxinas",
                "source": "both",
                "start": 15.0, "end": 20.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Our body has a pH, and the more alkaline we "
                         "are, the more toxins we eliminate. Unspecified "
                         "'toxins'; nothing retrieved tests it.",
            },
            {
                "text": "espaciar el consumo de alimentos que acidifiquen, que "
                        "te inflamen ... lo más importante es el alcohol, la "
                        "carne roja y los alimentos procesados",
                "start": 30.2, "end": 42.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: Cut down on foods that acidify and inflame you: "
                         "above all alcohol, red meat and processed foods. "
                         "The advice to limit these is mainstream for other "
                         "reasons, but the claim as stated is that they "
                         "acidify and inflame the body, which was not "
                         "retrieved.",
            },
            {
                "text": "tenemos que alimentarnos de comida que nos brinde "
                        "mucha energía con poco desgaste digestivo, para que tu "
                        "cuerpo se potencie en su alcalinidad, legumbres, "
                        "vegetales en general, frutas, verduras",
                "start": 46.7, "end": 62.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: Eat legumes, vegetables and fruit so your body "
                         "strengthens its alkalinity. The premise that diet "
                         "makes the body (rather than the urine) more "
                         "alkaline is the contested one; no retrieved paper "
                         "settles it.",
            },
        ],
    },
    {
        "video_id": "v139",
        "topic": "candida / garlic remedies",
        "case_tags": ["other_language", "clearly_false"],
        "confidence": "medium",
        "notes": "A supplement seller (@mr.danger2024) claiming garlic kills "
                 "candida and that clearing candida brings easy weight loss "
                 "and makes sinusitis, migraine and skin itching disappear -- "
                 "the 'candida overgrowth' theory. MISINFO on the sinusitis "
                 "claim: the Cochrane review of antifungal therapy for "
                 "chronic rhinosinusitis found no benefit. The rest is "
                 "INSUFFICIENT; notably even the garlic-kills-fungus premise "
                 "is shaky in people (a placebo-controlled trial of oral "
                 "garlic found no effect on vaginal candida counts) and in "
                 "vitro (allicin alone was not fungicidal in one study). "
                 "The randomised trial of nystatin for the 'candidiasis "
                 "hypersensitivity syndrome' (PMID:2247104) is the closest "
                 "test of the theory as a whole and is cited where it "
                 "applies.",
        "claims": [
            {
                "text": "El ajo tiene cualidades antifungal, antifungal quiere "
                        "decir que mata hongos",
                "source": "both",
                "start": 0.7, "end": 6.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:19095412", "PMID:24308540"],
                "confidence": "low",
                "notes": "EN: Garlic has antifungal qualities, meaning it "
                         "kills fungi. Screen: 'EL AJO: PLANTA ANTI FUNGAL'. "
                         "Weak evidence pointing against: allicin enhanced "
                         "amphotericin B but 'did not exert a fungicidal "
                         "effect' in vitro, and the oral garlic RCT found no "
                         "difference in vaginal candida counts, though it was "
                         "a pilot its authors say cannot inform practice. "
                         "Too weak for CONTRADICTED.",
            },
            {
                "text": "se usa un ajo bien concentrado en combinación con "
                        "otros suplementos como orégano y demás para de una "
                        "forma natural matar el hongo cándida",
                "start": 27.9, "end": 39.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:24308540"],
                "confidence": "medium",
                "notes": "EN: Concentrated garlic combined with oregano and "
                         "other supplements naturally kills candida. No trial "
                         "of the combination; the oral garlic pilot trial was "
                         "null.",
            },
            {
                "text": "cuando el cuerpo se limpia de hongo entonces la "
                        "persona tiene un buen metabolismo, adelgaza con "
                        "facilidad",
                "start": 39.2, "end": 48.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Once the body is cleared of fungus, the person "
                         "has a good metabolism and loses weight easily. "
                         "Nothing tests it.",
            },
            {
                "text": "cuando el cuerpo se limpia de hongo ... se le "
                        "desaparece la sinusitis",
                "start": 39.2, "end": 48.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:30199594"],
                "confidence": "medium",
                "notes": "EN: Clearing the fungus makes sinusitis disappear. "
                         "Cochrane (Head et al. 2018, eight RCTs, 490 adults): "
                         "topical and systemic antifungals for chronic "
                         "rhinosinusitis showed no significant difference "
                         "from placebo in quality of life or severity "
                         "(low-quality evidence). That tests the intervention "
                         "class the claim rests on; medium confidence because "
                         "the evidence is graded low quality.",
            },
            {
                "text": "cuando el cuerpo se limpia de hongo ... [se le "
                        "desaparece] la migraña",
                "start": 39.2, "end": 52.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:2247104"],
                "confidence": "medium",
                "notes": "EN: ...and migraine disappears. The nystatin trial "
                         "found antifungal therapy no better than placebo for "
                         "the systemic symptoms attributed to candida, but "
                         "migraine was not a named outcome, so it is "
                         "indirect.",
            },
            {
                "text": "cuando el cuerpo se limpia de hongo ... [se le "
                        "desaparecen] los picores en la piel",
                "start": 39.2, "end": 52.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:2247104"],
                "confidence": "medium",
                "notes": "EN: ...and skin itching disappears. Same indirect "
                         "evidence as c5.",
            },
        ],
    },
    {
        "video_id": "v140",
        "external_reason": "The refuted 'fake/lab avocado' claims cannot be checked "
                           "against PubMed, while his banana-starch explanation is "
                           "SUPPORTED, so NO_MISINFO fires before the possible-debunk "
                           "rule.",
        "topic": "food safety / 'fake' avocados",
        "case_tags": ["debunking", "other_language"],
        "confidence": "medium",
        "notes": "A Mexican science communicator (@soyrafacarbajal) answering "
                 "a viral 'they are selling fake avocados in Texas' clip: the "
                 "rubbery texture is an unripe avocado whose cell walls have "
                 "not broken down, not a lab-made or transgenic fruit. The "
                 "refuted claims cannot be settled from PubMed (no study "
                 "says avocados are not fake), so they are INSUFFICIENT, but "
                 "his explanatory banana claim is SUPPORTED, and section 9's "
                 "NO_MISINFO rule fires before the possible-debunk rule -- "
                 "the v68/v70 pattern. Most of the video is botany "
                 "(vacuoles, cell walls, ethylene), which is not a health "
                 "claim and is not labelled. Whisper garbled the opening "
                 "English clip ('Teyar se le infecaba codos sin texas'); the "
                 "caption has it right.",
        "claims": [
            {
                "text": "They are selling fake avocados in Texas",
                "source": "both",
                "start": 0.0, "end": 2.7,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "The quoted clip he answers. Not a matter any "
                         "retrievable source settles.",
            },
            {
                "text": "son aguacates transgénicos ... nos venden aguacates de "
                        "laboratorio artificiales",
                "start": 115.3, "end": 124.7,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: They are transgenic avocados; they sell us "
                         "artificial lab avocados. A search for genetically "
                         "modified avocado returned nothing relevant.",
            },
            {
                "text": "para el caso del plátano, cuando están verdes tiene "
                        "más almidón ... Lo mismo pasa con el almidón, "
                        "empiezan a romperse en azúcares más simples y se "
                        "hacen más dulce",
                "start": 49.3, "end": 65.3,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:31001305"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: Green bananas have more starch; as they ripen "
                         "the starch breaks down into simpler sugars and they "
                         "get sweeter. Food composition. The review of banana "
                         "ripening: bananas accumulate 15-35% starch and "
                         "sweeten through starch-to-sugar metabolism. His "
                         "parallel claim that fibre breaks into sugars is "
                         "left out of the row as it was not checked.",
            },
        ],
    },
    {
        "video_id": "v141",
        "external_reason": "The 'cure for cancer' soap is untested (INSUFFICIENT, not "
                           "CONTRADICTED) and the incidental imiquimod claim is SUPPORTED, "
                           "so the rules give NO_MISINFO to a misleading frame.",
        "topic": "cancer / skin cancer 'soap'",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "A French news-entertainment account (@booska_p) on Heman "
                 "Bekele, TIME's 2024 Kid of the Year, saying he 'invented a "
                 "cure for cancer': a soap that prevents and treats skin "
                 "cancer. The soap is a prototype never tested in people, so "
                 "the headline claims are INSUFFICIENT, not CONTRADICTED. "
                 "The one checkable side claim -- imiquimod cream is "
                 "effective -- is SUPPORTED, so the section 9 rules give "
                 "NO_MISINFO. This is a clear case of the rules under-calling "
                 "a misleading frame: 'remède contre le cancer' overstates an "
                 "untested idea, and section 7 has no verdict for "
                 "'overstated'. Paired with v143, the same story from another "
                 "French account, which has no supported side claim and "
                 "comes out CANNOT_RECOGNIZE.",
        "claims": [
            {
                "text": "Ce gamin de 15 ans a inventé un remède contre le "
                        "cancer",
                "source": "both",
                "start": 0.0, "end": 2.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: This 15-year-old invented a cure for cancer. A "
                         "search for the soap returned nothing; no clinical "
                         "study exists to support or refute it.",
            },
            {
                "text": "a fabriqué un savon qui prévient et traite le cancer "
                        "de la peau",
                "source": "both",
                "start": 6.8, "end": 11.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: He made a soap that prevents and treats skin "
                         "cancer. Untested in humans.",
            },
            {
                "text": "la crème médicament imiquimode. Efficace",
                "source": "both",
                "start": 11.9, "end": 19.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:22612571"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: The drug cream imiquimod is effective. Meta-"
                         "analysis of treatments for superficial basal cell "
                         "carcinoma: pooled complete response 86.2% and 1-year "
                         "tumour-free survival 87.3% with imiquimod. The video "
                         "does not name the indication; supported for the "
                         "skin cancer it is approved for.",
            },
            {
                "text": "Son savon il vient renforcer les cellules "
                        "dendritiques qui s'affaiblissent à cause du cancer",
                "source": "both",
                "start": 19.1, "end": 24.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: His soap strengthens the dendritic cells that "
                         "cancer weakens. The proposed mechanism; untested. "
                         "Whisper wrote 'd'entritique'; the caption reads "
                         "'DENDRITIQUES'.",
            },
        ],
    },
    {
        "video_id": "v142",
        "external_reason": "No retrievable source tests 'plastic eggs', so the claim is "
                           "INSUFFICIENT.",
        "topic": "food safety / 'plastic' eggs",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "A woman squeezing rubbery egg yolks and declaring them "
                 "'huevos de plástico', with a 'peligro comida plástica' "
                 "caption throughout. A food-fraud claim with no retrievable "
                 "test (a PubMed search for plastic eggs returned nothing), "
                 "so INSUFFICIENT and CANNOT_RECOGNIZE although the claim is "
                 "almost certainly false. One of the clearest examples in "
                 "the set of a false claim that the evidence sources cannot "
                 "reach.",
        "claims": [
            {
                "text": "esta es la mierda que nos están vendiendo[,] huevos de "
                        "plástico, de plástico todo",
                "source": "both",
                "start": 67.6, "end": 79.5,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: This is the crap they are selling us: plastic "
                         "eggs, all plastic. Caption: 'peligro comida "
                         "plastica ya, tener cuidado'. Nothing retrieved.",
            },
        ],
    },
    {
        "video_id": "v143",
        "external_reason": "Both soap claims are untested in people: INSUFFICIENT, not "
                           "CONTRADICTED.",
        "topic": "cancer / skin cancer 'soap'",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "@demotivateur_fr on the same Heman Bekele story as v141: a "
                 "15-year-old 'invented a soap that treats skin cancer', "
                 "which protects even after rinsing and costs 50 cents. Both "
                 "health claims are untested in people, so INSUFFICIENT and "
                 "CANNOT_RECOGNIZE. Compare v141: same story, but v141 adds a "
                 "true remark about imiquimod and so comes out NO_MISINFO. "
                 "The pair shows how a single incidental supported claim "
                 "flips the section 9 label.",
        "claims": [
            {
                "text": "il vient d'inventer un savon qui traite le cancer de la "
                        "peau",
                "source": "both",
                "start": 0.0, "end": 3.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: He just invented a soap that treats skin cancer. "
                         "No clinical study exists.",
            },
            {
                "text": "Il a conçu un savon qui protège du cancer de la peau, "
                        "avec de nombreuses propriétés qui persistent même "
                        "après rinçage",
                "source": "both",
                "start": 9.3, "end": 14.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: He designed a soap that protects against skin "
                         "cancer, with properties that persist after "
                         "rinsing. Untested.",
            },
        ],
    },
    {
        "video_id": "v144",
        "external_reason": "A gym meme with no assertion: no checkable claims.",
        "topic": "fitness (meme)",
        "case_tags": ["satire"],
        "confidence": "high",
        "notes": "A silent gym meme: the caption 'When your first week at the "
                 "gym is over' over footage. Fitness-themed but makes no "
                 "assertion at all. No checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v145",
        "external_reason": "No speech and no readable on-screen text, so nothing could be "
                           "labelled.",
        "topic": "unknown (no readable content)",
        "case_tags": [],
        "confidence": "low",
        "notes": "Fifteen seconds with no speech and no OCR text above the "
                 "confidence floor: nothing in the transcript to label. "
                 "Whether it has health content cannot be told from the "
                 "text, so it is not tagged out_of_scope. No checkable "
                 "claims; worth a look at the video itself in review.",
        "claims": [],
    },
    {
        "video_id": "v146",
        "external_reason": "No speech and only fragmentary on-screen text; no assertion "
                           "could be read.",
        "topic": "unknown (no readable content)",
        "case_tags": [],
        "confidence": "low",
        "notes": "No speech; the only on-screen text is fragments ('DermnX', "
                 "'Dorm', 'Oarm') and an end card crediting a director and "
                 "an AI video tool (Clipfly). Possibly dermatology-related, "
                 "but no assertion can be read. No checkable claims; not "
                 "tagged out_of_scope because health content cannot be ruled "
                 "out from the text.",
        "claims": [],
    },
    {
        "video_id": "v147",
        "external_reason": "A product advert of names and single words ('Hydration', "
                           "'Protection'); no checkable health assertion.",
        "topic": "skincare (product advert)",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A Centellian24 Madeca Cream advert over music: product names "
                 "and single words ('Time Reverse', 'Hydration', "
                 "'Protection', 'Backed by Korea's finest pharmaceutical "
                 "technology'). Product names with no health assertion are "
                 "not claims (section 4), and 'Protection' or 'Hydration' "
                 "alone states nothing checkable. No checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v148",
        "external_reason": "A weight-loss joke with no assertion: no checkable claims.",
        "topic": "weight loss (meme)",
        "case_tags": ["satire"],
        "confidence": "high",
        "notes": "Caption only: 'Need that January motivational weight loss? "
                 "Go re watch the VS 2024 fashion show'. Weight-loss-themed "
                 "joke, no assertion. No checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v149",
        "external_reason": "The advert's gut and detox claims are untested for the "
                           "product; absence of evidence leaves them INSUFFICIENT.",
        "topic": "detox / gut health supplement",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "An AI-voiced advert for a '7-day detox plan' capsule (senna "
                 "leaf, lotus leaf extract, probiotics) that 'supports "
                 "digestion, reduces bloating, promotes overall gut health' "
                 "and 'cleanses your system'. Structure-function marketing "
                 "language: none of it is tested for this product, and the "
                 "detox claim meets Klein and Kiat's critical review "
                 "(PMID:25522674), which found no randomised trials of "
                 "commercial detox diets -- absence of evidence, not "
                 "contradiction. CANNOT_RECOGNIZE. Senna is a stimulant "
                 "laxative, which the advert does not say.",
        "claims": [
            {
                "text": "This advanced formula supports digestion",
                "start": 15.4, "end": 21.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "No study of the product.",
            },
            {
                "text": "This advanced formula ... reduces bloating",
                "start": 15.4, "end": 21.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "No study of the product.",
            },
            {
                "text": "This advanced formula ... promotes overall gut health",
                "start": 15.4, "end": 21.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Vague; no study of the product.",
            },
            {
                "text": "designed to cleanse your system and leave you feeling "
                        "lighter and more energized",
                "start": 22.5, "end": 27.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "The detox claim. Klein and Kiat (2015): very "
                         "little clinical evidence for detox diets and no "
                         "RCTs of commercial ones; untested, not disproven.",
            },
        ],
    },
    {
        "video_id": "v150",
        "external_reason": "A gym skit and slogan with no health assertion.",
        "topic": "fitness (meme / advert)",
        "case_tags": ["satire"],
        "confidence": "high",
        "notes": "A gym-bro skit ('MI GYM BRO Y YO CADA VEZ QUE NOS VEMOS EN "
                 "EL GYM') branded for a sports-supplement shop. Compliments "
                 "and a slogan, no health assertion. No checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v151",
        "external_reason": "A religious exhortation to care for the body, with no "
                           "checkable assertion.",
        "topic": "wellbeing (religious motivation)",
        "case_tags": [],
        "confidence": "high",
        "notes": "'Your body is the temple of the Holy Spirit. The Holy "
                 "Spirit deserves a mansion, not a rundown motel. Start "
                 "renovating.' A motivational exhortation to look after "
                 "one's body with no checkable assertion. No checkable "
                 "claims.",
        "claims": [],
    },
    {
        "video_id": "v152",
        "external_reason": "Composition statements about one product (zero sugar, no red "
                           "dye) with no health assertion attached.",
        "topic": "nutrition (product advert)",
        "case_tags": [],
        "confidence": "medium",
        "notes": "A taste-test advert for a liquid water enhancer: 'zero "
                 "grams of sugar, zero calories and no red dye', 'made with "
                 "real fruits and veggies'. These are composition statements "
                 "about one product with no health assertion attached, and "
                 "the product's label is not a retrievable reference, so "
                 "they are not recorded as claims. No checkable claims.",
        "claims": [],
    },
    {
        "video_id": "v153",
        "topic": "none (non-health)",
        "case_tags": ["out_of_scope"],
        "confidence": "high",
        "notes": "Caption only: 'When you wake up at night, it means someone "
                 "who loves you or your ex is watching or thinking about "
                 "you'. A romance superstition, not a health claim.",
        "claims": [],
    },
    {
        "video_id": "v154",
        "external_reason": "The stress-immunity claim is SUPPORTED by meta-analyses and "
                           "the cancer-surveillance claim is INSUFFICIENT; nothing false "
                           "is endorsed.",
        "topic": "mental health / stress and immunity",
        "case_tags": ["accurate"],
        "confidence": "medium",
        "notes": "A clip of a clinician (apparently on a cancer-survivorship "
                 "podcast) saying that sitting in anxiety and depression "
                 "affects the immune system's ability to fight infections "
                 "and to surveil against cancer cells, and encouraging "
                 "people to seek support. The infection half is well "
                 "supported by meta-analyses and the Cohen cold-challenge "
                 "study; the cancer-surveillance half is not established in "
                 "humans. NO_MISINFO.",
        "claims": [
            {
                "text": "the more we sit in anxiety and depression on that "
                        "fight or flight mode ... That impacts our body in so "
                        "many ways, including importantly our immune systems "
                        "and our ability to not only fight infections",
                "source": "both",
                "start": 15.2, "end": 48.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:11566046", "PMID:15250815",
                               "PMID:1713648"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Zorrilla et al.: major depression is associated "
                         "with reduced NK-cell cytotoxicity and lymphocyte "
                         "proliferation. Segerstrom and Miller: chronic "
                         "stressors suppress cellular and humoral immunity, "
                         "though subjective stress reports alone generally did "
                         "not track immune change. Cohen et al.: psychological "
                         "stress raised infection rates after viral challenge "
                         "in a dose-response manner.",
            },
            {
                "text": "[anxiety and depression impact] ... our ability ... to "
                        "surveil against cancer cells",
                "source": "both",
                "start": 41.4, "end": 48.7,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:18493231"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Chida et al.'s meta-analysis links stress-related "
                         "psychosocial factors with cancer incidence overall "
                         "but not stressful life events, and asks for "
                         "caution; immune surveillance itself is not measured "
                         "in people. Too indirect for SUPPORTED. An IPD meta-"
                         "analysis of depression, anxiety and cancer risk "
                         "(PMID:37545248) was retrieved but its record has no "
                         "abstract text, so it is not cited.",
            },
        ],
    },
    {
        "video_id": "v155",
        "external_reason": "The turmeric-spread claims are untested for the product; "
                           "curcumin supplement trials are only indirect support.",
        "topic": "supplements / turmeric",
        "case_tags": ["screen_only", "uncertain_science"],
        "confidence": "medium",
        "notes": "A silent advert card for a turmeric spread ('Yogic "
                 "SuperFood', National Heart Month): five structure-function "
                 "claims on screen and nothing spoken, so OCR is the only way "
                 "in. None is tested for a turmeric spread; curcumin "
                 "supplement trials do lower inflammatory markers, cited on "
                 "the inflammation claim as indirect support. All "
                 "INSUFFICIENT, CANNOT_RECOGNIZE.",
        "claims": [
            {
                "text": "Turmeric ... Helps Encourage healthy inflammatory "
                        "function",
                "source": "screen",
                "start": 0.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:36804260"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "Dehzad et al. (66 RCTs): turmeric/curcumin "
                         "supplementation lowers CRP, TNF-alpha and IL-6. "
                         "That is supplements at trial doses, not a spread, "
                         "and 'healthy inflammatory function' is vague: "
                         "indirect, so INSUFFICIENT.",
            },
            {
                "text": "Turmeric ... Support digestion",
                "source": "screen",
                "start": 0.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Not retrieved for a turmeric spread.",
            },
            {
                "text": "Turmeric ... Promote cardiovascular health",
                "source": "screen",
                "start": 0.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Not retrieved for a turmeric spread.",
            },
            {
                "text": "Turmeric ... Support the immune system",
                "source": "screen",
                "start": 0.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Not retrieved for a turmeric spread.",
            },
            {
                "text": "Turmeric ... Promotes healthy skin",
                "source": "screen",
                "start": 0.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Not retrieved for a turmeric spread.",
            },
        ],
    },
    {
        "video_id": "v156",
        "topic": "none (non-health)",
        "case_tags": ["out_of_scope"],
        "confidence": "high",
        "notes": "Seven seconds of a song with the caption 'you must be the "
                 "ugly ex'. No health content.",
        "claims": [],
    },
    {
        "video_id": "v157",
        "external_reason": "Workout motivation with no checkable health assertion.",
        "topic": "fitness (motivation)",
        "case_tags": [],
        "confidence": "high",
        "notes": "A short motivational clip: working out before or after work "
                 "takes mental strength and is 'a badass mindset'. Praise, "
                 "not a checkable health assertion. No checkable claims.",
        "claims": [],
    },
]
