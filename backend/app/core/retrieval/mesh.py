"""Rule-based mapping from plain health terms to MeSH headings (§6 step 2).

A curated lexicon of the terms that come up in health-misinformation videos. Each entry
gives the MeSH heading (``[MeSH Terms]``), free-text synonyms searched in title and
abstract (``[tiab]``), and a broader heading used when a search comes back empty
(§6 "When nothing comes back").

Why a lexicon and not an online lookup: it is deterministic, testable offline and
reviewable. PubMed's own Automatic Term Mapping still applies to the free-text keyword
query the planner falls back on, so a term missing from the lexicon is not lost. Grow
the lexicon from the evaluation set (§14) rather than by guesswork; ``mesh=None`` marks
terms with no MeSH heading we are sure of, which are searched as free text only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from app.core.retrieval.schemas import Concept

Kind = Literal["condition", "intervention", "population", "outcome"]


@dataclass(frozen=True)
class LexiconEntry:
    key: str
    kind: Kind
    phrases: tuple[str, ...]  # surface forms matched in the claim (lower case)
    mesh: Optional[str] = None
    synonyms: tuple[str, ...] = ()  # searched as [tiab]; defaults to phrases
    parent_mesh: Optional[str] = None

    def concept(self, matched: str) -> Concept:
        return Concept(
            key=self.key,
            label=self.phrases[0],
            kind=self.kind,
            mesh=self.mesh,
            synonyms=self.synonyms or self.phrases,
            parent_mesh=self.parent_mesh,
            matched_text=matched,
        )


def _e(key, kind, phrases, mesh=None, synonyms=(), parent=None) -> LexiconEntry:
    return LexiconEntry(key, kind, tuple(phrases), mesh, tuple(synonyms), parent)


LEXICON: tuple[LexiconEntry, ...] = (
    # ---- conditions (usually the outcome side of a claim)
    _e("influenza", "condition", ["flu", "influenza", "the flu"], "Influenza, Human",
       ["influenza", "flu"], "Respiratory Tract Infections"),
    _e("common_cold", "condition", ["common cold", "colds", "a cold", "the cold"], "Common Cold",
       ["common cold"], "Respiratory Tract Infections"),
    _e("covid19", "condition", ["covid-19", "covid 19", "covid", "coronavirus", "sars-cov-2"],
       "COVID-19", ["covid-19", "sars-cov-2"], "Coronavirus Infections"),
    _e("cancer", "condition", ["cancer", "cancers", "tumor", "tumors", "tumour", "tumours"],
       "Neoplasms", ["cancer", "neoplasm", "tumor"]),
    _e("autism", "condition", ["autism", "autistic", "asd"], "Autism Spectrum Disorder",
       ["autism"], "Neurodevelopmental Disorders"),
    _e("diabetes", "condition", ["type 2 diabetes", "diabetes", "diabetic", "blood sugar"],
       "Diabetes Mellitus", ["diabetes"], "Endocrine System Diseases"),
    _e("hypertension", "condition", ["high blood pressure", "hypertension", "blood pressure"],
       "Hypertension", ["hypertension", "blood pressure"], "Cardiovascular Diseases"),
    _e("heart_disease", "condition", ["heart disease", "heart attack", "heart attacks",
       "cardiovascular disease"], "Cardiovascular Diseases", ["cardiovascular disease", "heart disease"]),
    _e("obesity", "condition", ["obesity", "obese", "overweight"], "Obesity",
       ["obesity"], "Nutritional and Metabolic Diseases"),
    _e("weight_loss", "outcome", ["weight loss", "lose weight", "losing weight", "fat loss",
       "burn fat", "burns fat"], "Weight Loss", ["weight loss"], "Body Weight"),
    _e("immunity", "outcome", ["immune system", "immunity", "immune"], "Immune System",
       ["immune system", "immunity"]),
    _e("measles", "condition", ["measles"], "Measles", ["measles"], "Morbillivirus Infections"),
    _e("hiv", "condition", ["hiv", "aids"], "HIV Infections", ["hiv"], "Virus Diseases"),
    _e("malaria", "condition", ["malaria"], "Malaria", ["malaria"], "Parasitic Diseases"),
    _e("depression", "condition", ["depression", "depressed"], "Depression",
       ["depression"], "Mental Disorders"),
    _e("anxiety", "condition", ["anxiety"], "Anxiety", ["anxiety"], "Mental Disorders"),
    _e("dementia", "condition", ["alzheimer's", "alzheimers", "alzheimer", "dementia"],
       "Alzheimer Disease", ["alzheimer", "dementia"], "Dementia"),
    _e("asthma", "condition", ["asthma"], "Asthma", ["asthma"], "Respiratory Tract Diseases"),
    _e("infertility", "condition", ["infertility", "infertile", "sterility"], "Infertility",
       ["infertility"]),
    _e("intelligence", "outcome", ["iq", "intelligence", "cognitive development"], "Intelligence",
       ["intelligence", "iq"], "Cognition"),
    _e("infection", "condition", ["infection", "infections", "virus", "viruses", "bacteria"],
       "Infections", ["infection"]),
    _e("inflammation", "condition", ["inflammation"], "Inflammation", ["inflammation"]),
    _e("toxins", "outcome", ["toxins", "detox", "detoxes", "detoxify"], None,
       ["detoxification", "toxins"]),
    # ---- interventions and exposures
    _e("mmr_vaccine", "intervention", ["mmr vaccine", "mmr"], "Measles-Mumps-Rubella Vaccine",
       ["mmr vaccine"], "Vaccines"),
    _e("covid_vaccine", "intervention", ["covid vaccine", "covid vaccines", "covid-19 vaccine",
       "covid-19 vaccines", "mrna vaccine", "mrna vaccines"], "COVID-19 Vaccines",
       ["covid-19 vaccine"], "Vaccines"),
    _e("hpv_vaccine", "intervention", ["hpv vaccine", "gardasil"], "Papillomavirus Vaccines",
       ["hpv vaccine"], "Vaccines"),
    _e("flu_vaccine", "intervention", ["flu shot", "flu shots", "flu vaccine", "influenza vaccine"],
       "Influenza Vaccines", ["influenza vaccine"], "Vaccines"),
    _e("vaccines", "intervention", ["vaccines", "vaccine", "vaccination", "vaccinations",
       "jab", "jabs"], "Vaccines", ["vaccine", "vaccination"], "Biological Products"),
    _e("garlic", "intervention", ["garlic"], "Garlic", ["garlic", "allicin"], "Plant Preparations"),
    _e("vitamin_c", "intervention", ["vitamin c", "ascorbic acid"], "Ascorbic Acid",
       ["vitamin c", "ascorbic acid"], "Vitamins"),
    _e("vitamin_d", "intervention", ["vitamin d", "vitamin d3"], "Vitamin D", ["vitamin d"], "Vitamins"),
    _e("zinc", "intervention", ["zinc"], "Zinc", ["zinc"]),
    _e("ivermectin", "intervention", ["ivermectin"], "Ivermectin", ["ivermectin"], "Antiparasitic Agents"),
    _e("hydroxychloroquine", "intervention", ["hydroxychloroquine", "hcq"], "Hydroxychloroquine",
       ["hydroxychloroquine"], "Antimalarials"),
    _e("hot_drinks", "intervention", ["hot water", "hot drinks", "hot drink", "warm water",
       "hot tea", "hot beverages"], None, ["hot drinks", "hot beverages", "hot water"], "Beverages"),
    _e("lemon", "intervention", ["lemon water", "lemon", "lemons"], None, ["lemon", "citrus"],
       "Citrus"),
    _e("honey", "intervention", ["honey"], "Honey", ["honey"]),
    _e("turmeric", "intervention", ["turmeric", "curcumin"], "Curcumin", ["curcumin", "turmeric"],
       "Plant Preparations"),
    _e("ginger", "intervention", ["ginger"], "Zingiber officinale", ["ginger"], "Plant Preparations"),
    _e("acv", "intervention", ["apple cider vinegar", "vinegar"], "Acetic Acid",
       ["apple cider vinegar", "vinegar"]),
    _e("fasting", "intervention", ["intermittent fasting", "fasting"], "Fasting", ["fasting"]),
    _e("keto", "intervention", ["keto diet", "ketogenic diet", "keto"], "Diet, Ketogenic",
       ["ketogenic diet"], "Diet"),
    _e("sugar", "intervention", ["sugar", "sugars"], "Dietary Sugars", ["sugar"]),
    _e("seed_oils", "intervention", ["seed oils", "seed oil", "vegetable oils"], "Plant Oils",
       ["seed oils", "vegetable oils"], "Dietary Fats"),
    _e("fluoride", "intervention", ["fluoride", "fluoridation", "fluoridated water"], "Fluorides",
       ["fluoride"]),
    _e("5g", "intervention", ["5g", "cell towers", "radiation from phones"], "Electromagnetic Fields",
       ["5g", "radiofrequency"]),
    _e("bleach", "intervention", ["bleach", "chlorine dioxide", "mms"], None,
       ["chlorine dioxide", "sodium hypochlorite"]),
    _e("colloidal_silver", "intervention", ["colloidal silver"], None, ["colloidal silver"]),
    _e("essential_oils", "intervention", ["essential oils", "essential oil"], "Oils, Volatile",
       ["essential oils"]),
    _e("alcohol", "intervention", ["alcohol", "drinking alcohol", "wine", "beer"], "Alcohol Drinking",
       ["alcohol"]),
    _e("smoking", "intervention", ["smoking", "cigarettes", "vaping", "tobacco"], "Tobacco Smoking",
       ["smoking"]),
    _e("masks", "intervention", ["face masks", "face mask", "masks", "mask"], "Masks", ["face mask"]),
    _e("antibiotics", "intervention", ["antibiotics", "antibiotic"], "Anti-Bacterial Agents",
       ["antibiotics"]),
    _e("chemotherapy", "intervention", ["chemotherapy", "chemo"], "Drug Therapy", ["chemotherapy"]),
    _e("homeopathy", "intervention", ["homeopathy", "homeopathic"], "Homeopathy", ["homeopathy"],
       "Complementary Therapies"),
    _e("probiotics", "intervention", ["probiotics", "probiotic"], "Probiotics", ["probiotics"]),
    _e("electrolytes", "intervention", ["electrolytes", "electrolyte"], "Electrolytes", ["electrolytes"]),
    _e("coffee", "intervention", ["coffee", "caffeine"], "Coffee", ["coffee"], "Beverages"),
    _e("raw_milk", "intervention", ["raw milk"], None, ["raw milk", "unpasteurized milk"], "Milk"),
    _e("sunscreen", "intervention", ["sunscreen", "sunscreens"], "Sunscreening Agents", ["sunscreen"]),
    _e("cannabis", "intervention", ["cbd", "cannabidiol"], "Cannabidiol", ["cannabidiol"], "Cannabis"),
    _e("exercise", "intervention", ["exercise", "exercising", "working out"], "Exercise", ["exercise"]),
    _e("water", "intervention", ["drinking water", "water"], "Drinking Water", ["water intake"],
       "Beverages"),
    # ---- populations
    _e("children", "population", ["children", "kids", "child"], "Child", ["children"]),
    _e("infants", "population", ["babies", "baby", "infants", "infant", "newborns"], "Infant",
       ["infants"]),
    _e("pregnancy", "population", ["pregnant women", "pregnant", "pregnancy"], "Pregnancy",
       ["pregnancy"]),
    _e("older_adults", "population", ["older adults", "elderly", "seniors", "the elderly"], "Aged",
       ["older adults", "elderly"]),
    _e("adolescents", "population", ["teenagers", "teens", "adolescents"], "Adolescent",
       ["adolescents"]),
    _e("adults", "population", ["adults"], "Adult", ["adults"]),
)


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    concept: Concept


def _compile() -> list[tuple[re.Pattern[str], LexiconEntry, str]]:
    patterns = []
    for entry in LEXICON:
        for phrase in entry.phrases:
            pat = re.compile(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])")
            patterns.append((pat, entry, phrase))
    # Longest phrase first, so "flu vaccine" wins over "flu" and "vaccine".
    patterns.sort(key=lambda p: -len(p[2]))
    return patterns


_PATTERNS = _compile()


def find_concepts(normalized_text: str) -> list[Match]:
    """All non-overlapping lexicon matches in ``normalized_text`` (lower case), in
    order of appearance. Each concept key appears once."""
    taken: list[tuple[int, int]] = []
    seen: set[str] = set()
    out: list[Match] = []
    for pat, entry, _ in _PATTERNS:
        for m in pat.finditer(normalized_text):
            s, e = m.span()
            if any(s < te and ts < e for ts, te in taken):
                continue
            taken.append((s, e))
            if entry.key in seen:
                continue
            seen.add(entry.key)
            out.append(Match(s, e, entry.concept(m.group(0))))
    return sorted(out, key=lambda m: m.start)


def map_to_mesh(text: str) -> list[Concept]:
    """Plain text → recognised concepts with MeSH headings (the §6 MCP tool's logic)."""
    from app.core.retrieval.planning import normalize_claim

    return [m.concept for m in find_concepts(normalize_claim(text))]
