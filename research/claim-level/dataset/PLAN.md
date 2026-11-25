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
   (Revised 2026-11-25, T47: a sarcastic debunk with a clear target is now
   `REFUTES`; `UNCLEAR` keeps genuinely ambiguous tone. See README §5.)
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

## Revision: 2026-11-22 (revised target design §4, §6, §9, §14)

The target design was revised after the first batch, using what this set
exposed. Applied here:

- **§9 judge**: two new rules, in the doc's order. `REFUTES` + `SUPPORTED` →
  `MISINFO`, always reviewed; `REFUTES` + `MIXED`/`INSUFFICIENT_EVIDENCE` →
  `CANNOT_RECOGNIZE`, reviewed as a possible debunk. `judge()` now returns the
  review reasons too, recorded in `videos.csv` `review_reasons`.
- **§4 `claim_kind`** on every claim (`research_question` / `fact_of_record`).
- **§6 references** for facts of record: a fixed allow-list in `evidence.py`,
  full-text snapshots with SHA-256, and `reference_citations.csv` holding the
  URL, retrieval date and quoted passage. Nine claims were re-checked to a
  verdict or given new reference evidence. The rest were searched and stay put,
  with the reason in their notes.
- **§14 `out_of_scope`**: the 16 videos with no health content are tagged and
  excluded from every count and metric.
- **Collector comparison**: `collector_agreement.md`, generated. The
  collectors' labels are the Box folder each file sat in; no separate
  collector spreadsheet was supplied with the bundle.

## Batch 2: 2026-11-23 (fact-checked and dataset videos, v83–v181)

A second delivery of 164 files, `videos/new_<platform>_<id>.<ext>` (gitignored,
like the first). Same rules and pipeline as batch 1: §4 claims, §5 stance,
§6/§7 evidence and verdicts, §9 judge, §14 tags and split.

### Sources

`scripts/add_batch2.py` maps every file to its source by the **platform video
id** in its filename. It never matches on a handle, a title or a full URL
string. The lists it reads are copied, URLs only, into `sources/batch2/`:

| List | What it holds |
|---|---|
| `download_urls.txt`, `batch2_factcheck_urls.txt` | creator videos named in fact-check articles, plus @malditobulo's own videos |
| `batch2_m4health_tiktok_v2.txt`, `batch2_dataset_links.csv` | M4Health (Shang, Zenodo 10.5281/zenodo.19616866) and MHMisinfo-Gold (Nguyen et al., ICWSM 2025) ids, each with the dataset's label |
| `batch2_mhmisinfo_youtube.txt` | MHMisinfo-Gold YouTube URLs |
| `candidates_full.csv` | `candidates.csv` from `origin/data/fact-checked-candidates` (321 rows): fact-checker, verdict word for word, article URL |

163 files matched a list directly. One X/Twitter download is named after the
tweet that carries the media, not the status that was linked. yt-dlp's
metadata for the linked status resolves it, and the resolution is hard-coded
in `add_batch2.py` with the command that produced it.

`video_index.csv` gains `source`, `source_label`, `source_url`,
`external_label`, `external_source`, `external_url` and `duration_seconds`.
Batch-1 rows get `source = collector_bundle` with the collector folder as
`source_label`. Their `external_*` stays empty: `collector_agreement.md`
already covers them.

- **external_label** is the source's own label, verbatim and untranslated.
  For a fact-checked video that is `fact_checker_verdict`; for a dataset
  video it is the dataset's label (M4Health: `FALSE / <category>`;
  MHMisinfo-Gold: `-1`, the dataset's code for mental-health misinformation).
- **external_source** is the fact-checker (e.g. `Maldita.es`, `Lead Stories`)
  or the dataset name; **external_url** is the fact-check article.
- Matched: **98 of 99** selected videos. The exception is **v127**
  (`@farmaceuticofernandez/video/7255212264200998170`): no row in
  `candidates_full.csv` carries its id, so `external_label` is empty and
  `sources/batch2_selection.csv` says why.

### Selection

Recorded per file in `sources/batch2_selection.csv` (selected or not, and the
reason). Seed **`20261123`** (`SELECTION_SEED` in `add_batch2.py`). The
3-minute cap is applied before sampling.

| Source | Files | Over 3 min | Selected | Rule |
|---|---:|---:|---:|---|
| fact-checked creator videos | 70 | 4 | **66** | all |
| @malditobulo (fact-checker's own) | 14 | 0 | **5** | random 5, tagged `fact_checker_produced` |
| M4Health | 19 | 1 | **18** | all; non-health ones become `out_of_scope` |
| MHMisinfo-Gold | 61 | 0 | **10** | random 10 |
| **Total** | **164** | **5** | **99** | |

`video_id`s continue from v82: **v83–v181**, assigned over the 99 selected
files sorted by lowercased filename, the batch-1 rule.

### What changed in the pipeline, and why

- **Split and blind subset are drawn per batch** (`blind_subset.batch_of`).
  Drawing them over all 181 ids would have moved batch-1 videos between tune
  and test and replaced the blind subset REVIEW.md promises is fixed forever.
  Same seed, same 30/70 and 20% rules. Batch 1's split and subset are byte-for-byte
  unchanged.
- **`EVIDENCE_MIN_INTERVAL`** in `evidence.py`. Batch 2 was labelled by
  several processes at once, each throttled so that together they stay under
  PubMed's 3 requests/second.
- **Batch-2 labels live in `labels_b2_*.py`**, collected by
  `labels_batch2.py` and appended to `labels.LABELS`. They follow the same
  format, plus an optional `external_reason`.
- **Other languages.** About half of batch 2 is Spanish, French or Hindi,
  and nothing in batch 1 was. Claim text stays verbatim in the speaker's
  language (README: quote, don't invent), with an English gloss in `notes`
  (`EN: …`). PubMed is searched in English. EasyOCR stays English-only, as §2
  and batch 1 set it; Latin-script captions still read, and Devanagari
  captions do not, which is recorded per video where it matters.
- **`compare_external.py` → `external_agreement.md`**: the source's label
  against the derived label, verbatim and mapped. The mapping uses the
  candidates curator's `candidate_tags`, not the verdict wording. Every
  disagreement needs a written reason, as for the collectors.

### Results

| | Batch 1 | Batch 2 | Set |
|---|---:|---:|---:|
| videos | 82 | 99 | **181** |
| out_of_scope (excluded) | 16 | 3 (v153, v156, v158; all M4Health) | 19 |
| videos in scope | 66 | 96 | **162** |
| claims | 248 | 286 | **534** |
| MISINFO / NO_MISINFO / DEBUNKING / CANNOT_RECOGNIZE | 9 / 28 / 14 / 15 | 17 / 23 / 3 / 53 | 26 / 51 / 17 / 68 |
| tune / test (in scope) | 18 / 48 | 30 / 66 | 48 / 114 |

Batch 2 claim verdicts: 160 INSUFFICIENT_EVIDENCE, 63 SUPPORTED, 30
CONTRADICTED, 24 NOT_VERIFIABLE, 9 MIXED. Stances: 262 ENDORSES, 18 REFUTES,
3 QUOTES, 2 UNCLEAR, 1 NEUTRAL. 28 of the 96 in-scope videos carry a review
reason. `validate.py` passes with no errors or warnings.

**Agreement with the sources** (`external_agreement.md`): **19 / 89 (21%)**,
Cohen's kappa **0.07**, on the 89 in-scope videos whose source label implies
a video label. The disagreements fall into four groups:

- **The source says false; the evidence is silent (39, of which 14 are
  M4Health and 6 MHMisinfo-Gold).** A fact-checker or a dataset calls the
  video false, but no study tests its claims, so §7 makes
  them INSUFFICIENT_EVIDENCE and §9 gives CANNOT_RECOGNIZE. Examples: seawater
  cures, urine eye drops, the salt pregnancy test. This is the §7 rule doing
  what it is for. It is also the strongest argument in this set that
  "unjudgeable" needs its own review path rather than being read as "fine".
- **Debunks that never state the myth (9 → NO_MISINFO, 11 →
  CANNOT_RECOGNIZE).** Many fact-checked "debunk-side" creators explain or
  warn without stating and refuting a claim. Examples: the seven "glued
  beans" responses, where whether one clip shows beans is NOT_VERIFIABLE.
  §9 can only give DEBUNKING to a refuted, contradicted claim.
- **M4Health (0 / 15).** M4Health rates every video in this list `FALSE` for
  credibility, a scheme that also covers memes, adverts and motivational
  clips. 12 of the 15 in-scope videos assert nothing checkable.
- **Real disagreements on the evidence**, each with a reason in
  `labels_b2_*.py`. Example: v109 is a "be careful with Ozempic" video that
  Maldita files as a warning. It lists stroke, seizures and new diabetes as
  risks, and trials show semaglutide lowers those.

### Caveats a reviewer needs

- **Not labelled blind to the source.** Batch 2 was labelled by four
  parallel workers that inherited a context in which every source verdict and
  candidate tag had already been printed. They were told not to consult the
  source label until a video was labelled, but they had seen it. Any bias this
  introduced would push towards agreement, so 21% is unlikely to be an
  underestimate. It does mean the batch-2 blind subset in REVIEW.md (20 videos,
  same seed) has to be labelled by a second person before batch-2 labels count
  as independent.
- **Checked after labelling.** All 30 CONTRADICTED claims were re-read
  against the titles of their cited papers. Two were changed: v109 c6
  (pancreatitis, null meta-analyses of a rare labelled event →
  INSUFFICIENT_EVIDENCE) and v124 c5 (four diseases contradicted on MS
  evidence alone → split per disease). Three grouped lists (v113 c1, v124 c5,
  v126 c6) were split one assertion per row. v87 c2 was MIXED with evidence on
  one side only and is now INSUFFICIENT_EVIDENCE.
- **Transcription.** Spanish Whisper output needed bracketed corrections
  (README: a plainly misheard word). v167 (Hindi) is garbled, tagged
  `noisy_audio`, every claim low confidence. EasyOCR missed its Devanagari
  captions.
- **v145, v146** have no speech and almost no readable text. They are
  `no_claims` rather than `out_of_scope` because health content could not be
  ruled out from text; someone should look at the video.

## Revision: 2026-11-23 (§7 UNSUPPORTED, §9 unproven rule)

Applied from `docs/target-system-design.md` on `origin/langgraph-build`.

- **§7 `UNSUPPORTED`.** All 223 endorsed `INSUFFICIENT_EVIDENCE` claims were
  re-read (the 32 with any other stance were left alone, since the rule needs
  `ENDORSES`). A claim became `UNSUPPORTED` only if it is a `treatment_efficacy`
  or `prevention` claim and the evidence shows nothing for or against: no
  citation on either side, and no animal or in-vitro study in its notes (that
  makes it "too weak", so it stays `INSUFFICIENT_EVIDENCE`). **18 claims in 9
  videos** changed: v20 c1–c4, v37 c4, v84 c1, v86 c1, v113 c1–c4 and c6,
  v141 c1–c2, v143 c1–c2, v149 c2, v164 c4. Each has
  `UNSUPPORTED (<category>): <reason>` at the start of its notes. The dataset
  had no `claim_category` column, so the category was judged by hand from the
  claim text and recorded only on the changed claims.
- **Left as `INSUFFICIENT_EVIDENCE`, on purpose:** harm and side-effect claims,
  mechanisms, statistics, diagnostic claims (v136's salt pregnancy test),
  vague wellness ("supports digestion", "boosts immunity": v138, v155, v149
  c1/c3/c4), and efficacy claims with weak evidence on record (v92 grounding
  and v35 miso have animal studies, v106 garlic has in-vitro work, v167 and
  v168 cite reviews that find too little). v72's TUDCA claim was never searched
  under its real name (Whisper heard "cut cut"), so the search is not
  exhausted and §7 does not allow `UNSUPPORTED` yet.
- **§9 judge.** `judge()` now returns `(label, misinfo_basis, deciding,
  reasons)`, with the unproven rule after `denies_supported` and before
  `DEBUNKING`. Review reasons are collected from every claim
  (`denies_supported`, `unproven_claim`, `possible_debunk`, `mixed_evidence`,
  `mixed_video`); the §11 triggers apply to deciding claims only, with the
  old "deciding or all claims" fallback dropped. `videos.csv` gains
  `misinfo_basis`.
- **`annotator`** is `labelling_pipeline_v1` on every row; `reviewer` stays
  empty until a person reviews.
- **`compare_external.py`** reports M4Health on its own line, outside the main
  agreement number.

**Effect.** In-scope labels went from MISINFO 26 / NO_MISINFO 51 / DEBUNKING 17
/ CANNOT_RECOGNIZE 68 to 33 / 50 / 17 / 62. Seven videos changed, all to MISINFO
with basis `unproven`: v20, v84, v113, v143, v149, v164 (from
CANNOT_RECOGNIZE) and v141 (from NO_MISINFO). v37 and v86 gained `UNSUPPORTED`
claims but were already MISINFO on a contradicted claim. Agreement with the
source label, M4Health excluded, went from 19/74 (kappa 0.10) to 23/74 (kappa
0.13); M4Health alone from 0/15 to 1/15. Collector agreement (batch 1) went
from 25/39 to 26/39 (v20).

**Review load moved.** Videos with any review reason: 43 → 41 of 162. 27 left
review: CANNOT_RECOGNIZE videos whose claims are all insufficient have no
deciding claim, so without the fallback no §11 trigger fires (v29 also loses
its UNCLEAR-stance flag this way). 25 joined, mostly through
`possible_debunk` and `mixed_evidence` now being collected from every claim.
The design may want "no claim could be judged" as an explicit review reason;
that is a question for §11, not changed here.
