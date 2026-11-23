# Project state and open decisions

The working memory for the coordinating session. It is rewritten whenever something important changes, so any session (or person) can pick the project up from here.
**Last updated:** 2026-11-24 (UTC), by the coordinating session.

How to use it:
- **Pick up work:** read this file first, then `automation/BUILD_QUEUE.md` (tasks) and `context/MULTI_AGENT.md` (decisions log).
- **Keep it current:** update it after every decision, merge, or finished task, and before a long conversation is condensed.
- **Scope:** for state and open questions only. Settled design lives in `docs/target-system-design.md`.

---

## 1. Decisions waiting on the project lead

| # | Decision | Recommendation | Status |
|---|---|---|---|
| D1 | **Untested health claims** (source says false, no study tests it; 39 golden-set videos). **A:** keep CANNOT_RECOGNIZE and send to review with high severity. **B:** new verdict UNSUPPORTED for *endorsed efficacy/treatment claims* with no evidence, so the video becomes "MISINFO (unproven claim)" | **B**: matches how fact-checkers and WHO judge such videos, and is labelled "unproven", not "disproven" | **Waiting on T25.** If extra sources resolve about half or more, skip B |
| D2 | Golden set `annotator` column says `pranav` on rows drafted by the labelling session. It should be neutral (e.g. `labelling_pipeline_v1`), with people's names only in `reviewer` | Fix before the blind review | Not yet sent to the local labelling session |
| D3 | Exclude **M4Health** from the external-agreement number. Its "FALSE" credibility label covers memes and adverts, and agreement is 0/15 | Exclude, but report it separately | Not done |
| D4 | Backend flags weak evidence on *non-deciding* claims for review (v64, v65; beyond §11's wording) | **Keep**: it only adds review, never removes it | Recommended; lead hasn't objected |
| D5 | Queue a **staging-prep task** for the demo to Dr. Brooks: Railway staging configuration, deploy checklist, script to pre-run demo videos | Yes, if the demo is in the next few days | Offered, not answered |
| D6 | Frontend designs: the lead will share Claude Design output | On receipt, review against the brief, map to the API, split into build tasks | Waiting on the designs |

Already decided (recorded here so they aren't asked again):
- Review reasons are collected from every claim, whatever rule sets the label. Mixed videos are MISINFO and always reviewed (§9; T21).
- Severity HIGH/MEDIUM/LOW sets review priority only (§12; T22). The table is a **draft** until the lead and Dr. Brooks sign it off and WHO confirms it.
- Regulatory claims ("banned in Europe") are **out of scope for now** (§4).
- Whisper stays on the hosted API at current scale.
- Calibration: Platt scaling (T15, after T14).
- Separate API keys per place (prod on Railway, dev in local `.env`, eval in the `infodemic-monitor` environment). A $20 prepaid balance acts as the cap, with auto-recharge off.

## 2. Waiting on the project lead to merge (into `langgraph-build`)

Nothing waiting. #70 (T22 severity), #71 (T24 judge cross-check) and #72 (T23 CI) were merged on 2026-11-24. CI (`pytest` with Postgres + pgvector) now runs on every PR to `langgraph-build` and `main`. GitGuardian flagged a dummy test-database password from #72's first commit; the final version has none.

## 3. Running now

- **T25** (orchestrator child): do Europe PMC, Cochrane, ClinicalTrials.gov and WHO/NHS/CDC guidance resolve the 39 "source false, evidence silent" videos? Report only. Its answer feeds D1.

## 4. Other open PRs

- **#62 golden set** (`data/golden-label-set`): **181 videos (162 in scope, 19 out of scope), 534 claims.** Labels MISINFO 26 / NO_MISINFO 51 / DEBUNKING 17 / CANNOT_RECOGNIZE 68. All rows `pending`.
  - Agreement with source labels: 21% (kappa 0.07).
  - Before merging: D2 fix, the judge.py update to match revised §9 (prompt in the coordinating session's history; summary below), and the human blind review (16 batch-1 + 20 batch-2 videos in `REVIEW.md`).
  - Merge with **Squash and merge**, because an early commit holds the lead's email.
- **#65 candidates:** don't merge. Its content is copied into #62 (`sources/batch2/`). **Close it** once #62 is merged.

Golden-set `judge.py` update to send to the local session (after D2): collect `denies_supported` and `possible_debunk` from every claim; add a `mixed_video` reason; treat any MIXED claim as a review trigger; drop the `deciding or claims` fallback for UNCLEAR and conflict triggers. Then regenerate `review_reasons` and rerun `validate.py`. Labels must not change.

## 5. Project lead's own to-do list

1. Rotate the OpenAI key that appeared in a local transcript.
3. Send the design prompt to Claude Design (D6).
4. Organise the blind review of the golden set (#62).
5. Staging run before any demo: separate Railway environment and Supabase dev project (or the #47 isolated schema), migrations 0006–0011, pgvector, `USE_GRAPH_PIPELINE` on there only.
6. Merge `langgraph-build` into `main` (not yet). Next: open a **draft** PR `langgraph-build` → `main` for Jared to review (one approving review is required); run staging first, because the API runs migrations on startup (`RUN_MIGRATIONS=true`), so merging to `main` would apply 0006–0011 to the production Supabase database; back up production; then merge with **Create a merge commit** (keeps per-task history).
7. Refresh the CDC stored snapshots about monthly (T19).

## 6. Blocked tasks

- **T14** evaluation vs baseline: needs the reviewed golden set (and D1 settled, since D1 changes labels).
- **T15** calibration: needs T14.

## 7. Key facts and numbers

- **Real cost and speed (T18):** graph median **$0.41 and 76 s per video**; single-call baseline $0.0026 and 1.5 s. A T14 run on the test split (~114 in-scope videos) is roughly $45–50, more than the $20 balance.
- **Tests:** about 990 passing on `langgraph-build` (independently re-run). CI arrives with #72.
- **Demo to Dr. Brooks:** feasible in 2–3 days as a progress demo (pipeline, real claims and evidence, basic job page). No accuracy numbers yet, and the full UI is not built.
- **WHO demo:** first week of December. Needs the frontend and a first accuracy number.

## 8. Where things are

| Thing | Location |
|---|---|
| Repo | `PranavCR01/infodemic-monitor`; integration branch `langgraph-build` (never auto-merged to `main`) |
| Design (source of truth) | `docs/target-system-design.md`; editable artifact https://claude.ai/artifact/SEYkNy1QMyqtix15pnmVYY (keep both in sync) |
| Build queue / orchestrator rules | `automation/BUILD_QUEUE.md`, `automation/ORCHESTRATOR.md`, `automation/TASK_PROMPT.md` |
| Orchestrator session | `session_013cWxq1xr2wMZ2m7f1Z5MU8` (hourly safety check, scheduled task `trig_01Rtmdgu8Bhq94pzYWvNdvvL`) |
| Coordinating session | `session_01KCUfq8FMGcfrX5Yz8FhZxe`; the orchestrator and children report here |
| Environments | `infodemic-monitor` (`env_01JA2Saj4x8sggokuxovPM68`): PubMed, references, Europe PMC, ClinicalTrials.gov, eval keys (`EVAL_ANTHROPIC_API_KEY` + OpenAI network secret). `infodemic-video-sourcing` (`env_011urkFTKL57KUCLxmHaWuxu`): fact-check sites, no keys. `Default`: shared with other projects, avoid |
| Task rules | Build tasks open PRs into `langgraph-build` and **do not self-merge**; the lead merges. No real API spend without the lead's direct approval in the orchestrator session |
| Local machine | Windows, `D:\Python files\infodemic-monitor`; videos in `research/claim-level/dataset/videos/` (gitignored); Box zip in `D:\Python files\labelling-data\` |
