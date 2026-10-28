# Claim-Level Labeled Dataset

Per-claim ground truth for evaluating the claim-level classifier (issue #13).
Target: at least 20 videos, each with its claims labeled individually.

## Files

| File | One row per | Columns |
|---|---|---|
| `videos.csv` | video | `video_id`, `source_url`, `platform`, `topic`, `video_level_label`, `notes` |
| `claims.csv` | claim | `video_id`, `claim_id`, `claim_text`, `ground_truth_label`, `speaker_stance`, `evidence_source`, `notes` |

`video_id` links the two files. `claim_id` is `c1`, `c2`, ... within a video, matching the `Claim.claim_id` field in the schema.

`video_id` uses the same format as the Model Evaluation dataset (`v01`, `v02`, ...). If a video is also in that dataset, use the same `video_id` so the two can be joined.

## Labels

Each claim gets two separate labels: whether the claim is **true**, and what the **speaker** does with it. Keeping them apart is what lets us tell misinformation from debunking.

### `ground_truth_label`: is the claim true?

Judged against a reliable source, regardless of what the speaker thinks of it.

| Label | Use when the claim... |
|---|---|
| `MISINFO` | is false or misleading according to the cited source |
| `NO_MISINFO` | is accurate according to the cited source |
| `CANNOT_RECOGNIZE` | can't be judged (too vague, no reliable source, or unverifiable) |

`DEBUNKING` is **not** used at claim level. It describes a whole video, not whether a claim is true.

### `speaker_stance`: what does the speaker do with the claim?

| Stance | Use when the speaker... |
|---|---|
| `ENDORSES` | presents the claim as true |
| `REFUTES` | says the claim is false or corrects it |
| `NEUTRAL` | mentions it without taking a side (e.g. "some people say...") |
| `QUOTES` | repeats someone else's claim, e.g. reading a comment, without endorsing or refuting it |

A debunked myth is a claim with `ground_truth_label = MISINFO` and `speaker_stance = REFUTES`. The **video** that does this gets `video_level_label = DEBUNKING` in `videos.csv`.

### `video_level_label` (in `videos.csv`)

One overall label for the video, using the system's four labels (`MISINFO`, `NO_MISINFO`, `DEBUNKING`, `CANNOT_RECOGNIZE`):

- Any false claim the speaker `ENDORSES` → `MISINFO`
- False claims raised only to refute them (`REFUTES`) → `DEBUNKING`
- All claims accurate, or nothing false endorsed → `NO_MISINFO`
- No claim can be judged → `CANNOT_RECOGNIZE`

## What counts as a claim

A discrete, checkable health assertion made in the video, e.g. "X cures Y" or "Z causes W." Not a claim: opinions, greetings, product pitches with no health assertion, restating a question.

- One assertion per row. Split compound statements ("A cures B and prevents C" becomes two claims).
- Copy the claim text as close to verbatim as possible from the transcript.
- If a video makes no checkable claims, leave it out of `claims.csv` and write `no checkable claims` in its `notes` in `videos.csv`.

## Labeling process

1. Pick the video and record it in `videos.csv`.
2. Watch it and write down the claims **yourself** from what is said. Do not start from the model's extracted claims, or the evaluation will be biased toward the model.
3. For each claim, set `ground_truth_label` against a reliable source (WHO, CDC, NIH, a systematic review or a PubMed paper) and record that source in `evidence_source`.
4. Set `speaker_stance` for each claim.
5. Set `video_level_label` in `videos.csv` using the rules above.
6. **Agreement check:** a second person independently labels at least 5 of the videos (claims, truth labels and stances) without seeing the first set of labels. Compare the two sets, settle any disagreements, and record the agreement rate (e.g. "agreed on 14 of 17 claims") in `context/CLAIM_LEVEL.md`. Disagreements usually mean these guidelines need to be clearer; update them.
7. Check the mix before finishing.

## Target mix (20+ videos)

- Several videos with **mixed claims** (some true, some false). These are the cases claim-level classification exists for.
- Some all-misinfo videos.
- Some all-accurate videos.
- A few debunking videos.
- A spread of topics (nutrition, vaccines, supplements, mental health, etc.).

## Example rows (format only, not real data)

Any field containing a comma must be wrapped in double quotes.

`videos.csv`
```
video_id,source_url,platform,topic,video_level_label,notes
v01,<url>,tiktok,supplements,MISINFO,"mixed: c1 accurate, c2 false"
v02,<url>,tiktok,nutrition,DEBUNKING,refutes the lemon water myth
```

`claims.csv`
```
video_id,claim_id,claim_text,ground_truth_label,speaker_stance,evidence_source,notes
v01,c1,<verbatim claim>,NO_MISINFO,ENDORSES,<source>,
v01,c2,<verbatim claim>,MISINFO,ENDORSES,<source>,
v02,c1,Lemon water cures cancer,MISINFO,REFUTES,<source>,
```
