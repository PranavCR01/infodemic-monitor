"""Statements about study design, quality or quantity are not efficacy claims (§4, §7; T51).

"These studies are observational", "the sample was small", "it's only one study", "the
trials weren't randomised" describe the evidence and assert no effect. These fixed rules
recognise them so the extractor can tag them ``evidence_meta``, whatever category the
model chose. ``evidence_meta`` is not an efficacy category, so §7's UNSUPPORTED is
never offered for it; the claim is still retrieved and verified like any other.

Deliberately **not** ``evidence_meta`` (review of PR #122): a statement that the
evidence **for** an intervention is strong, overwhelming, clear or proven, with or
without an explicit effect ("the evidence that turmeric cures cancer is overwhelming",
"the evidence for this detox tea is overwhelming"). That is an efficacy claim in an
evidence wrapper, a common misinformation framing, so it keeps the category of the
implied effect (``treatment_efficacy`` / ``prevention``) and stays eligible for
UNSUPPORTED; T49's on-topic guard still stops an empty or off-topic search from
producing it. Reported findings ("studies show X lowers Y", "clinically proven to
cure Z") likewise keep the finding's category.

When unsure the rules do not match: a wrong match would hide an efficacy claim.
"""
from __future__ import annotations

import re
import unicodedata

EVIDENCE_META = "evidence_meta"

_NOUN = (
    r"evidence|data|research|science|studies|study|trials?|literature|proof|findings?|"
    r"meta-analys[ie]s|samples?|sample sizes?"
)
# Words that make "<evidence> ... <word>" report a finding rather than describe the
# evidence: "studies show X is small" is a claim about X.
_FINDING = re.compile(
    r"\b(?:shows?|showed|shown|finds?|found|proves?|proved|proven|suggests?|suggested|"
    r"demonstrates?|demonstrated|confirms?|confirmed|says?|said|indicates?|indicated|"
    r"reveals?|revealed|links?|linked|tells?|told)\b"
)
# Design, quality or quantity words that assert no effect. Words saying the evidence
# for something is strong (overwhelming, clear, conclusive, solid, proven ...) are
# absent on purpose: see the module docstring.
_WEAKNESS = (
    r"observational|anecdotal|retrospective|preliminary|small|tiny|flawed|biased|"
    r"low[- ]quality|poor[- ]quality|correlational|outdated|old|weak|limited|thin|poor|sparse|"
    r"shaky|flimsy|inconclusive|mixed|insufficient|lacking|scarce|uncertain|contested|"
    r"controversial|unconvincing|inconsistent|unclear|cross-sectional|uncontrolled|"
    r"unblinded|unrandomi[sz]ed|non-randomi[sz]ed|underpowered|in (?:its|their) infancy|"
    r"not randomi[sz]ed|not blinded|not controlled|not peer[- ]reviewed|not replicated"
)
_DEGREE = (
    r"(?:(?:very|really|so|quite|pretty|still|just|all|mostly|largely|only|extremely|"
    r"incredibly|far too|absolutely|actually|fairly|rather|too)\s+)*"
)
_COPULA = r"(?:is|are|was|were|remains?|seems?|looks?|'s|'re)"

# A: "these studies are observational", "the sample was small", "the evidence for X is
# weak". The gap after the noun must start like a complement ("that ...", "on newborns",
# "for X") or be empty; a finding verb in it disqualifies (checked in code).
_STATE = re.compile(
    rf"\b(?P<noun>{_NOUN})(?P<gap>(?:\s+(?:that|for|on|about|behind|supporting|linking|in|from|of|"
    rf"so far|to date|we have|available|out there)\b[^.;!?]{{0,160}}?)?)\s+{_COPULA}\s+{_DEGREE}"
    rf"(?:{_WEAKNESS})\b"
)
# A': "the trials weren't randomised", "the study wasn't blinded".
_NOT_DESIGNED = re.compile(
    r"\b(?:" + _NOUN + r")\s+(?:was|were|is|are|has|have)(?:n't|\s+not|\s+never)\s+(?:been\s+)?(?:\w+\s+)?"
    r"(?:randomi[sz]ed|blinded|double[- ]blind(?:ed)?|controlled|peer[- ]reviewed|replicated|repeated|published)\b"
)
# B: "there is no / little / not enough evidence (that ...)". Negative quantities only:
# "there is overwhelming evidence that X" is a claim about X.
_EXISTENCE = re.compile(
    r"\bthere(?:'s|\s+is|\s+are|\s+was|\s+were|\s+has been|\s+have been)\s+"
    r"(?:no|little|very little|limited|not (?:much|enough|any)|insufficient|scant|zero|no good|"
    r"no real|no solid|no strong|no reliable|no quality|weak|mixed|conflicting)\s+(?:\w+\s+){0,2}?"
    r"(?:" + _NOUN + r")\b"
    r"|\bthere(?:\s+isn't|\s+aren't|\s+wasn't|\s+weren't)\s+(?:\w+\s+){0,2}?(?:" + _NOUN + r")\b"
)
# C: "it's only one study", "that was a mouse study", "it's just an observational study".
_DESIGN = re.compile(
    r"\b(?:it|this|that|these|those|they)(?:'s|'re|\s+is|\s+are|\s+was|\s+were)\s+(?:just|only|merely|all)?\s*"
    r"(?:an?\s+)?(?:\w+\s+)?(?:observational|anecdotal|small|animal|mouse|rat|in vitro|test[- ]tube|"
    r"retrospective|cross-sectional|correlational|industry[- ]funded|uncontrolled|pilot)\s+"
    r"(?:study|studies|data|evidence|trials?|research)\b"
)
_ONE_STUDY = re.compile(
    r"\b(?:only|just|merely)\s+(?:one|a single|1|two|a couple of|a few|a handful of)\s+(?:small\s+|tiny\s+)?"
    r"(?:study|studies|trials?|papers?|reports?)\b"
)
# D: "the study was funded by ...", "the studies were done in mice".
_CONDUCT = re.compile(
    r"\b(?:" + _NOUN + r")\s+(?:was|were|is|are|has been|have been)\s+(?:\w+\s+)?"
    r"(?:funded|paid for|sponsored|done|conducted|carried out|retracted|debunked|discredited)\b"
)
# E: "X has never been studied / tested in humans".
_UNSTUDIED = re.compile(
    r"\b(?:has|have|had)(?:n't|\s+not|\s+never)\s+(?:\w+\s+)?(?:been\s+)?(?:properly\s+|well\s+|adequately\s+|"
    r"rigorously\s+)?(?:studied|tested|researched|investigated)\b"
)
# Spanish / French (§4 rule 1 keeps the original language): the common A and B forms.
_STATE_ES_FR = re.compile(
    r"\b(?:la evidencia|las pruebas|los estudios|el estudio|la investigaci[oó]n|los datos|la muestra|"
    r"les preuves|les [ée]tudes|l'[ée]tude|la recherche|les donn[ée]es|l'[ée]chantillon)\b[^.;!?]{0,160}?\s+"
    r"(?:es|son|era|eran|est|sont|[ée]tait|[ée]taient)\s+(?:(?:muy|tr[eè]s|bien|plut[oô]t|assez)\s+)?"
    r"(?:d[ée]biles?|limitad[ao]s?|observacionales|anecd[oó]tic[ao]s?|peque[ñn][ao]s?|"
    r"faibles?|limit[ée]e?s?|observationnelles?|anecdotiques?|petite?s?|insuficientes?|insuffisante?s?)\b"
)
_EXISTENCE_ES_FR = re.compile(
    r"\b(?:no hay|hay (?:poca|pocas|pocos)|il n'y a (?:pas|aucune?)|il y a (?:peu|tr[eè]s peu))\s+"
    r"(?:de\s+|d')?(?:\w+\s+)?(?:evidencias?|pruebas|estudios|datos|preuves?|[ée]tudes?|donn[ée]es)\b"
)

# "The evidence (for X) is overwhelming / strong / clear", "there is overwhelming
# evidence", "proven": an efficacy claim in an evidence wrapper (PR #122 review).
_SUPPORT = re.compile(
    rf"\b(?:{_NOUN})\b[^.;!?]{{0,160}}?\s+{_COPULA}\s+{_DEGREE}(?:overwhelming|strong|clear|conclusive|"
    r"compelling|convincing|solid|robust|settled|undeniable|irrefutable|unequivocal|massive|huge|"
    r"abundant|extensive|consistent|high[- ]quality|good|in)\b"
    r"|\bthere(?:'s|\s+is|\s+are|\s+has been)\s+(?:overwhelming|strong|clear|good|solid|plenty of|lots of|"
    r"a lot of|tons of|growing|mounting|abundant)\s+(?:\w+\s+){0,2}?(?:" + _NOUN + r")\b"
    r"|\b(?:scientifically|clinically|medically)?\s*proven\b"
    # reported findings: "studies show X lowers Y"
    r"|\b(?:" + _NOUN + r")\s+(?:shows?|showed|proves?|proved|confirms?|confirmed|demonstrates?|"
    r"demonstrated|finds|found|says?|suggests?)\b"
    # Spanish / French: "la evidencia es abrumadora", "les preuves sont accablantes"
    r"|\b(?:es|son|est|sont)\s+(?:(?:muy|tr[eè]s)\s+)?(?:abrumador[ao]s?|s[oó]lid[ao]s?|clar[ao]s?|"
    r"concluyentes?|accablantes?|solides?|claires?|concluantes?|irr[ée]futables?)\b"
)
_PREVENTION_CUE = re.compile(
    r"\b(?:prevents?|prevented|preventing|prevention|preventive|preventative|prophyla\w*|protects?|"
    r"protection|wards? off|vaccines?|vaccinations?|immuni[sz]\w*|shots?|injections?|reduces? (?:the |your )?risk)\b"
)

# After "<evidence> is weak", a colon or "that ..." means the sentence goes on to assert
# something else; keep the model's category then.
_WRAPPER_TAIL = re.compile(r"\s*(?:[:—–]|-\s|,?\s*(?:and\s+)?that\b)")
# A finding verb is fine when negated: "the studies are observational, so they cannot
# prove that every bleeding event was caused by skipping vitamin K" (production c12)
# asserts no effect; "the trials are small, but they show X cures Y" asserts one.
_NEGATION = re.compile(
    r"\b(?:not|cannot|can't|can not|couldn't|don't|doesn't|didn't|won't|never|no|unable to|fail(?:s|ed)? to)"
    r"(?:\s+\w+){0,2}\s*$"
)


def _asserted_finding(tail: str) -> bool:
    return any(not _NEGATION.search(tail[:m.start()]) for m in _FINDING.finditer(tail))


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def _state_match(text: str) -> bool:
    for m in _STATE.finditer(text):
        if _FINDING.search(m.group("gap") or ""):
            continue
        tail = text[m.end():]
        if _WRAPPER_TAIL.match(tail) or _asserted_finding(tail):
            continue
        return True
    return False


def is_evidence_meta(text: str) -> bool:
    """True when the claim talks about the design, quality or quantity of the evidence
    and asserts no effect (see module docstring)."""
    t = _normalize(text)
    if not t:
        return False
    return bool(
        _state_match(t)
        or _NOT_DESIGNED.search(t)
        or _EXISTENCE.search(t)
        or _ONE_STUDY.search(t)
        or ((_DESIGN.search(t) or _CONDUCT.search(t)) and not _FINDING.search(t))
        or _UNSTUDIED.search(t)
        or _STATE_ES_FR.search(t)
        or _EXISTENCE_ES_FR.search(t)
    )


def is_support_statement(text: str) -> bool:
    """True when the claim says the evidence for something is strong, overwhelming,
    clear or proven: an efficacy claim in an evidence wrapper, never ``evidence_meta``."""
    t = _normalize(text)
    return bool(t) and not is_evidence_meta(t) and bool(_SUPPORT.search(t))


def implied_efficacy_category(text: str) -> str:
    """``prevention`` or ``treatment_efficacy`` for a support statement."""
    return "prevention" if _PREVENTION_CUE.search(_normalize(text)) else "treatment_efficacy"


def resolve_claim_category(given: str, claim_text: str, known: tuple[str, ...]) -> str:
    """The category the claim is stored with:

    - ``evidence_meta`` when the fixed rules recognise a design / quality / quantity
      statement (overrides the model);
    - for a support statement the model tagged ``evidence_meta``, the implied efficacy
      category (so it stays eligible for UNSUPPORTED);
    - otherwise the model's category when it is one of ``known``, else ``other``.
    """
    if is_evidence_meta(claim_text):
        return EVIDENCE_META
    g = (given or "").strip()
    if g == EVIDENCE_META and is_support_statement(claim_text):
        return implied_efficacy_category(claim_text)
    return g if g in known else "other"
