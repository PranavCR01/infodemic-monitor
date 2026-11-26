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
    _e("cancer", "condition", ["cancer", "cancers", "tumor", "tumors", "tumour", "tumours", "cáncer"],
       "Neoplasms", ["cancer", "neoplasm", "tumor"]),
    _e("autism", "condition", ["autism", "autistic", "asd"], "Autism Spectrum Disorder",
       ["autism"], "Neurodevelopmental Disorders"),
    _e("diabetes", "condition", ["diabetes", "diabetic", "blood sugar", "blood-sugar", "blood sugars"],
       "Diabetes Mellitus", ["diabetes"], "Endocrine System Diseases"),
    _e("hypertension", "condition", ["high blood pressure", "hypertension", "blood pressure", "presión arterial", "hipertensión", "tension artérielle"],
       "Hypertension", ["hypertension", "blood pressure"], "Cardiovascular Diseases"),
    _e("heart_disease", "condition", ["heart disease", "heart attack", "heart attacks",
       "cardiovascular disease", "coronary disease", "ataques cardíacos", "ataque cardíaco", "infarto de miocardio", "infarto", "crise cardiaque"], "Cardiovascular Diseases", ["cardiovascular disease", "heart disease"]),
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
    _e("dementia", "condition", ["alzheimer's", "alzheimers", "alzheimer", "dementia", "demencia", "démence"],
       "Alzheimer Disease", ["alzheimer", "dementia"], "Dementia"),
    _e("asthma", "condition", ["asthma"], "Asthma", ["asthma"], "Respiratory Tract Diseases"),
    _e("infertility", "condition", ["infertility", "infertile", "sterility"], "Infertility",
       ["infertility"]),
    _e("intelligence", "outcome", ["iq", "intelligence", "cognitive development"], "Intelligence",
       ["intelligence", "iq"], "Cognition"),
    _e("infection", "condition", ["infection", "infections", "virus", "viruses", "bacteria"],
       "Infections", ["infection"]),
    _e("inflammation", "condition", ["inflammation", "inflamación"], "Inflammation", ["inflammation"]),
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
       "jab", "jabs", "booster", "vacuna", "vacunas", "vacunados", "vaccin", "vaccins", "vacina"], "Vaccines", ["vaccine", "vaccination"], "Biological Products"),
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
    _e("sugar", "intervention", ["sugar", "sugars", "azúcar", "sucre"], "Dietary Sugars", ["sugar"]),
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
    _e("water", "intervention", ["drinking water", "tap water", "water"], "Drinking Water", ["water intake"],
       "Beverages"),
    # ---- T50 additions (§6 step 2). From production job 5cc07f48 (vitamin K video) and
    # the concepts the golden **tune** split's claims name that the lexicon missed
    # (claims searched as conversational keywords). Spanish and French surface forms
    # are matched too; the [tiab] synonyms stay English, the language PubMed indexes.
    _e("vkdb", "condition", ["vitamin k deficiency bleeding", "late vitamin k deficiency bleeding",
       "vkdb", "hemorrhagic disease of the newborn", "haemorrhagic disease of the newborn"],
       "Vitamin K Deficiency Bleeding", ["vitamin k deficiency bleeding", "VKDB"], "Vitamin K Deficiency"),
    _e("vitamin_k", "intervention", ["vitamin k", "vitamin k1", "vitamin k2", "phytonadione",
       "phylloquinone", "menaquinone", "vitamina k", "vitamine k"], "Vitamin K",
       ["vitamin k", "phytonadione", "phylloquinone"], "Vitamins"),
    _e("vitamin_b12", "intervention", ["vitamin b12", "b12", "vitamina b12", "cobalamin"], "Vitamin B 12",
       ["vitamin b12"], "Vitamins"),
    _e("vitamin_e", "intervention", ["vitamin e", "vitamina e", "tocopherol"], "Vitamin E", ["vitamin e"],
       "Vitamins"),
    _e("omega3", "intervention", ["omega 3", "omega-3", "fish oil"], "Fatty Acids, Omega-3",
       ["omega-3", "fish oil"], "Dietary Fats"),
    _e("hepatitis_b", "condition", ["hepatitis b", "hep b", "hbv"], "Hepatitis B", ["hepatitis b"],
       "Hepatitis"),
    _e("diabetes_t1", "condition", ["type 1 diabetes", "diabetes tipo 1", "diabète de type 1"],
       "Diabetes Mellitus, Type 1", ["type 1 diabetes"], "Diabetes Mellitus"),
    _e("diabetes_t2", "condition", ["type 2 diabetes", "diabetes tipo 2", "diabète de type 2"],
       "Diabetes Mellitus, Type 2", ["type 2 diabetes"], "Diabetes Mellitus"),
    _e("breast_milk", "intervention", ["breast milk", "breastmilk", "human milk", "breastfeeding",
       "leche materna", "lait maternel"], "Milk, Human", ["breast milk", "human milk"], "Milk"),
    _e("injection", "intervention", ["the shot", "shot", "injection", "intramuscular", "inyección"],
       "Injections, Intramuscular", ["injection", "intramuscular"]),
    _e("oral_drops", "intervention", ["oral drops", "oral dose", "by mouth", "oral"],
       "Administration, Oral", ["oral"]),
    _e("coagulation", "outcome", ["blood to clot", "blood clotting", "clotting", "clot", "coagulation"],
       "Blood Coagulation", ["coagulation", "clotting"]),
    _e("brain_bleed", "condition", ["bleed into the brain", "bleeding in the brain", "brain bleed",
       "brain bleeding", "intracranial hemorrhage", "intracranial haemorrhage"],
       "Intracranial Hemorrhages", ["intracranial hemorrhage"], "Hemorrhage"),
    _e("bleeding", "condition", ["bleeding", "bleed", "bleeds", "hemorrhage", "haemorrhage",
       "sangrado", "hémorragie"], "Hemorrhage", ["bleeding", "hemorrhage"]),
    _e("osteoporosis", "condition", ["osteoporosis", "ostéoporose"], "Osteoporosis", ["osteoporosis"],
       "Bone Diseases, Metabolic"),
    _e("bone_health", "outcome", ["bone density", "bone health", "bones", "bone"], "Bone Density",
       ["bone mineral density", "bone health"]),
    _e("calcium", "intervention", ["calcium", "calcio"], "Calcium", ["calcium"]),
    _e("magnesium", "intervention", ["magnesium", "magnesio"], "Magnesium", ["magnesium"]),
    _e("almonds", "intervention", ["almonds", "almond", "almendras"], "Prunus dulcis", ["almond"], "Nuts"),
    _e("eggs", "intervention", ["eggs", "egg", "huevos", "œufs"], "Eggs", ["egg", "eggs"]),
    _e("cholesterol", "outcome", ["hdl", "ldl", "cholesterol", "colesterol", "cholestérol"], "Cholesterol",
       ["cholesterol"], "Lipids"),
    _e("choline", "intervention", ["choline"], "Choline", ["choline"]),
    _e("fatty_liver", "condition", ["fatty liver", "hígado graso", "foie gras"], "Fatty Liver",
       ["fatty liver"], "Liver Diseases"),
    _e("gluten", "intervention", ["gluten"], "Glutens", ["gluten"]),
    _e("glyphosate", "intervention", ["glyphosate", "roundup"], "Glyphosate", ["glyphosate"], "Herbicides"),
    _e("glucose", "intervention", ["glucose", "glucosa"], "Glucose", ["glucose"]),
    _e("salt", "intervention", ["salt", "sodium", "la sal", "sal", "sel"], "Sodium Chloride, Dietary",
       ["salt intake", "sodium intake"]),
    _e("marijuana", "intervention", ["smoking marijuana", "smoke marijuana", "marijuana", "cannabis",
       "weed"], "Marijuana Smoking", ["marijuana", "cannabis"], "Cannabis"),
    _e("statins", "intervention", ["statins", "statin", "estatinas", "statines"],
       "Hydroxymethylglutaryl-CoA Reductase Inhibitors", ["statin"]),
    _e("coq10", "intervention", ["coenzyme q10", "coenzima q10", "coq10", "ubiquinone"], "Ubiquinone",
       ["coenzyme q10"]),
    _e("stroke", "condition", ["stroke", "strokes", "derrame cerebral", "derrames cerebrales", "avc"],
       "Stroke", ["stroke"], "Cerebrovascular Disorders"),
    _e("heart_failure", "condition", ["heart failure", "insuficiencia cardiaca", "insuficiencia cardíaca"],
       "Heart Failure", ["heart failure"], "Cardiovascular Diseases"),
    _e("testosterone", "outcome", ["testosterone", "testosterona"], "Testosterone", ["testosterone"]),
    _e("atrazine", "intervention", ["atrazine"], "Atrazine", ["atrazine"], "Herbicides"),
    _e("miscarriage", "condition", ["miscarriage", "miscarriages", "aborto espontáneo", "fausse couche"],
       "Abortion, Spontaneous", ["miscarriage"], "Pregnancy Complications"),
    _e("antioxidants", "intervention", ["antioxidants", "antioxidant", "antioxidantes"], "Antioxidants",
       ["antioxidant"]),
    _e("fiber", "intervention", ["dietary fiber", "fiber", "fibre", "fibra"], "Dietary Fiber", ["fiber"]),
    _e("saturated_fat", "intervention", ["saturated fats", "saturated fat", "grasas saturadas"], None,
       ["saturated fat", "saturated fatty acids"], "Dietary Fats"),
    _e("butter", "intervention", ["butter", "mantequilla", "beurre"], "Butter", ["butter"], "Dietary Fats"),
    _e("carbohydrates", "intervention", ["refined carbohydrates", "carbohydrates", "carbs", "carbohidratos",
       "carbohidratos refinados", "glucides"], "Dietary Carbohydrates", ["carbohydrate"]),
    _e("seawater", "intervention", ["seawater", "sea water", "ocean water", "agua de mar", "eau de mer"],
       "Seawater", ["seawater", "sea water"]),
    _e("heavy_metals", "intervention", ["heavy metals", "metales pesados", "métaux lourds"], "Metals, Heavy",
       ["heavy metals"]),
    _e("soap", "intervention", ["soap", "soaps", "savon", "jabón"], "Soaps", ["soap"]),
    _e("skin_cancer", "condition", ["skin cancer", "melanoma", "cancer de la peau", "cáncer de piel"],
       "Skin Neoplasms", ["skin cancer", "melanoma"], "Neoplasms"),
    _e("brain_tumor", "condition", ["brain tumors", "brain tumor", "brain tumours", "meningiomas",
       "meningioma"], "Brain Neoplasms", ["brain tumor", "meningioma"], "Neoplasms"),
    _e("thyroid_tumor", "condition", ["thyroid tumor", "tumor en la glándula tiroides", "thyroid cancer"],
       "Thyroid Neoplasms", ["thyroid cancer", "thyroid tumor"], "Neoplasms"),
    _e("macular_degeneration", "condition", ["macular degeneration", "dégénérescence maculaire"],
       "Macular Degeneration", ["macular degeneration"], "Eye Diseases"),
    _e("sea_moss", "intervention", ["irish sea moss", "irish moss", "sea moss", "seamoss"], "Chondrus",
       ["irish moss", "sea moss", "chondrus crispus"], "Seaweed"),
    _e("burdock", "intervention", ["burdock root", "burdock"], "Arctium", ["burdock", "arctium"],
       "Plant Preparations"),
    _e("moringa", "intervention", ["moringa", "moranga"], "Moringa oleifera", ["moringa"],
       "Plant Preparations"),
    _e("thyroid", "condition", ["thyroid issues", "thyroid problems", "thyroid disease", "thyroid"],
       "Thyroid Diseases", ["thyroid"]),
    _e("kidney_stones", "condition", ["kidney stones", "kidney & gallbladder stones", "kidney stone"],
       "Kidney Calculi", ["kidney stones"], "Urolithiasis"),
    _e("gallstones", "condition", ["gallbladder stones", "gallstones"], "Gallstones", ["gallstones"]),
    _e("eczema", "condition", ["eczema", "eczéma"], "Eczema", ["eczema"], "Skin Diseases"),
    _e("ionizing_radiation", "intervention", ["ionizing radiation", "radiation"], "Radiation, Ionizing",
       ["ionizing radiation"]),
    _e("benzene", "intervention", ["benzene"], "Benzene", ["benzene"]),
    _e("benzoyl_peroxide", "intervention", ["benzoyl peroxide"], "Benzoyl Peroxide", ["benzoyl peroxide"]),
    _e("dental_caries", "condition", ["cavities", "tooth decay", "dental caries", "caries"], "Dental Caries",
       ["dental caries"]),
    _e("adhd", "condition", ["adhd", "attention deficit"], "Attention Deficit Disorder with Hyperactivity",
       ["adhd"], "Neurodevelopmental Disorders"),
    _e("glaucoma", "condition", ["glaucoma"], "Glaucoma", ["glaucoma"], "Eye Diseases"),
    _e("insomnia", "condition", ["insomnia", "insomnio"], "Sleep Initiation and Maintenance Disorders",
       ["insomnia"]),
    _e("cocaine", "intervention", ["cocaine"], "Cocaine", ["cocaine"]),
    _e("schizophrenia", "condition", ["schizophrenia", "esquizofrenia", "schizophrénie"], "Schizophrenia",
       ["schizophrenia"], "Mental Disorders"),
    _e("panic", "condition", ["panic attack", "panic attacks", "anxiety attack"], "Panic Disorder",
       ["panic attack"], "Anxiety Disorders"),
    _e("pancreatitis", "condition", ["pancreatitis"], "Pancreatitis", ["pancreatitis"]),
    _e("seizures", "condition", ["seizures", "convulsiones", "convulsions"], "Seizures", ["seizures"]),
    _e("sex_selection", "outcome", ["tener un varón", "tener una niña", "sex of the baby", "gender of the baby"],
       "Sex Preselection", ["sex selection", "sex ratio"]),
    _e("ovulation", "outcome", ["ovulation", "ovulación"], "Ovulation", ["ovulation"]),
    _e("legumes", "intervention", ["legumes", "legumbre", "legumbres", "beans", "légumineuses"], "Fabaceae",
       ["legumes"]),
    _e("imiquimod", "intervention", ["imiquimod", "imiquimode"], "Imiquimod", ["imiquimod"]),
    _e("bicarbonate", "intervention", ["baking soda", "bicarbonato", "sodium bicarbonate", "bicarbonate"],
       "Sodium Bicarbonate", ["sodium bicarbonate"]),
    _e("semaglutide", "intervention", ["semaglutide", "ozempic", "wegovy"], "Semaglutide", ["semaglutide"],
       "Glucagon-Like Peptide-1 Receptor Agonists"),
    _e("grounding", "intervention", ["grounding", "earthing", "grounded"], None, ["grounding", "earthing"]),
    _e("oral_contraceptives", "intervention", ["birth control pills", "birth control", "the pill",
       "anticoncepción"], "Contraceptives, Oral", ["oral contraceptives"]),
    _e("cell_reprogramming", "intervention", ["cellular reprogramming", "reprogramación celular",
       "reprogramacion celular", "stem cells", "stem cell"], "Cellular Reprogramming",
       ["cell reprogramming", "stem cell"]),
    _e("blood_brain_barrier", "outcome", ["blood brain barrier", "blood-brain barrier"], "Blood-Brain Barrier",
       ["blood-brain barrier"]),
    _e("neem", "intervention", ["neem"], "Azadirachta", ["neem"], "Plant Preparations"),
    # ---- populations
    _e("children", "population", ["children", "kids", "child", "niños", "enfants"], "Child", ["children"]),
    _e("newborns", "population", ["newborns", "newborn", "neonates", "neonatal", "nouveau-nés",
       "recién nacidos"], "Infant, Newborn", ["newborn", "neonatal"], "Infant"),
    _e("infants", "population", ["babies", "baby", "infants", "infant", "bébés", "bebés"], "Infant",
       ["infants"]),
    _e("pregnancy", "population", ["pregnant women", "pregnant", "pregnancy", "embarazadas", "embarazo", "enceintes"], "Pregnancy",
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
