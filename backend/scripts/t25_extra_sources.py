"""T25 experiment: do more evidence sources resolve the 'source says false, evidence is
silent' golden-set videos? (design §6, §7, §14; automation/BUILD_QUEUE.md T25). Report only.

Scope: the batch-2 videos whose source label implies MISINFO but whose derived label is
CANNOT_RECOGNIZE (research/claim-level/dataset/external_agreement.md on the
data/golden-label-set branch), and every INSUFFICIENT_EVIDENCE claim in them. Each claim is
searched in:

- Europe PMC REST API (www.ebi.ac.uk; includes preprints and full text),
- Cochrane reviews via PubMed E-utilities ("Cochrane Database Syst Rev"[journal]),
- ClinicalTrials.gov API v2,
- the existing reference allow-list (config/reference_sources.yaml: WHO/NHS/FDA/EFSA
  catalogue pages fetched live, CDC from the stored snapshots, NCBI Bookshelf), through
  the production ReferenceSearcher, unchanged.

The search terms per claim are written by hand below (no model call; this script makes no
model API call of any kind). No fact-check database is queried: the golden set's external
labels come from fact-checkers, so that would leak the answer.

Verdicts are judged by a person/agent under the unchanged §7 rules after reading the hits,
and recorded in evals/reports/T25_judgments.json; ``report`` merges those into the
markdown report. Usage (from backend/):

    git show origin/data/golden-label-set:research/claim-level/dataset/claims.csv > /tmp/claims.csv
    git show origin/data/golden-label-set:research/claim-level/dataset/external_agreement.md > /tmp/ea.md
    python scripts/t25_extra_sources.py search --claims /tmp/claims.csv --agreement /tmp/ea.md \
        [--abstracts-dir /tmp/t25_abstracts]   # writes ../evals/reports/T25_extra_sources_results.json
    python scripts/t25_extra_sources.py report --claims /tmp/claims.csv --agreement /tmp/ea.md
                                               # writes ../evals/reports/T25_extra_sources.md

Rate limits: NCBI <= 2.5 requests/s (the shared limiter), Europe PMC and ClinicalTrials.gov
<= 4/s; 429 and 5xx are retried with backoff. A source that cannot be reached (for example a
proxy refusal) is recorded with its error and the run continues with the others.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.retrieval.pubmed import RateLimiter  # noqa: E402
from app.evaluation.metrics import judge_label  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "evals" / "reports"
RESULTS = REPORTS / "T25_extra_sources_results.json"
JUDGMENTS = REPORTS / "T25_judgments.json"
REPORT = REPORTS / "T25_extra_sources.md"

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
COCHRANE = '"Cochrane Database Syst Rev"[journal]'
TOOL = "who_infodemic_monitor"
UA = "who-infodemic-monitor/0.1 (research evaluation; T25)"
RETRY = {429, 500, 502, 503, 504}
MAX_HITS = 5

# ------------------------------------------------------------------ search plan
# Per claim: an English gloss (what the reference allow-list is searched with; its
# matching is English keyword-based), and the query for each source. Written by hand
# from the claim text and the labeller's notes; never from the source's label.
PLAN: dict[str, dict[str, str]] = {
    "v84/c1": dict(gloss="dry ginger powder in the nostril protects against COVID-19",
                   q="(ginger OR Zingiber) AND (COVID-19 OR SARS-CoV-2 OR coronavirus OR respiratory tract infections)",
                   epmc='(ginger OR "Zingiber officinale") AND (nasal OR intranasal) AND (COVID-19 OR SARS-CoV-2)',
                   ct="ginger AND (COVID-19 OR SARS-CoV-2)"),
    "v84/c2": dict(gloss="dry ginger is highly alkaline with a high pH",
                   q="(ginger OR Zingiber) AND (pH OR alkaline OR alkalinity)",
                   epmc='(ginger OR "Zingiber officinale") AND ("pH" OR alkaline OR alkalinity) AND powder',
                   ct="ginger AND pH"),
    "v84/c3": dict(gloss="infections are acidic with low pH and are killed instantly by alkaline ginger",
                   q="(alkaline OR alkalinization OR pH) AND (respiratory tract infections OR COVID-19) AND (nasal OR intranasal)",
                   epmc='(alkaline OR alkalinization) AND (virus OR viral infection) AND (nasal OR intranasal) AND (kill OR inactivation)',
                   ct="alkaline nasal spray"),
    "v85/c1": dict(gloss="wind turbine syndrome is a recognised disease",
                   q='(wind turbine OR "wind farm" OR wind power) AND (health OR noise OR syndrome)',
                   epmc='"wind turbine syndrome" OR ("wind turbine" AND noise AND health)',
                   ct="wind turbine noise"),
    "v92/c1": dict(gloss="grounding your feet (earthing) heals any kind of disease",
                   q="(grounding OR earthing OR barefoot) AND (health OR disease OR therapy)",
                   epmc='(earthing OR grounding) AND (barefoot OR "electrical grounding" OR "earth contact") AND (health OR disease) AND (randomized OR trial OR patients)',
                   ct="earthing OR grounding mat"),
    "v92/c2": dict(gloss="a body that is consistently grounded cannot sustain chronic inflammation",
                   q="(grounding OR earthing) AND (inflammation OR C-reactive protein OR cytokines)",
                   epmc='(earthing OR grounding) AND (barefoot OR "earth contact" OR "grounding mat") AND (inflammation OR "C-reactive protein" OR cytokines)',
                   ct="(earthing OR grounding) AND inflammation"),
    "v92/c3": dict(gloss="inflammation is the root cause of every disease",
                   q="(chronic inflammation OR inflammation) AND (chronic disease) AND (etiology OR cause)",
                   epmc='"chronic inflammation" AND ("chronic disease" OR "non-communicable disease") AND (etiology OR cause OR "root cause") AND review',
                   ct="chronic inflammation chronic disease"),
    "v94/c1": dict(gloss="the Spanish health ministry admits more than 35,000 vaccinated people died of COVID-19",
                   q="(COVID-19 vaccines) AND (mortality OR deaths) AND (vaccinated OR breakthrough)",
                   epmc='(Spain OR Spanish) AND COVID-19 AND (vaccinated OR "breakthrough infection") AND (deaths OR mortality)',
                   ct="COVID-19 vaccine mortality Spain"),
    "v94/c2": dict(gloss="7.5 million vaccinated people caught COVID-19 in Spain and more than 31,000 died",
                   q="(COVID-19 vaccines) AND (breakthrough infections) AND (mortality OR deaths)",
                   epmc='(Spain OR Spanish) AND COVID-19 AND "breakthrough" AND (deaths OR mortality OR "case fatality")',
                   ct="COVID-19 breakthrough infection Spain"),
    "v96/c1": dict(gloss="heavy metals dissolve in fat",
                   q="(heavy metals OR mercury OR cadmium OR lead) AND (lipids OR fat OR oil) AND (solubility OR partitioning OR distribution)",
                   epmc='("heavy metals" OR mercury OR cadmium OR lead) AND ("canned fish" OR "canned tuna") AND (oil OR "covering liquid" OR "packing medium")',
                   ct="heavy metals canned fish"),
    "v96/c2": dict(gloss="eating the oil from canned fish gives a higher concentration of heavy metals",
                   q="(canned fish OR tuna OR sardines) AND (heavy metals OR mercury OR cadmium)",
                   epmc='("canned fish" OR "canned tuna" OR sardines) AND (oil OR brine OR "packing medium") AND (mercury OR cadmium OR lead OR "heavy metals")',
                   ct="canned fish mercury"),
    "v106/c1": dict(gloss="raw garlic clove inserted in the vagina for five nights treats vaginal infection",
                    q="(garlic OR Allium sativum) AND (vaginitis OR vaginosis OR candidiasis OR vaginal)",
                    epmc='(garlic OR "Allium sativum") AND (vaginal OR vaginitis OR vaginosis OR candidiasis) AND (trial OR randomized OR patients OR women)',
                    ct="garlic AND (vaginosis OR vaginitis OR candidiasis)"),
    "v106/c2": dict(gloss="garlic is a natural antibiotic",
                    q="(garlic OR Allium sativum OR allicin) AND (infection OR antibacterial OR common cold)",
                    epmc='(garlic OR allicin) AND (antibiotic OR antibacterial) AND (randomized OR trial OR "systematic review")',
                    ct="garlic AND infection"),
    "v113/c1": dict(gloss="drinking sea water gives remarkable results in cancer patients",
                    q='("sea water" OR seawater OR "deep sea water" OR "Quinton") AND (neoplasms OR cancer)',
                    epmc='("sea water" OR seawater OR "Quinton plasma" OR "marine plasma") AND (drinking OR oral) AND (cancer OR neoplasm) AND (patients OR trial)',
                    ct='("sea water" OR seawater) AND cancer'),
    "v113/c2": dict(gloss="drinking sea water gives remarkable results in hypertension",
                    q='("sea water" OR seawater OR "deep sea water") AND (hypertension OR blood pressure)',
                    epmc='("sea water" OR seawater OR "deep sea water") AND (drinking OR oral) AND (hypertension OR "blood pressure") AND (trial OR randomized OR patients)',
                    ct='("sea water" OR seawater) AND hypertension'),
    "v113/c3": dict(gloss="drinking sea water gives remarkable results in diabetes",
                    q='("sea water" OR seawater OR "deep sea water") AND (diabetes mellitus OR glucose)',
                    epmc='("sea water" OR seawater OR "deep sea water") AND (drinking OR oral) AND (diabetes OR glucose) AND (trial OR randomized OR patients)',
                    ct='("sea water" OR seawater) AND diabetes'),
    "v113/c4": dict(gloss="drinking sea water gives remarkable results in skin diseases",
                    q='("sea water" OR seawater OR thalassotherapy OR balneotherapy OR "Dead Sea") AND (skin diseases OR psoriasis OR dermatitis OR eczema)',
                    epmc='("sea water" OR seawater) AND drinking AND (skin OR psoriasis OR dermatitis OR eczema)',
                    ct='("sea water" OR seawater OR balneotherapy) AND (psoriasis OR dermatitis OR eczema)'),
    "v113/c5": dict(gloss="sea water cleanses the colon and regenerates cells",
                    q='(colon cleansing OR "colonic irrigation" OR "saline laxative" OR "salt water flush") OR ("sea water" AND colon)',
                    epmc='("sea water" OR seawater OR "salt water flush") AND (colon OR "colon cleansing" OR detox)',
                    ct='"salt water flush" OR (seawater AND colon)'),
    "v113/c6": dict(gloss="sea water improves any disease or ailment from the first day",
                    q='("sea water" OR seawater OR "deep sea water") AND (drinking OR oral OR supplementation)',
                    epmc='("sea water" OR seawater OR "Quinton plasma") AND (drinking OR oral) AND (health OR disease) AND (trial OR randomized)',
                    ct='"sea water" OR seawater OR "deep sea water"'),
    "v120/c1": dict(gloss="sea water removes heavy metals from the body",
                    q='(chelation OR detoxification OR elimination) AND (heavy metals OR metals, heavy) AND ("sea water" OR seawater OR minerals)',
                    epmc='("sea water" OR seawater) AND (drinking OR oral) AND ("heavy metals" OR mercury OR lead) AND (excretion OR elimination OR detoxification)',
                    ct='seawater AND heavy metals'),
    "v120/c2": dict(gloss="the vaccine contains a lot of heavy metals",
                    q="(vaccines) AND (heavy metals OR aluminum OR mercury OR thimerosal) AND (safety OR content)",
                    epmc='(COVID-19 vaccine OR vaccine) AND ("heavy metals" OR "metallic contaminants") AND (content OR analysis OR ICP-MS)',
                    ct="vaccine heavy metals"),
    "v120/c3": dict(gloss="sea water contains 118 minerals of the periodic table",
                    q='("sea water" OR seawater) AND (minerals OR trace elements OR composition)',
                    epmc='("sea water" OR seawater) AND ("trace elements" OR "elemental composition" OR "chemical composition") AND periodic',
                    ct='seawater minerals'),
    "v120/c4": dict(gloss="drinking sea water acts as a laxative and cleans out accumulated residues",
                    q='(saline laxative OR "salt water" OR "sea water" OR seawater) AND (bowel cleansing OR bowel preparation OR constipation)',
                    epmc='("sea water" OR seawater OR "salt water flush" OR "saline water") AND (laxative OR "bowel cleansing" OR constipation)',
                    ct='"salt water" AND (constipation OR bowel cleansing)'),
    "v129/c1": dict(gloss="the FDA now says it is okay to prescribe ivermectin for COVID-19",
                    q="(ivermectin) AND (COVID-19 OR SARS-CoV-2)",
                    epmc='ivermectin AND (FDA OR "Food and Drug Administration") AND (COVID-19 OR "off-label")',
                    ct="ivermectin AND COVID-19"),
    "v136/c1": dict(gloss="a home pregnancy test using salt in early morning urine",
                    q='(pregnancy tests OR pregnancy test OR "pregnancy diagnosis") AND (urine OR home)',
                    epmc='("pregnancy test" OR "pregnancy diagnosis") AND (salt OR "sodium chloride") AND urine',
                    ct="salt urine pregnancy test"),
    "v137/c1": dict(gloss="a urine and salt pregnancy test read after 5 minutes",
                    q='(pregnancy tests OR pregnancy test) AND (urine) AND (salt OR sodium chloride OR home OR homemade)',
                    epmc='("pregnancy test" OR "pregnancy diagnosis") AND (salt OR "sodium chloride" OR homemade OR "home-made") AND urine',
                    ct="homemade pregnancy test"),
    "v138/c1": dict(gloss="the alkaline diet boosts the immune system",
                    q='("alkaline diet" OR "dietary acid load" OR "acid-base" OR alkaline) AND (diet) AND (immune OR immunity OR infection)',
                    epmc='("alkaline diet" OR "dietary acid load") AND (immune OR immunity OR "immune system") AND (trial OR randomized OR cohort OR review)',
                    ct='"alkaline diet" OR "dietary acid load"'),
    "v138/c2": dict(gloss="the alkaline diet improves sleep",
                    q='("alkaline diet" OR "dietary acid load") AND (sleep)',
                    epmc='("alkaline diet" OR "dietary acid load") AND sleep',
                    ct='"alkaline diet" AND sleep'),
    "v138/c3": dict(gloss="the alkaline diet improves digestion",
                    q='("alkaline diet" OR "dietary acid load" OR "alkaline water") AND (digestion OR gastrointestinal OR dyspepsia OR reflux)',
                    epmc='("alkaline diet" OR "dietary acid load" OR "alkaline water") AND (digestion OR dyspepsia OR reflux OR gastrointestinal)',
                    ct='"alkaline diet" AND (reflux OR digestion)'),
    "v138/c4": dict(gloss="the alkaline diet improves vitality and energy",
                    q='("alkaline diet" OR "dietary acid load") AND (fatigue OR energy OR vitality OR quality of life)',
                    epmc='("alkaline diet" OR "dietary acid load") AND (fatigue OR vitality OR energy OR "quality of life")',
                    ct='"alkaline diet"'),
    "v138/c5": dict(gloss="the more alkaline the body pH the more toxins are eliminated",
                    q='("alkaline diet" OR "dietary acid load" OR "acid-base equilibrium") AND (diet) AND (detoxification OR toxins OR blood pH)',
                    epmc='("alkaline diet" OR "dietary acid load") AND ("blood pH" OR "acid-base" OR detoxification OR toxins)',
                    ct='"alkaline diet" AND pH'),
    "v138/c6": dict(gloss="alcohol, red meat and processed food acidify the body and cause inflammation",
                    q='("dietary acid load" OR "potential renal acid load") AND (inflammation OR C-reactive protein)',
                    epmc='("dietary acid load" OR "potential renal acid load") AND (inflammation OR "C-reactive protein" OR inflammatory)',
                    ct='"dietary acid load" AND inflammation'),
    "v138/c7": dict(gloss="legumes, vegetables and fruit make the body more alkaline with little digestive effort",
                    q='("dietary acid load" OR "potential renal acid load" OR "alkaline diet") AND (fruit OR vegetables OR legumes) AND (urine pH OR blood pH OR acid-base)',
                    epmc='("dietary acid load" OR "alkaline diet") AND (fruit OR vegetables OR legumes) AND ("urine pH" OR "blood pH" OR "acid-base")',
                    ct='"alkaline diet" AND (fruit OR vegetables)'),
    "v142/c1": dict(gloss="plastic eggs are being sold as real eggs",
                    q='("artificial egg" OR "fake egg" OR "plastic egg" OR (eggs AND adulteration))',
                    epmc='("artificial egg" OR "fake egg" OR "fake eggs" OR "plastic egg" OR "plastic eggs") AND (food fraud OR adulteration OR counterfeit OR authenticity)',
                    ct="fake eggs"),
    "v143/c1": dict(gloss="a soap that treats skin cancer",
                    q="(soap OR topical OR imiquimod OR 5-fluorouracil) AND (skin neoplasms OR basal cell carcinoma OR melanoma)",
                    epmc='(soap OR "cleansing bar") AND ("skin cancer" OR melanoma OR "basal cell carcinoma") AND (treatment OR treat OR trial)',
                    ct="soap AND (skin cancer OR melanoma OR basal cell carcinoma)"),
    "v143/c2": dict(gloss="a soap that protects against skin cancer with properties that persist after rinsing",
                    q="(sunscreening agents OR soap OR topical) AND (skin neoplasms) AND (prevention)",
                    epmc='(soap OR "rinse-off" OR wash) AND ("skin cancer" OR melanoma OR "UV protection" OR sunscreen) AND (prevention OR protection)',
                    ct='soap AND skin cancer prevention'),
    "v149/c1": dict(gloss="a supplement formula supports digestion",
                    q="(dietary supplements OR probiotics OR digestive enzymes) AND (digestion OR dyspepsia)",
                    epmc='("detox" OR "gut health" OR "colon cleanse") AND (supplement OR formula) AND (digestion OR dyspepsia) AND (randomized OR trial)',
                    ct='"gut health" supplement digestion'),
    "v149/c2": dict(gloss="a supplement formula reduces bloating",
                    q="(dietary supplements OR probiotics OR digestive enzymes) AND (bloating OR flatulence OR abdominal distension)",
                    epmc='("detox" OR "gut health" OR "colon cleanse") AND (supplement OR formula) AND bloating AND (randomized OR trial)',
                    ct='supplement AND bloating'),
    "v149/c3": dict(gloss="a supplement formula promotes overall gut health",
                    q='(dietary supplements OR probiotics OR prebiotics) AND ("gut health" OR gastrointestinal microbiome) AND (healthy adults OR healthy volunteers)',
                    epmc='("detox" OR "colon cleanse") AND (supplement OR formula) AND ("gut health" OR microbiome) AND (randomized OR trial)',
                    ct='"gut health" supplement'),
    "v149/c4": dict(gloss="a detox formula cleanses your system and leaves you feeling lighter and more energized",
                    q='(detoxification OR "detox" OR "colon cleansing" OR cleanse) AND (diet OR supplement OR product)',
                    epmc='("detox" OR "colon cleanse" OR cleanse) AND (supplement OR diet OR product) AND (randomized OR trial OR "systematic review")',
                    ct='detox cleanse'),
    "v155/c1": dict(gloss="turmeric spread encourages healthy inflammatory function",
                    q="(curcumin OR turmeric OR Curcuma) AND (inflammation OR anti-inflammatory)",
                    epmc='(turmeric OR curcumin) AND (food OR spread OR dietary) AND (inflammation OR "C-reactive protein") AND (randomized OR trial)',
                    ct="(turmeric OR curcumin) AND inflammation"),
    "v155/c2": dict(gloss="turmeric supports digestion",
                    q="(curcumin OR turmeric OR Curcuma) AND (digestion OR dyspepsia OR irritable bowel syndrome OR gastrointestinal)",
                    epmc='(turmeric OR curcumin) AND (dyspepsia OR digestion OR "irritable bowel") AND (randomized OR trial)',
                    ct="(turmeric OR curcumin) AND (dyspepsia OR digestion)"),
    "v155/c3": dict(gloss="turmeric promotes cardiovascular health",
                    q="(curcumin OR turmeric OR Curcuma) AND (cardiovascular diseases OR lipids OR blood pressure)",
                    epmc='(turmeric OR curcumin) AND (cardiovascular OR lipids OR "blood pressure") AND (randomized OR "meta-analysis")',
                    ct="(turmeric OR curcumin) AND cardiovascular"),
    "v155/c4": dict(gloss="turmeric supports the immune system",
                    q="(curcumin OR turmeric OR Curcuma) AND (immune system OR immunity OR infection)",
                    epmc='(turmeric OR curcumin) AND (immune OR immunity) AND (randomized OR trial) AND (healthy OR adults)',
                    ct="(turmeric OR curcumin) AND immune"),
    "v155/c5": dict(gloss="turmeric promotes healthy skin",
                    q="(curcumin OR turmeric OR Curcuma) AND (skin OR skin diseases OR psoriasis OR acne)",
                    epmc='(turmeric OR curcumin) AND (skin OR psoriasis OR acne OR dermatitis) AND (randomized OR trial OR "systematic review")',
                    ct="(turmeric OR curcumin) AND skin"),
    "v159/c1": dict(gloss="10 minutes a day on a vibration plate is equivalent to jogging for an hour",
                    q='("whole body vibration" OR vibration) AND (exercise OR energy expenditure OR oxygen consumption)',
                    epmc='"whole body vibration" AND ("energy expenditure" OR "oxygen consumption" OR VO2) AND (running OR jogging OR walking OR aerobic)',
                    ct='"whole body vibration" AND energy expenditure'),
    "v161/c1": dict(gloss="oranges are the best fruit for boosting immunity",
                    q='(vitamin C OR ascorbic acid OR citrus OR oranges) AND (common cold OR immunity OR infection)',
                    epmc='(orange OR citrus) AND (fruit) AND (immunity OR "immune function" OR infection) AND (randomized OR trial OR comparison)',
                    ct="orange juice AND immune"),
    "v161/c2": dict(gloss="pineapple is the best fruit for digestion",
                    q="(bromelain OR pineapple OR Ananas) AND (digestion OR dyspepsia OR gastrointestinal)",
                    epmc='(pineapple OR bromelain) AND (digestion OR dyspepsia OR "gastric emptying") AND (randomized OR trial OR human)',
                    ct="(pineapple OR bromelain) AND digestion"),
    "v161/c3": dict(gloss="blueberries are the best fruit for brain health",
                    q="(blueberries OR Vaccinium OR anthocyanins OR berries) AND (cognition OR cognitive function OR dementia)",
                    epmc='(blueberry OR blueberries OR "wild blueberry") AND (cognition OR cognitive OR memory) AND (randomized OR trial)',
                    ct="blueberry AND cognition"),
    "v161/c4": dict(gloss="bananas are the best fruit for reducing stress",
                    q="(bananas OR Musa OR fruit) AND (stress, psychological OR anxiety)",
                    epmc='(banana OR bananas) AND (stress OR anxiety OR mood) AND (randomized OR trial OR human)',
                    ct="banana AND stress"),
    "v161/c5": dict(gloss="pomegranate is the best fruit for heart health",
                    q="(pomegranate OR Punica granatum) AND (cardiovascular diseases OR blood pressure OR lipids)",
                    epmc='(pomegranate OR "Punica granatum") AND (cardiovascular OR "blood pressure" OR lipids) AND ("meta-analysis" OR randomized)',
                    ct="pomegranate AND (cardiovascular OR blood pressure)"),
    "v161/c6": dict(gloss="lemon is the best fruit for detoxing the liver",
                    q="(lemon OR citrus OR Citrus limon) AND (liver OR hepatic OR detoxification)",
                    epmc='(lemon OR "Citrus limon" OR "lemon juice") AND (liver OR hepatic OR "fatty liver" OR detoxification) AND (human OR trial OR patients)',
                    ct="lemon AND liver"),
    "v163/c1": dict(gloss="working at a hospital caused a cluster of brain tumors among staff",
                    q="(brain neoplasms OR glioma OR meningioma) AND (occupational exposure OR health personnel OR cluster)",
                    epmc='("brain tumor" OR "brain tumour" OR glioma OR meningioma) AND (cluster OR "occupational exposure") AND (hospital OR "health care workers" OR "healthcare workers")',
                    ct="brain tumor occupational exposure"),
    "v167/c1": dict(gloss="stage four metastatic cancer reversed in forty days with a diet and herbal remedy",
                    q="(neoplasm metastasis OR advanced cancer) AND (diet therapy OR ketogenic diet OR herbal medicine OR fasting)",
                    epmc='("metastatic cancer" OR "stage IV" OR "advanced cancer") AND (diet OR "ketogenic diet" OR "herbal") AND (remission OR cure OR regression)',
                    ct="(ketogenic diet OR fasting) AND metastatic cancer"),
    "v167/c2": dict(gloss="if you give cancer no sugar and no carbohydrates the cancer cells starve and die",
                    q='(ketogenic diet OR carbohydrate-restricted diet OR "dietary sugars" OR fasting) AND (neoplasms OR cancer)',
                    epmc='("ketogenic diet" OR "carbohydrate restriction" OR "sugar-free" OR "low-carbohydrate") AND (cancer OR tumor) AND (survival OR "tumor growth") AND (patients OR trial)',
                    ct="(ketogenic diet OR low carbohydrate) AND cancer"),
    "v167/c3": dict(gloss="neem leaf, raw turmeric, lemon and apple cider vinegar paste cures cancer",
                    q="(neem OR Azadirachta OR turmeric OR curcumin OR vinegar) AND (neoplasms OR cancer) AND (treatment OR therapy)",
                    epmc='(neem OR "Azadirachta indica" OR "apple cider vinegar") AND (cancer OR tumor) AND (patients OR trial OR clinical)',
                    ct="(neem OR curcumin OR turmeric) AND cancer"),
    "v181/c1": dict(gloss="we crave salty foods when stressed or anxious because the brain has sodium sensors",
                    q="(sodium chloride, dietary OR salt) AND (anxiety OR stress, psychological) AND (appetite OR craving)",
                    epmc='(salt OR sodium) AND (craving OR appetite OR preference) AND (anxiety OR stress) AND (human OR humans OR participants)',
                    ct="salt AND anxiety"),
    "v181/c2": dict(gloss="a pinch of salt under the tongue with water relieves anxiety",
                    q="(sodium chloride OR salt OR saline) AND (anxiety OR panic) AND (treatment OR intervention)",
                    epmc='(salt OR "sodium chloride" OR "hypertonic saline") AND (anxiety OR panic) AND (randomized OR trial OR intervention)',
                    ct="(salt OR sodium chloride) AND anxiety"),
    "v181/c3": dict(gloss="magnesium is important for the nervous system and anxiety",
                    q="(magnesium) AND (anxiety OR stress, psychological OR nervous system)",
                    epmc='magnesium AND (anxiety OR stress) AND (supplementation OR supplement) AND (randomized OR "systematic review")',
                    ct="magnesium AND anxiety"),
    "v181/c4": dict(gloss="valerian, skullcap, passionflower and lemon balm together treat chronic anxiety",
                    q="(valerian OR Valeriana OR Passiflora OR passionflower OR Scutellaria OR skullcap OR Melissa officinalis OR lemon balm) AND (anxiety)",
                    epmc='(valerian OR Passiflora OR passionflower OR Scutellaria OR "Melissa officinalis" OR "lemon balm") AND anxiety AND (combination OR randomized OR "systematic review")',
                    ct="(valerian OR passiflora OR scutellaria OR melissa) AND anxiety"),
}


# ------------------------------------------------------------------ inputs

def scoped_videos(agreement_md: Path) -> list[str]:
    """Videos whose source label implies MISINFO and whose derived label is CANNOT_RECOGNIZE
    (the 'Every video' table of external_agreement.md)."""
    vids = []
    for line in agreement_md.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 7 and re.fullmatch(r"v\d+", cells[0]):
            implied, derived = cells[-4], cells[-3]
            if implied == "MISINFO" and derived == "CANNOT_RECOGNIZE":
                vids.append(cells[0])
    return vids


def load_claims(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ http

class Http:
    def __init__(self) -> None:
        self.client = httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=False)
        self.ncbi = RateLimiter(2.5)
        self.other = RateLimiter(4.0)

    def get(self, url: str, params: dict, limiter: RateLimiter, attempts: int = 4) -> httpx.Response:
        last: Optional[Exception] = None
        for i in range(attempts):
            limiter.acquire()
            try:
                resp = self.client.get(url, params=params)
            except httpx.HTTPError as exc:  # proxy refusal, DNS, timeout
                last = exc
                if isinstance(exc, (httpx.ProxyError, httpx.ConnectError)):
                    raise  # unreachable: do not retry around a network block
                time.sleep(min(8.0, 0.5 * 2 ** i))
                continue
            if resp.status_code in RETRY and i + 1 < attempts:
                time.sleep(min(8.0, 0.5 * 2 ** i))
                continue
            resp.raise_for_status()
            return resp
        raise last or RuntimeError("unreachable")


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


# ------------------------------------------------------------------ sources

def search_cochrane(http: Http, q: str, abstracts_dir: Optional[Path]) -> dict[str, Any]:
    term = f"({q}) AND {COCHRANE}"
    out: dict[str, Any] = {"query": term, "hits": []}
    try:
        r = http.get(f"{EUTILS}/esearch.fcgi", {"db": "pubmed", "term": term, "retmax": MAX_HITS,
                                                 "sort": "relevance", "retmode": "json", "tool": TOOL}, http.ncbi)
        res = r.json()["esearchresult"]
        out["count"] = int(res.get("count", 0))
        ids = res.get("idlist", [])
        if ids:
            s = http.get(f"{EUTILS}/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json",
                                                      "tool": TOOL}, http.ncbi).json()["result"]
            for pmid in ids:
                d = s.get(pmid, {})
                out["hits"].append({"id": f"PMID:{pmid}", "title": d.get("title", "")[:200],
                                    "year": (d.get("pubdate") or "")[:4],
                                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"})
            if abstracts_dir is not None:
                x = http.get(f"{EUTILS}/efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract",
                                                        "retmode": "text", "tool": TOOL}, http.ncbi)
                abstracts_dir.mkdir(parents=True, exist_ok=True)
                (abstracts_dir / f"cochrane_{'_'.join(ids)}.txt").write_text(x.text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        out["error"] = _err(exc)
    return out


def search_epmc(http: Http, q: str) -> dict[str, Any]:
    # Europe PMC searches abstracts and open full text by default; SRC:PPR rows are preprints.
    # Default order is relevance; an explicit sort=RELEVANCE answered 503 (2026-11-23).
    out: dict[str, Any] = {"query": q, "hits": []}
    try:
        r = http.get(EPMC, {"query": q, "format": "json", "pageSize": MAX_HITS, "resultType": "lite"}, http.other).json()
        out["count"] = int(r.get("hitCount", 0))
        for d in (r.get("resultList") or {}).get("result", []):
            ident = f"PMID:{d['pmid']}" if d.get("pmid") else f"{d.get('source')}:{d.get('id')}"
            out["hits"].append({"id": ident, "title": d.get("title", "")[:200], "year": d.get("pubYear", ""),
                                "source": d.get("source", ""),
                                "url": f"https://europepmc.org/article/{d.get('source')}/{d.get('id')}"})
    except Exception as exc:  # noqa: BLE001
        out["error"] = _err(exc)
    return out


def search_ctgov(http: Http, q: str) -> dict[str, Any]:
    out: dict[str, Any] = {"query": q, "hits": []}
    try:
        r = http.get(CTGOV, {"query.term": q, "pageSize": MAX_HITS, "countTotal": "true",
                             "fields": "NCTId,BriefTitle,OverallStatus,HasResults"}, http.other).json()
        out["count"] = int(r.get("totalCount", 0))
        for st in r.get("studies", []):
            ps = st.get("protocolSection", {})
            nct = ps.get("identificationModule", {}).get("nctId", "")
            out["hits"].append({"id": nct, "title": ps.get("identificationModule", {}).get("briefTitle", "")[:200],
                                "status": ps.get("statusModule", {}).get("overallStatus", ""),
                                "has_results": st.get("hasResults", False),
                                "url": f"https://clinicaltrials.gov/study/{nct}"})
    except Exception as exc:  # noqa: BLE001
        out["error"] = _err(exc)
    return out


def search_references(searcher: Any, gloss: str) -> dict[str, Any]:
    out: dict[str, Any] = {"query": gloss, "hits": []}
    try:
        res = searcher.search(gloss)
        out["candidates"] = list(res.candidates)
        out["errors"] = list(res.errors)
        for rec in res.records:
            out["hits"].append({"id": rec.evidence_id, "title": rec.title, "publisher": rec.publisher,
                                "url": rec.source_url, "passage": (rec.abstract or "")[:200]})
    except Exception as exc:  # noqa: BLE001
        out["error"] = _err(exc)
    return out


def reachability(http: Http) -> dict[str, str]:
    probes = {
        "europe_pmc": (EPMC, {"query": "ginger", "format": "json", "pageSize": 1}),
        "clinicaltrials_gov": (CTGOV, {"query.term": "ginger", "pageSize": 1}),
        "pubmed_eutils": (f"{EUTILS}/einfo.fcgi", {"retmode": "json", "tool": TOOL}),
    }
    status = {}
    for name, (url, params) in probes.items():
        try:
            http.get(url, params, http.ncbi if "eutils" in url else http.other, attempts=1)
            status[name] = "reachable"
        except Exception as exc:  # noqa: BLE001
            status[name] = "unreachable: " + _err(exc)
    return status


def cmd_search(args: argparse.Namespace) -> int:
    from app.core.retrieval.references.config import load_reference_config
    from app.core.retrieval.references.search import ReferenceSearcher

    vids = scoped_videos(Path(args.agreement))
    claims = [c for c in load_claims(Path(args.claims))
              if c["video_id"] in vids and c["claim_verdict"] == "INSUFFICIENT_EVIDENCE"]
    missing = [f"{c['video_id']}/{c['claim_id']}" for c in claims if f"{c['video_id']}/{c['claim_id']}" not in PLAN]
    if missing:
        print("no search plan for:", ", ".join(missing), file=sys.stderr)
        return 1
    http = Http()
    status = reachability(http)
    print(json.dumps(status, indent=1))
    searcher = ReferenceSearcher(load_reference_config(), rate_limiter=http.ncbi)
    abstracts = Path(args.abstracts_dir) if args.abstracts_dir else None
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "videos_in_scope": vids, "reachability": status, "claims": {}}
    for c in claims:
        key = f"{c['video_id']}/{c['claim_id']}"
        p = PLAN[key]
        row: dict[str, Any] = {"stance": c["speaker_stance"], "claim_kind": c["claim_kind"]}
        row["cochrane"] = search_cochrane(http, p["q"], abstracts)
        row["europe_pmc"] = (search_epmc(http, p["epmc"]) if status["europe_pmc"] == "reachable"
                             else {"query": p["epmc"], "hits": [], "error": status["europe_pmc"]})
        row["clinicaltrials_gov"] = (search_ctgov(http, p["ct"]) if status["clinicaltrials_gov"] == "reachable"
                                     else {"query": p["ct"], "hits": [], "error": status["clinicaltrials_gov"]})
        row["references"] = search_references(searcher, p["gloss"])
        out["claims"][key] = row
        print(key, "cochrane", row["cochrane"].get("count", row["cochrane"].get("error")),
              "| refs", len(row["references"]["hits"]), flush=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    # Compact: ids, titles (capped) and queries only, so the committed file stays small.
    RESULTS.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("wrote", RESULTS)
    return 0


# ------------------------------------------------------------------ report

def _md(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def _short(s: str, n: int = 90) -> str:
    s = _md(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def cmd_report(args: argparse.Namespace) -> int:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    judg = json.loads(JUDGMENTS.read_text(encoding="utf-8"))
    vids = results["videos_in_scope"]
    all_claims = [c for c in load_claims(Path(args.claims)) if c["video_id"] in vids]
    by_video: dict[str, list[dict[str, str]]] = {v: [] for v in vids}
    for c in all_claims:
        by_video[c["video_id"]].append(c)

    def new_verdict(c: dict[str, str]) -> str:
        key = f"{c['video_id']}/{c['claim_id']}"
        j = judg["claims"].get(key)
        return j["verdict"] if j else c["claim_verdict"]

    claim_keys = list(results["claims"])
    changed = {k: j for k, j in judg["claims"].items() if j["verdict"] != "INSUFFICIENT_EVIDENCE"}
    decidable = {k: j for k, j in changed.items() if j["verdict"] in ("SUPPORTED", "CONTRADICTED")}
    with_hits = {s: sum(1 for k in claim_keys if results["claims"][k][s]["hits"])
                 for s in ("cochrane", "europe_pmc", "clinicaltrials_gov", "references")}

    video_rows = []
    for v in vids:
        old = judge_label((c["speaker_stance"], c["claim_verdict"]) for c in by_video[v])
        new = judge_label((c["speaker_stance"], new_verdict(c)) for c in by_video[v])
        n_ins = sum(1 for c in by_video[v] if c["claim_verdict"] == "INSUFFICIENT_EVIDENCE")
        video_rows.append((v, len(by_video[v]), n_ins, old, new))
    became = [r for r in video_rows if r[4] != "CANNOT_RECOGNIZE"]

    L: list[str] = []
    a = L.append
    a("# T25: Do more evidence sources resolve the 'source says false, evidence is silent' videos?")
    a("")
    a(f"Report only (design §6, §7, §14; automation/BUILD_QUEUE.md T25). Generated by "
      f"`backend/scripts/t25_extra_sources.py report` from `T25_extra_sources_results.json` "
      f"(searched {results['generated_at']}) and `T25_judgments.json` (verdicts judged by hand under the "
      f"unchanged §7 rules, as the labelling was). No model API was called. No fact-check database was "
      f"searched. No accuracy against the golden labels is reported.")
    a("")
    a("## Headline")
    a("")
    a(f"- Videos in scope (source label implies MISINFO, derived label CANNOT_RECOGNIZE): **{len(vids)}**. "
      f"Of these, **{sum(1 for r in video_rows if r[2])}** have at least one INSUFFICIENT_EVIDENCE claim; the other "
      f"{sum(1 for r in video_rows if not r[2])} have no claim, or only NOT_VERIFIABLE/MIXED claims, so no evidence "
      f"source can change them.")
    a(f"- INSUFFICIENT_EVIDENCE claims searched: **{len(claim_keys)}**.")
    a(f"- Claims whose verdict would change under §7: **{len(changed)}** "
      f"({len(decidable)} to SUPPORTED or CONTRADICTED: "
      f"{sum(1 for j in decidable.values() if j['verdict'] == 'SUPPORTED')} SUPPORTED, "
      f"{sum(1 for j in decidable.values() if j['verdict'] == 'CONTRADICTED')} CONTRADICTED"
      + (f"; {len(changed) - len(decidable)} to MIXED" if len(changed) > len(decidable) else "") + ").")
    a(f"- Videos whose §9 label would leave CANNOT_RECOGNIZE: **{len(became)}** of {len(vids)}"
      + (" (" + ", ".join(f"{r[0]} → {r[4]}" for r in became) + ")" if became else "") + ".")
    a("")
    a("### Sources")
    a("")
    a("| source | status in this run | claims with any hit | claims it resolved |")
    a("|---|---|---:|---:|")
    names = {"cochrane": "Cochrane reviews (PubMed E-utilities, \"Cochrane Database Syst Rev\"[journal])",
             "europe_pmc": "Europe PMC REST API (www.ebi.ac.uk)",
             "clinicaltrials_gov": "ClinicalTrials.gov API v2",
             "references": "Reference allow-list (WHO/NHS/FDA/EFSA live, CDC stored snapshots, NCBI Bookshelf)"}
    reach = results["reachability"]
    status_of = {"cochrane": reach.get("pubmed_eutils", ""), "europe_pmc": reach.get("europe_pmc", ""),
                 "clinicaltrials_gov": reach.get("clinicaltrials_gov", ""),
                 "references": ("reachable, no fetch errors" if not any(
                     results["claims"][k]["references"].get("errors") or results["claims"][k]["references"].get("error")
                     for k in results["claims"]) else "reachable, with fetch errors (see results file)")}
    for s, n in names.items():
        resolved = sum(1 for j in changed.values() if s in j.get("resolved_by", []))
        a(f"| {n} | {_md(status_of[s])} | {with_hits[s]} | {resolved} |")
    a("")
    for para in judg.get("notes", []):
        a(para)
        a("")
    a("## Per claim")
    a("")
    a("Hits are the top results each source returned (at most 5; Cochrane ids are PMIDs). "
      "\"Relevant\" lists only the hits that address the claim; the rest were off-topic. "
      "Verdict is the §7 verdict with the extra sources added to what the labelling already had.")
    a("")
    a("| claim | stance | claim (as labelled) | Cochrane hits | allow-list hits | relevant evidence found | verdict now | why |")
    a("|---|---|---|---|---|---|---|---|")
    text = {f"{c['video_id']}/{c['claim_id']}": c["claim_text"] for c in all_claims}
    for k in claim_keys:
        r = results["claims"][k]
        j = judg["claims"].get(k, {})
        coch = r["cochrane"]
        ch = (f"{coch.get('count', 0)} (" + ", ".join(h["id"].split(":")[1] for h in coch["hits"]) + ")"
              if coch["hits"] else ("error" if coch.get("error") else "0"))
        refs = r["references"]
        rh = ", ".join(sorted({h["publisher"] or "?" for h in refs["hits"]})) or "none"
        a(f"| {k} | {r['stance']} | {_short(text.get(k, ''), 80)} | {ch} | {_md(rh)} | "
          f"{_md(j.get('relevant', '—'))} | **{j.get('verdict', 'INSUFFICIENT_EVIDENCE')}** | {_md(j.get('why', ''))} |")
    a("")
    down = [names[s] for s in ("europe_pmc", "clinicaltrials_gov") if not status_of[s].startswith("reachable")]
    if down:
        a("Not searched because unreachable during the run (queries are still in the script and results file): "
          + "; ".join(down) + ".")
        a("")
    a("Europe PMC and ClinicalTrials.gov hits for every claim, with their queries, are in "
      "`T25_extra_sources_results.json`; the table shows Cochrane and the allow-list, and names any hit from "
      "any source that bears on the claim under \"relevant evidence found\".")
    a("")
    a("## Per video")
    a("")
    a("| video | claims | INSUFFICIENT claims | §9 label before | §9 label with the extra sources |")
    a("|---|---:|---:|---|---|")
    for v, n, ni, old, new in video_rows:
        a(f"| {v} | {n} | {ni} | {old} | {new}{' **(changed)**' if new != old else ''} |")
    a("")
    a("## Left for a person")
    a("")
    for para in judg.get("for_a_person", []):
        a(f"- {para}")
    a("")
    REPORT.write_text("\n".join(L), encoding="utf-8")
    print("wrote", REPORT)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("search", "report"):
        p = sub.add_parser(name)
        p.add_argument("--claims", required=True, help="claims.csv from data/golden-label-set")
        p.add_argument("--agreement", required=True, help="external_agreement.md from data/golden-label-set")
        if name == "search":
            p.add_argument("--abstracts-dir", help="save Cochrane abstracts here for reading (not committed)")
    args = ap.parse_args(argv)
    return cmd_search(args) if args.cmd == "search" else cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
