# Project state and open decisions

The working memory for the coordinating session. It is rewritten whenever something important changes, so any session (or person) can pick the project up from here.
**Last updated:** 2026-11-24 (UTC), after D1, by the coordinating session.

How to use it:
- **Pick up work:** read this file first, then `automation/BUILD_QUEUE.md` (tasks) and `context/MULTI_AGENT.md` (decisions log).
- **Keep it current:** update it after every decision, merge, or finished task, and before a long conversation is condensed.
- **Scope:** for state and open questions only. Settled design lives in `docs/target-system-design.md`.

---

## 1. Decisions waiting on the project lead

| # | Decision | Recommendation | Status |
|---|---|---|---|
| D2 | Golden set `annotator` column says `pranav` on rows drafted by the labelling session. It should be neutral (e.g. `labelling_pipeline_v1`), with people's names only in `reviewer` | Fix before the blind review | Prompt given to the lead for the local labelling session (combined with the D1 re-derivation) |
| D3 | Exclude **M4Health** from the external-agreement number. Its "FALSE" credibility label covers memes and adverts, and agreement is 0/15 | Exclude, but report it separately | In the same local-session prompt |
| D5 | Queue a **staging-prep task** for the demo to Dr. Brooks: Railway staging configuration, deploy checklist, script to pre-run demo videos | Yes, if the demo is in the next few days | Offered, not answered |
| D6 | Frontend: Claude Design export goes into `design/claude-design/` on branch `design/frontend-v1` (brief: `design/BRIEF.md`). Frontend session `session_013cWxpynpigJCrZtXuYokiD` (env infodemic-video-sourcing, no keys) reviews, maps to the API, proposes a plan, then builds via PRs into `design/frontend-v1` (no self-merge) | Approve its plan; backend gaps it finds become queue tasks | Waiting on the lead's upload |

Already decided (recorded here so they aren't asked again):
- **D4 dropped (2026-11-24, lead chose B):** weak-evidence review triggers fire only for deciding claims (§11 as written). The backend was sending 135/162 golden videos (83%) to review vs the golden set's 68 (42%). Also: nothing_judged never lowers a case's severity (the LOW pin in #99 was a coordinating-session spec error). Both applied in #99 (T37).
- **D7 frontend (2026-11-24, all approved):** backend HIGH/MEDIUM/LOW with the blind "your judgement first" step for HIGH only; reason code + note on every decision, no separate MARK_INSUFFICIENT; keep "Not required" status; upload limit 3 min (PR #77); two-column result first, margin notes last; keep "CANNOT RECOGNIZE" with the reason underneath; T31 How we searched, T32 Request review; T29 = playback URL only (export client-side); queue position and evaluation pages later; feedback button dropped.
- **D1 = B (2026-11-24): unproven-claim verdict.** New verdict UNSUPPORTED, only for *endorsed* `treatment_efficacy`/`prevention` claims after the full retrieval budget finds nothing. Judge: after denies-supported, before DEBUNKING → MISINFO with `misinfo_basis: unproven`, shown as "MISINFO (unproven)", always reviewed. Harm/mechanism claims with no evidence stay INSUFFICIENT_EVIDENCE. T25 confirmed extra sources don't help (0 of 39 videos resolved). Design doc §7/§9/§11 updated (repo + artifact). Backend: T30. Golden set: re-derive labels in the local session.
- Review reasons are collected from every claim, whatever rule sets the label. Mixed videos are MISINFO and always reviewed (§9; T21).
- Severity HIGH/MEDIUM/LOW sets review priority only (§12; T22). The table is a **draft** until the lead and Dr. Brooks sign it off and WHO confirms it.
- Regulatory claims ("banned in Europe") are **out of scope for now** (§4).
- Whisper stays on the hosted API at current scale.
- Calibration: Platt scaling (T15, after T14).
- Separate API keys per place (prod on Railway, dev in local `.env`, eval in the `infodemic-monitor` environment). A $20 prepaid balance acts as the cap, with auto-recharge off.


Owner column gap (found by the frontend session, confirmed): videos/jobs had no owner_id, so ownership checks couldn't work. Assigned to T27; T26 and T28 told not to add one.

## 2. Waiting on the project lead to merge

- **#94** T33 ownership (into `langgraph-build`): updated by the coordinating session (migration 0014 → 0013, one head).
- **Frontend stack** into `design/frontend-v1`, **Create a merge commit** (stacked PRs): #79 → #82 → #85 → #87 → #88 → #89 → #90 → #91 → #92 → #93. #75 merged.
- Merged 2026-11-24: #73, #74, #76, #77, #78, #80 (T29), #81 (T28), #83 (T32), #84 (T31), #86 (T30).
- Migration chain on `langgraph-build`: 0011 T28 → 0012 T31 → 0013 T30 → 0014 T33 (#94) → 0015 T36 (running).
- Vercel free plan hit 100 deployments/day; recommended Ignored Build Step `git diff HEAD^ HEAD --quiet -- .` (lead to set).
- Lead to-do (Supabase): auth redirect URLs; own `app_metadata.role = admin`; storage bucket CORS for browser PUTs from the frontend origin.
- Before merging to `main`: production jobs have no owner; run T33's `scripts/assign_owners.py` in the staging run plan.
- Open question to the lead: add a review reason for "nothing could be judged" (27 golden-set videos left review after the judge change). Recommended yes, LOW priority.

## 3. Running now

- **T36** (traceable analysis version). Queued: T34 (after #94).
- **Frontend session**: holding; swaps adapters as backend tasks merge. Remaining plan items deferred (margin notes) or held (evaluation page until T14).

## 4. Other open PRs

- **#62 golden set** (`data/golden-label-set`): **181 videos (162 in scope, 19 out of scope), 534 claims.** Labels MISINFO 26 / NO_MISINFO 51 / DEBUNKING 17 / CANNOT_RECOGNIZE 68. All rows `pending`.
  - Agreement with source labels: 21% (kappa 0.07).
  - Before merging: D2 fix, the judge.py update to match revised §9 (prompt in the coordinating session's history; summary below), and the human blind review (16 batch-1 + 20 batch-2 videos in `REVIEW.md`).
  - Merge with **Squash and merge**, because an early commit holds the lead's email.
- **#65 candidates:** don't merge (its content is in #62's `sources/batch2/`). The lead keeps it open for now (2026-11-24); revisit after #62.

Golden-set `judge.py` update (now part of the combined local-session prompt, which also adds UNSUPPORTED): collect `denies_supported` and `possible_debunk` from every claim; add a `mixed_video` reason; treat any MIXED claim as a review trigger; drop the `deciding or claims` fallback for UNCLEAR and conflict triggers. Then regenerate `review_reasons` and rerun `validate.py`. Labels must not change.

## 5. Project lead's own to-do list

1. Rotate the OpenAI key that appeared in a local transcript.
3. Send the design prompt to Claude Design (D6).
4. Organise the blind review of the golden set (#62).
5. Staging run before any demo: separate Railway environment and Supabase dev project (or the #47 isolated schema), migrations 0006–0011, pgvector, `USE_GRAPH_PIPELINE` on there only.
6. Merge `langgraph-build` into `main` (not yet). Next: open a **draft** PR `langgraph-build` → `main` for Jared to review (one approving review is required); run staging first, because the API runs migrations on startup (`RUN_MIGRATIONS=true`), so merging to `main` would apply 0006–0011 to the production Supabase database; back up production; then merge with **Create a merge commit** (keeps per-task history).
7. Refresh the CDC stored snapshots about monthly (T19).

## 6. Blocked tasks

- **T14** evaluation vs baseline: needs the reviewed golden set, re-derived with UNSUPPORTED, and T30.
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
