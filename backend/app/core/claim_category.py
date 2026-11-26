"""Evidence-strength statements are not efficacy claims (§4, §7; T51).

"The evidence that the vitamin K shot prevents bleeding is overwhelming" and "these
studies are observational" talk about the **state, strength or design of the evidence**,
not about what an intervention does. In production job 5cc07f48 (vitamin K video,
2026-11-26) such a statement was tagged ``treatment_efficacy``, its search found nothing,
and it became UNSUPPORTED: an accurate video was labelled MISINFO (unproven).

These fixed rules recognise such statements so the extractor can tag them
``evidence_meta``, whatever category the model chose. ``evidence_meta`` is not an
efficacy category, so §7's UNSUPPORTED is never offered for it; the claim is still
retrieved and verified like any other (SUPPORTED, CONTRADICTED, MIXED or
INSUFFICIENT_EVIDENCE all stay possible).

Deliberately **not** matched, so they keep the model's category: statements that report
a finding ("studies show almonds help you lose weight", "this study didn't find higher
benzene levels", "clinically proven to cure acne"). Those assert the finding, which is
an efficacy claim in an evidence wrapper; tagging them ``evidence_meta`` would let an
unproven remedy claim escape UNSUPPORTED.

When unsure the rules do not match: a missed evidence statement can still be gated by
§7's on-topic guard (T49), while a wrong match would hide an efficacy claim.
"""
from __future__ import annotations

import re
import unicodedata

EVIDENCE_META = "evidence_meta"

_NOUN = (
    r"evidence|data|research|science|studies|study|trials?|literature|proof|findings?|"
    r"meta-analys[ie]s"
)
# Words that make "<evidence> ... <word>" report a finding rather than describe the
# evidence: "studies show X is good" is a claim about X.
_FINDING = re.compile(
    r"\b(?:shows?|showed|shown|finds?|found|proves?|proved|proven|suggests?|suggested|"
    r"demonstrates?|demonstrated|confirms?|confirmed|says?|said|indicates?|indicated|"
    r"reveals?|revealed|links?|linked|tells?|told)\b"
)
_STRENGTH = (
    r"overwhelming|strong|stronger|weak|weaker|limited|clear|unclear|conclusive|inconclusive|"
    r"mixed|solid|robust|settled|lacking|scarce|thin|poor|sparse|shaky|flimsy|compelling|"
    r"convincing|unconvincing|consistent|inconsistent|observational|anecdotal|retrospective|"
    r"preliminary|small|tiny|flawed|biased|low[- ]quality|high[- ]quality|correlational|"
    r"outdated|old|insufficient|uncertain|contested|controversial|massive|huge|"
    r"abundant|extensive|undeniable|irrefutable|unequivocal|weak at best|in (?:its|their) infancy"
)
_DEGREE = (
    r"(?:(?:very|really|so|quite|pretty|still|just|all|mostly|largely|only|not|extremely|"
    r"incredibly|far from|absolutely|actually|overwhelmingly|fairly|rather|too)\s+)*"
)
_COPULA = r"(?:is|are|was|were|remains?|seems?|looks?|isn't|aren't|wasn't|weren't|'s|'re)"

# A: "<the evidence (that X does Y)> is overwhelming", "these studies are observational".
# The gap after the noun must start like a complement ("that ...", "on newborns", "for
# X") or be empty; a finding verb anywhere in it disqualifies (checked in code).
_STATE = re.compile(
    rf"\b(?P<noun>{_NOUN})(?P<gap>(?:\s+(?:that|for|on|about|behind|supporting|linking|in|from|of|"
    rf"so far|to date|we have|available|out there)\b[^.;!?]{{0,160}}?)?)\s+{_COPULA}\s+{_DEGREE}"
    rf"(?:{_STRENGTH})\b"
)
# B: "there is no / little / overwhelming evidence (that ...)".
_EXISTENCE = re.compile(
    r"\bthere(?:'s|\s+is|\s+are|\s+was|\s+were|\s+has been|\s+have been|\s+isn't|\s+aren't)\s+"
    r"(?:(?:no|little|some|limited|not (?:much|enough|any)|insufficient|plenty of|lots of|a lot of|"
    r"strong|overwhelming|good|solid|clear|zero|scant|very little|no good|no real|no solid|no strong|"
    r"mixed|conflicting|weak|any|growing|mounting|tons of)\s+)+(?:\w+\s+){0,2}?(?:" + _NOUN + r")\b"
)
# C: "(it's / this is) just an observational study", "that was a mouse study".
_DESIGN = re.compile(
    r"\b(?:it|this|that|these|those|they)(?:'s|'re|\s+is|\s+are|\s+was|\s+were)\s+(?:just|only|merely|all)?\s*"
    r"(?:an?\s+)?(?:\w+\s+)?(?:observational|anecdotal|small|animal|mouse|rat|in vitro|test[- ]tube|"
    r"retrospective|cross-sectional|correlational|industry[- ]funded|uncontrolled|pilot)\s+"
    r"(?:study|studies|data|evidence|trials?|research)\b"
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
    r"\b(?:la evidencia|las pruebas|los estudios|el estudio|la investigaci[oó]n|los datos|"
    r"les preuves|les [ée]tudes|l'[ée]tude|la recherche|les donn[ée]es)\b[^.;!?]{0,160}?\s+"
    r"(?:es|son|era|eran|est|sont|[ée]tait|[ée]taient)\s+(?:(?:muy|tr[eè]s|bien|plut[oô]t|assez)\s+)?"
    r"(?:abrumadoras?|s[oó]lidas?|d[ée]biles|limitadas?|observacionales|anecd[oó]ticas?|"
    r"concluyentes|accablantes?|solides|faibles|limit[ée]es?|observationnelles?|anecdotiques?|"
    r"concluantes?|claires?|claras?)\b"
)
_EXISTENCE_ES_FR = re.compile(
    r"\b(?:no hay|hay (?:poca|pocas|muchas?|abundante)|il n'y a (?:pas|aucune?)|il y a (?:peu|beaucoup))\s+"
    r"(?:de\s+|d')?(?:\w+\s+)?(?:evidencias?|pruebas|estudios|datos|preuves?|[ée]tudes?|donn[ée]es)\b"
)


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


# After "<evidence> is clear", a colon or "that ..." means the sentence goes on to assert
# the finding itself ("the evidence is clear that sugar causes cancer"): an efficacy
# claim in an evidence wrapper, so it keeps the model's category.
_WRAPPER_TAIL = re.compile(r"\s*(?:[:\u2014\u2013]|-\s|,?\s*(?:and\s+)?(?:that|because|since|so|now)\b)")


def _state_match(text: str) -> bool:
    for m in _STATE.finditer(text):
        # "studies show that X is good" reports a finding; the noun phrase may not
        # contain a finding verb.
        if _FINDING.search(m.group("gap") or ""):
            continue
        tail = text[m.end():]
        if _WRAPPER_TAIL.match(tail) or _FINDING.search(tail):
            continue
        return True
    return False


def is_evidence_meta(text: str) -> bool:
    """True when the claim talks about the state, strength or design of the evidence
    rather than asserting what an intervention does (see module docstring)."""
    t = _normalize(text)
    if not t:
        return False
    return bool(
        _state_match(t)
        or _EXISTENCE.search(t)
        or ((_DESIGN.search(t) or _CONDUCT.search(t)) and not _FINDING.search(t))
        or _UNSTUDIED.search(t)
        or _STATE_ES_FR.search(t)
        or _EXISTENCE_ES_FR.search(t)
    )


def resolve_claim_category(given: str, claim_text: str, known: tuple[str, ...]) -> str:
    """The category the claim is stored with: ``evidence_meta`` when the fixed rules
    recognise an evidence-strength statement (this overrides the model, which tagged
    the production case ``treatment_efficacy``); otherwise the model's category when
    it is one of ``known``, else ``other``."""
    if is_evidence_meta(claim_text):
        return EVIDENCE_META
    g = (given or "").strip()
    return g if g in known else "other"
