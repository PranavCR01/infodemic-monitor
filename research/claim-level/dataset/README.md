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
| `video_index.csv` | video | `video_id`, `filename`, `relative_path`, `collector`, `collector_label`, `creator_handle`, `platform`, `size_mb`, `source`, `source_label`, `source_url`, `external_label`, `external_source`, `external_url`, `duration_seconds` |
| `videos.csv` | video | `video_id`, `source_url`, `platform`, `topic`, `video_level_label`, `misinfo_basis`, `review_reasons`, `text_type`, `case_tags`, `split`, `annotator`, `confidence`, `review_status`, `reviewer`, `reviewer_notes`, `notes`, `source`, `external_label`, `external_source`, `external_url` |
| `claims.csv` | claim | `video_id`, `claim_id`, `claim_text`, `claim_source`, `claim_kind`, `start_seconds`, `end_seconds`, `speaker_stance`, `claim_verdict`, `evidence_supporting`, `evidence_contradicting`, `annotator`, `confidence`, `review_status`, `reviewer`, `reviewer_notes`, `notes` |
| `reference_citations.csv` | cited reference | `evidence_id`, `video_id`, `claim_id`, `side`, `url`, `source_org`, `retrieved_at`, `snapshot_sha256`, `quoted_passage` (§6) |
| `collector_agreement.md` | — | collectors' folder labels vs. the derived label, with a reason per disagreement (generated, batch 1) |
| `external_agreement.md` | — | each batch-2 source's own label (fact-checker verdict or dataset label) vs. the derived label, with a reason per disagreement (generated) |
| `sources/batch2/`, `sources/batch2_selection.csv` | — | the URL lists batch 2 was downloaded from, and every file's source, selection and skip reason (`scripts/add_batch2.py`) |
| `transcripts/<video_id>.json` | video | speech segments with timestamps, OCR captions. **Text only — no media.** |

`videos.csv`, `claims.csv`, `reference_citations.csv`, `collector_agreement.md`
and `external_agreement.md` are **generated** — edit `scripts/labels.py` (batch
1 labels), `scripts/labels_b2_*.py` (batch 2 labels, quoted passages and
`external_reason`), `scripts/cite_references.py` (batch 1 quoted passages) or
`scripts/compare_collectors.py` (collector disagreement reasons), then run
`build_csvs.py`, `cite_references.py`, `compare_collectors.py`,
`compare_external.py` and `validate.py` in that order.

### Batches and sources

| Batch | videos | Source |
|---|---|---|
| 1 | v01–v82 | `mybox-selected.zip`, the collectors' bundle; `source = collector_bundle` |
| 2 | v83–v181 | fact-checked creator videos (`fact_checked_creator`), @malditobulo's own (`fact_checker_produced`), M4Health, MHMisinfo-Gold; see [PLAN.md](PLAN.md#batch-2-2026-11-23-fact-checked-and-dataset-videos-v83v181) |

`external_label` holds the source's own label **verbatim**: the fact-checker's
verdict (`external_source` = the fact-checker, `external_url` = the article)
or the dataset's label. It is a cross-check, never the label: `video_level_label`
is still derived from our own claims by §9. The split and the blind subset are
drawn per batch, so adding a batch never moves an earlier video.

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
| `UNSUPPORTED` | an **endorsed efficacy claim** (X cures, treats, prevents or reverses Y) where the search found nothing for or against |
| `INSUFFICIENT_EVIDENCE` | any other claim nothing tests directly, or what exists is too weak |
| `NOT_VERIFIABLE` | the claim can't be tested ("this tea feels amazing") |

**The most important rule: absence of evidence is not contradiction.** If no study
tests the claim, the verdict is `INSUFFICIENT_EVIDENCE`, never `CONTRADICTED`
(§7). Calling an untested claim false is overconfident, and §14 tracks it as its
own failure mode.

**`UNSUPPORTED` is not `CONTRADICTED`** (§7): it says "no evidence supports
this", never "this is false". In this set it is used only when all of these
hold: the speaker `ENDORSES` the claim; the claim is `treatment_efficacy` or
`prevention`; and the evidence shows nothing for or against (no citation on
either side, and no animal or in-vitro study either, which would make it "too
weak", so `INSUFFICIENT_EVIDENCE`). Claims about harm, side effects, mechanism,
statistics or vague wellness ("supports digestion", "boosts immunity") stay
`INSUFFICIENT_EVIDENCE`. `notes` opens with
`UNSUPPORTED (<category>): <reason>`; in `labels*.py` that is the claim's
`claim_category` and `unsupported_reason`.

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

### `claim_kind` (§4)

| Kind | Use when the claim is… |
|---|---|
| `research_question` | whether X works, causes or prevents Y — settled by studies |
| `fact_of_record` | a schedule, a legal or regulatory limit or action, a statistic, food composition, a diagnostic criterion, or textbook physiology — settled by an authoritative reference |

Retrieval picks its sources from this (§6): studies for research questions, the
reference allow-list (below) as well as PubMed for facts of record. A §6
reference URL may only be cited on a `fact_of_record` claim; `validate.py`
enforces it.

### `evidence_supporting` / `evidence_contradicting`

Semicolon-separated PMIDs (`PMID:12345678`) or URLs, listing papers and guidance
pages **you actually retrieved**. Never cite from memory, and never cite a paper
you have not looked at — §7: "It may only cite what was retrieved."

**URLs must be §6 references**, from the fixed allow-list in
`scripts/evidence.py` (`REFERENCE_SOURCES`): NCBI Bookshelf; CDC, WHO, NHS, ECDC;
FDA, EMA, EFSA; USDA FoodData Central; WHO GHO and national statistics offices.
Fetch them with `python scripts/evidence.py ref <url> [regex]`, which stores a
full-text snapshot with its SHA-256 and retrieval time under
`evidence_cache/reference/`. Then add the quoted passage to
`scripts/cite_references.py`; it writes `reference_citations.csv` and refuses
any passage that is not in the snapshot. FoodData Central records are JSON and
are quoted as `Nutrient: amount unit` (`evidence.snapshot_text`); the API URL
carries `api_key=DEMO_KEY`, api.data.gov's public demo key, not a secret.

The §6 verdict rules are the §7 ones: a reference supports `CONTRADICTED` only if
it says the claim is false or gives a conflicting figure. "No evidence that X"
or "not classified as" is still `INSUFFICIENT_EVIDENCE`.

Two retrieval limits met in practice: www.cdc.gov answers scripted requests with
HTTP 403 (its `wwwn.cdc.gov` / ATSDR pages work), and NCBI Bookshelf pages answer
with a reCAPTCHA. `fetch_reference` treats both as failures and never caches
them. PubMed indexes StatPearls chapters and MMWR reports, so their abstracts are
still reachable through `evidence.py search` / `abstract`.

`evidence.py` reads an optional `NCBI_EMAIL` environment variable for the
E-utilities contact address; no address is stored in the repo.

Retrieve through `scripts/evidence.py`, which calls PubMed E-utilities at no more
than 3 requests/second and caches every response under `evidence_cache/`, so the
retrieval is reproducible and the IDs are provably real.

Two columns, not one, because §11 treats "both supporting and contradicting
papers exist for a deciding claim" as a review trigger — a single merged column
cannot express that.

Both may be empty **only** when the verdict is `INSUFFICIENT_EVIDENCE`,
`UNSUPPORTED` or `NOT_VERIFIABLE`, and must be empty for `UNSUPPORTED`.
`validate.py` enforces this.

### `claim_source`, `start_seconds`, `end_seconds`

`claim_source` is `speech`, `screen` or `both` (§4: "Where each claim comes
from"). Timestamps come from the transcript segments the claim was taken from.
The modality track reads `claim_source` to find the screen-only claims that
decide whether OCR earns its cost.

### `video_level_label` (in `videos.csv`)

**Derived, not hand-assigned.** `scripts/judge.py` applies the §9 rules in order
and `scripts/validate.py` re-checks every row against them:

| If any claim… | Video label | `misinfo_basis` |
|---|---|---|
| is **endorsed** by the speaker and **contradicted** by the evidence | `MISINFO` | `contradicted` |
| otherwise, is **refuted** by the speaker but **supported** by the evidence | `MISINFO`, always reviewed | `denies_supported` |
| otherwise, is an **endorsed** efficacy claim the evidence leaves **unsupported** | `MISINFO` (shown as "MISINFO (unproven)"), always reviewed | `unproven` |
| otherwise, is **refuted** by the speaker and contradicted by the evidence | `DEBUNKING` | |
| otherwise, at least one claim was judged (`SUPPORTED` or `CONTRADICTED`) and nothing false is endorsed | `NO_MISINFO` | |
| otherwise, is **refuted** while the evidence is `MIXED` or `INSUFFICIENT_EVIDENCE` | `CANNOT_RECOGNIZE`, reviewed as a possible debunk | |
| no claim could be judged (all insufficient or not verifiable, or no claims) | `CANNOT_RECOGNIZE` | |

`misinfo_basis` (in `videos.csv`) is empty unless the label is `MISINFO`.

Order matters: a video that both endorses one falsehood and refutes another is
`MISINFO`, not `DEBUNKING`, and carries the `mixed` tag and the `mixed_video`
review reason — §9 lists it as a case the rules alone shouldn't settle.

`review_reasons` (semicolon-separated) first holds the reasons the §9 rules
collect from **every** claim, whichever rule decides the label:
`denies_supported:<claim>`, `unproven_claim:<claim>`,
`possible_debunk:<claim>` (refuted while `MIXED` or `INSUFFICIENT_EVIDENCE`,
so a debunk of an unsettled claim is flagged even when another claim makes the
video `NO_MISINFO`), `mixed_evidence:<claim>` (any `MIXED` claim), and
`mixed_video`. Then the §11 triggers on the **deciding** claims only:
`deciding_insufficient:<claim>`, `evidence_both_sides:<claim>`,
`unclear_stance:<claim>`. When no claim could be judged and none is refuted,
there is no deciding claim, so the rules add `nothing_judged` instead if any
claim is `INSUFFICIENT_EVIDENCE` (a person should see what could not be
checked, at LOW priority). A video with no claims, or only `NOT_VERIFIABLE`
ones, gets no reason. `validate.py` re-derives the column.

### Out of scope (§14)

A video with no health content is tagged `out_of_scope` — as its **only** tag —
and has no claims. It keeps the `CANNOT_RECOGNIZE` the rules give an empty video,
but it is left out of every count and metric so it cannot inflate
`CANNOT_RECOGNIZE`. Consumers must filter on the tag. `stats.py`, `validate.py`
and `compare_collectors.py` already do.

### `text_type`, `case_tags`, `split`

- `text_type`: `high_text` or `low_text`. Set from the OCR output — a video is
  `high_text` when on-screen text carries substantive content (burned-in
  subtitles, overlays, infographics). The modality track uses this to build the
  deliberate high/low mix `context/MODALITY.md` §6.1 asks for.
- `case_tags`: semicolon-separated, from the §14 hard-case table — `debunking`,
  `satire`, `mixed`, `screen_only`, `uncertain_science`, `noisy_audio`,
  `other_language`, `multi_claim`, `missing_evidence`, `prompt_injection`,
  `clearly_false`, `accurate`, `neutral_discussion`, `speech_screen_disagree`,
  plus `out_of_scope` (above) and `fact_checker_produced` (a fact-checker's own
  video, added by `build_csvs.py` from `video_index.csv`'s `source`).
- `split`: `tune` or `test`, roughly 30/70, **assigned per video** so no video
  appears in both (§14: "split by video, not by sentence"), drawn within each
  batch. Seed recorded in `REVIEW.md`.

### Review fields

On every row in both files: `annotator`, `confidence` (`low` / `medium` /
`high`), `review_status` (`pending` until a reviewer touches it), `reviewer`,
`reviewer_notes`. `annotator` names the process that produced the row
(`labelling_pipeline_v1`), never a person; people's names go only in
`reviewer`, once they have reviewed the row. See [REVIEW.md](REVIEW.md).

## What counts as a claim

A discrete, checkable health assertion, e.g. "X cures Y" or "Z causes W".

- **One assertion per row.** "Vitamin C prevents flu and cures pneumonia" becomes
  two claims.
- **Keep the meaning, including negation and qualifiers** — age group, dose,
  population, disease. "1000 mg a day for adults" is not the same claim as
  "vitamin C" (§4).
- **Quote, don't invent.** Stay close to the original words; never fill in
  missing context. Where the sentence starts with a pronoun whose referent is in
  an earlier segment, name the referent in **square brackets** —
  "[Fructose] produces more body fat" — so the row is readable on its own
  without inventing wording. Brackets are the only editorial addition allowed;
  `…` marks words dropped from the middle of a quote.
- **Separate quoting from asserting.** Record the claim either way; what the
  speaker does with it is `speaker_stance`'s job.
- **Each claim once, with all its sources.** Said and shown at the same moment is
  one claim with `claim_source = both`, not two claims.
- **A word the transcription plainly misheard** may be corrected in square
  brackets, keeping the transcribed form beside it or in `notes`
  ("colídeos [colirios]"). Batch 2's Spanish speech needed this; a quote of a
  non-word is not more faithful than the correction, as long as both are on
  the row.
- **Other languages: quote in the original.** A Spanish claim stays in Spanish,
  with an English gloss at the start of the claim's `notes` (`EN: …`), and the
  video is tagged `other_language`. Evidence is searched in English.

**Not a claim:** greetings, usernames, "follow for more", product names with no
health assertion, opinions ("I love this tea"), and questions without an
assertion.

If a video makes no checkable claims, leave it out of `claims.csv` and write
`no checkable claims` in its `notes` in `videos.csv`. It will come out as
`CANNOT_RECOGNIZE`. If it has no health content at all, tag it `out_of_scope`.

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
video_id,source_url,platform,topic,video_level_label,misinfo_basis,text_type,case_tags,split,annotator,confidence,review_status,reviewer,reviewer_notes,notes
v01,,tiktok,nutrition,MISINFO,contradicted,high_text,clearly_false;multi_claim,test,labelling_pipeline_v1,high,pending,,,"mixed: c1 accurate, c2 false"
v02,,tiktok,nutrition,DEBUNKING,,low_text,debunking,tune,labelling_pipeline_v1,high,pending,,,refutes the lemon water myth
```

`claims.csv`
```
video_id,claim_id,claim_text,claim_source,claim_kind,start_seconds,end_seconds,speaker_stance,claim_verdict,evidence_supporting,evidence_contradicting,annotator,confidence,review_status,reviewer,reviewer_notes,notes
v01,c1,<verbatim claim>,speech,research_question,3.5,8.0,ENDORSES,SUPPORTED,PMID:12345678,,labelling_pipeline_v1,high,pending,,,
v02,c1,Lemon water cures cancer,both,research_question,1.2,4.8,REFUTES,CONTRADICTED,,PMID:23456789,labelling_pipeline_v1,high,pending,,,
v03,c1,Atrazine has a regulatory limit of three parts per billion,speech,fact_of_record,37.1,44.8,ENDORSES,SUPPORTED,https://wwwn.cdc.gov/tsp/PHS/PHS.aspx?phsid=336&toxid=59,,labelling_pipeline_v1,high,pending,,,
```
