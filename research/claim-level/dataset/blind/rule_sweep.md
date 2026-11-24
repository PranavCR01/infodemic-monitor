# Rule sweep (A2–A4), report only

These are claims elsewhere in the in-scope set that the adjudicated rules could change. **None of them has been applied**; the project lead decides.

How they were found: A2 by scanning OCR captions for efficacy words not covered by speech or by an existing claim; A3 by searching endorsed INSUFFICIENT_EVIDENCE claims for detox/remove/cleanse wording; A4 by searching endorsed INSUFFICIENT_EVIDENCE efficacy claims whose notes describe indirect evidence (ingredient, supplement, animal, different intervention). The heuristics produced about 60 hits, which were then read one by one. Those listed below are the ones that survived that reading.

## Candidates that would change (8)

| # | rule | row | claim | now | change it would need |
|---|---|---|---|---|---|
| 1 | A2 | v36 (new) | Infographic: Irish Sea Moss "Boost Mens Sexual Wellness", "Building Muscles Mass", "Reduces Diseases Risk" (34–40 s) | not extracted | add as screen-only ENDORSES claims; efficacy, nothing found, so likely UNSUPPORTED (no label change: v36 is already MISINFO/unproven) |
| 2 | A2 | v36 (new) | Infographic: Burdock "Fights Infections", "Soothes Eczema", "Assists with PMS Symptoms"; Moringa "Promotes Liver Protection", "Treats Urinary Disorders", "Anti-Ulcer" (28–56 s) | not extracted | as #1; each needs its own search (several herbs have animal studies, so they would be INSUFFICIENT rather than UNSUPPORTED) |
| 3 | A2 | v81 (new) | On-screen list for legs-up-the-wall: "Improved sleep", "Reduce swelling", "Support lymph flow" (38 s) | not extracted (v81 has one speech claim) | add screen-only ENDORSES claims; "reduce swelling" is an efficacy claim, so UNSUPPORTED if nothing found, which would make v81 MISINFO/unproven |
| 4 | A3 | v35 c2 | miso soup carried binders that would actually remove any form of radiation from the human body | INSUFFICIENT_EVIDENCE, S: PMID:11833659 | already efficacy under A3; stays INSUFFICIENT only if PMID:11833659 (animal radioprotection) is judged to bear on it under A4. If A4 rules it out (animal miso study vs human radiation removal), it becomes UNSUPPORTED and v35 becomes MISINFO/unproven |
| 5 | A3 | v161 c6 | The best fruit for detoxing the liver is lemon | INSUFFICIENT_EVIDENCE, no evidence | "detoxing the liver" as a specific effect makes it efficacy; with nothing found it becomes UNSUPPORTED (treatment_efficacy). "Best fruit" is a comparative, so the lead may still read it as vague |
| 6 | A3 | v139 c5 | cuando el cuerpo se limpia de hongo … [se le desaparece] la migraña | INSUFFICIENT_EVIDENCE, C: PMID:2247104 | a fungal "cleanse" curing migraine is efficacy. It cites contradicting evidence, so UNSUPPORTED is barred: either CONTRADICTED if PMID:2247104 tests it, or drop the citation under A4 and make it UNSUPPORTED |
| 7 | A3 | v139 c6 | cuando el cuerpo se limpia de hongo … [se le desaparecen] los picores en la piel | as #6 | as #6 |
| 8 | A4 | v22 c2 | Eggs are high in antioxidants, which is really good to prevent … macular degeneration | INSUFFICIENT_EVIDENCE (lutein review, indirect) | prevention claim; the evidence is on a nutrient (lutein), not on egg intake and AMD, so A4 gives UNSUPPORTED (prevention), and v22 would go NO_MISINFO → **MISINFO/unproven** (rule 3 outranks rule 5) |

## Read and set aside (borderline, likely no change)

- v113 c5 "limpiar el colon y regenerar las células", v120 c4 "limpieza de todo lo que han comido", v149 c4 "cleanse your system", v138 c5 "más alcalino, más eliminación de toxinas": non-specific cleansing or mechanism, so they stay vague wellness unless A3 is read to cover any "cleanse".
- v12 c3 "you pee out the fat" and v13 c3 "flush it out": mechanism or vague, not a claimed therapeutic effect of an intervention.
- v36 c8 (burdock lowers blood sugar): rodent studies of burdock itself, the same intervention, so under the README rule animal data keeps it INSUFFICIENT. A4 is about a different intervention, not a different species.
- v92 c1 (earthing heals any disease): rat study of earthing itself, as above.
- v155 c1 (turmeric spread, "healthy inflammatory function") and v161 c1 (oranges "boost immunity"): A4 applies to the evidence, but the claims are vague wellness, which the README keeps INSUFFICIENT.
- v40 c2 (electrolytes: think better, energy, immune health, no more headaches): mostly vague; only "no more headaches" is efficacy. Split it if the lead wants that row judged.
- v29 "New Cancer Miracle Cure?", v74 "best foods to fight cancer!", v37 metformin headlines: screen titles that are questions or already covered by speech claims.

Count: **8 candidates** (3 A2, 4 A3, 1 A4); 4 of them would change a video label (#3 v81, #4 v35, #6/#7 v139 depending on the citation, #8 v22).
