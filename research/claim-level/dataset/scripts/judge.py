"""The section 9 judge rules, in code.

video_level_label is derived from the claim rows rather than hand-assigned, so
the label can never drift from the claims that are supposed to justify it. This
is a transcription of the pseudocode in docs/target-system-design.md section 9
(origin/langgraph-build, with the unproven rule), checked in the same order:

  1. ENDORSES + CONTRADICTED                      -> MISINFO, basis contradicted
  2. REFUTES  + SUPPORTED  (denies a true claim)  -> MISINFO, basis
                                                     denies_supported, reviewed
  3. ENDORSES + UNSUPPORTED (untested efficacy)   -> MISINFO, basis unproven,
                                                     reviewed
  4. REFUTES  + CONTRADICTED                      -> DEBUNKING
  5. any claim SUPPORTED or CONTRADICTED          -> NO_MISINFO
  6. REFUTES  + MIXED / INSUFFICIENT_EVIDENCE     -> CANNOT_RECOGNIZE, reviewed
                                                     as a possible debunk
  7. otherwise                                    -> CANNOT_RECOGNIZE; reviewed
                                                     (nothing_judged, LOW
                                                     priority) if any claim
                                                     is INSUFFICIENT_EVIDENCE

Review reasons are collected from every claim, whichever rule decides the label
(section 9). They are written as "<kind>:<claim_id>", or "mixed_video".

Used by build_csvs.py (to assign) and validate.py (to check).
"""

VERDICTS = ("SUPPORTED", "CONTRADICTED", "MIXED", "UNSUPPORTED",
            "INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE")
STANCES = ("ENDORSES", "REFUTES", "QUOTES", "NEUTRAL", "UNCLEAR")
VIDEO_LABELS = ("MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE")
MISINFO_BASES = ("contradicted", "denies_supported", "unproven")
CLAIM_KINDS = ("research_question", "fact_of_record")
# Section 7: UNSUPPORTED applies only to an efficacy claim.
EFFICACY_CATEGORIES = ("treatment_efficacy", "prevention")

# The review reasons the rules themselves add (section 9, fourth return value).
REASON_DENIES_TRUE = "denies_supported"
REASON_UNPROVEN = "unproven_claim"
REASON_OPEN_DEBUNK = "possible_debunk"
REASON_MIXED_EVIDENCE = "mixed_evidence"
REASON_MIXED_VIDEO = "mixed_video"
REASON_NOTHING_JUDGED = "nothing_judged"
JUDGE_REASONS = (REASON_DENIES_TRUE, REASON_UNPROVEN, REASON_OPEN_DEBUNK,
                 REASON_MIXED_EVIDENCE, REASON_MIXED_VIDEO,
                 REASON_NOTHING_JUDGED)


def reason_kind(reason):
    """'possible_debunk:c3' -> 'possible_debunk'."""
    return reason.split(":", 1)[0]


def judge(claims):
    """claims: iterable of dicts with 'claim_id', 'speaker_stance' and
    'claim_verdict'.

    Returns (label, misinfo_basis, deciding_claims, review_reasons) exactly
    as section 9 specifies. misinfo_basis is None unless the label is MISINFO.
    """
    claims = list(claims)

    def pick(stance, verdicts):
        return [c for c in claims
                if (stance is None or c["speaker_stance"] == stance)
                and c["claim_verdict"] in verdicts]

    endorsed_false = pick("ENDORSES", ("CONTRADICTED",))
    denied_true = pick("REFUTES", ("SUPPORTED",))
    unproven = pick("ENDORSES", ("UNSUPPORTED",))
    refuted_false = pick("REFUTES", ("CONTRADICTED",))
    judged = pick(None, ("SUPPORTED", "CONTRADICTED"))
    refuted_open = pick("REFUTES", ("MIXED", "INSUFFICIENT_EVIDENCE"))

    reasons = ["%s:%s" % (REASON_DENIES_TRUE, c["claim_id"])
               for c in denied_true]
    reasons += ["%s:%s" % (REASON_UNPROVEN, c["claim_id"]) for c in unproven]
    reasons += ["%s:%s" % (REASON_OPEN_DEBUNK, c["claim_id"])
                for c in refuted_open]
    reasons += ["%s:%s" % (REASON_MIXED_EVIDENCE, c["claim_id"])
                for c in claims if c["claim_verdict"] == "MIXED"]
    if (endorsed_false or unproven) and refuted_false:
        reasons.append(REASON_MIXED_VIDEO)

    if endorsed_false:
        return "MISINFO", "contradicted", endorsed_false, reasons
    if denied_true:
        return "MISINFO", "denies_supported", denied_true, reasons
    if unproven:
        return "MISINFO", "unproven", unproven, reasons
    if refuted_false:
        return "DEBUNKING", None, refuted_false, reasons
    if judged:
        return "NO_MISINFO", None, judged, reasons
    if refuted_open:
        return "CANNOT_RECOGNIZE", None, refuted_open, reasons
    # Nothing could be judged. If a claim needed checking but the evidence was
    # too thin, a person should still see it (LOW priority); videos with no
    # claims, or only NOT_VERIFIABLE ones, are not sent.
    if any(c["claim_verdict"] == "INSUFFICIENT_EVIDENCE" for c in claims):
        reasons.append(REASON_NOTHING_JUDGED)
    return "CANNOT_RECOGNIZE", None, [], reasons


def is_mixed(claims):
    """Section 9: a mixed video endorses a false or unproven claim and refutes
    a false one. Code detects the pattern; it does not change the label."""
    claims = list(claims)
    endorsed = any(c["speaker_stance"] == "ENDORSES"
                   and c["claim_verdict"] in ("CONTRADICTED", "UNSUPPORTED")
                   for c in claims)
    refuted_false = any(c["speaker_stance"] == "REFUTES"
                        and c["claim_verdict"] == "CONTRADICTED"
                        for c in claims)
    return endorsed and refuted_false


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
    """The section 11 review rule on the deciding claims only, limited to the
    signals this dataset carries. The rest of the rule (reranking scores,
    critic escalation, calibrated confidence) belongs to the running
    pipeline, not to a hand-labelled set.

    A deciding claim that is MIXED or UNSUPPORTED is already covered by the
    judge's mixed_evidence and unproven_claim reasons, so only
    INSUFFICIENT_EVIDENCE is added here.
    """
    out = []
    for c in deciding:
        if c["claim_verdict"] == "INSUFFICIENT_EVIDENCE":
            out.append("deciding_insufficient:%s" % c["claim_id"])
        if c.get("evidence_supporting") and c.get("evidence_contradicting"):
            out.append("evidence_both_sides:%s" % c["claim_id"])
        if c["speaker_stance"] == "UNCLEAR":
            out.append("unclear_stance:%s" % c["claim_id"])
    return out


def review_reasons(claims):
    """Everything that sends a video to a person: the judge's own reasons
    first, then the section 11 triggers on its deciding claims, without
    repeats. Recorded in videos.csv's review_reasons column and re-derived by
    validate.py."""
    _label, _basis, deciding, reasons = judge(claims)
    out = []
    for r in reasons + review_triggers(claims, deciding):
        if r not in out:
            out.append(r)
    return out
