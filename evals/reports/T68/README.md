# T68: on-screen text kinds and routing (vision OCR). Sanity check, no spend

**Read this as a sanity check on two tune videos, not an accuracy figure.** No model ran:
the vision replies are mocked (`backend/app/tests/fixtures/vision_ocr/v36.json`,
`v135.json`, `synthetic: true`), and I assigned the kinds in them by hand following the new
prompt. The check tests the **routing code**. It does not test whether a real model labels
boxes this way. That is what the proposed (g) comparison would measure.

Reproduce: `cd backend && python -m app.evaluation.screen_text_check`, which writes
`screen_text_check.json`. Cost: $0, 0 model calls.

## What runs

The real code, not a re-implementation:

- `vision_ocr.plan_frame_times` on the recorded scene cuts, capped at `OCR_MAX_FRAMES` = 16.
- The tool-reply parser and `collapse_boxes`.
- `screen_text.route` against the golden Whisper transcript (`research/claim-level/dataset/transcripts/<id>.json`).

The "before" column reads the same replies the pre-T68 way: every non-interface box
verbatim, documents included, all of it sent to extraction.

## How the metrics are defined

- **Screen-only input recall.** A golden `claim_source=screen` claim counts as found when an
  OCR segment bound for extraction is shown at the claim's time (±2 s) and contains ≥ 75 % of
  the claim's words. This is a **ceiling** for extraction: no extraction model was run.
- **New-content segments.** OCR segments bound for extraction whose words are not already
  spoken in their time window (< 60 % containment).

## Results

| video | variant | screen-only recall after (before) | segments to extraction after (before) | chars after (before) | new-content segments after (before) | subtitles dropped | documents |
|---|---|---|---|---|---|---|---|
| v36 | as labelled | 12/12 (12/12) | 7 (9) | 1439 (2439) | 5 (7) | 0 | 1 |
| v36 | Pinterest infographic labelled as a document | 9/12 (10/12) | 6 (9) | 1006 (2459) | 4 (7) | 0 | 2 |
| v135 | as labelled | 0/0 (0/0) | 3 (14) | 238 (4292) | 2 (10) | 15 | 11 |

## Reading it

### v36 (main case: 12 screen-only claims)

All 12 claims reach extraction, from the three benefit cards (Burdock Root 28–34 s, Irish Sea
Moss 34–42 s, Moringa 50–58 s). The "102 minerals" element chart becomes one note instead
of about 1,000 characters of element names.

**The weak point is the kind boundary.** The Moringa card is a screenshot of a Pinterest
infographic. If a model calls it `document_or_chart`, c15–c17 are lost (9/12). That is
worse than before, because the old verbatim read still caught c15 through the garbled text.

The prompt now says that an infographic listing claims is a card even when it is a
screenshot. Whether models follow that is untested. It is the first thing (g) should
measure.

### v135 (must gain no new claims)

The 11 documents and 15 burned-in subtitles no longer reach extraction:

- Documents: the CNN, Valisure, WHO, American Cancer Society and Washington Post pages, the
  worst-case table and the JAAD 2022 article.
- Subtitles: every one matched the speech in its window, misreads included ("it @ooks like").

Extraction input from the screen drops from 4,292 to 238 characters.

**"No new claims" is not guaranteed.** Two made-for-video cards still reach extraction with
content that is not spoken:

- "1% = 1000 ppm": a unit conversion, not a health claim.
- The "Known carcinogen" explainer card, 36–44 s. It includes "Bacon, alcohol and sunlight
  are known carcinogens", which an extractor could turn into a claim the golden set does not
  have.

Routing by kind can't stop this: the card is exactly the kind of text T68 sends to
extraction. Whether extraction actually extracts it is untested (no spend).

### find_study hints

These are the notes offered for v135's golden claims; see `hints_for_golden_claims` in the
JSON.

- c1 (11.9–17.8 s) gets the Valisure report notes (Figure 4 and Figures 4D–4F), the
  production trigger (job f85f2daa).
- c6 ("this study didn't find higher benzene levels in people who use sunscreen") gets the
  JAAD 2022 NHANES article note.

Hints only reach find_study when it already runs for the claim: when the claim cites a
study, or when nothing on topic was kept. T68 adds no new trigger and no spend.

## (g) Proposed frame-level model comparison: NOT RUN, needs the lead's approval

- **Harness:** `backend/app/evaluation/vision_ocr_compare.py`. Configuration:
  `vision_compare.yaml`.
- **Request:** the same as production (prompt, tool, batches of 4).
- **Scores, per model:**
  - kind accuracy per box;
  - card and subtitle text similarity;
  - frames where a document's text was copied anyway (a leak);
  - frames where interface text was kept.
- **Frames:** 20–30, extracted locally with `extract`. They are not committed (video
  content, binaries). A person labels `expected` by hand.
- **Refusal:** a live run is refused unless every model is priced in `config/routing.yaml`,
  the run is given `--live --approved-by <name> --max-usd <cap>`, and the upper-bound
  estimate fits under the cap.

### Cost estimate

From `vision_compare_estimate_30_frames.json` (one run, 8 requests per model):

| candidate | expected | upper bound | price source |
|---|---|---|---|
| Haiku 5.5 | $0.008 | $0.037 | routing.yaml |
| Sonnet 5.5 | $0.166 | $0.731 | routing.yaml |
| GPT-6.1 Terra | $0.318 | $0.996 | **assumed** (GPT-5.6 Terra prices; reasoning allowance 1,500 tokens per request) |
| GPT-6 Luna | $0.032 | $0.100 | **assumed** (GPT-5.6 Luna prices) |
| **total** | **$0.52** | **$1.86** | |

With 20 frames: $0.34 expected, $1.17 upper bound. **Proposed cap: $2.**

Before a run, these need a person:

- the exact GPT-6.x API ids and their prices, added to `routing.yaml`;
- the labelled frames;
- the lead's go-ahead.
