import pytest

from app.core.inference.providers import anthropic_provider, openai_provider
from app.core.schemas.pipeline import MisinfoLabel


@pytest.mark.parametrize("module", [anthropic_provider, openai_provider])
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("MISINFO", MisinfoLabel.MISINFO),
        ("misinfo", MisinfoLabel.MISINFO),
        ("  debunking  ", MisinfoLabel.DEBUNKING),
        ("No_Misinfo", MisinfoLabel.NO_MISINFO),
        ("CANNOT_RECOGNIZE", MisinfoLabel.CANNOT_RECOGNIZE),
        ("FAKE_NEWS", MisinfoLabel.CANNOT_RECOGNIZE),
        ("", MisinfoLabel.CANNOT_RECOGNIZE),
        (None, MisinfoLabel.CANNOT_RECOGNIZE),
    ],
)
def test_safe_label_normalizes_to_known_labels(module, raw, expected):
    assert module._safe_label(raw) == expected


def test_openai_strips_trailing_period():
    assert openai_provider._safe_label("MISINFO.") == MisinfoLabel.MISINFO


def test_anthropic_does_not_strip_trailing_period():
    # The Anthropic tool schema restricts the label to an enum, so a trailing
    # period is not expected there; this documents the current behaviour.
    assert anthropic_provider._safe_label("MISINFO.") == MisinfoLabel.CANNOT_RECOGNIZE
