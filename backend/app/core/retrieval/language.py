"""Rule-based language detection for claim text (T50 item h, design §6 "Planning").

Planning reads claims in English: the stop words, the claim verbs and most of the MeSH
lexicon's surface forms are English, and PubMed indexes English titles and abstracts.
A Spanish or French claim run through the English rules gives keyword queries such as
``ce gamin de 15 ans`` or ``los beneficios son muchísimo`` (T49 report). So planning
first asks which language a claim is in; a non-English claim is translated before
planning when a translator is configured (``app.core.retrieval.assist``), and otherwise
planned with that language's stop words and the lexicon's non-English surface forms.

Deterministic and offline: function-word counts for the languages the golden set holds
(English, Spanish, French, Portuguese, German, Italian), a script check for non-Latin
text (Devanagari, Cyrillic, Arabic, CJK ...), and ``"und"`` when too little is known.
"""
from __future__ import annotations

import re
import unicodedata

# Short, frequent function words that are rare in the other languages listed. Words
# shared between languages ("de", "a", "la") are left out so they cannot decide.
_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset("""the and is are was were this that with you your of to it for not have has
        what which who they their there been can will would should do does don't it's""".split()),
    "es": frozenset("""el los las del que una por con para es son está están muy pero más también
        hay sí puede pueden tiene tienen esto eso como cuando porque sus nos lo te vas
        hacer ser fue al mediante cuerpo riesgo salud forma tipo sabías""".split()),
    "fr": frozenset("""le les des du une est sont qui pour avec dans pas sur au aux ce cette
        il elle ils vous nous mais très aussi fait été être son ses leur peut qu'il c'est corps santé
        risque""".split()),
    "pt": frozenset("""os das dos uma não são está com para mais também isso você muito pelo pela
        tem têm foi ser""".split()),
    "de": frozenset("""der die das und ist sind nicht mit ein eine für auch sich auf dem den
        wird werden kann""".split()),
    "it": frozenset("""il gli che della delle sono è non per con una anche questo questa
        molto più può""".split()),
}
_ACCENTS: dict[str, str] = {"es": "ñ¿¡", "fr": "çœêèàù", "pt": "ãõç", "de": "ßäöü"}
_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)

STOPWORDS: dict[str, frozenset[str]] = {
    "es": _MARKERS["es"] | frozenset("""de la a en y o un se me mi mis tu tus su le les ya ni
        sin sobre entre hasta desde todo toda todos todas otro otra este esta estos estas ese
        esa esos esas aquel muchísimo mucho mucha muchos muchas poco primero segundo así
        bien mal mejor peor solo sólo vez veces cosa cosas gente persona personas años año
        día días dice dicen decir ahora siempre nunca usted ustedes vamos va van voy
        beneficios""".split()),
    "fr": _MARKERS["fr"] | frozenset("""de la a à en et ou un se me ma mes ta tes sa ne ni sans
        sous entre jusqu tout toute tous toutes autre cet ces y en plus moins bien mal
        meilleur pire seulement fois chose choses gens personne ans an jour jours dit
        disent dire maintenant toujours jamais gamin gamine garçon fille vient venir
        inventé invente fabriqué contre""".split()),
    "pt": _MARKERS["pt"] | frozenset("de da do a o e em um se me mas".split()),
    "de": _MARKERS["de"] | frozenset("zu im in von es ich du wir sie er".split()),
    "it": _MARKERS["it"] | frozenset("di la lo le a e in un si mi ma".split()),
}


def _script(text: str) -> str | None:
    """A non-Latin script that dominates the letters, or None."""
    counts: dict[str, int] = {}
    letters = 0
    for ch in text:
        if not ch.isalpha():
            continue
        letters += 1
        name = unicodedata.name(ch, "")
        if name.startswith("LATIN"):
            continue
        script = name.split(" ")[0]
        counts[script] = counts.get(script, 0) + 1
    if not letters or not counts:
        return None
    script, n = max(counts.items(), key=lambda kv: kv[1])
    return script.lower() if n / letters > 0.5 else None


_SCRIPT_LANG = {"devanagari": "hi", "cyrillic": "ru", "arabic": "ar", "cjk": "zh", "hiragana": "ja",
                "katakana": "ja", "hangul": "ko", "greek": "el", "hebrew": "he", "thai": "th",
                "bengali": "bn", "tamil": "ta"}


def detect_language(text: str) -> str:
    """ISO 639-1 code of the claim's language (``en``, ``es``, ``fr``, ``pt``, ``de``,
    ``it``, or a non-Latin script's language), or ``und`` when undetermined."""
    t = unicodedata.normalize("NFKC", text or "").lower().replace("’", "'")
    script = _script(t)
    if script:
        return _SCRIPT_LANG.get(script, "und")
    words = _WORD_RE.findall(t)
    if not words:
        return "und"
    scores = {lang: sum(1 for w in words if w in markers) for lang, markers in _MARKERS.items()}
    for lang, chars in _ACCENTS.items():
        if any(c in t for c in chars):
            scores[lang] += 1
    best = max(scores, key=lambda k: scores[k])
    top = scores[best]
    if top == 0:
        return "und"
    if list(scores.values()).count(top) > 1:
        return "en" if scores["en"] == top else "und"
    return best


def is_english(lang: str) -> bool:
    """``und`` is treated as English: short claims ("Moringa: Anti-Ulcer") carry no
    function word, and they are mostly English in this dataset."""
    return lang in ("en", "und")


__all__ = ["STOPWORDS", "detect_language", "is_english"]
