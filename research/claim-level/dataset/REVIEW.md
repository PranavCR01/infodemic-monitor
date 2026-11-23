# Reviewer checklist — golden label set

Every row in `videos.csv` and `claims.csv` ships with `review_status = pending`.
A row is not part of the golden set until a second person has marked it
`verified` or `corrected`. This file says what to check and how to record it.

`docs/target-system-design.md` is the authority. Section numbers below refer to
it. If a label looks wrong but matches the doc, the doc wins — raise it as a
design question rather than "fixing" the row.

## How to mark a row

Fill in three columns on the row you reviewed:

| Column | What to put |
|---|---|
| `reviewer` | your name or handle |
| `review_status` | `verified` if you agree as-is; `corrected` if you changed any field |
| `reviewer_notes` | **required when `corrected`**: what you changed and why, citing the section (e.g. "stance ENDORSES→UNCLEAR, two speakers disagree, §5") |

Change the label fields in place. Do not delete rows — a claim you think is not a
claim becomes a `corrected` row with the reason in `reviewer_notes`, so the
disagreement stays visible and countable.

After editing, run the validator. It will reject a label outside the allowed set
and any `video_level_label` that no longer follows from its claims:

```powershell
.\.venv\Scripts\python.exe research\claim-level\dataset\scripts\validate.py
```

## Per claim row — what to check

1. **Is it a claim at all?** A discrete, checkable *health* assertion. Greetings,
   usernames, "follow for more", opinions ("I love this tea") and questions
   without an assertion are not claims (§4).
2. **One assertion per row.** "Vitamin C prevents flu and cures pneumonia" must
   be two rows. Check nothing compound slipped through.
3. **Verbatim and complete.** `claim_text` should stay close to the speaker's
   words and keep every qualifier that changes the meaning — dose, age group,
   population, disease, and **negation** (§4). "1000 mg a day for adults" is not
   the same claim as "vitamin C".
4. **`speaker_stance`** (§5): does the speaker present it as true (`ENDORSES`),
   correct it (`REFUTES`), repeat someone else's claim without taking a side
   (`QUOTES`), discuss it without a position (`NEUTRAL`), or can you genuinely not
   tell (`UNCLEAR`)?
   - Read **speech and screen together**. A caption reading "MYTH: …" next to the
     claim confirms `REFUTES`.
   - A screen-only claim stated as fact is `ENDORSES` unless framed as a myth.
   - `UNCLEAR` is the right answer for sarcasm, irony, two speakers who disagree,
     and a speaker who contradicts themselves. **Prefer it to a guess** — it is a
     review trigger (§11), and this is the distinction the whole design exists to
     protect.
5. **`claim_verdict`** (§7): does it describe the *evidence*, not the speaker?
   - **`INSUFFICIENT_EVIDENCE`, never `CONTRADICTED`, when nothing tests the
     claim.** This is §7's most important rule and §14 tracks violations of it as
     their own failure mode. If you find a `CONTRADICTED` row whose evidence does
     not actually test the claim, correct it.
   - Check **directness**: does the cited paper test *this* intervention, for
     *this* outcome, in a *similar population*? A cell-culture study of an herb
     does not test "+300% immunity" in people.
   - Check **study design**: a systematic review outweighs one small trial.
   - Check **strength**: is the verdict stronger than the evidence allows?
6. **Evidence actually says what the row claims.** Open at least one cited PMID or
   URL. A real paper cited for something it does not say is the "evidence
   laundering" failure in §7's probe — retrieval proves a paper exists, not that
   it was read correctly. This check is the point of the review.
7. **Evidence fields** may be empty **only** for `INSUFFICIENT_EVIDENCE` or
   `NOT_VERIFIABLE`. Anything else needs at least one ID on the matching side,
   and `MIXED` needs both.
8. **`claim_source`** — `speech` / `screen` / `both` — and **timestamps** point at
   the right moment. Spot-check against `transcripts/<video_id>.json`.
9. **`claim_kind`** (§4): `fact_of_record` for a schedule, limit, regulatory
   action, statistic, food composition, diagnostic criterion or textbook fact;
   `research_question` otherwise. For a cited reference URL, open
   `reference_citations.csv` and check that the quoted passage really settles
   the claim *as stated*, not a nearby claim. A passage about fluid guidance does
   not settle "you need eight cups of water".

## Per video row — what to check

1. **`video_level_label` is derived, not chosen.** Apply the §9 rules in order to
   that video's claims:
   1. any claim `ENDORSES` + `CONTRADICTED` → `MISINFO`
   2. else any claim `REFUTES` + `SUPPORTED` → `MISINFO`, review reason
      "speaker denies a supported claim"
   3. else any claim `REFUTES` + `CONTRADICTED` → `DEBUNKING`
   4. else at least one claim `SUPPORTED` or `CONTRADICTED` → `NO_MISINFO`
   5. else any claim `REFUTES` + `MIXED` / `INSUFFICIENT_EVIDENCE` →
      `CANNOT_RECOGNIZE`, review reason "possible debunk of an unsettled claim"
   6. else → `CANNOT_RECOGNIZE`

   Order matters: a video that endorses one falsehood *and* refutes another is
   `MISINFO`, not `DEBUNKING`, and must carry the `mixed` tag. `validate.py`
   enforces both, and checks `review_reasons`.
2. **`out_of_scope`** is only for videos with **no health content**. It must be
   the video's only tag, and the video has no claims. Check it isn't hiding a
   health video with weak claims, which should be `CANNOT_RECOGNIZE` and counted.
3. **`text_type`** (`high_text` / `low_text`) matches what OCR found. The modality
   track depends on this column being honest.
4. **`case_tags`** describe the video and come from the §14 table. Add a tag you
   think is missing — coverage gaps are reported in the PR and are meant to be
   filled.
5. **`notes`** flags mixed videos and anything a reader would otherwise have to
   re-watch the video to discover.

## The blind subset (inter-annotator agreement)

§14 asks for two independent labellers per item with Cohen's kappa reported.
A randomly selected **20% of videos — 16 of 82** are the blind subset. Reproduce
the selection with:

```powershell
.\.venv\Scripts\python.exe research\claim-level\dataset\scripts\blind_subset.py
```

- **Random seed: `20261121`** (fixed in `scripts/blind_subset.py`). Same seed,
  same subset, forever.
- Selection is per batch, over every video in the batch, including ones with
  no claims — "this video makes no checkable health claim" is itself a
  judgement worth a second opinion. Drawing it per batch means a new batch
  never changes a subset already handed out.

**Batch 1: the 16 blind videos** (`blind_subset.py --batch 1`, 16 of 82):

```
v01 v10 v11 v21 v22 v23 v24 v36 v44 v45 v47 v68 v69 v71 v78 v79
```

**Batch 2: the 20 blind videos** (`blind_subset.py --batch 2`, 20 of 99, same
seed):

```
v100 v109 v110 v114 v120 v121 v122 v123 v131 v135 v141 v143 v144 v146 v150 v152 v160 v167 v176 v177
```

For batch 2, the blind labeller should also not look at `external_label`,
`external_source` or `sources/` before labelling, for the same reason.

### How to label them blind

1. **Do not open `claims.csv` or `videos.csv` for these video_ids first.** That is
   the whole point — seeing the existing labels destroys the agreement measure.
2. Work from `transcripts/<video_id>.json` (and the video itself if you have it).
   Write your own claims, stances and verdicts into a **separate** file,
   `blind/<your-name>.csv`, using the same columns as `claims.csv` and
   `videos.csv`.
3. Retrieve your own evidence with `scripts/evidence.py`. Do not reuse the first
   labeller's citations — whether two people find the same evidence is part of
   what is being measured.
4. Only when your file is complete, compare against the main CSVs.

### Then

- Report **Cohen's kappa** separately for `speaker_stance`, `claim_verdict` and
  `video_level_label`, plus claim-extraction agreement (how many of the same
  claims both labellers found), since a disagreement about *which claims exist*
  is not the same as one about how to label a shared claim.
- Settle every disagreement and record the outcome in the row's
  `reviewer_notes`.
- Record the numbers in `context/CLAIM_LEVEL.md` §7 with the date.
- **A disagreement usually means these guidelines are unclear, not that someone
  was careless.** Update `README.md` and this file when you settle one, so the
  next labeller does not hit it again.

## Rows to look at first

Reviewer time is scarce, so start where the design says the risk is (§11):

1. Any claim with both `evidence_supporting` and `evidence_contradicting`.
2. Every `CONTRADICTED` claim — the overconfidence failure mode.
3. Every `UNCLEAR` stance and every `MIXED` verdict.
4. Every video tagged `mixed`, `satire` or `speech_screen_disagree`.
5. Every row with `confidence = low`.
6. Every video where `video_level_label` disagrees with `collector_label` in
   `video_index.csv` (the folder the collectors filed it under). Those
   disagreements are listed in the PR description and are the most informative
   rows in the set.
7. Every batch-2 video where `video_level_label` disagrees with the label its
   source implies (`external_agreement.md`). A fact-checker calling a video
   false while every claim in it is `INSUFFICIENT_EVIDENCE` is exactly the §7
   boundary a reviewer should check.
