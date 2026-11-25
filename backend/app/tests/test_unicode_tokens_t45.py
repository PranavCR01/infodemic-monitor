"""T45 (a): Unicode-aware tokens in the grounding guardrail, claim dedup and the strict
claim matcher. Examples are invented, not golden-set claims."""
from __future__ import annotations

import random
import re
import string

import pytest

from app.core.graph.claims import lexical_similarity
from app.core.guardrails.outputs import grounding_overlap
from app.core.text_tokens import word_tokens
from app.evaluation import metrics as m

OLD = re.compile(r"[a-z0-9]+")  # the pre-T45 tokeniser, kept here to prove ASCII is unchanged

HINDI_CLAIM = "हल्दी वाला दूध कैंसर को ठीक करता है"           # "turmeric milk cures cancer"
HINDI_SOURCE = "दोस्तों, हल्दी वाला दूध कैंसर को ठीक करता है, रोज़ पियो"
HINDI_OTHER = "नींबू पानी से वज़न घटता"                          # "lemon water reduces weight"
SPANISH_CLAIM = "la reprogramación celular cura la diabetes"
SPANISH_SOURCE = "Mira, la reprogramación celular cura la diabetes en semanas."


# ------------------------------------------------------------------ the tokeniser


def test_ascii_text_tokenises_exactly_as_before():
    rng = random.Random(45)
    alphabet = string.ascii_letters + string.digits + string.punctuation + " \t\n_"
    samples = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60))) for _ in range(2000)]
    samples += [
        "Vitamin C prevents flu and cures pneumonia.", "Don't take 1000mg/day!!", "COVID-19 vaccines",
        "snake_case_words", "", "   ", "e=mc^2", "HERB X: +300% IMMUNITY",
    ]
    for s in samples:
        assert word_tokens(s) == OLD.findall(s.lower()), s


def test_devanagari_words_stay_whole_including_vowel_signs_and_virama():
    # "हल्दी" has a virama (्) and a vowel sign (ी), both category M; \w alone would cut it.
    assert word_tokens("हल्दी वाला दूध") == ["हल्दी", "वाला", "दूध"]
    assert word_tokens("कैंसर, ठीक!") == ["कैंसर", "ठीक"]


def test_accented_latin_words_are_one_token_and_normalised():
    assert word_tokens("reprogramación") == ["reprogramación"]          # was ["reprogramaci", "n"]
    decomposed = "reprogramación"                                  # o + combining acute
    assert word_tokens(decomposed) == word_tokens("reprogramación")    # NFC
    assert word_tokens("Ça GUÉRIT") == ["ça", "guérit"]


def test_underscore_is_still_a_separator():
    assert word_tokens("a_b") == ["a", "b"]


# ------------------------------------------------------------------ grounding guardrail


def test_hindi_claim_is_grounded_in_its_own_source():
    # Before T45: 0.0 for both (no ASCII tokens), so extract_window dropped the claim.
    assert grounding_overlap(HINDI_CLAIM, HINDI_CLAIM) == 1.0
    assert grounding_overlap(HINDI_CLAIM, HINDI_SOURCE) == 1.0


def test_hindi_claim_not_in_source_is_still_ungrounded():
    assert grounding_overlap(HINDI_OTHER, HINDI_SOURCE) == 0.0
    # An English translation is not grounded in Hindi speech (it must be quoted, not translated).
    assert grounding_overlap("turmeric milk cures cancer", HINDI_SOURCE) == 0.0


def test_spanish_claim_grounding():
    assert grounding_overlap(SPANISH_CLAIM, SPANISH_SOURCE) == 1.0
    # Before T45 "reprogramaci" + "n" matched a source spelled without the accent; now a
    # claim must keep the source's spelling, like any other word.
    assert grounding_overlap("reprogramación", "reprogramacion") == 0.0


def test_english_grounding_unchanged():
    assert grounding_overlap("Vitamin C cures the flu", "they say vitamin c cures the flu fast") == 1.0
    assert grounding_overlap("garlic stops colds", "vitamin c cures flu") == 0.0
    assert grounding_overlap("the a of", "anything") == 0.0  # stop words only


# ------------------------------------------------------------------ strict matcher


def test_two_different_devanagari_claims_no_longer_match():
    # Before T45: both token-less, Jaccard 1.0, so any Hindi prediction matched any gold.
    assert m.text_similarity(HINDI_CLAIM, HINDI_OTHER) == 0.0
    assert m.text_similarity(HINDI_CLAIM, HINDI_CLAIM) == 1.0
    assert m.match_claims([HINDI_CLAIM], [HINDI_OTHER]) == []
    assert m.match_claims([HINDI_CLAIM], [HINDI_OTHER, HINDI_CLAIM]) == [(0, 1, 1.0)]


def test_spanish_strict_similarity():
    assert m.text_similarity(SPANISH_CLAIM, SPANISH_CLAIM.upper()) == 1.0
    assert m.text_similarity("reprogramación celular", "reprogramación celular cura") == pytest.approx(2 / 3)


def test_english_strict_similarity_unchanged():
    assert m.text_similarity("turmeric cures cancer", "the speaker says turmeric can cure cancer") == pytest.approx(2 / 8)
    assert m.text_similarity("", "") == 1.0
    assert m.text_similarity("...", "!!") == 1.0  # punctuation only, as before


# ------------------------------------------------------------------ claim dedup


def test_dedup_merges_hindi_copies_and_keeps_distinct_hindi_claims():
    # Overlapping windows return the same claim twice; before T45 a Hindi pair scored 0
    # and both copies survived.
    assert lexical_similarity(HINDI_CLAIM, HINDI_CLAIM) == 1.0
    assert lexical_similarity(HINDI_CLAIM, HINDI_OTHER) == 0.0


def test_dedup_english_unchanged():
    assert lexical_similarity("X cures Y", "X does not cure Y") == 0.0
    assert lexical_similarity("vitamin c cures flu", "Vitamin C cures flu!") == 1.0
