"""The golden label set, as data.

build_csvs.py turns this into videos.csv and claims.csv. video_level_label is
NOT stored here -- it is derived by the section 9 judge rules, so a label can
never contradict the claims under it.

Per video:
  video_id    v01..v82, from video_index.csv
  topic       health topic, or "none (non-health)" for off-topic videos
  text_type   high_text | low_text  (does on-screen text carry content?)
  case_tags   from the section 14 hard-case table; build_csvs.py adds
              mixed / no_claims / multi_claim / single_claim automatically
  confidence  low | medium | high -- how sure the annotator is overall
  notes       anything a reader would otherwise have to re-watch to learn
  claims      list, in the order they appear

Per claim:
  text        verbatim, one assertion, qualifiers and negation kept (section 4)
  source      speech | screen | both
  start, end  seconds, from the transcript segments
  stance      ENDORSES | REFUTES | QUOTES | NEUTRAL | UNCLEAR (section 5)
  verdict     SUPPORTED | CONTRADICTED | MIXED | INSUFFICIENT_EVIDENCE |
              NOT_VERIFIABLE (section 7)
  supporting, contradicting
              lists of "PMID:nnnnnnnn" or URLs that were actually retrieved
              through evidence.py. Absence of evidence is INSUFFICIENT_EVIDENCE,
              never CONTRADICTED.
"""

ANNOTATOR = "pranav"

LABELS = [
    {
        "video_id": "v01",
        "topic": "none (non-health)",
        "text_type": "high_text",
        "case_tags": [],
        "confidence": "high",
        "notes": "Off-topic for this dataset: a police/retail identity dispute "
                 "with no health content. Burned-in subtitles carry the whole "
                 "dialogue, so it is high_text, but no health assertion is "
                 "made. Collectors filed it under 'No info', which agrees.",
        "claims": [],
    },
    {
        "video_id": "v02",
        "topic": "none (non-health)",
        "text_type": "high_text",
        "case_tags": ["debunking"],
        "confidence": "high",
        "notes": "A genuine debunking video (@dustindeanmentalist explains that "
                 "paranormal 'spirit flashlight' responses are thermal "
                 "expansion of the contacts), but the debunked claim is "
                 "paranormal, not health, so there is no checkable health "
                 "assertion to label. Kept and tagged 'debunking' because the "
                 "stance structure is exactly what the stance step must handle; "
                 "the verdict columns stay empty because the claim is "
                 "out of scope. Collectors filed it under DEBUNKING.",
        "claims": [],
    },
]
