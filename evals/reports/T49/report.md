# T49: unproven guard on the tune split's frozen evidence

Frozen evidence: `origin/data/t38-frozen-evidence:frozen_evidence_tune.json` (recorded 2026-11-24T03:04:34+00:00, code 93068e61633d). Golden set: in-repo `research/claim-level/dataset`, tune split only. No model calls.

The golden set has 12 MISINFO (unproven) videos in total; 5 are in the tune split. The other 7 are in the test split, which this task must not read.

## Evidence mode `retrieved+cited`: 0/5 tune videos keep MISINFO (unproven)

| video | label after | basis | UNSUPPORTED claims → after guard |
| --- | --- | --- | --- |
| v22 | NO_MISINFO | - | c2 → INSUFFICIENT_EVIDENCE (1 kept, 0 on topic) |
| v36 | CANNOT_RECOGNIZE | - | c6 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic); c7 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic); c10 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic); c14 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic) |
| v120 | CANNOT_RECOGNIZE | - | c1 → INSUFFICIENT_EVIDENCE (0 kept, 0 on topic) |
| v141 | NO_MISINFO | - | c1 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic); c2 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic) |
| v143 | CANNOT_RECOGNIZE | - | c1 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic); c2 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic) |

## Evidence mode `retrieved`: 0/5 tune videos keep MISINFO (unproven)

| video | label after | basis | UNSUPPORTED claims → after guard |
| --- | --- | --- | --- |
| v22 | NO_MISINFO | - | c2 → INSUFFICIENT_EVIDENCE (0 kept, 0 on topic) |
| v36 | CANNOT_RECOGNIZE | - | c6 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic); c7 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic); c10 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic); c14 → INSUFFICIENT_EVIDENCE (no frozen record) (0 kept, 0 on topic) |
| v120 | CANNOT_RECOGNIZE | - | c1 → INSUFFICIENT_EVIDENCE (0 kept, 0 on topic) |
| v141 | NO_MISINFO | - | c1 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic); c2 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic) |
| v143 | CANNOT_RECOGNIZE | - | c1 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic); c2 → INSUFFICIENT_EVIDENCE (10 kept, 0 on topic) |

## Why the labels change

- **Empty search** (v22 c2 eggs / macular degeneration; v120 c1 seawater, Spanish): the pipeline's retrieval kept 0 records. In `retrieved+cited` v22 also sees the golden-cited lutein review, which mentions egg yolks but not antioxidants in eggs, so it is not on topic.
- **Condition-only search** (v141, v143: French 'a soap that treats/prevents skin cancer'): the planner recognised only 'cancer' and kept 10 generic cancer papers (pancreatic cancer, cachexia, angiogenesis). None mentions a soap; this is the same failure as the vitamin K c11.
- **No recorded search** (v36 c6/c7/c10/c14: sea moss, burdock root): the T38 frozen file recorded only v36 c1-c5, so these claims replay as an empty search. Their real outcome depends on what retrieval finds for 'Irish sea moss' / 'burdock root'.
- Where a video has other SUPPORTED claims (v22, v141) it becomes NO_MISINFO; otherwise CANNOT_RECOGNIZE with `nothing_judged` (v36, v120, v143).

## Per claim (mode `retrieved`)

- **v22:c2** "Eggs are high in antioxidants, which is really good to prevent something called macular degeneration": terms ['eggs', 'antioxidants'] (fallback, all); 0 kept; on topic none
- **v36:c6** "Irish Sea Moss: Cures Thyroid Issues": terms ['irish', 'sea', 'moss'] (fallback, all); 0 kept; on topic none
- **v36:c7** "Burdock Root: Rids Kidney & Gallbladder Stones": terms ['burdock', 'root'] (fallback, all); 0 kept; on topic none
- **v36:c10** "Irish Sea Moss: Building Muscles Mass": terms ['irish', 'sea', 'moss'] (fallback, all); 0 kept; on topic none
- **v36:c14** "Burdock Root: Assists with PMS Symptoms": terms ['burdock', 'root'] (fallback, all); 0 kept; on topic none
- **v120:c1** "los beneficios son muchísimo primero elimina los metales pesados del cuerpo": terms ['los', 'beneficios', 'son', 'muchísimo'] (fallback, all); 0 kept; on topic none
- **v141:c1** "Ce gamin de 15 ans a inventé un remède contre le cancer": terms ['ce', 'gamin', 'de 15', 'ans'] (fallback, all); 10 kept; on topic none; first titles: ['Familial Pancreatic Cancer.', 'Cancer cachexia.', 'Angiogenesis in cancer.']
- **v141:c2** "a fabriqué un savon qui prévient et traite le cancer de la peau": terms ['fabriqué', 'un', 'savon', 'qui'] (fallback, all); 10 kept; on topic none; first titles: ['Familial Pancreatic Cancer.', 'Cancer cachexia.', 'Angiogenesis in cancer.']
- **v143:c1** "il vient d'inventer un savon qui traite le cancer de la peau": terms ['il', 'vient', "d'inventer", 'un'] (fallback, all); 10 kept; on topic none; first titles: ['Familial Pancreatic Cancer.', 'Cancer cachexia.', 'Angiogenesis in cancer.']
- **v143:c2** "Il a conçu un savon qui protège du cancer de la peau, avec de nombreuses propriétés qui persistent m": terms ['il', 'conçu', 'un', 'savon'] (fallback, all); 10 kept; on topic none; first titles: ['Familial Pancreatic Cancer.', 'Cancer cachexia.', 'Angiogenesis in cancer.']
