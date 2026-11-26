"""User-facing text about sources: one formatter for the verifier, the API and the export (T65).

Production job d2bf4179 (the vitamin K re-analysis) showed four problems in the
exported report, all fixed here so the verifier's output check, the result API and the
export use the same rules:

- **Internal evidence ids** (``ev_37337123``) in explanations. ``render_evidence_ids``
  replaces them with the paper's short title, or "PMID n" when there is no title; an id
  that names no known source is dropped. ``EVIDENCE_ID_RE`` is the check the verifier
  uses to reject such text (repair once, else render).
- **"The reviewer"** for the critic's notes. Those notes come from a second automated
  check, not a person; ``reword_reviewer`` rewrites the phrase.
- **Double full stops** ("… a systematic review.. 2016"): ``clean_title`` strips the
  trailing full stop PubMed puts on titles, so whoever adds one adds the only one.
- **Journal and date** for the source line (``source_line``).

Pure functions, no model calls.
"""
from __future__ import annotations

import re
from typing import Callable, Mapping, Optional

# The ids the retrieval tools mint: ev_<pmid>, ev_stub_<cid>_<n>, ev_<anything word-like>.
EVIDENCE_ID_RE = re.compile(r"\bev_[A-Za-z0-9][A-Za-z0-9_\-]*")
_ID_RUN_RE = re.compile(
    r"\bev_[A-Za-z0-9][A-Za-z0-9_\-]*(?:\s*(?:,|;|/|\band\b|&)\s*ev_[A-Za-z0-9][A-Za-z0-9_\-]*)*"
)
SHORT_TITLE_WORDS = 8
SECOND_CHECK = "a second automated check"
UNKNOWN_SOURCE = "a retrieved paper"


# ------------------------------------------------------------------ titles


def clean_title(title: Optional[str]) -> str:
    """The title without surrounding space and without a trailing full stop (or
    several). A title ending in '?' or '!' keeps it: that is part of the title."""
    t = " ".join((title or "").split())
    while t.endswith(".") and not t.endswith("..."):
        t = t[:-1].rstrip()
    return t


def short_title(title: Optional[str], max_words: int = SHORT_TITLE_WORDS) -> str:
    """The part of a title a sentence can carry: the main title before a subtitle
    (": a systematic review"), cut to ``max_words`` words with an ellipsis."""
    t = clean_title(title)
    head = re.split(r":\s|\s[-–—]\s", t, maxsplit=1)[0].strip()
    if len(head.split()) >= 3:
        t = head
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return t


def source_name(title: Optional[str], pmid: Optional[str] = None) -> Optional[str]:
    """How user-facing text names one source: its short title in quotes, else its PMID."""
    st = short_title(title)
    if st:
        return f"“{st}”"
    if pmid:
        return f"PMID {pmid}"
    return None


def source_line(title: Optional[str], *, journal: Optional[str] = None, pub_date: Optional[str] = None,
                year: Optional[int] = None) -> str:
    """"Title. Journal, 2016-11." — one full stop after the title, whatever PubMed sent."""
    t = clean_title(title)
    meta = ", ".join(x for x in (journal, pub_date or (str(year) if year else None)) if x)
    head = t if t.endswith(("?", "!", "...", "…")) else f"{t}." if t else ""
    if not meta:
        return head
    return f"{head} {meta}." if head else f"{meta}."


# ------------------------------------------------------------------ evidence ids


def has_evidence_ids(text: Optional[str]) -> bool:
    return bool(EVIDENCE_ID_RE.search(text or ""))


def evidence_ids_in(text: Optional[str]) -> list[str]:
    return list(dict.fromkeys(EVIDENCE_ID_RE.findall(text or "")))


def render_evidence_ids(text: Optional[str], names: Mapping[str, Optional[str]] | Callable[[str], Optional[str]]) -> str:
    """Replace evidence ids with source names. ``names`` maps an id to its name (see
    ``source_name``); an id with no name is dropped, with the brackets or commas it
    leaves behind."""
    if not text or not has_evidence_ids(text):
        return text or ""
    lookup = names if callable(names) else (lambda i: names.get(i))  # type: ignore[union-attr]

    def run(m: re.Match[str]) -> str:
        found = [n for n in (lookup(i) for i in dict.fromkeys(EVIDENCE_ID_RE.findall(m.group(0)))) if n]
        found = list(dict.fromkeys(found))
        if found:
            return "; ".join(found)
        before = m.string[:m.start()].rstrip()
        return "" if before.endswith(("(", "[", ",", ";")) else UNKNOWN_SOURCE

    out = _ID_RUN_RE.sub(run, text)
    # tidy what dropped ids leave: "()", "( ; x)", " ,", double spaces
    out = re.sub(r"\(\s*[;,]?\s*\)", "", out)
    out = re.sub(r"\(\s*[;,]\s*", "(", out)
    out = re.sub(r"\s*[;,]\s*\)", ")", out)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


# ------------------------------------------------------------------ "the reviewer"

_REVIEWER_RE = re.compile(
    r"\b(?:(the|a|an|our)\s+)?(?:(automated|automatic|second|critic|ai|model)\s+)?reviewer(s?)('s|’s|s'|s’)?\b",
    re.IGNORECASE,
)


def reword_reviewer(text: Optional[str]) -> str:
    """"The reviewer was right that …" → "A second automated check was right that …".
    In verifier text a "reviewer" can only be the critic, which is a second automated
    check, not a person (people review later and their words are not verifier text)."""
    if not text:
        return text or ""

    def sub(m: re.Match[str]) -> str:
        plural = bool(m.group(3)) or (m.group(4) or "").startswith("s")
        possessive = bool(m.group(4))
        word = "second automated checks" if plural else SECOND_CHECK
        if possessive:
            word += "'" if plural else "'s"
        start = m.start()
        sentence_start = start == 0 or re.search(r"[.!?]\s*$|^\s*$|\n\s*$", m.string[:start]) is not None
        first = m.group(1) or ""
        if first[:1].isupper() or (sentence_start and not first):
            word = word[0].upper() + word[1:]
        return word

    return _REVIEWER_RE.sub(sub, text)


def mentions_reviewer(text: Optional[str]) -> bool:
    return bool(_REVIEWER_RE.search(text or ""))


def user_text(text: Optional[str], names: Mapping[str, Optional[str]] | Callable[[str], Optional[str]]) -> str:
    """Both rules: evidence ids rendered as source names, "reviewer" reworded."""
    return reword_reviewer(render_evidence_ids(text, names))
