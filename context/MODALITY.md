# Modality Comparison Track Context

## 1. What This Role Is

Two students (Student-MC1, Student-MC2) working as a pair on **research**. Your deliverable
is a validated, written recommendation — production implements it, you don't have to.

## 2. Last Semester Findings (Task 3)

Compared **audio-only** vs. **visual-only (EasyOCR)** vs. **multimodal** (audio + OCR
fused) on 5 TikTok videos, using Mistral 7B as the classifier.

**Results:**
- 0% label change from adding OCR — no video's classification changed between audio-only
  and multimodal.
- Average confidence was identical (**0.77**) across all three modes.
- 2 `CANNOT_RECOGNIZE` failures occurred, but these were traced to data quality issues
  (poor audio, unreadable overlay text), not fundamental modality limitations.
- **Current production recommendation, in effect today:** audio-only by default.

## 3. Why This Isn't Settled

5 videos is a pilot, not a finding. "OCR adds no value" cannot be concluded from a 5-video
sample — it could just as easily mean none of the 5 videos happened to carry
misinformation-relevant text on screen. **This semester's job is to validate or disprove
the finding at scale**, not assume it's correct.

## 4. The Confidence Trigger Hypothesis

The proposed production implementation (not yet built) is: **run OCR only when transcript
confidence < 0.60.** Rather than always-on or always-off OCR, OCR kicks in conditionally
when the audio signal alone is weak.

Your job is to validate whether **0.60 is the right threshold** and whether OCR actually
helps in those low-confidence cases specifically (as opposed to helping or not helping
uniformly across all confidence levels).

## 5. System Context

OCR is **fully implemented**, not stubbed — `VideoTextExtractor` at
`backend/app/core/extraction/ocr/text_extractor.py` works end-to-end. It is currently
**disabled by omission**: `multimodal.py` never imports or calls it. There is no feature
flag and no commented-out code — it's simply not wired in. Read `context/PROJECT_CONTEXT.md`
for full system context before starting.

## 6. Objectives This Semester

1. Test on a minimum of **20 videos**, with a deliberate mix of high-text content
   (subtitles, on-screen overlays, infographic-style videos) and low-text content.
2. Measure three things per video, not just label change:
   - Does OCR change the **label**?
   - Does it change the **confidence**?
   - Does it change the **evidence snippets** returned?
3. Validate or revise the **0.60 confidence threshold** — test at multiple thresholds if
   the data supports it, don't just confirm or reject the single number blindly.
4. Produce a written recommendation the production student can implement **directly** —
   specific enough to become a straightforward conditional in `multimodal.py`, not a vague
   suggestion.

## 7. Output Format

CSV:

```
video_id, audio_label, audio_confidence, ocr_label, ocr_confidence, multimodal_label, multimodal_confidence, ocr_added_value
```

`ocr_added_value` is a boolean — true if OCR changed the label, meaningfully changed
confidence, or surfaced evidence the audio-only pass missed.

## 8. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

-

## 9. PR Requirements

- PRs for any scripts, using `.github/ISSUE_TEMPLATE/modality.md` for the originating
  issue.
- Reference the GitHub issue (`Closes #N`).
- Update this file with findings as they are confirmed.
