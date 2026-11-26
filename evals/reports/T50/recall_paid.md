# T50 paid run (T53): search recall on the tune split, rules-only b52e952 baseline → helpers on (current code)

Before: code b52e9521935b (rules only); after: `tune_paid.json`, current langgraph-build code with plan_search, translate_claim and find_study live. Live PubMed, up to 3 rounds per claim. On topic = the T49 deterministic check (`unproven_guard.on_topic`, from the after code, for both runs).

## D8 search quality bar (lead, 2026-11-26)

Strict: a golden-cited PMID is among the records the reranker kept (claims with a golden PMID). Lenient: strict, or at least one kept record is on topic. Target: lenient >= 80%. Two on-topic yardsticks: *intervention* = the T49 check only (for a claim with no recognised intervention it needs every leftover word, e.g. 'also loves acid', so it under-counts); *claim* = the T49 check when the claim has a recognised intervention, else one of the claim's concepts in the record (the rule that triggers find-the-study).

| set | claims | lenient (intervention) before → after | lenient (claim) before → after | strict before → after |
| --- | --- | --- | --- | --- |
| all tune claims | 187 | 51/187 (27.3%) → 119/187 (63.6%) | 74/187 (39.6%) → 156/187 (83.4%) | 4/118 (3.4%) → 18/118 (15.3%) |
| English | 128 | 50/128 (39.1%) → 92/128 (71.9%) | 66/128 (51.6%) → 113/128 (88.3%) | 4/84 (4.8%) → 14/84 (16.7%) |
| non-English | 59 | 1/59 (1.7%) → 27/59 (45.8%) | 8/59 (13.6%) → 43/59 (72.9%) | 0/34 (0.0%) → 4/34 (11.8%) |

Target lenient >= 80%: **met** with the helpers on, on the claim yardstick only (intervention 119/187 (63.6%), claim 156/187 (83.4%)); not met on the intervention yardstick.

## Retrieval detail

| set | claims | on topic (any round) before → after | round 1 only | kept by reranker | empty searches | repeated rounds | golden PMID retrieved |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all tune claims | 187 | 57/187 (30.5%) → 122/187 (65.2%) | 55/187 (29.4%) → 116/187 (62.0%) | 51/187 (27.3%) → 117/187 (62.6%) | 84 → 1 | 253 → 0 | 7/118 (5.9%) → 23/118 (19.5%) |
| English | 128 | 56/128 (43.8%) → 96/128 (75.0%) | 54/128 (42.2%) → 90/128 (70.3%) | 50/128 (39.1%) → 92/128 (71.9%) | 42 → 0 | 158 → 0 | 7/84 (8.3%) → 16/84 (19.0%) |
| non-English | 59 | 1/59 (1.7%) → 26/59 (44.1%) | 1/59 (1.7%) → 26/59 (44.1%) | 1/59 (1.7%) → 25/59 (42.4%) | 42 → 1 | 95 → 0 | 0/34 (0.0%) → 7/34 (20.6%) |

Gained on topic: 68; lost: 3.

## Lost

- v177:c1: before ['schizophrenia hearing voices seeing things'] → after ['(Schizophrenia[MeSH Terms] OR schizophrenia[tiab])', '"Mental Disorders"[MeSH Terms]']
- v177:c2: before ['multiple personality yes'] → after ['("Dissociative Identity Disorder"[MeSH Terms] OR "multiple personality disorder"[tiab] OR "multiple personality"[tiab] OR "dissociative identity disorder"[tiab])', 'multiple personality']
- v95:c2: before ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])'] → after ['("Brain Neoplasms"[MeSH Terms] OR "brain tumor"[tiab] OR meningioma[tiab])', 'Neoplasms[MeSH Terms]']

## Non-English claims

- v100:c1 (es): False → True; after queries ['("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND ("Diabetes Mellitus, Type 1"[MeSH Terms] OR "type 1 diabetes"[tiab])', '("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND "Diabetes Mellitus"[MeSH Terms]']
- v100:c2 (es): False → True; after queries ['("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND ("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND "Diabetes Mellitus"[MeSH Terms]']
- v100:c3 (es): False → False; after queries ['"Stem Cell Transplantation"[MeSH Terms] OR "stem cell transplantation"[tiab] OR "islet transplantation"[tiab] OR "stem cell-derived islets"[tiab] AND "pancreatic islet cells"[tiab] OR "beta cell replacement"[tiab] OR "insulin-producing cells"[tiab] AND "Diabetes Mellitus, Type 1"[MeSH Terms] OR "type 1 diabetes"[tiab] OR "insulin dependent diabetes"[tiab] OR "pancreatic function restoration"[', '("Stem Cell Transplantation"[MeSH Terms] OR "stem cell transplantation"[tiab] OR "islet transplantation"[tiab] OR "stem cell-derived islets"[tiab]) AND ("pancreatic islet cells"[tiab] OR "beta cell replacement"[tiab] OR "insulin-producing cells"[tiab])']
- v109:c1 (es): False → False; after queries ['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '"Diabetes Mellitus"[MeSH Terms]']
- v109:c10 (es): False → False; after queries ['("dose escalation"[tiab] OR "dose titration"[tiab] OR "gradual dose increase"[tiab]) AND ("Pancreatic Diseases"[MeSH Terms] OR "pancreas failure"[tiab] OR "pancreatic dysfunction"[tiab] OR "pancreatic insufficiency"[tiab])', '("dose escalation"[tiab] OR "dose titration"[tiab] OR "gradual dose increase"[tiab])']
- v109:c11 (es): False → False; after queries ['("weight loss"[tiab] OR "stopping treatment"[tiab] OR discontinuation[tiab]) AND ("Weight Regain"[MeSH Terms] OR "weight regain"[tiab] OR "weight gain after discontinuation"[tiab] OR "weight rebound"[tiab])', '("weight loss"[tiab] OR "stopping treatment"[tiab] OR discontinuation[tiab])']
- v109:c2 (es): False → False; after queries ['(Stroke[MeSH Terms] OR stroke[tiab])', '"Cerebrovascular Disorders"[MeSH Terms]']
- v109:c3 (es): False → False; after queries ['("Cardiovascular Diseases"[MeSH Terms] OR "cardiovascular disease"[tiab] OR "heart disease"[tiab])']
- v109:c4 (es): False → False; after queries ['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '"Diabetes Mellitus"[MeSH Terms]']
- v109:c5 (es): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab]) AND ("Thyroid Diseases"[MeSH Terms] OR thyroid[tiab])']
- v109:c6 (es): False → False; after queries ['(Pancreatitis[MeSH Terms] OR pancreatitis[tiab])']
- v109:c7 (es): False → False; after queries ['(Seizures[MeSH Terms] OR seizures[tiab])']
- v109:c8 (es): False → False; after queries ['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '"Diabetes Mellitus"[MeSH Terms]']
- v109:c9 (es): False → False; after queries ['(Stroke[MeSH Terms] OR stroke[tiab])', '"Cerebrovascular Disorders"[MeSH Terms]']
- v110:c1 (es): False → False; after queries ['("eye color change"[tiab] OR "iris color change"[tiab] OR "iris pigmentation treatment"[tiab]) AND ("Eye Color"[MeSH Terms] OR "iris color"[tiab] OR "eye color"[tiab] OR "iris pigmentation"[tiab])', '("eye color change"[tiab] OR "iris color change"[tiab] OR "iris pigmentation treatment"[tiab])']
- v111:c1 (es): False → True; after queries ['(Fabaceae[MeSH Terms] OR legumes[tiab])']
- v111:c2 (es): False → False; after queries ['(Fabaceae[MeSH Terms] OR legumes[tiab])']
- v111:c3 (es): False → False; after queries ['(Flatulence[MeSH Terms] OR gas[tiab] OR bloating[tiab]) AND ("Gastrointestinal Transit"[MeSH Terms] OR "slow digestion"[tiab] OR "delayed gastric emptying"[tiab])', 'bloating slow digestion']
- v111:c4 (es): False → False; after queries ['(Fabaceae[MeSH Terms] OR legumes[tiab])']
- v111:c5 (es): False → True; after queries ['(Fabaceae[MeSH Terms] OR legumes[tiab])']
- v114:c2 (es): False → True; after queries ['("Sodium Chloride, Dietary"[MeSH Terms] OR "salt intake"[tiab] OR "sodium intake"[tiab])']
- v114:c3 (es): False → True; after queries ['("Dietary Sugars"[MeSH Terms] OR sugar[tiab]) AND ("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND (Hypertension[MeSH Terms] OR hypertension[tiab] OR "blood pressure"[tiab])', '("Dietary Sugars"[MeSH Terms] OR sugar[tiab]) AND ("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND "Cardiovascular Diseases"[MeSH Terms]']
- v114:c4 (es): False → True; after queries ['("Sodium Chloride, Dietary"[MeSH Terms] OR "salt intake"[tiab] OR "sodium intake"[tiab])']
- v114:c5 (es): False → True; after queries ['("Dietary Sugars"[MeSH Terms] OR sugar[tiab])']
- v119:c2 (es): False → False; after queries ['("alkaline diet"[tiab] OR "alkalizing diet"[tiab] OR "alkaline water"[tiab]) AND ("Acid-Base Imbalance"[MeSH Terms] OR "body ph"[tiab] OR "acid-base balance"[tiab] OR alkalosis[tiab])', '("alkaline diet"[tiab] OR "alkalizing diet"[tiab] OR "alkaline water"[tiab])']
- v119:c3 (es): False → True; after queries ['("Sodium Bicarbonate"[MeSH Terms] OR "sodium bicarbonate"[tiab])']
- v119:c4 (es): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])']
- v120:c1 (es): False → False; after queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']
- v120:c2 (es): False → True; after queries ['(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab]) AND ("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])', '(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab])']
- v120:c3 (es): False → True; after queries ['(Seawater[MeSH Terms] OR seawater[tiab] OR "sea water"[tiab])']
- v120:c4 (es): False → False; after queries ['("colon cleansing"[tiab] OR "colonic irrigation"[tiab] OR "bowel cleansing"[tiab]) AND (Laxatives[MeSH Terms] OR laxative[tiab] OR purgative[tiab] OR enema[tiab]) AND (Constipation[MeSH Terms] OR "bowel evacuation"[tiab] OR "intestinal residue"[tiab]) AND ("fecal residue"[tiab] OR "colon cleansing effect"[tiab])', '("colon cleansing"[tiab] OR "colonic irrigation"[tiab] OR "bowel cleansing"[tiab]) AND (Laxatives[MeSH Terms] OR laxative[tiab] OR purgative[tiab] OR enema[tiab])']
- v121:c1 (es): False → True; after queries ['(contraception[tiab] OR contraceptive[tiab] OR "birth control"[tiab]) AND (Contraception[MeSH Terms] OR "pregnancy prevention"[tiab] OR "unintended pregnancy"[tiab])', '(contraception[tiab] OR contraceptive[tiab] OR "birth control"[tiab])']
- v121:c2 (es): False → False; after queries ['("natural products"[tiab] OR "herbal remedies"[tiab] OR "natural substances"[tiab]) AND (Vaginitis[MeSH Terms] OR "vaginal irritation"[tiab] OR "vaginal mucosal irritation"[tiab] OR "mucosal irritation"[tiab])', '("natural products"[tiab] OR "herbal remedies"[tiab] OR "natural substances"[tiab])']
- v121:c3 (es): False → False; after queries ['(Pruritus[MeSH Terms] OR "genital itching"[tiab] OR "vulvovaginal itching"[tiab] OR "genital pruritus"[tiab])', 'itches genitals']
- v122:c1 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND (Cholesterol[MeSH Terms] OR cholesterol[tiab])', '("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND Lipids[MeSH Terms]']
- v122:c2 (es): False → True; after queries ['(Ubiquinone[MeSH Terms] OR "coenzyme q10"[tiab])']
- v122:c3 (es): False → True; after queries ['("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND (Cholesterol[MeSH Terms] OR cholesterol[tiab])', '("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND Lipids[MeSH Terms]']
- v122:c4 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND ("Alzheimer Disease"[MeSH Terms] OR alzheimer[tiab] OR dementia[tiab])', '("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND Dementia[MeSH Terms]']
- v122:c5 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab])']
- v122:c6 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND ("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND "Diabetes Mellitus"[MeSH Terms]']
- v122:c7 (es): False → True; after queries ['("Vitamin B 12"[MeSH Terms] OR "vitamin b12"[tiab]) AND ("Vitamin K"[MeSH Terms] OR "vitamin k"[tiab] OR phytonadione[tiab] OR phylloquinone[tiab])', '(("Vitamin B 12"[MeSH Terms] OR "vitamin b12"[tiab]) OR ("Vitamin K"[MeSH Terms] OR "vitamin k"[tiab] OR phytonadione[tiab] OR phylloquinone[tiab]))']
- v122:c8 (es): False → True; after queries ['(Ubiquinone[MeSH Terms] OR "coenzyme q10"[tiab]) AND ("Heart Failure"[MeSH Terms] OR "heart failure"[tiab])', '(Ubiquinone[MeSH Terms] OR "coenzyme q10"[tiab]) AND "Cardiovascular Diseases"[MeSH Terms]']
- v141:c1 (fr): False → False; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND (Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])', '(Soaps[MeSH Terms] OR soap[tiab])']
- v141:c2 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']
- v141:c3 (fr): False → True; after queries ['(Imiquimod[MeSH Terms] OR imiquimod[tiab])']
- v141:c4 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND (Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])', '(Soaps[MeSH Terms] OR soap[tiab])']
- v143:c1 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']
- v143:c2 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']
- v167:c1 (hi): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])']
- v167:c2 (hi): False → False; after queries ['Carbohydrates[MeSH Terms] OR "carbohydrate restriction"[tiab] OR "low carbohydrate diet"[tiab] OR "sugar restriction"[tiab] AND Sugars[MeSH Terms] OR "sugar deprivation"[tiab] OR "dietary sugar"[tiab] OR "glucose restriction"[tiab] AND "ketogenic diet"[tiab] OR "starvation therapy"[tiab] OR fasting[tiab] AND Neoplasms[MeSH Terms] OR cancer[tiab] OR "tumor growth"[tiab] OR "cancer cell proli', '(Carbohydrates[MeSH Terms] OR "carbohydrate restriction"[tiab] OR "low carbohydrate diet"[tiab] OR "sugar restriction"[tiab]) AND (Sugars[MeSH Terms] OR "sugar deprivation"[tiab] OR "dietary sugar"[tiab] OR "glucose restriction"[tiab]) AND ("ketogenic diet"[tiab] OR "starvation therapy"[tiab] OR fasting[tiab])']
- v167:c3 (hi): False → False; after queries ['("neem leaves"[tiab] OR "neem leaf paste"[tiab] OR "azadirachta indica"[tiab]) AND ("turmeric paste"[tiab] OR "raw turmeric"[tiab] OR "curcuma longa"[tiab]) AND ("apple cider vinegar"[tiab] OR vinegar[tiab] OR lemon[tiab])']
- v167:c4 (hi): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab]) AND ("Fatty Liver"[MeSH Terms] OR "fatty liver"[tiab])', '(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab]) AND "Liver Diseases"[MeSH Terms]']
- v88:c1 (es): False → False; after queries ['("x-bearing sperm"[tiab] OR "x chromosome sperm"[tiab] OR "sperm sex selection"[tiab]) AND ("sperm resistance"[tiab] OR "sperm survival"[tiab] OR "sperm viability"[tiab]) AND (Spermatozoa[MeSH Terms] OR "human sperm"[tiab] OR spermatozoa[tiab])', '("x-bearing sperm"[tiab] OR "x chromosome sperm"[tiab] OR "sperm sex selection"[tiab]) AND ("sperm resistance"[tiab] OR "sperm survival"[tiab] OR "sperm viability"[tiab])']
- v88:c2 (es): False → False; after queries ['(Ovulation[MeSH Terms] OR ovulation[tiab])']
- v88:c3 (es): False → False; after queries ['(Ovulation[MeSH Terms] OR ovulation[tiab])']
- v94:c1 (es): True → True; after queries ['("COVID-19 Vaccines"[MeSH Terms] OR "covid-19 vaccine"[tiab] OR vaccinated[tiab] OR "sars-cov-2 vaccine"[tiab]) AND ("COVID-19"[MeSH Terms] OR "coronavirus disease 2019"[tiab] OR "covid-19 deaths"[tiab] OR "vaccine breakthrough mortality"[tiab])', '("COVID-19 Vaccines"[MeSH Terms] OR "covid-19 vaccine"[tiab] OR vaccinated[tiab] OR "sars-cov-2 vaccine"[tiab])']
- v94:c2 (es): False → False; after queries ['("COVID-19"[MeSH Terms] OR "covid-19"[tiab] OR "sars-cov-2"[tiab])', '"Coronavirus Infections"[MeSH Terms]']
- v96:c1 (es): False → False; after queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']
- v96:c2 (es): False → False; after queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']
