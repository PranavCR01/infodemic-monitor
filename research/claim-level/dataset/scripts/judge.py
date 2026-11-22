"""The section 9 judge rules, in code.

video_level_label is derived from the claim rows rather than hand-assigned, so
the label can never drift from the claims that are supposed to justify it. This
is a transcription of the pseudocode in docs/target-system-design.md section 9,
checked in the same order.

Used by both label_videos.py (to assign) and validate.py (to check).
"""

VERDICTS = ("SUPPORTED", "CONTRADICTED", "MIXED", "INSUFFICIENT_EVIDENCE",
            "NOT_VERIFIABLE")
STANCES = ("ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR")
VIDEO_LABELS = ("MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE")


def judge(claims):
    """claims: iterable of dicts with 'speaker_stance' and 'claim_verdict'.

    Returns (label, deciding_claims) exactly as section 9 specifies.
    """
    endorsed_false = [c for c in claims
                      if c["speaker_stance"] == "ENDORSES"
                      and c["claim_verdict"] == "CONTRADICTED"]
    refuted_false = [c for c in claims
                     if c["speaker_stance"] == "REFUTES"
                     and c["claim_verdict"] == "CONTRADICTED"]
    judged = [c for c in claims
              if c["claim_verdict"] in ("SUPPORTED", "CONTRADICTED")]
    if endorsed_false:
        return "MISINFO", endorsed_false
    if refuted_false:
        return "DEBUNKING", refuted_false
    if judged:
        return "NO_MISINFO", judged
    return "CANNOT_RECOGNIZE", []


def is_mixed(claims):
    """Section 9: 'Mixed videos: one false claim endorsed and another refuted.'
    Code detects the pattern; it does not change the label."""
    endorsed_false = any(c["speaker_stance"] == "ENDORSES"
                         and c["claim_verdict"] == "CONTRADICTED"
                         for c in claims)
    refuted_false = any(c["speaker_stance"] == "REFUTES"
                        and c["claim_verdict"] == "CONTRADICTED"
                        for c in claims)
    return endorsed_false and refuted_false


def has_true_and_false(claims):
    """Section 14's "mixed videos (true and false claims)" category.

    Distinct from is_mixed() above, which is section 9's narrower judge-policy
    edge case (one falsehood endorsed AND another refuted in the same video).
    A video can carry both supported and contradicted claims without hitting
    that pattern at all, and section 14 wants those covered on purpose.
    """
    return (any(c["claim_verdict"] == "SUPPORTED" for c in claims)
            and any(c["claim_verdict"] == "CONTRADICTED" for c in claims))


def review_triggers(claims, deciding):
    """The section 11 review rule, limited to the signals this dataset carries.

    The rest of the rule (reranking scores, critic escalation, calibrated
    confidence) belongs to the running pipeline, not to a hand-labelled set.
    """
    out = []
    pool = deciding or claims
    for c in pool:
        if c["claim_verdict"] in ("INSUFFICIENT_EVIDENCE", "MIXED"):
            out.append("deciding claim %s is %s"
                       % (c["claim_id"], c["claim_verdict"]))
        if c.get("evidence_supporting") and c.get("evidence_contradicting"):
            out.append("claim %s has both supporting and contradicting evidence"
                       % c["claim_id"])
        if c["speaker_stance"] == "UNCLEAR":
            out.append("claim %s stance is UNCLEAR" % c["claim_id"])
    return out
