"""Derive the two fields that depend on the OCR output, by rule rather than by
eye, so they are reproducible and the modality track can trust them.

  text_type     high_text / low_text, per video
  claim_source  speech / screen / both, per claim

Both can be overridden per video or per claim in labels.py ("text_type": ...,
"source": ...) when the rule gets a case wrong; the override wins and should
carry a note saying why.
"""
import json
import re
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1]
TRANSCRIPTS = DATASET / "transcripts"

# Platform furniture and watermarks: present on screen but carrying no claim.
FURNITURE = re.compile(
    r"(?i)^(tiktok|tik\s*tok|reels?|shorts|follow|follow for more|like|share|"
    r"subscribe|original sound|sound|music|fyp|for you|@?[a-z0-9_.]{3,}\s*$)")

# A video counts as high_text when it carries at least this many distinct
# substantive captions per minute. Calibrated against the hand-read cases:
# v03/v05/v06 (dense burned-in subtitles and charts) land well above it, v04
# (a title sting plus a handle watermark) lands below.
HIGH_TEXT_PER_MINUTE = 6.0


def substantive(text, handle=""):
    """Is this caption real content rather than furniture or a watermark?"""
    t = (text or "").strip()
    if len(t) < 3:
        return False
    letters = sum(c.isalpha() for c in t)
    if letters < 3 or letters / float(len(t)) < 0.5:
        return False
    if FURNITURE.match(t):
        return False
    if handle:
        bare = handle.lstrip("@").lower()
        squashed = re.sub(r"[^a-z0-9]", "", t.lower())
        # OCR mangles watermarks ("dustindeanmnentalist"), so compare loosely
        if bare and (bare in squashed or squashed in bare):
            return False
    return True


def load(vid):
    p = TRANSCRIPTS / ("%s.json" % vid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def distinct_substantive(doc):
    handle = doc.get("creator_handle", "")
    out, seen = [], set()
    for c in (doc.get("on_screen", {}) or {}).get("captions", []) or []:
        if not substantive(c.get("text", ""), handle):
            continue
        k = " ".join(c["text"].lower().split())
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def derive_text_type(doc):
    """Returns (text_type, rate, n_distinct) for the record."""
    caps = distinct_substantive(doc)
    dur = float((doc.get("transcript", {}) or {})
                .get("duration_seconds", 0) or 0)
    minutes = max(dur / 60.0, 1.0 / 60.0)
    rate = len(caps) / minutes
    return ("high_text" if rate >= HIGH_TEXT_PER_MINUTE else "low_text",
            round(rate, 1), len(caps))


def derive_claim_source(doc, start, end, pad=2.0):
    """speech / screen / both for one claim's time window.

    'both' when substantive on-screen text overlaps the window -- the design
    doc's section 4 rule that a claim said and shown at the same moment is one
    claim with two sources. 'screen' when the video has no speech at all, which
    is the case OCR exists for.
    """
    segs = (doc.get("transcript", {}) or {}).get("segments", []) or []
    has_speech = bool(segs)
    overlapping = [
        c for c in distinct_substantive(doc)
        if c["start"] <= end + pad and c["end"] >= start - pad
    ]
    if not has_speech:
        return "screen"
    return "both" if overlapping else "speech"
