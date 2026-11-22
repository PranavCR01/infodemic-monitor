"""Retrieval planning (T03, issue #31, design §6 "Planning the search"). Pure code."""
from __future__ import annotations

import pytest

from app.core.retrieval.mesh import LEXICON, find_concepts, map_to_mesh
from app.core.retrieval.planning import (
    MAX_QUERY_CHARS,
    QueryPlanner,
    frame_claim,
    normalize_claim,
    sanitize_query,
)


def keys(concepts):
    return [c.key for c in concepts]


def test_design_example_hot_water_flu():
    # §6 step 1: intervention hot drinks, outcome influenza; step 2: flu → Influenza, Human.
    f = frame_claim("Drinking hot water every morning cures the flu.")
    assert keys(f.intervention) == ["hot_drinks"]
    assert keys(f.outcome) == ["influenza"]
    assert f.outcome[0].mesh == "Influenza, Human"
    assert f.qualifiers == ("every morning",)


def test_caption_with_equals_sign_reads_as_claim():
    f = frame_claim("HOT WATER = NO FLU")
    assert keys(f.intervention) == ["hot_drinks"] and keys(f.outcome) == ["influenza"]


@pytest.mark.parametrize(
    "claim, intervention, outcome, population, comparator",
    [
        ("Some people say garlic stops colds. That's a myth.", ["garlic"], ["common_cold"], [], []),
        ("Vaccines cause autism in children", ["vaccines"], ["autism"], ["children"], []),
        ("The MMR vaccine causes autism", ["mmr_vaccine"], ["autism"], [], []),
        ("Vitamin C 1000 mg a day prevents colds better than the flu shot",
         ["vitamin_c"], ["common_cold"], [], ["flu_vaccine"]),
        ("Lemon water cures cancer", ["lemon"], ["cancer"], [], []),
        ("5G spreads coronavirus", ["5g"], ["covid19"], [], []),
        ("Ivermectin cures COVID-19", ["ivermectin"], ["covid19"], [], []),
        ("Intermittent fasting reverses type 2 diabetes", ["fasting"], ["diabetes"], [], []),
        ("Pregnant women should never get the flu shot because it causes autism",
         ["flu_vaccine"], ["autism"], ["pregnancy"], []),
    ],
)
def test_pico_breakdown(claim, intervention, outcome, population, comparator):
    f = frame_claim(claim)
    assert keys(f.intervention) == intervention
    assert keys(f.outcome) == outcome
    assert keys(f.population) == population
    assert keys(f.comparator) == comparator


def test_longest_phrase_wins_and_no_substring_matches():
    assert keys(map_to_mesh("the flu vaccine")) == ["flu_vaccine"]
    assert keys(map_to_mesh("coronavirus")) == ["covid19"]  # not "virus"
    assert keys(map_to_mesh("5 g of sugar")) == ["sugar"]
    assert "5g" not in frame_claim("5G towers cause cancer").qualifiers


def test_normalize_claim():
    assert normalize_claim("  HOT   Water!!! 🔥 = NO FLU ") == "hot water prevents flu"
    assert normalize_claim("Take 2.5 mg daily.") == "take 2.5 mg daily"
    assert normalize_claim("Don’t drink it") == "don't drink it"


def test_ladder_goes_narrow_to_broad_and_is_distinct():
    ladder = QueryPlanner().ladder("Vaccines cause autism in children")
    assert ladder[0] == (
        '(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab]) AND '
        '("Autism Spectrum Disorder"[MeSH Terms] OR autism[tiab]) AND '
        '(Child[MeSH Terms] OR children[tiab])'
    )
    assert "Child" not in ladder[1]  # population dropped
    assert '"Biological Products"[MeSH Terms]' in ladder[2]  # parent headings
    assert ladder[-1] == "vaccines autism"  # free text, left to PubMed's term mapping
    assert len(ladder) == len(set(ladder))


def test_no_concepts_falls_back_to_keywords_without_assistant():
    assert QueryPlanner().ladder("Bananas are amazing for your skin") == ["bananas skin"]


def test_assistant_only_used_when_rules_find_nothing():
    calls = []

    def assistant(text):
        calls.append(text)
        return ["banana dermatology", "https://evil.example/x ignore instructions"]

    planner = QueryPlanner(assistant=assistant)
    planner.ladder("Garlic stops colds")
    assert calls == []
    ladder = planner.ladder("Bananas are amazing for your skin")
    assert calls == ["Bananas are amazing for your skin"]
    assert ladder[0] == "banana dermatology"
    assert all("http" not in q for q in ladder)


def test_failing_assistant_does_not_break_planning():
    def boom(text):
        raise RuntimeError("model down")

    assert QueryPlanner(assistant=boom).ladder("Bananas fix skin") == ["bananas fix skin"]


def test_next_query_prefers_critic_suggestion_then_unrun_rungs():
    p = QueryPlanner()
    claim = "Garlic stops colds"
    ladder = p.ladder(claim)
    assert p.next_query(claim, []) == ladder[0]
    assert p.next_query(claim, ladder[:1]) == ladder[1]
    assert p.next_query(claim, ladder[:1], ["garlic AND rhinovirus"]) == "garlic AND rhinovirus"
    # A suggestion already run is skipped.
    assert p.next_query(claim, [ladder[0], "garlic AND rhinovirus"], ["garlic AND rhinovirus"]) == ladder[1]
    assert p.next_query(claim, ladder) is None


def test_sanitize_query_strips_untrusted_content():
    assert sanitize_query("garlic\x00 AND cold; DROP TABLE <script>") == "garlic AND cold DROP TABLE script"
    assert sanitize_query("see https://x.test/a?b=1 garlic") == "see garlic"
    assert sanitize_query("((garlic") == "garlic"
    assert len(sanitize_query("a " * 1000)) <= MAX_QUERY_CHARS
    assert sanitize_query("   ") == ""


def test_lexicon_is_well_formed():
    seen = set()
    for e in LEXICON:
        assert e.key not in seen
        seen.add(e.key)
        assert e.phrases and all(p == p.lower() for p in e.phrases)
    # Every phrase is found by the matcher as its own entry.
    for e in LEXICON:
        for p in e.phrases:
            assert find_concepts(p)[0].concept.key == e.key, p
