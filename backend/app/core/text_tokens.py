"""Unicode-aware word tokens, shared by the grounding guardrail, claim dedup and the
strict claim matcher (T45).

Before T45 each of those used ``re.compile(r"[a-z0-9]+")`` on lower-cased text, which
only sees ASCII letters and digits:

- a Devanagari claim had no tokens at all, so ``grounding_overlap(t, t) == 0.0`` and
  the extract node dropped every Hindi claim as ``claim_ungrounded``;
- two token-less strings had Jaccard similarity 1.0 in ``metrics.text_similarity``, so
  any Devanagari prediction "matched" any Devanagari gold claim;
- accented Latin words split ("reprogramación" -> "reprogramaci" + "n").

A token here is a maximal run of characters that are letters or digits in any script
(``str.isalnum``) or combining marks (Unicode category M*: Devanagari vowel signs and
virama, which ``isalnum`` and ``\\w`` both reject, would otherwise cut every Hindi word
apart). Text is NFC-normalised and lower-cased first. Underscore is not a word
character, as before.

For pure-ASCII text the result is identical to the old ``[a-z0-9]+`` on ``lower()``
(tested). Scripts written without spaces (Chinese, Japanese, Thai) come out as one
token per run; the golden set has none, so that is left alone.
"""
from __future__ import annotations

import unicodedata


def _is_word_char(ch: str) -> bool:
    if ch.isascii():
        return ch.isalnum()
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def word_tokens(text: str | None) -> list[str]:
    """Lower-cased word tokens of ``text`` in order, any script."""
    s = unicodedata.normalize("NFC", text or "").lower()
    out: list[str] = []
    start = -1
    for i, ch in enumerate(s):
        if _is_word_char(ch):
            if start < 0:
                start = i
        elif start >= 0:
            out.append(s[start:i])
            start = -1
    if start >= 0:
        out.append(s[start:])
    return out
