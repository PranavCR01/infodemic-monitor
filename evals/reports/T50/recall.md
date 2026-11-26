# T50: search recall on the tune split (rules only, no model)

Before: code b52e9521935b; after: code 95025fb99ab2. Live PubMed, up to 3 rounds per claim. On topic = the T49 deterministic check (`unproven_guard.on_topic`, from the after code, for both runs).

## D8 search quality bar (lead, 2026-11-26)

Strict: a golden-cited PMID is among the records the reranker kept (claims with a golden PMID). Lenient: strict, or at least one kept record is on topic. Target: lenient >= 80%. Two on-topic yardsticks: *intervention* = the T49 check only (for a claim with no recognised intervention it needs every leftover word, e.g. 'also loves acid', so it under-counts); *claim* = the T49 check when the claim has a recognised intervention, else one of the claim's concepts in the record (the rule that triggers find-the-study).

| set | claims | lenient (intervention) before → after | lenient (claim) before → after | strict before → after |
| --- | --- | --- | --- | --- |
| all tune claims | 187 | 52/187 (27.8%) → 113/187 (60.4%) | 75/187 (40.1%) → 149/187 (79.7%) | 4/118 (3.4%) → 16/118 (13.6%) |
| English | 128 | 51/128 (39.8%) → 87/128 (68.0%) | 67/128 (52.3%) → 107/128 (83.6%) | 4/84 (4.8%) → 12/84 (14.3%) |
| non-English | 59 | 1/59 (1.7%) → 26/59 (44.1%) | 8/59 (13.6%) → 42/59 (71.2%) | 0/34 (0.0%) → 4/34 (11.8%) |

Target lenient >= 80%: **not met** rules-only (intervention 113/187 (60.4%), claim 149/187 (79.7%)); the model helpers (assistant, translation, find-the-study) are not in these numbers.

## Retrieval detail

| set | claims | on topic (any round) before → after | round 1 only | kept by reranker | empty searches | repeated rounds | golden PMID retrieved |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all tune claims | 187 | 57/187 (30.5%) → 122/187 (65.2%) | 55/187 (29.4%) → 118/187 (63.1%) | 52/187 (27.8%) → 111/187 (59.4%) | 84 → 9 | 253 → 0 | 7/118 (5.9%) → 19/118 (16.1%) |
| English | 128 | 56/128 (43.8%) → 96/128 (75.0%) | 54/128 (42.2%) → 92/128 (71.9%) | 51/128 (39.8%) → 87/128 (68.0%) | 42 → 0 | 158 → 0 | 7/84 (8.3%) → 14/84 (16.7%) |
| non-English | 59 | 1/59 (1.7%) → 26/59 (44.1%) | 1/59 (1.7%) → 26/59 (44.1%) | 1/59 (1.7%) → 24/59 (40.7%) | 42 → 9 | 95 → 0 | 0/34 (0.0%) → 5/34 (14.7%) |

Gained on topic: 68; lost: 3.

## Lost

- v177:c1: before ['schizophrenia hearing voices seeing things'] → after ['(Schizophrenia[MeSH Terms] OR schizophrenia[tiab])', '"Mental Disorders"[MeSH Terms]']
- v177:c2: before ['multiple personality yes'] → after ['multiple personality', 'personality']
- v95:c2: before ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])'] → after ['("Brain Neoplasms"[MeSH Terms] OR "brain tumor"[tiab] OR meningioma[tiab])', 'Neoplasms[MeSH Terms]']

## Non-English claims

- v100:c1 (es): False → True; after queries ['("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND ("Diabetes Mellitus, Type 1"[MeSH Terms] OR "type 1 diabetes"[tiab])', '("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND "Diabetes Mellitus"[MeSH Terms]']
- v100:c2 (es): False → True; after queries ['("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND ("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '("Cellular Reprogramming"[MeSH Terms] OR "cell reprogramming"[tiab] OR "stem cell"[tiab]) AND "Diabetes Mellitus"[MeSH Terms]']
- v100:c3 (es): False → False; after queries ['cientificos pancreas funcionar', 'cientificos funcionar']
- v109:c1 (es): False → False; after queries ['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '"Diabetes Mellitus"[MeSH Terms]']
- v109:c10 (es): False → False; after queries ['aumentando páncreas funcionar', 'aumentando funcionar']
- v109:c11 (es): False → False; after queries ['obviamente regresar estabas', 'obviamente regresar']
- v109:c2 (es): False → False; after queries ['(Stroke[MeSH Terms] OR stroke[tiab])', '"Cerebrovascular Disorders"[MeSH Terms]']
- v109:c3 (es): False → False; after queries ['("Cardiovascular Diseases"[MeSH Terms] OR "cardiovascular disease"[tiab] OR "heart disease"[tiab])']
- v109:c4 (es): False → False; after queries ['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '"Diabetes Mellitus"[MeSH Terms]']
- v109:c5 (es): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])']
- v109:c6 (es): False → False; after queries ['(Pancreatitis[MeSH Terms] OR pancreatitis[tiab])']
- v109:c7 (es): False → False; after queries ['(Seizures[MeSH Terms] OR seizures[tiab])']
- v109:c8 (es): False → False; after queries ['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '"Diabetes Mellitus"[MeSH Terms]']
- v109:c9 (es): False → False; after queries ['(Stroke[MeSH Terms] OR stroke[tiab])', '"Cerebrovascular Disorders"[MeSH Terms]']
- v110:c1 (es): False → False; after queries ['puedes cambiar color', 'puedes cambiar']
- v111:c1 (es): False → True; after queries ['(Fabaceae[MeSH Terms] OR legumes[tiab])']
- v111:c2 (es): False → False; after queries ['digiere']
- v111:c3 (es): False → False; after queries ['(Inflammation[MeSH Terms] OR inflammation[tiab])']
- v111:c4 (es): False → False; after queries ['final pudre fermenta', 'final fermenta']
- v111:c5 (es): False → True; after queries ['(Fabaceae[MeSH Terms] OR legumes[tiab])']
- v114:c2 (es): False → True; after queries ['("Sodium Chloride, Dietary"[MeSH Terms] OR "salt intake"[tiab] OR "sodium intake"[tiab]) AND ("Cardiovascular Diseases"[MeSH Terms] OR "cardiovascular disease"[tiab] OR "heart disease"[tiab])', '("Sodium Chloride, Dietary"[MeSH Terms] OR "salt intake"[tiab] OR "sodium intake"[tiab])']
- v114:c3 (es): False → True; after queries ['("Dietary Sugars"[MeSH Terms] OR sugar[tiab]) AND ("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND (Hypertension[MeSH Terms] OR hypertension[tiab] OR "blood pressure"[tiab])', '("Dietary Sugars"[MeSH Terms] OR sugar[tiab]) AND ("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND "Cardiovascular Diseases"[MeSH Terms]']
- v114:c4 (es): False → True; after queries ['("Sodium Chloride, Dietary"[MeSH Terms] OR "salt intake"[tiab] OR "sodium intake"[tiab])']
- v114:c5 (es): False → True; after queries ['("Dietary Sugars"[MeSH Terms] OR sugar[tiab])']
- v119:c2 (es): False → False; after queries ['alcaliniza']
- v119:c3 (es): False → True; after queries ['("Sodium Bicarbonate"[MeSH Terms] OR "sodium bicarbonate"[tiab])']
- v119:c4 (es): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])']
- v120:c1 (es): False → False; after queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']
- v120:c2 (es): False → True; after queries ['(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab]) AND ("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])', '(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab])']
- v120:c3 (es): False → True; after queries ['(Seawater[MeSH Terms] OR seawater[tiab] OR "sea water"[tiab])']
- v120:c4 (es): False → False; after queries ['mandar limpieza constantemente', 'limpieza constantemente']
- v121:c1 (es): False → True; after queries ['("Contraceptives, Oral"[MeSH Terms] OR "oral contraceptives"[tiab])']
- v121:c2 (es): False → False; after queries ['naturales irritar vaginal', 'naturales irritar']
- v121:c3 (es): False → False; after queries ['pica genitales', 'genitales']
- v122:c1 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND (Cholesterol[MeSH Terms] OR cholesterol[tiab])', '("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND Lipids[MeSH Terms]']
- v122:c2 (es): False → True; after queries ['(Ubiquinone[MeSH Terms] OR "coenzyme q10"[tiab])']
- v122:c3 (es): False → True; after queries ['("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND (Cholesterol[MeSH Terms] OR cholesterol[tiab])', '("Dietary Carbohydrates"[MeSH Terms] OR carbohydrate[tiab]) AND Lipids[MeSH Terms]']
- v122:c4 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND ("Alzheimer Disease"[MeSH Terms] OR alzheimer[tiab] OR dementia[tiab])', '("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND Dementia[MeSH Terms]']
- v122:c5 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab])']
- v122:c6 (es): False → True; after queries ['("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND ("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])', '("Hydroxymethylglutaryl-CoA Reductase Inhibitors"[MeSH Terms] OR statin[tiab]) AND "Diabetes Mellitus"[MeSH Terms]']
- v122:c7 (es): False → True; after queries ['("Vitamin B 12"[MeSH Terms] OR "vitamin b12"[tiab]) AND ("Vitamin K"[MeSH Terms] OR "vitamin k"[tiab] OR phytonadione[tiab] OR phylloquinone[tiab])', '(("Vitamin B 12"[MeSH Terms] OR "vitamin b12"[tiab]) OR ("Vitamin K"[MeSH Terms] OR "vitamin k"[tiab] OR phytonadione[tiab] OR phylloquinone[tiab]))']
- v122:c8 (es): False → True; after queries ['(Ubiquinone[MeSH Terms] OR "coenzyme q10"[tiab]) AND ("Heart Failure"[MeSH Terms] OR "heart failure"[tiab])', '(Ubiquinone[MeSH Terms] OR "coenzyme q10"[tiab]) AND "Cardiovascular Diseases"[MeSH Terms]']
- v141:c1 (fr): False → False; after queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])']
- v141:c2 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']
- v141:c3 (fr): False → True; after queries ['(Imiquimod[MeSH Terms] OR imiquimod[tiab])']
- v141:c4 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND (Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])', '(Soaps[MeSH Terms] OR soap[tiab])']
- v143:c1 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']
- v143:c2 (fr): False → True; after queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']
- v167:c1 (hi): False → False; after queries []
- v167:c2 (hi): False → False; after queries []
- v167:c3 (hi): False → False; after queries []
- v167:c4 (hi): False → False; after queries []
- v88:c1 (es): False → False; after queries ['espermatozoides mujeres resistentes', 'espermatozoides resistentes']
- v88:c2 (es): False → False; after queries ['(Ovulation[MeSH Terms] OR ovulation[tiab]) AND ("Sex Preselection"[MeSH Terms] OR "sex selection"[tiab] OR "sex ratio"[tiab])']
- v88:c3 (es): False → False; after queries ['(Ovulation[MeSH Terms] OR ovulation[tiab]) AND ("Sex Preselection"[MeSH Terms] OR "sex selection"[tiab] OR "sex ratio"[tiab])']
- v94:c1 (es): True → True; after queries ['(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab]) AND ("COVID-19"[MeSH Terms] OR "covid-19"[tiab] OR "sars-cov-2"[tiab])', '(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab]) AND "Coronavirus Infections"[MeSH Terms]']
- v94:c2 (es): False → False; after queries ['("COVID-19"[MeSH Terms] OR "covid-19"[tiab] OR "sars-cov-2"[tiab])', '"Coronavirus Infections"[MeSH Terms]']
- v96:c1 (es): False → False; after queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']
- v96:c2 (es): False → False; after queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']
