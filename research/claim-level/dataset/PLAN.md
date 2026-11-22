# Golden Label Set — Plan

One shared, versioned labelled set serving all three research tracks, as
`docs/target-system-design.md` §14 requires ("One shared, versioned set used by
every track, not separate spreadsheets").

**Authority:** `docs/target-system-design.md`. Where the older
`research/claim-level/dataset/README.md` disagreed with it, the target doc won and
the README was updated in this PR (see *Schema changes* below).

## What the set contains

| File | One row per | Purpose |
|---|---|---|
| `video_index.csv` | video | filename → `video_id` mapping, plus the collectors' own folder labels and creator handles. Filenames only — no media. |
| `videos.csv` | video | video-level label, `split`, `text_type`, `case_tags`, review fields |
| `claims.csv` | claim | claim text, stance, verdict, evidence, timestamps, review fields |
| `transcripts/<video_id>.json` | video | speech segments with timestamps + OCR captions. Text only. |

Source bundle: `mybox-selected.zip` (82 `.mp4` files), delivered by the data
collectors. It lives at `D:\Python files\labelling-data\` and is **never** in the
repo. Extracted videos sit in `research/claim-level/dataset/videos/`, which is
gitignored.

## Columns each track needs

The three tracks read different columns off the same two files. Nothing is
duplicated into a per-track spreadsheet.

**Claim-level track** (`context/CLAIM_LEVEL.md` §6.3 — per-claim ground truth):
reads `claims.csv` in full — `claim_text`, `speaker_stance`, `claim_verdict`,
`evidence_supporting`, `evidence_contradicting`, `start_seconds`, `end_seconds`,
`claim_source`. These are the per-claim ground truth the track has never had.

**Model Evaluation track** (`context/MODEL_EVAL.md` §6 — needs
`video_id, transcript_snippet, model_*_label, agreement, ground_truth`):
reads `videos.csv` for `video_level_label` as its `ground_truth` column, and
`transcripts/<video_id>.json` for `transcript_snippet`. `split` keeps tuning and
test videos apart. Its labels stay in the production `MisinfoLabel` vocabulary
(`MISINFO` / `NO_MISINFO` / `DEBUNKING` / `CANNOT_RECOGNIZE`), which is exactly
what `video_level_label` holds.

**Modality track** (`context/MODALITY.md` §6.1 — needs "a deliberate mix of
high-text and low-text content"): reads `text_type` on `videos.csv` to build that
mix without re-watching anything, and `claim_source` on `claims.csv` to find the
claims that exist **only** on screen — the cases that decide whether OCR earns
its cost.

Shared by all three: `split`, `case_tags`, `annotator`, `confidence`,
`review_status`.

## Schema changes against the old README

The old README predates the target design. Three changes, all from the target doc:

1. **`ground_truth_label` → `claim_verdict`.** The old README put the video-level
   vocabulary (`MISINFO`/`NO_MISINFO`/`CANNOT_RECOGNIZE`) on claim rows. §7 gives
   claims their own five verdicts: `SUPPORTED`, `CONTRADICTED`, `MIXED`,
   `INSUFFICIENT_EVIDENCE`, `NOT_VERIFIABLE`. This matters: the old scheme could
   not tell "the evidence says this is false" from "nobody has studied it", and
   §7's most important rule is that those must not be conflated.
2. **`speaker_stance` gains `UNCLEAR`** (§5) for sarcasm, disagreeing speakers and
   self-contradiction. The old four-value list forced a guess on exactly the cases
   §5 says to abstain on.
3. **`evidence_source` → `evidence_supporting` + `evidence_contradicting`.** §7
   outputs two separate lists, and §11 treats "both lists non-empty" as a
   measurable review trigger. One merged column cannot express that.

Video-level labels are unchanged: the §9 four, applied by the §9 rules in order.

## Method

1. **Extract** (`scripts/extract.py`): faster-whisper `small` (float16 on the
   GTX 1650, int8 on CPU) for speech with segment timestamps; EasyOCR English at
   0.5 fps, frames resized to a 960 px longest side, detections below 0.5
   confidence dropped (§2). Cached per video so the run resumes.
2. **Split claims** per the README rules: one checkable health assertion per row,
   verbatim, compound claims split.
3. **Label** each claim: `speaker_stance` (§5) from the video, `claim_verdict`
   (§7) from evidence actually retrieved. The two are decided separately and in
   that order, because §5's probe notes that answering both at once is how
   debunking videos get mislabelled.
4. **Retrieve evidence** (`scripts/evidence.py`): PubMed E-utilities, rate-limited
   to 3 requests/second, plus WHO/CDC pages fetched live. Every PMID and URL in
   the set was returned by a real request and cached under `evidence_cache/`.
   Nothing is cited from memory.
5. **Judge** (`scripts/judge.py`): the §9 rules in code, applied in order, so
   `video_level_label` is derived rather than hand-assigned.
6. **Validate** (`scripts/validate.py`): allowed-value checks, referential
   integrity, judge-consistency, and the evidence-presence rule.

## Decisions taken

- **`video_id` assignment.** `videos.csv` was header-only and no Model Evaluation
  dataset exists in the repo, so there were no ids to reuse. Ids are assigned
  `v01`–`v82` over all 82 videos sorted by lowercased filename. Eight files in one
  collector's `NO-MISINFO` folder carry their own `v01_`–`v08_` prefixes; those are
  that collector's local numbering of 8 videos inside one subfolder, not
  dataset-wide ids, and honouring them would have conflicted with a stable global
  order. `video_index.csv` keeps every original filename, so the old numbering is
  recoverable.
- **Collector folder labels are a prior, not the label.** The bundle sorts videos
  into `MISINFO` / `DEBUNKING` / `NO-MISINFO` / `No info` folders (55 of 82
  videos). Those are recorded as `collector_label` in `video_index.csv` and used as
  a cross-check, but `video_level_label` is derived from our own claims via §9.
  Disagreements are reported, not silently resolved — they are the most useful
  rows in the set.
- **`source_url` is left empty where it is not known.** Filenames of the form
  `ssstik.io_@handle_<timestamp>` give the platform and creator handle, which are
  recorded; the original post URL is not recoverable from them, and inventing one
  would put a fabricated citation in a dataset whose whole point is that citations
  are real.
- **Split is 30/70 tune/test, assigned per video** (§14: "split by video, not by
  sentence"), with a recorded random seed.
