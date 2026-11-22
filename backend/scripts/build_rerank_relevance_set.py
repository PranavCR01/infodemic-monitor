"""Builds ``app/tests/fixtures/rerank/relevance_set.jsonl`` (T05, issue #32).

The hand-labelled relevance set for the reranker: 12 claims, each with the candidate
papers in the order a PubMed relevance search returns them, every paper labelled:

- 2 = tests the claim: this intervention, this outcome, in humans (the population the
  claim is about, when it names one);
- 1 = related human evidence the verifier could use, but indirect (a broader exposure, a
  different but close outcome, or a review that mentions the question);
- 0 = not evidence for the claim (mechanistic, animal, food chemistry, off-topic, opinion,
  social-media analysis).

**SYNTHETIC.** The build environment cannot reach NCBI, so these papers are written to
look like what PubMed returns for each claim (realistic mixes of trials, cohorts, cell
and animal work, and off-topic hits); they are not real records. PMIDs are 98000xxx and
every abstract starts "Synthetic." The labels were written by the build agent, which also
wrote the reranker, so the measured precision is optimistic: replace this file with real
PubMed results for the same claims, labelled by two people, before trusting the number
(see context/MULTI_AGENT.md §7f).

    python scripts/build_rerank_relevance_set.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "tests" / "fixtures" / "rerank" / "relevance_set.jsonl"

JA = "Journal Article"
RCT = "Randomized Controlled Trial"
SR = "Systematic Review"
MA = "Meta-Analysis"
REV = "Review"
OBS = "Observational Study"
CR = "Case Reports"
CT = "Clinical Trial"
ED = "Editorial"

# claim_id, claim text, then papers in PubMed order: (title, abstract, types, label)
CLAIMS: list[tuple[str, str, list[tuple[str, str, list[str], int]]]] = [
    ("r01", "Lemon water cures cancer.", [
        ("Lemon peel extract induces apoptosis in MCF-7 breast cancer cells",
         "Synthetic. Lemon peel extract reduced viability of cultured breast cancer cells in vitro.", [JA], 0),
        ("Citrus fruit intake and risk of cancer: a meta-analysis of prospective studies",
         "Synthetic. Pooled cohorts of adults; higher citrus intake was associated with modestly lower risk of several cancers.", [JA, MA, SR], 1),
        ("D-limonene suppresses tumour growth in a murine xenograft model",
         "Synthetic. Mice bearing xenografts received oral limonene; tumour volume decreased.", [JA], 0),
        ("Phenolic content and antioxidant capacity of lemon juice by HPLC",
         "Synthetic. Composition analysis of lemon juice from five cultivars.", [JA], 0),
        ("Lemon juice drinking in patients undergoing chemotherapy for colorectal cancer: a randomised trial",
         "Synthetic. Patients with colorectal cancer were randomised to daily lemon water or plain water; no difference in tumour response or survival.", [JA, RCT], 2),
        ("Citrus consumption and gastric cancer incidence: a population-based cohort",
         "Synthetic. Adults followed for 12 years; citrus intake was weakly inversely associated with gastric cancer.", [JA, OBS], 1),
        ("Alkaline water and cancer claims on social media: a content analysis",
         "Synthetic. Videos claiming lemon water alkalises the body and cures cancer were coded for accuracy.", [JA], 0),
        ("Use of alternative medicine instead of conventional treatment and survival of patients with cancer",
         "Synthetic. Cohort of patients who chose alternative medicine, including dietary cures such as lemon water, had higher mortality.", [JA, OBS], 2),
        ("Citrus flavonoids in cancer biology: an overview",
         "Synthetic. This review summarises cell and animal studies of citrus flavonoids and cancer pathways.", [JA, REV], 0),
        ("Lemon water: separating fact from fiction",
         "Synthetic. Editorial on popular health claims about lemon water.", [ED], 0),
    ]),
    ("r02", "Drinking hot water every morning cures the flu.", [
        ("Thermal inactivation of influenza A virus in aqueous solution",
         "Synthetic. Influenza virus titres in vitro fell at temperatures above 56 C.", [JA], 0),
        ("Hot drinks and symptom relief in adults with common cold and flu: a randomised trial",
         "Synthetic. Adults with influenza-like illness were randomised to a hot or room-temperature drink; hot drinks relieved symptoms but did not shorten illness.", [JA, RCT], 2),
        ("Fluid intake for acute respiratory infections: a systematic review",
         "Synthetic. No trials showed that increased fluids, hot or cold, shorten influenza or other respiratory infections in humans.", [JA, SR], 2),
        ("Water temperature preferences in a national drinking survey",
         "Synthetic. Survey of beverage temperature preferences among adults.", [JA], 0),
        ("Influenza vaccination coverage among healthcare workers",
         "Synthetic. Cross-sectional survey of influenza vaccine uptake.", [JA], 0),
        ("Effect of hot beverages on nasal mucus velocity in healthy volunteers",
         "Synthetic. Hot water increased nasal mucus velocity compared with cold water in 15 volunteers.", [JA, CT], 1),
        ("Oseltamivir for influenza in adults: a meta-analysis",
         "Synthetic. Antiviral treatment shortened symptoms by about one day in adults with influenza.", [JA, MA], 0),
        ("Home remedies used for influenza-like illness: a cross-sectional study",
         "Synthetic. Participants reported using hot drinks, honey and rest; remedy use was not associated with faster recovery.", [JA, OBS], 1),
        ("Heat exposure and immune function in mice infected with influenza",
         "Synthetic. Mice housed at higher ambient temperature had altered survival after influenza infection.", [JA], 0),
        ("Beverage temperature and recovery from influenza-like illness: a cohort study",
         "Synthetic. Adults recording beverage temperature during illness; no association with time to recovery from influenza.", [JA, OBS], 2),
    ]),
    ("r03", "Garlic stops colds.", [
        ("Allicin inhibits rhinovirus replication in cultured epithelial cells",
         "Synthetic. Allicin reduced rhinovirus replication in vitro.", [JA], 0),
        ("Garlic for the prevention and treatment of the common cold: a systematic review",
         "Synthetic. One trial of 146 adults; too little evidence to conclude garlic prevents colds.", [JA, SR], 2),
        ("Garlic supplement and common cold incidence: a double-blind placebo-controlled trial",
         "Synthetic. Adults were randomised to an allicin supplement or placebo for 12 weeks; fewer colds were reported in the garlic group.", [JA, RCT], 2),
        ("Effects of garlic extract on upper respiratory infection in mice",
         "Synthetic. Mice fed garlic extract had lower viral load.", [JA], 0),
        ("Garlic and cardiovascular risk factors: a meta-analysis",
         "Synthetic. Garlic lowered blood pressure modestly in adults with hypertension.", [JA, MA], 0),
        ("Aged garlic extract and immune cell function in healthy adults: a randomised trial",
         "Synthetic. Adults taking aged garlic extract had fewer days with cold and flu symptoms, though not fewer colds.", [JA, RCT], 2),
        ("Organosulfur compounds in garlic: chemistry and composition",
         "Synthetic. Composition of garlic cultivars by HPLC.", [JA], 0),
        ("Vitamin C for preventing and treating the common cold",
         "Synthetic. Regular vitamin C did not reduce cold incidence in the general population.", [JA, SR], 0),
        ("Complementary remedies for the common cold in primary care: a narrative review",
         "Synthetic. We review echinacea, zinc, garlic and other remedies for colds.", [JA, REV], 1),
        ("Garlic allergy presenting as contact dermatitis",
         "Synthetic. We report a case of a 45-year-old cook with garlic dermatitis.", [JA, CR], 0),
    ]),
    ("r04", "Vaccines cause autism in children.", [
        ("Thimerosal exposure and neuronal cell death in vitro",
         "Synthetic. Neuronal cell lines exposed to thimerosal showed reduced viability.", [JA], 0),
        ("Vaccines are not associated with autism: a meta-analysis of case-control and cohort studies",
         "Synthetic. Over 1.2 million children; no association between vaccination and autism.", [JA, MA, SR], 2),
        ("Measles, mumps, rubella vaccination and autism: a nationwide cohort study",
         "Synthetic. Danish children followed from birth; MMR vaccine was not associated with autism spectrum disorder.", [JA, OBS], 2),
        ("Vaccine hesitancy among parents of children with autism",
         "Synthetic. Survey of parental attitudes to vaccination.", [JA], 1),
        ("Aluminium adjuvant injection and behaviour in mice",
         "Synthetic. Neonatal mice injected with aluminium adjuvant showed altered behaviour.", [JA], 0),
        ("Genetic architecture of autism spectrum disorder",
         "Synthetic. This review summarises heritability and risk genes for autism.", [JA, REV], 0),
        ("Timing of the first MMR dose and autism diagnosis in children: a case-control study",
         "Synthetic. Children with autism were not more likely to have received MMR vaccine before diagnosis.", [JA, OBS], 2),
        ("Vaccination and autism: the retraction of a fraudulent paper",
         "Synthetic. Editorial on the retracted 1998 paper.", [ED], 1),
        ("Prenatal influenza vaccination and autism in offspring: a cohort study",
         "Synthetic. Maternal influenza vaccine in pregnancy was not associated with autism in children.", [JA, OBS], 2),
        ("Autism prevalence trends in the United States",
         "Synthetic. Surveillance data show rising prevalence of autism diagnoses in children.", [JA], 0),
    ]),
    ("r05", "Vitamin C prevents the common cold.", [
        ("Vitamin C for preventing and treating the common cold: a systematic review",
         "Synthetic. 29 trials; regular vitamin C did not reduce the incidence of colds in the general population.", [JA, SR, MA], 2),
        ("Ascorbic acid uptake by leukocytes in vitro",
         "Synthetic. Leukocyte ascorbic acid transport was measured in cell culture.", [JA], 0),
        ("Vitamin C supplementation and common cold incidence in marathon runners: a randomised trial",
         "Synthetic. Runners randomised to vitamin C had fewer colds after the race.", [JA, RCT], 2),
        ("Vitamin C and sepsis outcomes: a meta-analysis",
         "Synthetic. Intravenous vitamin C in sepsis did not reduce mortality.", [JA, MA], 0),
        ("Dietary vitamin C intake and respiratory infections in older adults: a cohort",
         "Synthetic. Higher dietary vitamin C was weakly associated with fewer respiratory infections.", [JA, OBS], 1),
        ("Vitamin C content of fruit juices after storage",
         "Synthetic. Ascorbic acid content declined with storage time.", [JA], 0),
        ("High-dose vitamin C at onset of the common cold: a randomised placebo-controlled trial",
         "Synthetic. Adults taking 8 g at symptom onset had shorter colds; incidence was not studied.", [JA, RCT], 1),
        ("Scurvy in a patient on a restrictive diet",
         "Synthetic. We describe a case of scurvy.", [JA, CR], 0),
        ("Vitamin C deficiency impairs antiviral immunity in mice",
         "Synthetic. Gulo knockout mice lacking vitamin C had worse influenza outcomes.", [JA], 0),
        ("Vitamin C supplementation in children and common cold episodes: a randomised trial",
         "Synthetic. Children randomised to vitamin C had a similar number of colds to placebo.", [JA, RCT], 2),
    ]),
    ("r06", "Ivermectin cures COVID-19.", [
        ("Ivermectin inhibits SARS-CoV-2 replication in vitro",
         "Synthetic. Ivermectin reduced viral RNA in Vero cells at high concentrations.", [JA], 0),
        ("Effect of early treatment with ivermectin on hospitalisation among patients with COVID-19",
         "Synthetic. Outpatients with COVID-19 were randomised to ivermectin or placebo; no reduction in hospitalisation.", [JA, RCT], 2),
        ("Ivermectin for preventing and treating COVID-19: a systematic review",
         "Synthetic. Reliable trials show no benefit of ivermectin on mortality or recovery from COVID-19.", [JA, SR, MA], 2),
        ("Ivermectin toxicity cases reported to poison centres during the pandemic",
         "Synthetic. Calls about ivermectin exposure rose; most involved veterinary products.", [JA, OBS], 0),
        ("Ivermectin in onchocerciasis control programmes",
         "Synthetic. Mass drug administration of ivermectin reduced onchocerciasis transmission.", [JA], 0),
        ("Ivermectin prescribing trends in the United States during COVID-19",
         "Synthetic. Outpatient ivermectin prescriptions increased in 2021.", [JA, OBS], 0),
        ("Ivermectin and time to recovery in adults with mild COVID-19: a randomised platform trial",
         "Synthetic. Participants randomised to ivermectin recovered no faster than those on usual care.", [JA, RCT], 2),
        ("Ivermectin pharmacokinetics and achievable lung concentrations",
         "Synthetic. Modelling suggested plasma concentrations far below those active in vitro.", [JA], 0),
        ("Ivermectin treatment in hamsters infected with SARS-CoV-2",
         "Synthetic. Hamsters given ivermectin had reduced olfactory symptoms.", [JA], 0),
        ("Repurposed drugs for COVID-19: an overview",
         "Synthetic. This review covers hydroxychloroquine, ivermectin and other repurposed drugs for COVID-19.", [JA, REV], 1),
    ]),
    ("r07", "Intermittent fasting reverses type 2 diabetes.", [
        ("Intermittent fasting and remission of type 2 diabetes: a randomised clinical trial",
         "Synthetic. Adults with type 2 diabetes on intermittent fasting achieved more remission than controls at 3 months.", [JA, RCT], 2),
        ("Fasting-induced autophagy in pancreatic beta cells",
         "Synthetic. Beta cell lines under nutrient deprivation showed increased autophagy.", [JA], 0),
        ("Time-restricted feeding improves insulin sensitivity in obese mice",
         "Synthetic. Mice on time-restricted feeding had improved glucose tolerance.", [JA], 0),
        ("Intermittent fasting versus continuous calorie restriction for type 2 diabetes: a meta-analysis",
         "Synthetic. Both approaches produced similar HbA1c reductions in adults with diabetes.", [JA, MA, SR], 2),
        ("Ramadan fasting and glycaemic control in patients with diabetes: a cohort study",
         "Synthetic. HbA1c changed little during Ramadan fasting in patients with type 2 diabetes.", [JA, OBS], 1),
        ("Hypoglycaemia during fasting in insulin-treated patients",
         "Synthetic. Case series of hypoglycaemia during religious fasting.", [JA, CR], 0),
        ("Fasting glucose reference ranges in children",
         "Synthetic. Population reference values for fasting plasma glucose.", [JA], 0),
        ("Diet and diabetes remission: a narrative review",
         "Synthetic. We review low-calorie diets, fasting and remission of type 2 diabetes.", [JA, REV], 1),
        ("Intermittent fasting and weight loss in adults with obesity: a randomised trial",
         "Synthetic. Weight loss was similar to daily calorie restriction; diabetes was an exclusion criterion.", [JA, RCT], 0),
        ("Alternate-day fasting in adults with type 2 diabetes: a pilot trial",
         "Synthetic. Twelve participants with type 2 diabetes on alternate-day fasting reduced medication use.", [JA, CT], 2),
    ]),
    ("r08", "Apple cider vinegar causes weight loss.", [
        ("Acetic acid suppresses lipid accumulation in hepatocytes",
         "Synthetic. Acetic acid reduced lipid droplets in cultured liver cells.", [JA], 0),
        ("Vinegar intake reduces body weight in obese Japanese adults: a randomised trial",
         "Synthetic. Adults drinking vinegar daily for 12 weeks lost about 1 kg more than placebo.", [JA, RCT], 2),
        ("Apple cider vinegar and body weight: a systematic review and meta-analysis",
         "Synthetic. Few small trials; apple cider vinegar produced small, uncertain weight loss.", [JA, SR, MA], 2),
        ("Acetic acid feeding and fat accumulation in rats",
         "Synthetic. Rats fed acetic acid gained less body fat.", [JA], 0),
        ("Esophageal injury after apple cider vinegar tablet",
         "Synthetic. We report a case of a woman with throat burn from a vinegar tablet.", [JA, CR], 0),
        ("Vinegar and postprandial glucose in adults with insulin resistance",
         "Synthetic. Vinegar before a meal lowered post-meal glucose in a crossover trial.", [JA, CT], 1),
        ("Apple cider vinegar diet plus calorie restriction in overweight adults: a randomised trial",
         "Synthetic. Adding apple cider vinegar to calorie restriction gave greater weight loss than calorie restriction alone.", [JA, RCT], 2),
        ("Polyphenol composition of apple cider vinegars",
         "Synthetic. HPLC composition analysis of commercial vinegars.", [JA], 0),
        ("Weight-loss claims for apple cider vinegar on social media",
         "Synthetic. Content analysis of weight loss claims in videos.", [JA], 0),
        ("Dietary supplements for weight loss: an overview",
         "Synthetic. This review covers green tea, garcinia and apple cider vinegar for weight loss.", [JA, REV], 1),
    ]),
    ("r09", "Fluoride in drinking water lowers IQ in children.", [
        ("Fluoride exposure and neurotoxicity in rats",
         "Synthetic. Rats given high-fluoride water showed learning deficits.", [JA], 0),
        ("Community water fluoridation and IQ in children: a prospective cohort",
         "Synthetic. Children in fluoridated and non-fluoridated areas had similar IQ at age 7.", [JA, OBS], 2),
        ("Fluoride exposure and children's intelligence: a systematic review and meta-analysis",
         "Synthetic. Higher fluoride exposure, mostly above 1.5 mg/L in drinking water, was associated with lower IQ in children.", [JA, SR, MA], 2),
        ("Dental caries after cessation of water fluoridation",
         "Synthetic. Caries increased in children after fluoridation stopped.", [JA, OBS], 0),
        ("Maternal urinary fluoride during pregnancy and IQ in offspring",
         "Synthetic. A birth cohort found an association between prenatal fluoride and lower child IQ.", [JA, OBS], 1),
        ("Fluoride toothpaste and dental fluorosis risk in young children",
         "Synthetic. Cross-sectional survey of fluorosis.", [JA], 0),
        ("Fluoride and neuronal cell apoptosis in vitro",
         "Synthetic. Neuronal cell lines exposed to fluoride showed increased apoptosis.", [JA], 0),
        ("Drinking water fluoride levels and cognitive scores in schoolchildren: a cross-sectional study",
         "Synthetic. Children in high-fluoride villages scored lower on intelligence tests.", [JA, OBS], 2),
        ("Water fluoridation: a public health review",
         "Synthetic. We review the history and benefits of community water fluoridation.", [JA, REV], 1),
        ("Groundwater fluoride concentrations in rural wells",
         "Synthetic. Survey of fluoride concentrations in well water.", [JA], 0),
    ]),
    ("r10", "Honey cures cough in children.", [
        ("Antibacterial activity of manuka honey against respiratory pathogens in vitro",
         "Synthetic. Honey inhibited bacterial growth in culture.", [JA], 0),
        ("Honey for acute cough in children: a systematic review",
         "Synthetic. Honey probably relieves cough symptoms in children more than no treatment.", [JA, SR], 2),
        ("Effect of honey, dextromethorphan and no treatment on nocturnal cough in children: a randomised trial",
         "Synthetic. Children with upper respiratory infection given honey had less night cough.", [JA, RCT], 2),
        ("Infant botulism after honey ingestion",
         "Synthetic. We report a case of botulism in a 4-month-old infant fed honey.", [JA, CR], 0),
        ("Honey composition and adulteration detection by spectroscopy",
         "Synthetic. Composition analysis of commercial honeys.", [JA], 0),
        ("Over-the-counter cough medicines in children: a systematic review",
         "Synthetic. Little evidence that cough syrups help children with acute cough; honey was not studied.", [JA, SR], 1),
        ("Honey and wound healing in adults with burns",
         "Synthetic. Honey dressings healed burns faster than conventional dressings.", [JA, RCT], 0),
        ("Parental use of home remedies for cough in children",
         "Synthetic. Survey of parents; honey was the most common remedy.", [JA], 1),
        ("Honey versus placebo for cough in children aged 1 to 5: a double-blind trial",
         "Synthetic. Children randomised to honey had greater improvement in cough frequency than placebo.", [JA, RCT], 2),
        ("Honey supplementation and cough in rats exposed to citric acid",
         "Synthetic. Rats given honey coughed less after citric acid challenge.", [JA], 0),
    ]),
    ("r11", "5G spreads coronavirus.", [
        ("5G and COVID-19 misinformation on Twitter: a network analysis",
         "Synthetic. Analysis of tweets linking 5G to the coronavirus pandemic.", [JA], 0),
        ("Radiofrequency exposure and viral transmission: a review of biological plausibility",
         "Synthetic. No mechanism exists by which radiofrequency fields could transmit SARS-CoV-2.", [JA, REV], 2),
        ("Mobile network coverage and COVID-19 incidence across regions: an ecological study",
         "Synthetic. 5G coverage was not associated with COVID-19 incidence after adjusting for population density.", [JA, OBS], 2),
        ("Radiofrequency electromagnetic fields and health: a systematic review",
         "Synthetic. Exposures below guideline limits had no established health effects in humans.", [JA, SR], 1),
        ("Arson attacks on cell towers during the COVID-19 pandemic",
         "Synthetic. Report on attacks on telecommunications infrastructure.", [JA], 0),
        ("5G millimetre wave antenna design for urban networks",
         "Synthetic. Engineering design of antennas.", [JA], 0),
        ("Electromagnetic field exposure and immune function in mice",
         "Synthetic. Mice exposed to radiofrequency fields showed no change in immune markers.", [JA], 0),
        ("Belief in 5G COVID-19 conspiracy theories and vaccine hesitancy",
         "Synthetic. Survey of adults; conspiracy belief predicted vaccine hesitancy.", [JA, OBS], 0),
        ("SARS-CoV-2 transmission routes: a systematic review",
         "Synthetic. Transmission occurs through respiratory droplets and aerosols between people.", [JA, SR], 1),
        ("Debunking 5G and coronavirus claims",
         "Synthetic. Editorial on the 5G coronavirus myth.", [ED], 1),
    ]),
    ("r12", "Probiotics prevent antibiotic-associated diarrhea.", [
        ("Probiotic strains adhere to intestinal epithelial cell lines",
         "Synthetic. Adhesion of Lactobacillus strains to Caco-2 cells in vitro.", [JA], 0),
        ("Probiotics for the prevention of antibiotic-associated diarrhea: a meta-analysis",
         "Synthetic. Probiotics reduced antibiotic-associated diarrhea in children and adults.", [JA, SR, MA], 2),
        ("Saccharomyces boulardii for antibiotic-associated diarrhea in children: a randomised trial",
         "Synthetic. Children on antibiotics randomised to S. boulardii had less diarrhea than placebo.", [JA, RCT], 2),
        ("Antibiotic prescribing for respiratory infections in primary care",
         "Synthetic. Cross-sectional study of prescribing rates.", [JA], 0),
        ("Probiotics and gut microbiota recovery after antibiotics in mice",
         "Synthetic. Mice given probiotics after antibiotics had delayed microbiome recovery.", [JA], 0),
        ("Probiotic bacteraemia in an immunocompromised patient",
         "Synthetic. We report a case of Lactobacillus bacteraemia.", [JA, CR], 0),
        ("Lactobacillus for prevention of diarrhea in older adults on antibiotics: a multicentre randomised trial",
         "Synthetic. Older adults randomised to Lactobacillus had a similar rate of antibiotic-associated diarrhea to placebo.", [JA, RCT], 2),
        ("Probiotics for irritable bowel syndrome: a systematic review",
         "Synthetic. Some probiotics improved IBS symptoms.", [JA, SR], 0),
        ("Clostridioides difficile infection after antibiotics: risk factors",
         "Synthetic. Cohort of hospital patients on antibiotics; probiotic use was not recorded.", [JA, OBS], 1),
        ("Viability of probiotic bacteria in commercial yoghurts",
         "Synthetic. Colony counts in yoghurts during storage.", [JA], 0),
    ]),
]


def rows() -> list[dict]:
    out = []
    for n, (cid, claim, papers) in enumerate(CLAIMS, start=1):
        for rank, (title, abstract, types, label) in enumerate(papers, start=1):
            pmid = f"98{n:03d}{rank:03d}"
            out.append({
                "claim_id": cid, "claim": claim, "pubmed_rank": rank, "pmid": pmid,
                "title": f"{title} (synthetic)", "abstract": abstract,
                "publication_type": types, "label": label,
            })
    return out


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for row in rows():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
