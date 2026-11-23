"""Batch 2, part b: v108-v132. Rules and format: labels.py, labels_batch2.py."""

_GLUED_BEANS = ("One of six videos in this part answering the same viral clip, "
                "in which 'ticks' or 'bugs' are picked off skin and turn out "
                "to be glued-on beans (v108, v117, v118, v123, v128, v130, "
                "v132). The debunked claim is about what one staged video "
                "shows, which no paper or reference can test, so it is "
                "NOT_VERIFIABLE and the debunk cannot be scored as DEBUNKING "
                "under section 9. Kept in scope rather than out_of_scope: the "
                "hoax is a skin-parasite health scare, and how the pipeline "
                "handles an unjudgeable debunk is exactly what this set "
                "should measure.")

LABELS = [
    {
        "video_id": "v108",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking", "other_language"],
        "confidence": "high",
        "notes": "@idermatologo, Spanish. A dermatologist tagged in a clip of "
                 "a barber 'removing ticks with a razor' says they are "
                 "black-eyed peas and the glue is visible; captions 'EATEN BY "
                 "TICKS' then '#FAKE'. " + _GLUED_BEANS,
        "external_reason": "The refuted 'ticks' claim is about what one "
                           "staged clip shows, which no study can test, so "
                           "it is NOT_VERIFIABLE and the debunk is "
                           "unjudgeable.",
        "claims": [
            {
                "text": "supuestamente el barbero remove estas garrapatas con "
                        "navaja",
                "start": 0.0, "end": 4.9,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "EN: supposedly the barber removes these ticks with a "
                         "razor. Refuted at once ('estos son frijoles ... se "
                         "ve el pegamento, así que esto es súper falso'), and "
                         "the closing caption reads '#FAKE'. Whether a "
                         "particular clip shows ticks or beans is not a "
                         "question PubMed or a reference can answer.",
            },
        ],
    },
    {
        "video_id": "v109",
        "topic": "medicines / semaglutide (Ozempic) self-medication",
        "case_tags": ["other_language"],
        "confidence": "medium",
        "notes": "@danydlg, Spanish, answering a commenter who wants to buy "
                 "Ozempic without a prescription. A warning against "
                 "self-medication, which is sound advice, built from eleven "
                 "assertions: four true benefits (diabetes, stroke, heart "
                 "attack, diabetes-related death), weight regain after "
                 "stopping (true), a thyroid-tumour signal (supported by "
                 "trial meta-analyses), and then three listed harms that the "
                 "evidence runs against -- stroke and new type 2 diabetes, "
                 "which semaglutide lowers, and seizures, where the "
                 "retrieved cohorts show lower risk. The stroke row "
                 "contradicts her own second sentence. So a debunk-style "
                 "warning video comes out MISINFO, on the risks it lists "
                 "rather than on its message. Pancreatitis, the labelled "
                 "risk most people know, is the one the retrieved "
                 "meta-analysis does not support either.",
        "external_reason": "Her warning against self-medicating is sound, "
                           "but among its listed risks are stroke, seizures "
                           "and new type 2 diabetes, which trials and "
                           "cohorts show semaglutide lowers.",
        "claims": [
            {
                "text": "Es un medicamento que trata diabetes tipo 2",
                "start": 3.5, "end": 6.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:27633186", "PMID:30615985"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: It is a medicine that treats type 2 diabetes. "
                         "SUSTAIN-6 and the review of once-weekly semaglutide "
                         "are both in people with type 2 diabetes.",
            },
            {
                "text": "reduce el riesgo de un derrame cerebral",
                "start": 6.0, "end": 8.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:27633186", "PMID:31422062"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: it reduces the risk of stroke. SUSTAIN-6: "
                         "nonfatal stroke 1.6% vs 2.7% (HR 0.61, 0.38-0.99); "
                         "class meta-analysis HR 0.84 for fatal or nonfatal "
                         "stroke.",
            },
            {
                "text": "reduce los riesgos de ataques cardíacos",
                "start": 8.4, "end": 10.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:31422062", "PMID:37952131"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: it reduces the risk of heart attacks. The "
                         "GLP-1 receptor agonist meta-analysis gives HR 0.91 "
                         "(0.84-1.00) for fatal or nonfatal MI, and SELECT "
                         "reduced a composite including nonfatal MI in "
                         "people without diabetes. SUSTAIN-6 alone did not "
                         "reach significance for MI (HR 0.74, 0.51-1.08), "
                         "hence medium.",
            },
            {
                "text": "reduce los riesgos de la muerte causada por diabetes "
                        "tipo 2",
                "start": 10.6, "end": 14.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:31422062"],
                "contradicting": [],
                "confidence": "low",
                "notes": "EN: it reduces the risk of death caused by type 2 "
                         "diabetes. Read as death in people with type 2 "
                         "diabetes: the class meta-analysis found all-cause "
                         "mortality down 12% and cardiovascular death HR "
                         "0.88. SUSTAIN-6 alone found similar cardiovascular "
                         "death rates. Low confidence because the wording "
                         "('death caused by diabetes') is not an outcome any "
                         "trial reports.",
            },
            {
                "text": "si no está llevado de la mano con un médico "
                        "especialista, puede llegar a darte un tumor en la "
                        "glándula tiroidea",
                "start": 17.0, "end": 23.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:38018310", "PMID:40437949"],
                "contradicting": [],
                "confidence": "low",
                "notes": "EN: if not supervised by a specialist, it can give "
                         "you a thyroid tumour. Two meta-analyses of RCTs "
                         "found more thyroid cancer with GLP-1 receptor "
                         "agonists (MH-OR 1.52 and 1.55), with a fragility "
                         "index of 1 and a 5-year number needed to harm of "
                         "1349. The 'without a specialist' condition is not "
                         "something the trials test; supervision is not "
                         "shown to change this risk.",
            },
            {
                "text": "[puede llegar a darte] pancreatitis",
                "start": 23.8, "end": 25.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:38555109", "PMID:40499738"],
                "confidence": "low",
                "notes": "EN: [it can give you] pancreatitis. The "
                         "semaglutide-specific meta-analysis of 21 trials "
                         "found no increase in acute pancreatitis (OR 0.7, "
                         "0.5-1.2), and the 55-trial GLP-1RA meta-analysis "
                         "found little or no effect on GI events other than "
                         "gallstones and GERD. Not CONTRADICTED: the claim "
                         "is 'it can', pancreatitis is a labelled warning, "
                         "and trials are not powered for rare events, so a "
                         "null pooled estimate does not show it cannot "
                         "happen (section 7, strength of inference). The two "
                         "meta-analyses stay cited as the evidence against.",
            },
            {
                "text": "[puede llegar a darte] convulsiones",
                "start": 25.0, "end": 26.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:42308439", "PMID:39764175"],
                "confidence": "medium",
                "notes": "EN: [it can give you] seizures. A target-trial "
                         "emulation found semaglutide associated with lower "
                         "adult-onset seizure risk (HR 0.44 vs other "
                         "glucose-lowering drugs), and the 12-month TriNetX "
                         "cohort found no increase in neurological outcomes. "
                         "Observational only, hence medium.",
            },
            {
                "text": "puedes desarrollar diabetes tipo 2",
                "start": 26.2, "end": 28.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:35724304"],
                "confidence": "high",
                "notes": "EN: you can develop type 2 diabetes. In STEP 1, 3 "
                         "and 4, 84-90% of participants with prediabetes "
                         "reached normoglycaemia on semaglutide vs 48-70% on "
                         "placebo, and fewer normoglycaemic participants "
                         "progressed to prediabetes.",
            },
            {
                "text": "derrames cerebrales entre otras tragedias que te "
                        "pueden llegar a pasar si lo consumes por ti sola",
                "start": 28.6, "end": 33.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:27633186", "PMID:31422062"],
                "confidence": "medium",
                "notes": "EN: strokes, among other tragedies that can happen "
                         "if you take it on your own. Contradicts c2 in the "
                         "same video: the drug lowers stroke risk. 'On your "
                         "own' is not a condition any trial tests, which is "
                         "why medium rather than high.",
            },
            {
                "text": "se tiene que ir aumentando la dosis poco a poco ya que "
                        "si no se hace esto tu páncreas puede dejar de "
                        "funcionar",
                "start": 37.0, "end": 50.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: the dose has to be increased gradually, because "
                         "otherwise your pancreas can stop working. Gradual "
                         "escalation is the labelled regimen (for GI "
                         "tolerability), but nothing retrieved links skipping "
                         "it to pancreatic failure.",
            },
            {
                "text": "obviamente vas a regresar a tu peso en el que "
                        "estabas",
                "start": 46.0, "end": 50.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35441470"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: obviously you will go back to the weight you "
                         "were. STEP 1 extension: one year after stopping, "
                         "participants regained two-thirds of the weight "
                         "lost.",
            },
        ],
    },
    {
        "video_id": "v110",
        "topic": "ophthalmology / cosmetic eye colour change",
        "case_tags": ["screen_only", "other_language"],
        "confidence": "medium",
        "notes": "@charlotteinga, Spanish, no speech (whisper returned one "
                 "'You' over music). Captions document three sessions of a "
                 "cosmetic eye-colour procedure ('Mis ojos eran color "
                 "avellana', 'Primera sesión', 'Lentes para la sensibilidad "
                 "a la luz'). The one checkable assertion -- that you can "
                 "change your eye colour -- is true: laser iris "
                 "depigmentation does it. What the video leaves out is the "
                 "risk, which v116 is about. An omission is not a claim, so "
                 "this is NO_MISINFO; a promotional testimonial with no "
                 "false sentence is a useful hard case for a classifier "
                 "that reads intent.",
        "claims": [
            {
                "text": "Sabías que puedes cambiar el color de tus ojos?",
                "start": 0.0, "end": 2.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33484383", "PMID:35061240"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Did you know you can change the colour of your "
                         "eyes? Framed as a question but asserted. The "
                         "photoablative iridoplasty series reports colour "
                         "change in 1176 eyes; the review covers the "
                         "surgical alternatives. Safety is a separate "
                         "question the video does not raise (see v116).",
            },
        ],
    },
    {
        "video_id": "v111",
        "topic": "nutrition / legumes",
        "case_tags": ["other_language", "clearly_false"],
        "confidence": "high",
        "notes": "@lahorademiguelangelruiz, Spanish, a clip of a "
                 "naturopathic speaker arguing that legumes are unhealthy "
                 "because starch and protein are an 'incompatible mixture' "
                 "(food-combining theory). The core claim that legumes are "
                 "not healthy is contradicted by meta-analyses of legume "
                 "intake and mortality.",
        "claims": [
            {
                "text": "La legumbre no es buena porque está hecha de almidón "
                        "y proteína y es una mezcla incompatible",
                "start": 0.0, "end": 7.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:10805507"],
                "confidence": "medium",
                "notes": "EN: Legumes are not good because they are made of "
                         "starch and protein, an incompatible mixture. The "
                         "only trial of food combining found it no better "
                         "than a balanced diet for weight and metabolic "
                         "markers, which undercuts the theory but does not "
                         "test 'incompatibility' itself.",
            },
            {
                "text": "Que no se digiere",
                "start": 7.8, "end": 14.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:29771297"],
                "confidence": "medium",
                "notes": "EN: It is not digested. Dual-tracer measurement in "
                         "humans: indispensable amino acid digestibility of "
                         "chickpea and mung bean protein about 57-58%. Lower "
                         "than animal protein, but digested.",
            },
            {
                "text": "te vas a estar con gases o con inflamación, con una "
                        "digestión lenta",
                "start": 7.8, "end": 14.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:22104320"], "contradicting": [],
                "confidence": "low",
                "notes": "EN: you will have gas or inflammation, with slow "
                         "digestion. In three feeding studies fewer than half "
                         "reported more flatulence in the first week, and the "
                         "authors call the concern exaggerated. So gas in "
                         "some people is supported, the universal 'you will' "
                         "is not, and 'inflammation' and slow digestion were "
                         "not tested.",
            },
            {
                "text": "eso al final se pudre y se fermenta",
                "start": 14.2, "end": 16.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: in the end it rots and ferments. Colonic "
                         "fermentation of legume fibre is normal physiology; "
                         "'rots' as a harm was not found tested anywhere.",
            },
            {
                "text": "hay gente que piensa que la legumbre es sana, pero no "
                        "lo es",
                "start": 17.6, "end": 21.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:36811595", "PMID:28077199"],
                "confidence": "high",
                "notes": "EN: some people think legumes are healthy, but "
                         "they are not. Dose-response meta-analysis: higher "
                         "legume intake with lower all-cause mortality (HR "
                         "0.94); CVD meta-analysis: 10% lower CVD and CHD "
                         "risk.",
            },
        ],
    },
    {
        "video_id": "v112",
        "topic": "cancer / ketogenic diet",
        "case_tags": ["other_language", "clearly_false"],
        "confidence": "high",
        "notes": "@farandafit, Spanish. A speaker presents the Warburg effect "
                 "as universal ('99.98% of cancers') and concludes that a "
                 "ketogenic diet starves cancer cells into apoptosis; the "
                 "persistent caption reads 'La KETO mata de hambre al "
                 "cáncer'. The mechanistic premise is contradicted by "
                 "reviews showing many cancer cells use their mitochondria; "
                 "the clinical promise is untested in people.",
        "claims": [
            {
                "text": "La KETO mata de hambre al cáncer",
                "start": 0.0, "end": 46.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [],
                "contradicting": ["PMID:33813635", "PMID:28353094"],
                "confidence": "high",
                "notes": "EN: Keto starves cancer. Two systematic reviews: no "
                         "conclusive evidence of anti-tumour effects or "
                         "better survival, mostly low-quality studies. That "
                         "is absence of evidence, so INSUFFICIENT, cited on "
                         "the contradicting side because both reviews "
                         "address and fail to support it.",
            },
            {
                "text": "la inmensa mayoría, el 99,98% de los cánceres, "
                        "obtienen su nutrición a partir de la glucosa, de esa "
                        "fermentación",
                "start": 0.0, "end": 22.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:32548570", "PMID:36367492"],
                "confidence": "medium",
                "notes": "EN: the vast majority, 99.98% of cancers, get "
                         "their nutrition from glucose, from that "
                         "fermentation. 'Mitochondria in cancer': constitutive "
                         "glycolysis was treated as a hallmark of cancer "
                         "cells, 'which it is not'; the Warburg/OXPHOS review "
                         "describes cancer cells switching reversibly between "
                         "the two pathways. The 99.98% figure appears in "
                         "nothing retrieved.",
            },
            {
                "text": "porque no pueden utilizar la glucosa a nivel "
                        "mitocondrial, sino que la queman en el citoplasma",
                "start": 0.0, "end": 22.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:32548570", "PMID:36367492"],
                "confidence": "medium",
                "notes": "EN: because they cannot use glucose in the "
                         "mitochondria, so they burn it in the cytoplasm. "
                         "Same reviews: mitochondria remain powerhouses in "
                         "some cancer cells.",
            },
            {
                "text": "cuando yo le cambio el switch metabólico y empieza a "
                        "priorizar el uso de grasas esa célula cancerosa se "
                        "queda sin alimento ... tiene que generar la "
                        "apoptosis",
                "start": 31.3, "end": 46.65,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:33813635"],
                "confidence": "medium",
                "notes": "EN: when I flip the metabolic switch to burning fat, "
                         "the cancer cell runs out of food and must undergo "
                         "apoptosis. No human evidence of tumour cell death "
                         "from a ketogenic diet in the review of 39 studies.",
            },
        ],
    },
    {
        "video_id": "v113",
        "topic": "alternative remedies / drinking seawater",
        "case_tags": ["other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "@sabiduriancestral, Spanish, with the narration repeated "
                 "in captions. Drinking diluted seawater is promoted as a "
                 "near-universal cure (cancer, hypertension, diabetes, skin, "
                 "colon cleansing, cell regeneration). Almost certainly "
                 "false, but nothing retrieved tests drinking seawater for "
                 "any of these: the only human trials are of desalinated "
                 "deep-sea mineral water, a different product. Every claim "
                 "is INSUFFICIENT_EVIDENCE, so the video is CANNOT_RECOGNIZE "
                 "-- the section 7 rule working as designed on a video a "
                 "reader would call misinformation instantly.",
        "external_reason": "Every cure claim is untested rather than "
                           "disproven (the only human trials are of "
                           "desalinated deep-sea water), so nothing is "
                           "CONTRADICTED and the video is unjudgeable.",
        "claims": [
            {
                "text": 'el agua de mar ha demostrado resultados asombrosos en pacientes con enfermedades como cáncer',
                "start": 12.6, "end": 25.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: seawater has shown amazing results in patients with diseases such as cancer. One of four diseases listed together, split one per row (section 4). Searched ('drinking seawater health effects'); the hits test desalinated deep-sea water (PMID 35276942, 32878045) or rats, not seawater for any of these diseases.",
            },
            {
                "text": 'el agua de mar ha demostrado resultados asombrosos en pacientes con enfermedades como … hipertensión',
                "start": 12.6, "end": 25.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'EN: ... such as hypertension. Same list and the same search as the cancer row: nothing tests drinking seawater for it.',
            },
            {
                "text": 'el agua de mar ha demostrado resultados asombrosos en pacientes con enfermedades como … diabetes',
                "start": 12.6, "end": 25.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'EN: ... such as diabetes. Same list and the same search as the cancer row: nothing tests drinking seawater for it.',
            },
            {
                "text": 'el agua de mar ha demostrado resultados asombrosos en pacientes con enfermedades como … enfermedades de la piel',
                "start": 12.6, "end": 25.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'EN: ... such as skin disease. Same list and the same search as the cancer row: nothing tests drinking seawater for it.',
            },
            {
                "text": "su capacidad para limpiar el colon y regenerar las "
                        "células",
                "start": 20.2, "end": 28.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: its ability to cleanse the colon and "
                         "regenerate cells. Nothing tests either.",
            },
            {
                "text": "vas a sentir los resultados de la mejoría de "
                        "cualquier enfermedad o dolencia desde el primer día",
                "start": 48.2, "end": 52.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: you will feel improvement in any disease or "
                         "ailment from day one. Too broad to test; no study "
                         "exists.",
            },
        ],
    },
    {
        "video_id": "v114",
        "topic": "nutrition / salt, sugar and blood pressure",
        "case_tags": ["screen_only", "other_language", "clearly_false"],
        "confidence": "medium",
        "notes": "@keto_increiblee, Spanish, six seconds. The speech is song "
                 "lyrics ('I know it's getting late'); everything is in one "
                 "on-screen card headed 'NOS MINTIERON' (they lied to us). "
                 "The statements under the heading are what the card "
                 "presents as the truth, so they are ENDORSES. A second "
                 "screen-only case like v18: without OCR there is nothing to "
                 "label. The OCR line 'el cuerpo puede fabricar, sin embargo "
                 "el azúcar sí' plainly lost a 'no' (the card means the body "
                 "cannot make salt, but can make sugar); quoted as read.",
        "claims": [
            {
                "text": "Eliminar toda la sal sube la presión arterial",
                "start": 0.0, "end": 4.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:23558162"],
                "confidence": "high",
                "notes": "EN: Cutting out all salt raises blood pressure. "
                         "Cochrane meta-analysis of 34 trials: a 4.4 g/day "
                         "salt reduction lowered systolic BP by 4.2 mm Hg, "
                         "with a dose-response.",
            },
            {
                "text": "[Eliminar toda la sal ...] y se tiene incidencia a "
                        "infarto de miocardio",
                "start": 0.0, "end": 4.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:24651634", "PMID:34579105"],
                "contradicting": ["PMID:35944931"],
                "confidence": "low",
                "notes": "EN: [cutting out all salt] brings myocardial "
                         "infarction. The genuine controversy: cohort "
                         "meta-analysis finds more deaths and CVD events "
                         "with low than with usual sodium, and the PURE "
                         "authors recommend 3-5 g/day; the trial evidence on "
                         "low-sodium salt substitutes points to benefit. "
                         "Neither tests eliminating all salt.",
            },
            {
                "text": "La causa de hipertensión es la prediabetes, el azúcar "
                        "de los carbohidratos refinados",
                "start": 0.0, "end": 4.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:24808490"], "contradicting": [],
                "confidence": "low",
                "notes": "EN: The cause of hypertension is prediabetes, the "
                         "sugar of refined carbohydrates. Trials do link "
                         "higher sugar intake to worse cardiometabolic "
                         "markers, but nothing tests sugar as THE cause. The "
                         "salt-reduction trials under c1 show salt is a "
                         "cause, which undermines the exclusivity without "
                         "contradicting sugar's role.",
            },
            {
                "text": "La sal es vida, el cuerpo puede fabricar,",
                "start": 0.0, "end": 4.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN (as meant): Salt is life, the body [cannot] make "
                         "it. OCR dropped the 'no' (see video notes). True "
                         "as textbook physiology -- sodium is an element and "
                         "an essential nutrient -- but no retrieved paper or "
                         "reference states it, so it stays unsettled here.",
            },
            {
                "text": "sin embargo el azúcar sí [puede fabricar el cuerpo]",
                "start": 0.0, "end": 4.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:28731034"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: however the body can make sugar. Hepatic "
                         "gluconeogenesis: 'the liver ... produces glucose "
                         "during fasting'. Bracketed words restore the "
                         "referent from the previous line.",
            },
        ],
    },
    {
        "video_id": "v115",
        "topic": "weight loss / unnamed diet pills",
        "case_tags": ["screen_only", "other_language"],
        "confidence": "high",
        "notes": "@dianitaflorez, Spanish, no speech. A before/after "
                 "testimonial for unnamed 'poderosas pastillas' with an "
                 "Instagram business handle on screen -- a sales funnel. The "
                 "product is never named, so its effect cannot be checked: "
                 "NOT_VERIFIABLE, and the video is CANNOT_RECOGNIZE. The "
                 "rest is anecdote (felt 100 kg, depressed, earlier "
                 "surgery).",
        "claims": [
            {
                "text": "Sin mis pastillas no lo hubiera logrado",
                "start": 26.0, "end": 30.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "EN: Without my pills I would not have made it. "
                         "Personal testimony about an unnamed product; "
                         "earlier captions ('Así estaba antes de probar mis "
                         "poderosas pastillas', 'Empezó la magia de mis "
                         "pastillas') make the same assertion.",
            },
        ],
    },
    {
        "video_id": "v116",
        "topic": "ophthalmology / cosmetic laser iris depigmentation",
        "case_tags": ["debunking", "other_language"],
        "confidence": "medium",
        "notes": "@itsevaruiz, Spanish, an optometry student reacting to an "
                 "influencer about to have eye-colour-change surgery, then "
                 "explaining the mechanism of harm. A real debunk, but it "
                 "refutes the procedure's safety implicitly rather than "
                 "naming a claim to refute, so every row is her own "
                 "assertion (ENDORSES). The mechanism is supported "
                 "(melanin, depigmentation, case reports of pigment-driven "
                 "IOP rise and glaucoma), so the video is NO_MISINFO, not "
                 "DEBUNKING. The harm rows are MIXED: a 1176-eye series by "
                 "the procedure's developer reports no IOP change, against "
                 "case reports and reviews of pigmentary glaucoma. The "
                 "counterpart of v110.",
        "external_reason": "She argues against the procedure without naming "
                           "a claim to refute, so all her rows are her own "
                           "endorsed, largely supported statements and the "
                           "rules give NO_MISINFO.",
        "claims": [
            {
                "text": "a nadie le compensa con tal de tener los ojos azules "
                        "tener una ceguera a largo plazo, quedarte sin vista",
                "start": 34.8, "end": 46.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:36175318", "PMID:39545587"],
                "contradicting": ["PMID:33484383"],
                "confidence": "medium",
                "notes": "EN: it is not worth long-term blindness and "
                         "losing your sight just to have blue eyes. Case "
                         "reports call the consequences potentially "
                         "devastating; no study measures long-term vision "
                         "loss, and the large series reports none.",
            },
            {
                "text": "El color de los ojos viene determinado por el "
                        "pigmento, la melanina que tenemos en el iris, a más "
                        "pigmento más oscuros",
                "start": 55.8, "end": 66.7,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:9154287", "PMID:18353148"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: Eye colour is set by pigment, the melanin in "
                         "the iris; more pigment, darker eyes. Iris colour "
                         "differences come from the amount of melanin in "
                         "stromal melanocytes, with more melanin in darker "
                         "irides.",
            },
            {
                "text": "En esta cirugía un láser te va despigmentando el iris "
                        "y se te quedan los ojos de color azul",
                "start": 60.7, "end": 71.5,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:33484383", "PMID:41982480"],
                "contradicting": [],
                "confidence": "high",
                "notes": "EN: In this surgery a laser depigments the iris and "
                         "your eyes turn blue. The iridoplasty series "
                         "reports turquoise-blue to grey-blue results.",
            },
            {
                "text": "este pigmento no desaparece ... se te acumula el "
                        "humor acuoso en la cámara anterior ... deriva en una "
                        "presión intraocular aumentada",
                "start": 76.9, "end": 102.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:41982480", "PMID:36175318"],
                "contradicting": ["PMID:33484383"],
                "confidence": "medium",
                "notes": "EN: the pigment does not vanish; it accumulates in "
                         "the aqueous humour of the anterior chamber, "
                         "leading to raised intraocular pressure. Case "
                         "reports: IOP of 34 and 60 mm Hg after laser iris "
                         "depigmentation, and secondary pigmentary glaucoma. "
                         "The 1176-eye series reports no IOP change. "
                         "Evidence on both sides.",
            },
            {
                "text": "esto deriva en enfermedades ... como glaucoma, daños "
                        "en el nervio óptico",
                "start": 102.4, "end": 108.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:36175318", "PMID:39545587"],
                "contradicting": ["PMID:33484383"],
                "confidence": "medium",
                "notes": "EN: this leads to diseases such as glaucoma and "
                         "optic nerve damage. Same split as c4: case report "
                         "and review of pigmentary glaucoma vs a large "
                         "series without it.",
            },
            {
                "text": "desprendimientos de vitreo, desprendimientos de "
                        "retina",
                "start": 108.5, "end": 112.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: vitreous detachment, retinal detachment. None "
                         "of the retrieved case reports or reviews mention "
                         "either after laser iris depigmentation.",
            },
            {
                "text": "es una cirugía prohibida en tantos y tantos países",
                "start": 122.3, "end": 128.7,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: it is a surgery banned in many countries. A "
                         "regulatory claim; no retrieved reference lists "
                         "where the procedure is or is not permitted.",
            },
        ],
    },
    {
        "video_id": "v117",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "@teawithmd, a dermatologist duetting the bean clip: they "
                 "are beans, the glue is visible, and gluing things to skin "
                 "can cause allergy. " + _GLUED_BEANS + " Unlike the others, "
                 "she adds a checkable side claim (glue allergy), which is "
                 "SUPPORTED, so this one comes out NO_MISINFO.",
        "external_reason": "The refuted 'bugs' claim is NOT_VERIFIABLE (one "
                           "staged clip), and her supported glue-allergy "
                           "claim makes the rules give NO_MISINFO.",
        "claims": [
            {
                "text": "she's pretending that this is like bugs coming off",
                "start": 0.2, "end": 9.6,
                "kind": "fact_of_record",
                "stance": "REFUTES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "Refuted in the next breath ('clearly these are "
                         "obviously beans'). Not testable against "
                         "literature.",
            },
            {
                "text": "you can get a nasty allergy from glue on your skin",
                "start": 23.5, "end": 28.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:38386590"], "contradicting": [],
                "confidence": "medium",
                "notes": "Systematic review of allergic contact dermatitis "
                         "to octyl cyanoacrylate skin glue, patch-test "
                         "confirmed in 21 studies. Medium: the glue in the "
                         "clip is unknown, and the evidence is for medical "
                         "cyanoacrylates.",
            },
        ],
    },
    {
        "video_id": "v118",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking", "speech_screen_disagree"],
        "confidence": "medium",
        "notes": "@mikemuellnermd, ten seconds, 'Doctor Reacts'. The speech "
                 "plays along ('I don't know what this is. We need an urgent "
                 "dermatology referral') and the closing caption gives the "
                 "answer ('Those are just glued on beans!'). Speech and "
                 "screen disagree, and only the screen carries the "
                 "speaker's real position -- a small, clean "
                 "speech_screen_disagree case. " + _GLUED_BEANS,
        "external_reason": "The debunk is about what one staged clip shows "
                           "(beans, not a skin condition), which is "
                           "NOT_VERIFIABLE, so the video is unjudgeable.",
        "claims": [
            {
                "text": "Those are just glued on beans!",
                "start": 8.0, "end": 10.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Screen only. The spoken 'urgent dermatology "
                         "referral' is a set-up joke, not a claim the "
                         "speaker holds, so it is not recorded as one.",
            },
        ],
    },
    {
        "video_id": "v119",
        "topic": "cancer / sugar, alkaline diet, 'cancer is a fungus'",
        "case_tags": ["other_language", "clearly_false"],
        "confidence": "medium",
        "notes": "@the_lost_mind_guy. English speech from a clinic "
                 "spokesperson ('We're gonna starve that cancer ... it loves "
                 "glucose'), with Spanish captions that add claims the "
                 "speaker never makes: 'Alcaliniza tu cuerpo', 'El "
                 "bicarbonato es bueno', 'El cáncer es un hongo' (the "
                 "Simoncini theory). The decisive false claim is screen "
                 "only, in a second language.",
        "claims": [
            {
                "text": "We're gonna starve that cancer. ... It loves glucose. "
                        "And so we suggested six weeks no sugar, no honey, no "
                        "sweet at all",
                "start": 0.2, "end": 24.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:33813635"],
                "confidence": "medium",
                "notes": "Captioned 'Cúrate del cáncer matándolo de hambre' "
                         "(cure yourself of cancer by starving it). No human "
                         "evidence that cutting dietary sugar starves "
                         "tumours; the systematic review of carbohydrate-"
                         "restricted diets in cancer found no conclusive "
                         "anti-tumour effect.",
            },
            {
                "text": "Alcaliniza tu cuerpo",
                "start": 0.0, "end": 58.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Alkalinise your body (as a cancer measure). The "
                         "systematic review of dietary acid load and alkaline "
                         "water in cancer (PMID 27297008) found almost no "
                         "research either way -- absence, not contradiction. "
                         "Not cited on either side for that reason.",
            },
            {
                "text": "El Bicarbonato es bueno",
                "start": 0.0, "end": 58.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "EN: Bicarbonate is good. Too vague to test as "
                         "stated ('good' for what, in what dose); in context "
                         "it alludes to bicarbonate as a cancer treatment.",
            },
            {
                "text": "El Cancer es un hongo",
                "start": 0.0, "end": 58.4,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:34459009", "PMID:21376230"],
                "confidence": "medium",
                "notes": "EN: Cancer is a fungus. Contradicted by what cancer "
                         "is: the retrieved reviews describe it as somatic "
                         "evolution of the body's own cells (branched "
                         "evolution 'grounded in somatic selection') with "
                         "defined cellular hallmarks. Neither paper "
                         "addresses the fungus theory by name, hence "
                         "medium.",
            },
        ],
    },
    {
        "video_id": "v120",
        "topic": "alternative remedies / drinking seawater",
        "case_tags": ["other_language", "missing_evidence"],
        "confidence": "medium",
        "notes": "@marcomendoza007, Spanish, three minutes at the beach "
                 "drinking seawater from a bottle. Claims it removes heavy "
                 "metals (linked to an 'experimental vaccine' said to "
                 "contain them), holds 118 minerals of the periodic table, "
                 "and cleanses the gut. All untested in anything retrieved, "
                 "so CANNOT_RECOGNIZE, like v113. The '118 minerals' claim "
                 "is very likely false (118 is the count of all known "
                 "elements, including synthetic ones), but no retrieved "
                 "reference gives seawater's composition to contradict it.",
        "external_reason": "Each claim (heavy-metal removal, vaccine metals, "
                           "118 minerals, gut cleansing) is untested in "
                           "anything retrieved rather than contradicted, so "
                           "the video is unjudgeable.",
        "claims": [
            {
                "text": "los beneficios son muchísimo primero elimina los "
                        "metales pesados del cuerpo",
                "start": 26.7, "end": 37.4,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: the benefits are many; first, it removes heavy "
                         "metals from the body. Repeated at 55.9-63.9 ('los "
                         "minerales que tiene el agua de mar pueden eliminar "
                         "esos metales pesados'), kept as one claim. No study "
                         "found.",
            },
            {
                "text": "se dice que en la vacuna hay muchos metales pesados",
                "start": 37.4, "end": 47.0,
                "kind": "fact_of_record",
                "stance": "QUOTES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: it is said that the vaccine contains a lot of "
                         "heavy metals. Attributed ('se dice') and then "
                         "framed as doubt ('tenemos la duda'), so QUOTES. "
                         "Searched for COVID-19 vaccine composition and "
                         "heavy metals; nothing relevant came back.",
            },
            {
                "text": "el agua de mar contiene 118 minerales de la tabla "
                        "periódica",
                "start": 72.6, "end": 80.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: seawater contains 118 minerals of the periodic "
                         "table. See video notes; the seawater composition "
                         "search returned only sediment and plankton "
                         "papers.",
            },
            {
                "text": "les va a mandar al baño ... porque les va a hacer una "
                        "limpieza de todo lo que han comido y si lo hacen "
                        "constantemente va a limpiar todos los residuos",
                "start": 114.5, "end": 130.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: it will send you to the bathroom because it "
                         "cleanses everything you have eaten, and done "
                         "regularly it cleans out all accumulated residues. "
                         "Searched for oral saline as a laxative; no hits.",
            },
        ],
    },
    {
        "video_id": "v121",
        "topic": "gynaecology / garlic vaginal ovules",
        "case_tags": ["satire", "other_language", "debunking"],
        "confidence": "medium",
        "notes": "@dra.moltoni.gineco, Spanish. A gynaecologist mocks the "
                 "trend of inserting garlic cloves vaginally: three "
                 "deadpan 'advantages' (work for street vendors, "
                 "recyclable, contraception by smell), then captions "
                 "'Ahora fuera del humor ...': don't self-medicate for "
                 "discharge or itching, natural things can irritate the "
                 "mucosa, not all genital itching is [yeast]. The speech is "
                 "satire, so its claim is UNCLEAR; the on-screen warnings "
                 "are supported. NO_MISINFO. A satire case whose real "
                 "position is only on screen.",
        "external_reason": "This is the gynaecologist mocking the garlic "
                           "trend, not promoting it; her on-screen warnings "
                           "are supported, so the rules give NO_MISINFO.",
        "claims": [
            {
                "text": "si andás necesitando anticoncepción, puede ser una "
                        "opción, con el olor que te va a quedar",
                "start": 15.0, "end": 21.0,
                "kind": "research_question",
                "stance": "UNCLEAR", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: if you need contraception, [garlic ovules] can "
                         "be an option, with the smell you'll be left with. "
                         "Sarcasm, so UNCLEAR per section 5, and a joke "
                         "rather than a testable assertion. Whisper garbles "
                         "it ('adiconcepción', 'efecto de ausentar persona').",
            },
            {
                "text": "Aún cosas naturales pueden irritar la mucosa vaginal",
                "start": 12.0, "end": 14.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35174620", "PMID:33691515",
                               "PMID:24308540"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Even natural things can irritate the vaginal "
                         "mucosa. Case reports of garlic chemical burns of "
                         "skin and of oral mucosa, and in the oral-garlic "
                         "candida trial more adverse effects with garlic "
                         "(83% vs 43%). No vaginal case was retrieved, hence "
                         "medium.",
            },
            {
                "text": "No todo lo que pica en los genitales son …",
                "start": 16.0, "end": 20.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:32181734", "PMID:7741332"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: Not everything that itches in the genitals is "
                         "... (the caption is cut off at the frame edge; in "
                         "context, a yeast infection). Vulvar pruritus has "
                         "many causes beyond candidiasis, and clinical "
                         "criteria and self-diagnosis are unreliable for "
                         "yeast vaginitis.",
            },
        ],
    },
    {
        "video_id": "v122",
        "topic": "cardiology / statins",
        "case_tags": ["other_language", "clearly_false"],
        "confidence": "high",
        "notes": "@alquimiamariel, Spanish, speech plus a long run of dense "
                 "captions after the speech ends (43-59 s) that add claims "
                 "of their own. The spoken core -- statins damage the "
                 "heart, cause dementia, and the only way to lower "
                 "cholesterol is cutting refined carbohydrates -- is "
                 "contradicted by statin trial meta-analyses. Several "
                 "caption claims are true (CoQ10 depletion, muscle "
                 "symptoms, the 46% diabetes figure, which comes from "
                 "METSIM), which is what makes the video persuasive: true "
                 "fragments supporting a false conclusion, like v42 in "
                 "batch 1.",
        "claims": [
            {
                "text": "los medicamentos para el colesterol, los que llaman "
                        "las famosas estatinas ... hacen daño al corazón",
                "start": 0.0, "end": 17.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:16214597"],
                "confidence": "high",
                "notes": "EN: cholesterol drugs, the famous statins, damage "
                         "the heart. CTT meta-analysis of 14 trials (90,056 "
                         "participants): myocardial infarction or coronary "
                         "death down 23% and coronary mortality down 19% per "
                         "mmol/L LDL reduction.",
            },
            {
                "text": "Está demostrado que interfieren con la creación de "
                        "COQ10, que necesita el músculo del corazón",
                "start": 14.9, "end": 22.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35480616"], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: It is proven that they interfere with the "
                         "making of CoQ10, which heart muscle needs. The "
                         "review of medicine-induced nutrient depletion: "
                         "'The coenzyme CoQ10 was depleted by statins.'",
            },
            {
                "text": "La única forma de bajar el colesterol es bajar los "
                        "carbohidratos refinados",
                "start": 22.9, "end": 26.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:16214597", "PMID:33317019"],
                "confidence": "high",
                "notes": "EN: The only way to lower cholesterol is to cut "
                         "refined carbohydrates. Statins lower LDL by about 1 "
                         "mmol/L in the CTT trials, and in the diet "
                         "meta-analysis low-carbohydrate diets raised LDL and "
                         "total cholesterol relative to low-fat diets.",
            },
            {
                "text": "[las estatinas] trae demencia",
                "start": 35.2, "end": 42.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:34871380"],
                "confidence": "medium",
                "notes": "EN: [statins] bring dementia. Meta-analysis of 36 "
                         "observational studies: statin use associated with "
                         "lower dementia risk (OR 0.80) and lower Alzheimer's "
                         "risk (OR 0.68). Observational, hence medium.",
            },
            {
                "text": "Las estatinas pueden causar una infinidad de "
                        "síntomas musculares, dolor, rigidez, fatiga, aumento "
                        "de la sensibilidad, debilidad, calambres, pesadez",
                "start": 42.9, "end": 45.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:36049498"], "contradicting": [],
                "confidence": "medium",
                "notes": "Screen only. EN: Statins can cause a host of "
                         "muscle symptoms. The CTT individual-participant "
                         "meta-analysis of blinded trials confirms a small "
                         "excess (RR 1.03; 7% relative in year one), while "
                         "noting only about 1 in 15 such reports on statin "
                         "are caused by it. 'Infinidad' overstates it.",
            },
            {
                "text": "El tratamiento con estatinas se asoció con un 46% más "
                        "de riesgo de la diabetes tipo 2",
                "start": 47.6, "end": 47.6,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:25754552"], "contradicting": [],
                "confidence": "high",
                "notes": "Screen only. EN: Statin treatment was associated "
                         "with a 46% higher risk of type 2 diabetes. The "
                         "figure is exactly METSIM's (adjusted HR 1.46).",
            },
            {
                "text": "Además inhiben la absorción de la vitamina B12, "
                        "disminuyen la vitamina K y ácido fólico lo que puede "
                        "inducir anemias e interferencias con "
                        "anticoagulantes",
                "start": 47.6, "end": 49.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Screen only. EN: They also inhibit vitamin B12 "
                         "absorption and lower vitamin K and folic acid, "
                         "which can cause anaemia and interfere with "
                         "anticoagulants. The nutrient-depletion review "
                         "(PMID 35480616) names B12 depletion by other drug "
                         "classes and only CoQ10 for statins; the B12 search "
                         "found nothing on statins.",
            },
            {
                "text": "la coenzima q10 ... disminuye el riesgo de muerte en "
                        "pacientes con insuficiencia cardiaca",
                "start": 52.3, "end": 54.6,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:35608922"], "contradicting": [],
                "confidence": "low",
                "notes": "Screen only. EN: CoQ10 lowers the risk of death in "
                         "heart failure patients. Cochrane 2021: 'probably "
                         "reduces' all-cause mortality (RR 0.58), but from a "
                         "single trial of 420 people, and all studies at "
                         "unclear or high risk of bias. Low confidence; a "
                         "reviewer may prefer INSUFFICIENT_EVIDENCE.",
            },
            {
                "text": "la coenzima Q10 ... reduce la presión arterial",
                "start": 56.9, "end": 59.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "MIXED",
                "supporting": ["PMID:36130103"],
                "contradicting": ["PMID:26935713"],
                "confidence": "medium",
                "notes": "Screen only. EN: CoQ10 lowers blood pressure. "
                         "Cochrane (primary hypertension, moderate quality): "
                         "no clinically significant effect. The dose-"
                         "response meta-analysis in cardiometabolic disease: "
                         "systolic BP reduction, moderate quality. Different "
                         "populations, opposite conclusions.",
            },
        ],
    },
    {
        "video_id": "v123",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "@dermdoctor, eleven seconds: 'This guy really went and "
                 "glued garbanzo beans to his legs.' " + _GLUED_BEANS,
        "external_reason": "The debunk is about what one staged clip shows, "
                           "which is NOT_VERIFIABLE, so the video is "
                           "unjudgeable.",
        "claims": [
            {
                "text": "This guy really went and glued garbanzo beans to his "
                        "legs",
                "start": 7.2, "end": 10.8,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "The speaker never states the hoax claim itself, so "
                         "his own correction is recorded, ENDORSES.",
            },
        ],
    },
    {
        "video_id": "v124",
        "topic": "immunology / parasites and autoimmune disease",
        "case_tags": ["clearly_false"],
        "confidence": "medium",
        "notes": "@dr.austin.lake, a functional-medicine practitioner "
                 "selling a programme: parasites skew immunity to TH2 and "
                 "suppress TH1, so 'the number one indicator of parasites "
                 "is an autoimmune condition'. The immunology is half right "
                 "(helminths do skew towards TH2 and damp TH1), but the "
                 "conclusion is backwards: the human evidence shows helminth "
                 "infection inversely associated with autoimmunity, with "
                 "infected MS patients relapsing less. Also calls TH1 cells "
                 "innate, which they are not. Same claim as v126.",
        "claims": [
            {
                "text": "[parasites] stimulate TH2 immune cells, which "
                        "actually create antibodies",
                "start": 12.8, "end": 19.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:11964470", "PMID:30043455"],
                "contradicting": [],
                "confidence": "low",
                "notes": "Helminth infections are 'TH2-skewed' (hygiene-"
                         "hypothesis review; worms and type 2 immunity "
                         "review). Low confidence because 'which create "
                         "antibodies' is loose: TH2 cells help B cells, "
                         "which make the antibodies.",
            },
            {
                "text": "they actually suppress TH1 cells",
                "start": 19.0, "end": 23.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:17230481"], "contradicting": [],
                "confidence": "medium",
                "notes": "Infected MS patients had fewer IL-12 and "
                         "interferon-gamma secreting cells, the TH1 profile, "
                         "and more regulatory cells.",
            },
            {
                "text": "TH1 cells, which are our part of your innate immune "
                        "system",
                "start": 19.0, "end": 25.1,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:22474485"],
                "confidence": "medium",
                "notes": "TH1 cells are CD4 T cells, which are 'activated "
                         "after interaction with antigen-MHC complex' -- "
                         "adaptive, not innate, immunity. Textbook, from a "
                         "review rather than a study.",
            },
            {
                "text": "the number one indicator of parasites is actually an "
                        "autoimmune condition",
                "start": 25.1, "end": 29.3,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:25472634", "PMID:17230481"],
                "confidence": "medium",
                "notes": "'The epidemiology of MS shows an inverse "
                         "correlation with helminth infections', and "
                         "naturally infected MS patients had fewer "
                         "exacerbations and MRI changes over 4.6 years. The "
                         "direction is the reverse of the claim. Some "
                         "parasites can worsen inflammatory disease (PMID "
                         "25403350), which is why medium.",
            },
            {
                "text": "MS ... can ... be linked back to parasite activity",
                "start": 29.3, "end": 35.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:25472634", "PMID:17230481"],
                "confidence": "low",
                "notes": "One of four diseases listed together ('MS, celiac "
                         "disease, fibromyalgia, Hashimoto's can all be "
                         "linked back to parasite activity'), split one per "
                         "row (section 4). For MS the retrieved human "
                         "evidence runs the other way: an inverse "
                         "association with helminth infection, and most MS "
                         "patients in the cohort uninfected. Low confidence: "
                         "'linked' is loose.",
            },
            {
                "text": '… celiac disease … can all be linked back to parasite activity',
                "start": 29.3, "end": 35.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Split from the same list as the MS row. Nothing retrieved tests celiac disease for a link to parasites.",
            },
            {
                "text": '… fibromyalgia … can all be linked back to parasite activity',
                "start": 29.3, "end": 35.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Split from the same list as the MS row. Nothing retrieved tests fibromyalgia for a link to parasites.",
            },
            {
                "text": "… Hashimoto's … can all be linked back to parasite activity",
                "start": 29.3, "end": 35.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Split from the same list as the MS row. Nothing retrieved tests Hashimoto's for a link to parasites.",
            },
            {
                "text": "if you don't fix the problem and get out the root "
                        "cause, you're likely to develop other autoimmune "
                        "conditions down the road",
                "start": 35.0, "end": 41.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing tests clearing parasites to prevent "
                         "further autoimmune disease.",
            },
        ],
    },
    {
        "video_id": "v125",
        "topic": "food safety / lab-grown meat",
        "case_tags": ["uncertain_science"],
        "confidence": "medium",
        "notes": "@kennythetrainer, replying to a commenter that lab-grown "
                 "meat uses 'pre-cancer cells'. He plays an AP explainer "
                 "('companies choose the cells most likely to reproduce "
                 "quickly'), then a search result ('cancer cells typically "
                 "grow and divide more rapidly than normal cells'), and "
                 "concludes 'it sounds like they're taking the cancerous "
                 "or pre-cancerous cells'. A syllogism from a true premise "
                 "to an untested insinuation. The true premise is the only "
                 "judged claim, so section 9 gives NO_MISINFO -- the same "
                 "'true fragment' effect as v122 and batch-1 v68, here "
                 "landing on the lenient side. The insinuation itself is "
                 "untested: a cell-line review names tumorigenicity as a "
                 "hazard cultivated-meat cell banks must control (PMID "
                 "42335783), which is neither support nor contradiction.",
        "external_reason": "The 'cancer cells' insinuation is untested "
                           "rather than disproven, and the one judged claim "
                           "(cancer cells divide fast) is true, so the "
                           "rules give NO_MISINFO.",
        "claims": [
            {
                "text": "Cancer cells. Typically grow and divide more rapidly "
                        "than normal cells",
                "start": 70.3, "end": 80.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:21376230"], "contradicting": [],
                "confidence": "medium",
                "notes": "Read from a search result he shows. Hallmarks of "
                         "cancer: sustaining proliferative signalling and "
                         "evading growth suppressors.",
            },
            {
                "text": "it sounds like they're taking the cancerous cells or "
                        "pre-cancerous cells from these animals to reproduce, "
                        "to make the meat that we bout to eat",
                "start": 93.7, "end": 107.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "Hedged ('sounds like', and 'do your own research "
                         "to find out if it's true or not') but the video's "
                         "whole point, so ENDORSES with low confidence; "
                         "UNCLEAR would also be defensible. Nothing "
                         "retrieved says cultivated meat uses cancer cells, "
                         "and nothing retrieved rules it out.",
            },
        ],
    },
    {
        "video_id": "v126",
        "topic": "parasites / autoimmune disease and symptom lists",
        "case_tags": ["clearly_false"],
        "confidence": "medium",
        "notes": "@shaysnaturalremedies, selling parasite cleanses. Opens "
                 "with the v124 claim in its absolute form ('If you have an "
                 "autoimmune condition, you have parasites'), then a long "
                 "symptom list, then full-moon egg laying. The opening "
                 "claim is contradicted by the inverse helminth-"
                 "autoimmunity evidence. The symptom list is split by the "
                 "evidence that applies, not item by item: the itchy-bum "
                 "sign is genuine (pinworm), the rest is untested.",
        "claims": [
            {
                "text": "If you have an autoimmune condition, you have "
                        "parasites",
                "start": 0.0, "end": 10.1,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [],
                "contradicting": ["PMID:25472634", "PMID:17230481"],
                "confidence": "medium",
                "notes": "Same evidence as v124 c4: inverse association "
                         "between helminth infection and MS; most MS "
                         "patients in the cohort were uninfected.",
            },
            {
                "text": "if you have parasites, you also have toxicity in your "
                        "body. See, parasites love toxins",
                "start": 4.9, "end": 15.8,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "'Toxicity' and 'toxins' are not defined; nothing "
                         "measurable to test.",
            },
            {
                "text": "they also thrive in environments that are highly "
                        "acidic and where the lymphatic system is completely "
                        "stagnant",
                "start": 10.1, "end": 21.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "No study of body acidity or lymph flow and "
                         "parasite survival was found.",
            },
            {
                "text": "I couldn't possibly have parasites. Oh, you do. In "
                        "fact, most of us do",
                "start": 21.0, "end": 33.8,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "low",
                "notes": "WHO's fact sheet (retrieved) puts soil-transmitted "
                         "helminths at 1.5 billion people, 24% of the world, "
                         "and the pinworm review at about 30% of children. "
                         "Both are below 'most', but neither counts all "
                         "parasites, so neither gives a conflicting figure "
                         "for the claim as stated. Not cited for that "
                         "reason.",
            },
            {
                "text": "So let's hit some of the signs of parasitic "
                        "infestations. ... maybe you have an itchy bum",
                "start": 27.0, "end": 55.4,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:38288810", "PMID:31507346"],
                "contradicting": [],
                "confidence": "high",
                "notes": "Nocturnal pruritus ani is the most common symptom "
                         "of pinworm infection, and perianal irritation is a "
                         "described finding across several parasites.",
            },
            {
                "text": 'the signs of parasitic infestations. If you have … horrible brain fog',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'One of eight symptoms listed together at 27.0-48.2s, split one per row (section 4). None is tested as a sign of parasitic infection in anything retrieved; all are non-specific.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … fatigue',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … anxiety',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … depression',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … crazy mood swings',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … a hormonal imbalance',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … insomnia',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": 'the signs of parasitic infestations. If you have … night sweats',
                "start": 27.0, "end": 48.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": 'Same list and the same search as the brain-fog row: untested as a sign of parasites.',
            },
            {
                "text": "or do you find yourself grinding your teeth at "
                        "night?",
                "start": 70.8, "end": 76.9,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": ["PMID:19040814"],
                "confidence": "medium",
                "notes": "Asked as a question but listed as a sign. A "
                         "case-control study in children found no "
                         "association between bruxism and intestinal "
                         "parasites (30% vs 41%, P=.40). One small null "
                         "study is too weak to call the claim false.",
            },
            {
                "text": "parasites tend to be most active at night and during "
                        "a full moon, because every month on a full moon, "
                        "they migrate to your gut to lay more eggs",
                "start": 76.9, "end": 86.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Night-time activity fits pinworm (nocturnal "
                         "itching), but nothing retrieved tests a lunar "
                         "cycle, and pinworms lay eggs on perianal skin, not "
                         "in the gut -- not stated in a retrieved abstract, "
                         "so not used.",
            },
            {
                "text": "when you kill them, they will lay eggs ... And a few "
                        "weeks later, those eggs will hatch. And now you feel "
                        "even worse than when you started",
                "start": 90.1, "end": 100.2,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "Nothing found on parasites laying eggs in response "
                         "to treatment or on rebound symptoms.",
            },
        ],
    },
    {
        "video_id": "v127",
        "topic": "men's health / underwear under swimwear",
        "case_tags": ["other_language", "accurate"],
        "confidence": "medium",
        "notes": "@farmaceuticofernandez, Spanish, a pharmacist on whether "
                 "to wear underwear under swim trunks. No fact-checker "
                 "verdict was found for this video: candidates_full.csv has "
                 "no row with its platform id, so external_label is empty. "
                 "Light-hearted but accurate on the one checkable point "
                 "(heat and sperm production).",
        "claims": [
            {
                "text": "el bañador está pensado para que se seque rápido y si "
                        "te pones debajo un calzón de algodón eso ya no pasa "
                        "Y se favorece que se produzca una infección y "
                        "bastante irritación",
                "start": 9.5, "end": 18.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "EN: trunks are made to dry quickly; cotton "
                         "underwear underneath stops that and favours "
                         "infection and irritation. Plausible, but no study "
                         "of wet cotton under swimwear was found.",
            },
            {
                "text": "el calzoncillo puede subir la temperatura y reducir "
                        "la producción de soldaditos",
                "start": 18.5, "end": 24.5,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:42293842", "PMID:2136041"],
                "contradicting": [],
                "confidence": "medium",
                "notes": "EN: underwear can raise the temperature and reduce "
                         "the production of 'little soldiers' (sperm). "
                         "Narrative review: tighter underwear raises scrotal "
                         "temperature, with modest and inconsistent "
                         "differences in sperm parameters; the pilot "
                         "crossover found semen parameters fell in tight "
                         "underwear and recovered in loose. 'Puede' (can) "
                         "matches the strength of the evidence.",
            },
        ],
    },
    {
        "video_id": "v128",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "@derm.tok, thirteen seconds: 'these are not ticks. They're "
                 "beans glued to the skin.' " + _GLUED_BEANS,
        "external_reason": "The debunk is about what one staged clip shows, "
                           "which is NOT_VERIFIABLE, so the video is "
                           "unjudgeable.",
        "claims": [
            {
                "text": "these, these are not ticks. They're beans glued to "
                        "the skin. You can even see the glue there",
                "start": 0.3, "end": 12.5,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "The opening 'it's tick season, be careful' is "
                         "general advice, not an assertion about these "
                         "lesions, so it is not recorded.",
            },
        ],
    },
    {
        "video_id": "v129",
        "topic": "COVID-19 / ivermectin regulation",
        "case_tags": ["missing_evidence"],
        "confidence": "medium",
        "notes": "@meghanelinor, over an Epoch Times headline 'Doctors Can "
                 "Prescribe Ivermectin for COVID-19: FDA Lawyer'. The one "
                 "checkable claim is regulatory, and the reference that "
                 "would settle it is gone: FDA's consumer page 'Why you "
                 "should not use ivermectin to treat or prevent COVID-19' "
                 "now returns HTTP 404. So it is INSUFFICIENT_EVIDENCE and "
                 "the video CANNOT_RECOGNIZE. The implied payload (that "
                 "ivermectin works for COVID, 'conspiracies ... becoming "
                 "reality') is never stated as a claim, so it is not "
                 "invented here, though trials contradict it (PMID "
                 "38908535: no reduction in hospitalisation or "
                 "mortality). A case where the falsehood is in the "
                 "implicature.",
        "external_reason": "The only stated claim is a regulatory one that "
                           "no retrievable reference settles (FDA's "
                           "ivermectin page now returns 404); the implied "
                           "efficacy claim is never said.",
        "claims": [
            {
                "text": "The FDA is now saying that it is okay to prescribe "
                        "ivermectin",
                "start": 0.0, "end": 5.2,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": [], "contradicting": [],
                "confidence": "medium",
                "notes": "On screen with 'for COVID-19'. The headline reports "
                         "an FDA lawyer's court statement that doctors may "
                         "prescribe off-label; that is not the FDA saying it "
                         "is okay for COVID-19. Section 6 reference search "
                         "(2026-11-23): fda.gov's ivermectin consumer update "
                         "returns 404, so the agency's current position "
                         "could not be retrieved.",
            },
        ],
    },
    {
        "video_id": "v130",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "@drsinghdermatolog, fifteen seconds: not bugs, not "
                 "insects, glued-on beans; 'gently pick them off'. "
                 + _GLUED_BEANS,
        "external_reason": "The debunk is about what one staged clip shows, "
                           "which is NOT_VERIFIABLE, so the video is "
                           "unjudgeable.",
        "claims": [
            {
                "text": "It's not bugs and it's not insects ... all these are "
                        "some beans that have been glued on by someone",
                "start": 5.4, "end": 12.1,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "'Gently pick them off' is advice, not an "
                         "assertion.",
            },
        ],
    },
    {
        "video_id": "v131",
        "topic": "nutrition / sugar",
        "case_tags": ["clearly_false"],
        "confidence": "high",
        "notes": "@drone721xxx, a 'Sugar in X is called Y' list over stock "
                 "footage, same text spoken and on screen. Nine claims, "
                 "split per section 4. One is SUPPORTED (caries), one is a "
                 "diagnostic definition (diabetes), the ADHD claim is "
                 "contradicted by the meta-analysis of blinded sugar "
                 "challenges, and the rest rest on observational "
                 "associations or rat data -- INSUFFICIENT, not "
                 "CONTRADICTED. The 'eight times more powerful than "
                 "cocaine' line traces to a rat study.",
        "claims": [
            {
                "text": "[Sugar in a baby's brain] is called ADHD",
                "start": 0.0, "end": 2.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "CONTRADICTED",
                "supporting": [], "contradicting": ["PMID:7474248"],
                "confidence": "high",
                "notes": "Speech starts mid-sentence; the caption gives "
                         "'sugar in a baby's brain is called'. Meta-analysis "
                         "of blinded, placebo-controlled sugar challenges: "
                         "'sugar does not affect the behavior or cognitive "
                         "performance of children'.",
            },
            {
                "text": "Sugar in an adult's brain is called dementia and "
                        "Alzheimer's",
                "start": 2.0, "end": 7.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:42814269"], "contradicting": [],
                "confidence": "medium",
                "notes": "Umbrella review: sugar intake associated with "
                         "cognitive disorders. Observational association, "
                         "not the identity or causation the claim states.",
            },
            {
                "text": "Sugar in your eyes is called glaucoma",
                "start": 7.0, "end": 10.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:37013760"], "contradicting": [],
                "confidence": "medium",
                "notes": "Diabetes and fasting glucose are risk factors for "
                         "glaucoma in the meta-analysis; dietary sugar is not "
                         "tested.",
            },
            {
                "text": "Sugar in your teeth is called cavities",
                "start": 10.0, "end": 13.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:24323509"], "contradicting": [],
                "confidence": "high",
                "notes": "WHO-commissioned systematic review: 42 of 50 "
                         "child studies and 5 of 5 adult studies found a "
                         "positive sugars-caries association.",
            },
            {
                "text": "Sugar on your skin is called aging",
                "start": 13.0, "end": 16.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:20620757"], "contradicting": [],
                "confidence": "medium",
                "notes": "Glycation of dermal collagen is a described "
                         "mechanism (narrative review); no human study ties "
                         "sugar intake to measured skin ageing.",
            },
            {
                "text": "Sugar in your sleep is called insomnia",
                "start": 16.0, "end": 19.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:42814269"], "contradicting": [],
                "confidence": "medium",
                "notes": "Umbrella review lists poor sleep among outcomes "
                         "associated with excessive sugar; associational.",
            },
            {
                "text": "Sugar in your blood is called diabetes",
                "start": 19.0, "end": 22.0,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "SUPPORTED",
                "supporting": ["PMID:9803200"], "contradicting": [],
                "confidence": "medium",
                "notes": "Read as raised blood glucose: diabetes is diagnosed "
                         "by fasting plasma glucose of 126 mg/dL or more. "
                         "Medium because the slogan omits 'high'.",
            },
            {
                "text": "Excess sugar in your system is called cancer",
                "start": 22.0, "end": 26.0,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:42814269"], "contradicting": [],
                "confidence": "medium",
                "notes": "Umbrella review: 'a positive association' between "
                         "excessive sugar and cancer, weaker than for "
                         "diabetes or caries. Association only.",
            },
            {
                "text": "Addiction to sugar is eight times, eight times, more "
                        "powerful than cocaine",
                "start": 26.0, "end": 41.54,
                "kind": "research_question",
                "stance": "ENDORSES", "verdict": "INSUFFICIENT_EVIDENCE",
                "supporting": ["PMID:17668074"],
                "contradicting": ["PMID:27372453"],
                "confidence": "medium",
                "notes": "The source of the meme is a rat study in which 94% "
                         "of rats chose saccharin or sucrose over IV cocaine "
                         "-- animal only, and no 'eight times' figure. The "
                         "state-of-the-science review finds little evidence "
                         "of sugar addiction in humans. Animal support and "
                         "absence in humans: INSUFFICIENT, with evidence "
                         "on both sides.",
            },
        ],
    },
    {
        "video_id": "v132",
        "topic": "dermatology / hoax video (glued beans)",
        "case_tags": ["debunking", "other_language"],
        "confidence": "high",
        "notes": "@doctorchrisantiage, Spanish, no captions: people glue "
                 "beans or coffee grains to themselves for content; it is "
                 "not an animal. " + _GLUED_BEANS,
        "external_reason": "The debunk is about what one staged clip shows, "
                           "which is NOT_VERIFIABLE, so the video is "
                           "unjudgeable.",
        "claims": [
            {
                "text": "esto no es nada más de gente que se pegan con pegante "
                        "son como ... granos ... de frijoles o de café ... no "
                        "es ni ningún tipo de animal",
                "start": 6.2, "end": 20.1,
                "kind": "fact_of_record",
                "stance": "ENDORSES", "verdict": "NOT_VERIFIABLE",
                "supporting": [], "contradicting": [],
                "confidence": "high",
                "notes": "EN: this is just people gluing things on, like "
                         "beans or coffee grains; it is not any kind of "
                         "animal. Whisper's last line ('es calor frío') is "
                         "unintelligible and not used.",
            },
        ],
    },
]
