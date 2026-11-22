# Claim-Level Labeled Dataset — the golden label set

Per-claim and per-video ground truth for the whole project (issue #13). One
shared, versioned set used by every track, not separate spreadsheets
(`docs/target-system-design.md` §14).

**`docs/target-system-design.md` is the authority for every label in this
directory.** Where this README used to disagree with it, the target doc won; the
changes are listed in [PLAN.md](PLAN.md#schema-changes-against-the-old-readme).
If you find a new disagreement, fix the README, not the labels.

## Files

| File | One row per | Columns |
|---|---|---|
| `video_index.csv` | video | `video_id`, `filename`, `relative_path`, `collector`, `collector_label`, `creator_handle`, `platform`, `size_mb` |
| `videos.csv` | video | `video_id`, `source_url`, `platform`, `topic`, `video_level_label`, `text_type`, `case_tags`, `split`, `annotator`, `confidence`, `review_status`, `reviewer`, `reviewer_notes`, `notes` |
| `claims.csv` | claim | `video_id`, `claim_id`, `claim_text`, `claim_source`, `start_seconds`, `end_seconds`, `speaker_stance`, `claim_verdict`, `evidence_supporting`, `evidence_contradicting`, `annotator`, `confidence`, `review_status`, `reviewer`, `reviewer_notes`, `notes` |
| `transcripts/<video_id>.json` | video | speech segments with timestamps, OCR captions. **Text only — no media.** |

`video_id` links all three. `claim_id` is `c1`, `c2`, … within a video, matching
`Claim.claim_id` in `backend/app/core/schemas/pipeline.py`.

`video_id` uses the same format as the Model Evaluation dataset (`v01`, `v02`, …).
If a video is also in that dataset, reuse the same `video_id` so the two can be
joined.

### Never commit media

The repo is public. `research/claim-level/dataset/videos/` is gitignored, as are
`*.mp4`, `*.mov`, `*.webm`, `*.mkv`, `*.m4a`, `*.wav` and `*.zip`. Source videos
live outside the repo (`D:\Python files\labelling-data\`). Run `git status` before
every commit and confirm no media appears.

## Labels

Each claim gets two **separate** labels — what the evidence says about the claim,
and what the speaker does with it. Keeping them apart is what lets us tell
misinformation from debunking, and it is why they are decided in that order by
different steps (§5 probe).

### `claim_verdict`: what does the evidence say? (§7)

Judged against evidence actually retrieved, regardless of what the speaker thinks.

| Verdict | Use when… |
|---|---|
| `SUPPORTED` | the evidence backs the claim as stated |
| `CONTRADICTED` | the evidence shows the claim is false |
| `MIXED` | good studies point in different directions |
| `INSUFFICIENT_EVIDENCE` | nothing tests this claim directly, or what exists is too weak |
| `NOT_VERIFIABLE` | the claim can't be tested ("this tea feels amazing") |

**The most important rule: absence of evidence is not contradiction.** If no study
tests the claim, the verdict is `INSUFFICIENT_EVIDENCE`, never `CONTRADICTED`
(§7). Calling an untested claim false is overconfident, and §14 tracks it as its
own failure mode.

Also weigh, per §7: **directness** (does the paper test this intervention, for
this outcome, in a similar population?), **study design** (a systematic review
counts for more than one small study), and **strength of inference** (is the
verdict stronger than the evidence?).

This column replaces the old `ground_truth_label`. The video-level vocabulary
(`MISINFO` / `NO_MISINFO` / `CANNOT_RECOGNIZE`) does **not** belong on a claim
row: it cannot tell "the evidence says this is false" from "nobody has studied
it", which is exactly the distinction §7 exists to protect.

### `speaker_stance`: what does the speaker do with it? (§5)

| Stance | Use when the speaker… |
|---|---|
| `ENDORSES` | presents the claim as true |
| `REFUTES` | says it's false or corrects it |
| `QUOTES` | repeats someone else's claim without taking a side |
| `NEUTRAL` | discusses it without a position |
| `UNCLEAR` | can't be determined |

`UNCLEAR` is for sarcasm, irony, several speakers who disagree, and a speaker who
contradicts themselves. **Use it rather than guessing** — it is a human-review
trigger (§11), and a wrong guess on a hard case is worse than an honest abstention.

Read speech and screen **together**: the caption "MYTH: GARLIC STOPS COLDS" next
to a speaker debunking it confirms `REFUTES`. A screen-only claim stated as fact
("HERB X: +300% IMMUNITY") is `ENDORSES` unless it is framed as a myth.

A debunked myth is `claim_verdict = CONTRADICTED` with `speaker_stance = REFUTES`.

### `evidence_supporting` / `evidence_contradicting`

Semicolon-separated PMIDs (`PMID:12345678`) or URLs, listing papers and guidance
pages **you actually retrieved**. Never cite from memory, and never cite a paper
you have not looked at — §7: "It may only cite what was retrieved."

Retrieve through `scripts/evidence.py`, which calls PubMed E-utilities at no more
than 3 requests/second and caches every response under `evidence_cache/`, so the
retrieval is reproducible and the IDs are provably real.

Two columns, not one, because §11 treats "both supporting and contradicting
papers exist for a deciding claim" as a review trigger — a single merged column
cannot express that.

Both may be empty **only** when the verdict is `INSUFFICIENT_EVIDENCE` or
`NOT_VERIFIABLE`. `validate.py` enforces this.

### `claim_source`, `start_seconds`, `end_seconds`

`claim_source` is `speech`, `screen` or `both` (§4: "Where each claim comes
from"). Timestamps come from the transcript segments the claim was taken from.
The modality track reads `claim_source` to find the screen-only claims that
decide whether OCR earns its cost.

### `video_level_label` (in `videos.csv`)

**Derived, not hand-assigned.** `scripts/judge.py` applies the §9 rules in order
and `scripts/validate.py` re-checks every row against them:

| If any claim… | Video label |
|---|---|
| is **endorsed** by the speaker and **contradicted** by the evidence | `MISINFO` |
| otherwise, is **refuted** by the speaker and contradicted by the evidence | `DEBUNKING` |
| otherwise, at least one claim was judged (`SUPPORTED` or `CONTRADICTED`) and nothing false is endorsed | `NO_MISINFO` |
| no claim could be judged (all insufficient or not verifiable, or no claims) | `CANNOT_RECOGNIZE` |

Order matters: a video that both endorses one falsehood and refutes another is
`MISINFO`, not `DEBUNKING`. Flag that pattern in `notes` as a mixed video — §9
lists it as a case the rules alone shouldn't settle.

### `text_type`, `case_tags`, `split`

- `text_type`: `high_text` or `low_text`. Set from the OCR output — a video is
  `high_text` when on-screen text carries substantive content (burned-in
  subtitles, overlays, infographics). The modality track uses this to build the
  deliberate high/low mix `context/MODALITY.md` §6.1 asks for.
- `case_tags`: semicolon-separated, from the §14 hard-case table — `debunking`,
  `satire`, `mixed`, `screen_only`, `uncertain_science`, `noisy_audio`,
  `other_language`, `multi_claim`, `missing_evidence`, `prompt_injection`,
  `clearly_false`, `accurate`, `neutral_discussion`, `speech_screen_disagree`.
- `split`: `tune` or `test`, roughly 30/70, **assigned per video** so no video
  appears in both (§14: "split by video, not by sentence"). Seed recorded in
  `REVIEW.md`.

### Review fields

On every row in both files: `annotator`, `confidence` (`low` / `medium` /
`high`), `review_status` (`pending` until a reviewer touches it), `reviewer`,
`reviewer_notes`. See [REVIEW.md](REVIEW.md).

## What counts as a claim

A discrete, checkable health assertion, e.g. "X cures Y" or "Z causes W".

- **One assertion per row.** "Vitamin C prevents flu and cures pneumonia" becomes
  two claims.
- **Keep the meaning, including negation and qualifiers** — age group, dose,
  population, disease. "1000 mg a day for adults" is not the same claim as
  "vitamin C" (§4).
- **Quote, don't invent.** Stay close to the original words; never fill in
  missing context.
- **Separate quoting from asserting.** Record the claim either way; what the
  speaker does with it is `speaker_stance`'s job.
- **Each claim once, with all its sources.** Said and shown at the same moment is
  one claim with `claim_source = both`, not two claims.

**Not a claim:** greetings, usernames, "follow for more", product names with no
health assertion, opinions ("I love this tea"), and questions without an
assertion.

If a video makes no checkable claims, leave it out of `claims.csv` and write
`no checkable claims` in its `notes` in `videos.csv`. It will come out as
`CANNOT_RECOGNIZE`.

## Labeling process

1. Record the video in `videos.csv`.
2. Read the transcript and OCR captions and write down the claims **yourself**.
   Do not start from the model's extracted claims, or the evaluation is biased
   toward the model.
3. Set `speaker_stance` from the video (§5).
4. Retrieve evidence with `scripts/evidence.py`, then set `claim_verdict` (§7)
   and record the IDs you actually retrieved.
5. Run `scripts/validate.py`. It derives `video_level_label` via the §9 rules and
   fails the build on any inconsistency.
6. **Agreement check:** a second person independently labels the blind subset in
   `REVIEW.md` without seeing these labels. Compare, settle disagreements, record
   Cohen's kappa in `context/CLAIM_LEVEL.md`. Disagreements usually mean these
   guidelines need to be clearer — update them.

## Reproducing the extraction

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install faster-whisper easyocr opencv-python requests
.\.venv\Scripts\python.exe research\claim-level\dataset\scripts\build_index.py `
    research\claim-level\dataset\videos research\claim-level\dataset\video_index.csv
.\.venv\Scripts\python.exe research\claim-level\dataset\scripts\extract.py
.\.venv\Scripts\python.exe research\claim-level\dataset\scripts\validate.py
```

`extract.py` caches per video and skips what is already done, so an interrupted
run resumes. It picks CUDA when the CUDA runtime loads and CPU otherwise
(faster-whisper `small`, float16 on GPU / int8 on CPU; EasyOCR English, 0.5 fps,
longest side 960 px, confidence floor 0.5 per §2).

## Example rows

Any field containing a comma must be wrapped in double quotes.

`videos.csv`
```
video_id,source_url,platform,topic,video_level_label,text_type,case_tags,split,annotator,confidence,review_status,reviewer,reviewer_notes,notes
v01,,tiktok,nutrition,MISINFO,high_text,clearly_false;multi_claim,test,pranav,high,pending,,,"mixed: c1 accurate, c2 false"
v02,,tiktok,nutrition,DEBUNKING,low_text,debunking,tune,pranav,high,pending,,,refutes the lemon water myth
```

`claims.csv`
```
video_id,claim_id,claim_text,claim_source,start_seconds,end_seconds,speaker_stance,claim_verdict,evidence_supporting,evidence_contradicting,annotator,confidence,review_status,reviewer,reviewer_notes,notes
v01,c1,<verbatim claim>,speech,3.5,8.0,ENDORSES,SUPPORTED,PMID:12345678,,pranav,high,pending,,,
v02,c1,Lemon water cures cancer,both,1.2,4.8,REFUTES,CONTRADICTED,,PMID:23456789;https://www.cancer.gov/...,pranav,high,pending,,,
```
