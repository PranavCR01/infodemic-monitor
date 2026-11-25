"""T47: a sarcastic or mocking debunk with a clear target is REFUTES (lead decision,
2026-11-25). The label rules are unchanged; the stance prompts mark the rationale
"Sarcasm:", and the user-facing explanation carries that nuance.

No network and no model calls.
"""
from __future__ import annotations

import pytest

from app.core.graph import judge as jg
from app.core.graph import stance as stance_mod
from app.core.graph.state import Stance, StanceResult, Verdict
from app.core.schemas.pipeline import MisinfoLabel
from app.tests.test_judge import FakeCaller, make_state, run_judge

RF, E, U = Stance.REFUTES, Stance.ENDORSES, Stance.UNCLEAR
SUP, CON, INS = Verdict.SUPPORTED, Verdict.CONTRADICTED, Verdict.INSUFFICIENT_EVIDENCE


def with_rationale(state: dict, cid: str, rationale: str) -> dict:
    old = state["stance_results"][cid]
    state["stance_results"][cid] = StanceResult(
        claim_id=cid, stance=old.stance, stance_segment_ids=old.stance_segment_ids, rationale=rationale)
    return state


SARC = "Sarcasm: the speaker mocks the idea that a copper bracelet cures diabetes."


# ------------------------------------------------------------------ prompts


@pytest.mark.parametrize("version", ["stance_v1", "stance_v2"])
def test_stance_prompts_make_a_sarcastic_debunk_refutes(version):
    text = " ".join(stance_mod.load_prompt(version).split())
    assert "A sarcastic or mocking debunk with a clear target is REFUTES" in text
    assert 'starts with "Sarcasm:"' in text
    assert "a joke that rejects no clear claim" in text
    # the live prompt no longer sends all sarcasm to UNCLEAR
    assert "Sarcasm and irony, several speakers with different views, and a speaker who contradicts themselves are UNCLEAR" not in text


def test_live_stance_prompt_is_still_stance_v1():
    assert stance_mod.DEFAULT_PROMPT_VERSION == "stance_v1"


def test_explain_prompt_tells_the_writer_to_mention_sarcasm():
    text = " ".join(jg.load_prompt("explain_v2").split())
    assert '"sarcasm: yes"' in text and "a sarcastic debunk is still a debunk" in text


# ------------------------------------------------------------------ detection


@pytest.mark.parametrize("rationale, stance, expected", [
    (SARC, RF, True),
    ("sarcastic: rolls eyes at the remedy", RF, True),
    ("  SARCASM - mocks it", RF, True),
    ("The speaker says it is a myth.", RF, False),
    ("Not sarcasm: the speaker plainly corrects it.", RF, False),
    (SARC, E, False),   # only a debunk is reported as sarcastic
    (SARC, U, False),
    ("", RF, False),
])
def test_sarcastic_flag(rationale, stance, expected):
    state = with_rationale(make_state((stance, CON)), "c1", rationale)
    views, _ = jg.claim_views(state)
    assert views[0].sarcastic is expected


# ------------------------------------------------------------------ template explanation


def test_sarcastic_debunk_is_debunking_with_the_nuance_in_the_explanation():
    final, _ = run_judge(with_rationale(make_state((RF, CON)), "c1", SARC))
    assert final.classification == MisinfoLabel.DEBUNKING  # the label is unchanged by sarcasm
    assert final.explanation.startswith("Debunked (the speaker uses sarcasm): The speaker refutes the first claim")
    assert "(using sarcasm), and the evidence contradicts it (ev_c1)" in final.explanation
    assert "Sarcasm:" not in final.explanation  # the model's rationale itself is not shown


def test_plain_debunk_explanation_is_unchanged():
    final, _ = run_judge(make_state((RF, CON)))
    assert final.classification == MisinfoLabel.DEBUNKING
    assert final.explanation.startswith("The speaker refutes the first claim")
    assert "sarcasm" not in final.explanation


def test_sarcastic_denial_of_a_true_claim_is_misinfo_and_says_so():
    final, _ = run_judge(with_rationale(make_state((RF, SUP)), "c1", SARC))
    assert final.classification == MisinfoLabel.MISINFO
    assert "denies the first claim" in final.explanation and "(using sarcasm), but the evidence supports it" in final.explanation
    assert "Debunked" not in final.explanation


def test_sarcastic_unsettled_debunk_mentions_sarcasm():
    final, _ = run_judge(with_rationale(make_state((RF, INS)), "c1", SARC))
    assert final.classification == MisinfoLabel.CANNOT_RECOGNIZE
    assert "(using sarcasm), but the evidence is insufficient" in final.explanation


# ------------------------------------------------------------------ model explanation prompt


def test_explanation_prompt_marks_the_sarcastic_claim_and_fences_its_note():
    state = with_rationale(make_state((RF, CON), (RF, CON)), "c1", SARC)
    d = jg.decide(jg.claim_views(state)[0])
    prompt = jg.build_prompt(d, jg.load_prompt("explain_v2"))
    rendered = prompt.render()
    row1 = next(line for line in rendered.splitlines() if line.startswith("- c1 |"))
    assert row1.endswith("| sarcasm: yes")
    assert "sarcasm: yes" not in next(line for line in rendered.splitlines() if line.startswith("- c2 |"))
    assert "copper bracelet" in rendered  # the stance note is passed, fenced as model output


def test_model_explanation_mentioning_sarcasm_is_accepted():
    state = with_rationale(make_state((RF, CON)), "c1", SARC)
    text = "The speaker debunks the first claim using sarcasm, and ev_c1 contradicts it."
    final, errors = run_judge(state, FakeCaller({"explanation": text}))
    assert final.classification == MisinfoLabel.DEBUNKING
    assert final.explanation.startswith(text)
    assert not [e for e in errors if "template used" in e.message]
