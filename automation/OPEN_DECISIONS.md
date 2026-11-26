# Project state and open decisions

The working memory for the coordinating session. It is rewritten whenever something important changes, so any session (or person) can pick the project up from here.
**Last updated:** 2026-11-26 (UTC), after T49 merged and the DOI-evidence decision, by the coordinating session.

How to use it:
- **Pick up work:** read this file first, then `automation/BUILD_QUEUE.md` (tasks) and `context/MULTI_AGENT.md` (decisions log).
- **Keep it current:** update it after every decision, merge, or finished task, and before a long conversation is condensed.
- **Scope:** for state and open questions only. Settled design lives in `docs/target-system-design.md`.

---

## 1. Decisions waiting on the project lead

| # | Decision | Recommendation | Status |
|---|---|---|---|
| D2 | Golden-set `annotator` column names a person on model-drafted rows | Neutral value (`labelling_pipeline_v1`) | With the lead's local session |
| D3 | Exclude M4Health from the external-agreement number | Exclude, report separately | With the lead's local session |

Already decided (recorded here so they aren't asked again):
- **Production, no staging (lead, 2026-11-25).** Supabase project 'sentinel' (kscfszhdrlsbpsqwfirv) was an unrelated app: exported (sent to the lead) and wiped, renamed **infodemic-prod**. Done: pgvector 0.8.2, private 'videos' bucket (100 MB, mp4/mov), sign-ups disabled, site URL https://infodemic-monitor.vercel.app, redirects <site>/auth/callback + localhost, lead invited as admin. Tables are created by the API's migrations on first start. Blocker: T48 (project signs ES256; backend accepted HS256 only). Lead to revoke the Supabase access token after the first deploy. Ops session runs in environment 'infodemic-monitor-ops' (api.supabase.com only).
- **Golden-set review (2026-11-24):** no human blind review. Instead a blind model re-label of the 41-video sample (session_013cWxq3GcesFJeRxR6AiPtT, branch data/blind-relabel-model), with the lead adjudicating only the disagreements. Report it as model-assisted review, with model-model agreement and the lead adjudicating; never as human inter-annotator agreement. T14 must state this caveat.
- **D4 dropped (2026-11-24, lead chose B):** weak-evidence review triggers fire only for deciding claims (§11 as written). The backend was sending 135/162 golden videos (83%) to review vs the golden set's 68 (42%). Also: nothing_judged never lowers a case's severity (the LOW pin in #99 was a coordinating-session spec error). Both applied in #99 (T37).
- **D7 frontend (2026-11-24, all approved):** backend HIGH/MEDIUM/LOW with the blind "your judgement first" step for HIGH only; reason code + note on every decision, no separate MARK_INSUFFICIENT; keep "Not required" status; upload limit 3 min (PR #77); two-column result first, margin notes last; keep "CANNOT RECOGNIZE" with the reason underneath; T31 How we searched, T32 Request review; T29 = playback URL only (export client-side); queue position and evaluation pages later; feedback button dropped.
- **D1 = B (2026-11-24): unproven-claim verdict.** New verdict UNSUPPORTED, only for *endorsed* `treatment_efficacy`/`prevention` claims after the full retrieval budget finds nothing. Judge: after denies-supported, before DEBUNKING → MISINFO with `misinfo_basis: unproven`, shown as "MISINFO (unproven)", always reviewed. Harm/mechanism claims with no evidence stay INSUFFICIENT_EVIDENCE. T25 confirmed extra sources don't help (0 of 39 videos resolved). Design doc §7/§9/§11 updated (repo + artifact). Backend: T30. Golden set: re-derive labels in the local session.
- Review reasons are collected from every claim, whatever rule sets the label. Mixed videos are MISINFO and always reviewed (§9; T21).
- Severity HIGH/MEDIUM/LOW sets review priority only (§12; T22). The table is a **draft** until the lead and Dr. Brooks sign it off and WHO confirms it.
- Regulatory claims ("banned in Europe") are **out of scope for now** (§4).
- Whisper stays on the hosted API at current scale.
- Calibration: Platt scaling (T15, after T14).
- Separate API keys per place (prod on Railway, dev in local `.env`, eval in the `infodemic-monitor` environment). A $20 prepaid balance acts as the cap, with auto-recharge off.
- **D8 search quality bar (lead, 2026-11-26):** T50 must report tune-split search recall (strict: golden-cited PMID kept; lenient: or an on-topic kept record), target lenient ≥ 80%, and add a CI regression set of real production misses. Still to queue after T50: production search-health metrics and reviewer MISSING_SOURCE → regression case.
- **Evidence by DOI (lead, 2026-11-26):** when PubMed doesn't have a paper yet, a journal page cited by DOI (verified via Crossref, with a text snapshot) is acceptable evidence. Web search may *find* studies, but only records we verify (PMID via E-utilities, DOI via Crossref) become evidence; web text never does. T50 (i).
- **Unproven guard (T49, merged #121, 2026-11-26):** UNSUPPORTED stands only if retrieval kept a record on topic for the claim's intervention; otherwise INSUFFICIENT_EVIDENCE → CANNOT_RECOGNIZE + nothing_judged. Cause: prod labelled an accurate vitamin K video MISINFO (unproven). Effect today: all 5 tune unproven videos lose the label because their searches were broken; T50 should restore real ones.
- **Production deploy (lead, 2026-11-25):** directly on prod, no staging; Jared not involved.

## 2. Waiting on the project lead

- Done 2026-11-26: release #123 (T49 + T52) merged to `main` and live on API and worker (c1187b2).
- **Revoke the temporary tokens** used for the deploy (Supabase PAT, Railway project token, Vercel token) once deploy work is finished.
- T14 accuracy run on the test split (~$45–50): needs an Anthropic top-up and approval in the orchestrator. Better after T50, since search quality now dominates accuracy.

## 3. Running / queued

- **T50** search rewrite (todo, starts now T49 is merged): keep 'vitamin K'; MeSH gaps; LLM query assistant; distinct broader query per round; citation lookup; no 8-word AND fallback; (g) store screened-out papers; (h) translate non-English claims + re-run T49 replay; (i) web find-the-study with PMID/DOI verification. Paid calls need a cap approved in the orchestrator.
- **T51** extraction: evidence-strength statements are not efficacy claims (todo, after T49).
- Done today: T49 (#121), T52 (#119), /health Redis fix (#120, on `main`; prod /health = healthy).

## 4. Production (live since 2026-11-25)

- **Frontend:** Vercel `infodemic-monitor.vercel.app` (root `frontend`).
- **API + worker:** Railway project `340ecd09…`, services `infodemic-monitor` (API, `infodemic-monitor-production.up.railway.app`, runs migrations on start) and `worker` (Celery, `RUN_MIGRATIONS=false`; auto-deploy on `main` enabled by the lead 2026-11-26, it had none before, so it missed #120 until redeployed by hand), plus Railway Redis (`REDIS_URL=${{Redis.REDIS_URL}}` on both). `USE_GRAPH_PIPELINE=true`.
- **Supabase infodemic-prod** (`kscfszhdrlsbpsqwfirv`): Postgres + pgvector, migrations 0001–0016, private `videos` bucket, ES256 auth (T48 JWKS), sign-ups disabled; lead is admin.
- `PUBMED_RESULTS_PER_CLAIM=2` on Railway is read only by the legacy single-call path; harmless, left as is.
- First real runs (2026-11-26): `Download.mp4` and `Download (4).mp4` (vitamin K, job 5cc07f48). Both exposed search failures → T49–T52.

## 5. Project lead's own to-do list

1. Rotate the OpenAI key that appeared in a local transcript.
2. Revoke the deploy tokens (see §2).
3. Refresh the CDC stored snapshots about monthly (T19).
4. Severity table sign-off with Dr. Brooks (draft until then).

## 6. Blocked tasks

- **T14** evaluation vs baseline: needs funding approval; best run after T50.
- **T15** calibration: needs T14.

## 7. Key facts and numbers

- **Golden set** (in `langgraph-build`, = data/golden-label-set @ 948b1c2, keep that branch): 162 in-scope videos, 550 claims; NO_MISINFO 47 / CANNOT_RECOGNIZE 59 / MISINFO 39 (26 contradicted, 12 unproven, 1 denies_supported) / DEBUNKING 17; 71 in review; tune 48 / test 114. 315 claims cite a PubMed paper (basis for search recall). Model-assisted review, never "human inter-annotator agreement".
- **Routing (T38, tune):** extract Sonnet 0.42 > Haiku > Luna; stance Sonnet 0.64; verify Opus 0.68. Proposed routing_v2 Sonnet/Sonnet/Opus. T45 added extract_v3 / stance_v2 and a `use_ocr` switch.
- **Cost/speed (T18):** graph median $0.41 and 76 s per video; vitamin K prod run 105 s.
- **Tests:** ~1700 passing on `langgraph-build`; CI on every PR.
- **WHO demo:** first week of December.

## 8. Where things are

| Thing | Location |
|---|---|
| Repo | `PranavCR01/infodemic-monitor`; integration branch `langgraph-build` (never auto-merged to `main`); `main` = production, needs 1 approving review (lead merges with bypass) |
| Design (source of truth) | `docs/target-system-design.md`; editable artifact https://claude.ai/artifact/SEYkNy1QMyqtix15pnmVYY (keep both in sync) |
| Build queue / orchestrator rules | `automation/BUILD_QUEUE.md`, `automation/ORCHESTRATOR.md`, `automation/TASK_PROMPT.md` |
| Orchestrator session | `session_013cWxq1xr2wMZ2m7f1Z5MU8` (hourly safety check, scheduled task `trig_01Rtmdgu8Bhq94pzYWvNdvvL`) |
| Coordinating session | `session_01KCUfq8FMGcfrX5Yz8FhZxe`; the orchestrator and children report here |
| Environments | `infodemic-monitor` (`env_01JA2Saj4x8sggokuxovPM68`): PubMed, references, Europe PMC, ClinicalTrials.gov, eval keys (`EVAL_ANTHROPIC_API_KEY` + OpenAI network secret). `infodemic-video-sourcing` (`env_011urkFTKL57KUCLxmHaWuxu`): fact-check sites, no keys. `Default`: shared with other projects, avoid |
| Task rules | Build tasks open PRs into `langgraph-build` and **do not self-merge**; the lead merges. No real API spend without the lead's direct approval in the orchestrator session |
| Local machine | Windows, `D:\Python files\infodemic-monitor`; videos in `research/claim-level/dataset/videos/` (gitignored); Box zip in `D:\Python files\labelling-data\` |
