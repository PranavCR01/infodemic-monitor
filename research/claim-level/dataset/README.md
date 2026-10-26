# Claim-Level Labeled Dataset

Per-claim ground truth for evaluating the claim-level classifier (issue #13).
Target: at least 20 videos, each with its claims labeled individually.

## Files

| File | One row per | Columns |
|---|---|---|
| `videos.csv` | video | `video_id`, `source_url`, `platform`, `topic`, `video_level_label`, `notes` |
| `claims.csv` | claim | `video_id`, `claim_id`, `claim_text`, `ground_truth_label`, `evidence_source`, `notes` |

`video_id` links the two files. `claim_id` is `c1`, `c2`, ... within a video, matching the `Claim.claim_id` field in the schema.

## Labels

Same four labels as the system (`MisinfoLabel`):

| Label | Use when the claim... |
|---|---|
| `MISINFO` | is false or misleading according to the cited source |
| `NO_MISINFO` | is accurate, or neutral/non-health |
| `DEBUNKING` | is the video explicitly correcting a false claim |
| `CANNOT_RECOGNIZE` | can't be judged (too vague, no reliable source, or unverifiable) |

## What counts as a claim

A discrete, checkable health assertion made in the video, e.g. "X cures Y" or "Z causes W." Not a claim: opinions, greetings, product pitches with no health assertion, restating a question.

- One assertion per row. Split compound statements ("A cures B and prevents C" becomes two claims).
- Copy the claim text as close to verbatim as possible from the transcript.
- If a video makes no checkable claims, give it one row with `CANNOT_RECOGNIZE` and note why, or leave it out of the dataset.

## Labeling process

1. Pick the video and record it in `videos.csv`.
2. Watch it and write down the claims **yourself** from what is said. Do not start from the model's extracted claims, or the evaluation will be biased toward the model.
3. Label each claim against a reliable source (WHO, CDC, NIH, a systematic review or PubMed paper) and record it in `evidence_source`.
4. Set `video_level_label` in `videos.csv` using the same rule the system uses: one overall label for the video.
5. Check the mix before finishing.

## Target mix (20+ videos)

- Several videos with **mixed claims** (some true, some false). These are the cases claim-level classification exists for.
- Some all-misinfo videos.
- Some all-accurate videos.
- A few debunking videos.
- A spread of topics (nutrition, vaccines, supplements, mental health, etc.).

## Example rows (format only, not real data)

`videos.csv`
```
video_id,source_url,platform,topic,video_level_label,notes
v001,<url>,tiktok,supplements,MISINFO,mixed: c1 accurate, c2 false
```

`claims.csv`
```
video_id,claim_id,claim_text,ground_truth_label,evidence_source,notes
v001,c1,<verbatim claim>,NO_MISINFO,<source>,
v001,c2,<verbatim claim>,MISINFO,<source>,
```
