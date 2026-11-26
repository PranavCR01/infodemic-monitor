# T49 replay after the T50 search rewrite

Evidence: the rewritten planner's own retrieval on the tune split (`scripts/t50_search_recall.py record`, live PubMed, rules only, no model; recorded 2026-11-26T03:18:06Z, code 95025fb99ab2). `t50_kept` is what the reranker kept (what the verifier would see); `t50_retrieved` is everything the searches returned. Guard and judge unchanged. The find-the-study step and the search assistant need a model and are not in this replay.

## `t50_kept`: 4/5 tune videos keep MISINFO (unproven)

| video | label after | basis | UNSUPPORTED claims → after guard |
| --- | --- | --- | --- |
| v22 | MISINFO | unproven | c2 → UNSUPPORTED (10 records, 10 on topic) |
| v36 | MISINFO | unproven | c6 → UNSUPPORTED (2 records, 2 on topic); c7 → INSUFFICIENT_EVIDENCE (0 records, 0 on topic); c10 → UNSUPPORTED (10 records, 10 on topic); c14 → UNSUPPORTED (10 records, 10 on topic) |
| v120 | CANNOT_RECOGNIZE | - | c1 → INSUFFICIENT_EVIDENCE (10 records, 0 on topic) |
| v141 | MISINFO | unproven | c1 → INSUFFICIENT_EVIDENCE (10 records, 0 on topic); c2 → UNSUPPORTED (6 records, 6 on topic) |
| v143 | MISINFO | unproven | c1 → UNSUPPORTED (6 records, 6 on topic); c2 → UNSUPPORTED (6 records, 6 on topic) |

## `t50_retrieved`: 4/5 tune videos keep MISINFO (unproven)

| video | label after | basis | UNSUPPORTED claims → after guard |
| --- | --- | --- | --- |
| v22 | MISINFO | unproven | c2 → UNSUPPORTED (48 records, 48 on topic) |
| v36 | MISINFO | unproven | c6 → UNSUPPORTED (20 records, 18 on topic); c7 → UNSUPPORTED (20 records, 18 on topic); c10 → UNSUPPORTED (18 records, 16 on topic); c14 → UNSUPPORTED (20 records, 18 on topic) |
| v120 | CANNOT_RECOGNIZE | - | c1 → INSUFFICIENT_EVIDENCE (20 records, 0 on topic) |
| v141 | MISINFO | unproven | c1 → INSUFFICIENT_EVIDENCE (20 records, 0 on topic); c2 → UNSUPPORTED (51 records, 47 on topic) |
| v143 | MISINFO | unproven | c1 → UNSUPPORTED (51 records, 47 on topic); c2 → UNSUPPORTED (51 records, 47 on topic) |

## Per claim (`t50_kept`)

- **v22:c2** "Eggs are high in antioxidants, which is really good to prevent something called macular de": terms ['eggs', 'egg', 'antioxidants', 'antioxidant'] (concept); queries ['(Eggs[MeSH Terms] OR egg[tiab] OR eggs[tiab]) AND (Antioxidants[MeSH Terms] OR antioxidant[tiab]) AND ("Macular Degeneration"[MeSH Terms] OR "macular degeneration"[tiab])', '(Eggs[MeSH Terms] OR egg[tiab] OR eggs[tiab]) AND (Antioxidants[MeSH Terms] OR antioxidant[tiab]) AND "Eye Diseases"[MeSH Terms]']; on topic ['ev_42343583', 'ev_27080067', 'ev_11023002']; first titles: ['Assessment of Dietary Nutritional Profile in Turkish Patients with Age-Related Macular Degeneration.', 'Effect of dietary α-tocopherol on the bioavailability of lutein in laying hen.']
- **v36:c6** "Irish Sea Moss: Cures Thyroid Issues": terms ['irish sea moss', 'chondrus', 'irish moss', 'sea moss'] (concept); queries ['(Chondrus[MeSH Terms] OR "irish moss"[tiab] OR "sea moss"[tiab] OR "chondrus crispus"[tiab]) AND ("Thyroid Diseases"[MeSH Terms] OR thyroid[tiab])', '(Chondrus[MeSH Terms] OR "irish moss"[tiab] OR "sea moss"[tiab] OR "chondrus crispus"[tiab])']; on topic ['ev_40499895', 'ev_30990756']; first titles: ['Feeding incremental amounts of the red seaweed Chondrus crispus: Effects on production performance, methane emissions, n', 'Iodine in Edible Seaweed, Its Absorption, Dietary Use, and Relation to Iodine Nutrition in Arctic People.']
- **v36:c7** "Burdock Root: Rids Kidney & Gallbladder Stones": terms ['burdock root', 'arctium', 'burdock'] (concept); queries ['(Arctium[MeSH Terms] OR burdock[tiab] OR arctium[tiab]) AND (Gallstones[MeSH Terms] OR gallstones[tiab])', '(Arctium[MeSH Terms] OR burdock[tiab] OR arctium[tiab])']; on topic none
- **v36:c10** "Irish Sea Moss: Building Muscles Mass": terms ['irish sea moss', 'chondrus', 'irish moss', 'sea moss'] (concept); queries ['(Chondrus[MeSH Terms] OR "irish moss"[tiab] OR "sea moss"[tiab] OR "chondrus crispus"[tiab])']; on topic ['ev_5968606', 'ev_18144183', 'ev_37396716']; first titles: ['Sterols in Irish moss (Chondrus crispus).', 'CHONDRUS extract.']
- **v36:c14** "Burdock Root: Assists with PMS Symptoms": terms ['burdock root', 'arctium', 'burdock'] (concept); queries ['(Arctium[MeSH Terms] OR burdock[tiab] OR arctium[tiab])']; on topic ['ev_20981575', 'ev_31338098', 'ev_20320691']; first titles: ['A review of the pharmacological effects of Arctium lappa (burdock).', 'Arctium Species Secondary Metabolites Chemodiversity and Bioactivities.']
- **v120:c1** "los beneficios son muchísimo primero elimina los metales pesados del cuerpo": terms ['los', 'beneficios', 'son', 'muchísimo'] (fallback); queries ['("Metals, Heavy"[MeSH Terms] OR "heavy metals"[tiab])']; on topic none; first titles: ['Bioremediation of Heavy Metals by the Genus Bacillus.', 'Disorders of heavy metals.']
- **v141:c1** "Ce gamin de 15 ans a inventé un remède contre le cancer": terms ['ce', 'gamin', 'de 15', 'ans'] (fallback); queries ['(Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])']; on topic none; first titles: ['Familial Pancreatic Cancer.', 'Cancer cachexia.']
- **v141:c2** "a fabriqué un savon qui prévient et traite le cancer de la peau": terms ['savon', 'soap', 'soaps'] (concept); queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']; on topic ['ev_12637935', 'ev_39423608', 'ev_10499830']; first titles: ['UVA, melanoma, and antibacterial soaps.', "From science fair to TIME cover: The hype surrounding a teen's skin cancer treating soap."]
- **v143:c1** "il vient d'inventer un savon qui traite le cancer de la peau": terms ['savon', 'soap', 'soaps'] (concept); queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']; on topic ['ev_12637935', 'ev_39423608', 'ev_10499830']; first titles: ['UVA, melanoma, and antibacterial soaps.', "From science fair to TIME cover: The hype surrounding a teen's skin cancer treating soap."]
- **v143:c2** "Il a conçu un savon qui protège du cancer de la peau, avec de nombreuses propriétés qui pe": terms ['savon', 'soap', 'soaps'] (concept); queries ['(Soaps[MeSH Terms] OR soap[tiab]) AND ("Skin Neoplasms"[MeSH Terms] OR "skin cancer"[tiab] OR melanoma[tiab])', '(Soaps[MeSH Terms] OR soap[tiab]) AND Neoplasms[MeSH Terms]']; on topic ['ev_12637935', 'ev_39423608', 'ev_10499830']; first titles: ['UVA, melanoma, and antibacterial soaps.', "From science fair to TIME cover: The hype surrounding a teen's skin cancer treating soap."]
