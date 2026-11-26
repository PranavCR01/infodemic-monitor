# T67: critic-budget, thin-contradiction and analysis-incomplete label rules

> **Result: changes 1 and 2 were built and are switched OFF.** Each made at least one tune
> label worse on the offline replay, and the lead's gate was "ship a change only if it
> makes no tune label worse".
>
> **Change 3 (`analysis_incomplete`, lead addendum) ships ON.** It changes no tune label
> (it fires on none of them), and it turns production job 3d48e75e into CANNOT RECOGNIZE.
>
> These are development numbers on the TUNE split, not product accuracy. No model calls
> were made ($0), no migration was needed, and the test split was not read.

## What was built

| | change 1: keep verdict when the critic budget runs out | change 2: thin contradictions can't decide |
|---|---|---|
| Where | `routing.verdicts_for_judge`, `routing.second_check_disagreed_ids`, `routing.verdict_hard_failure`; review rule `second_check_disagreed` | `judge.thin_contradiction`, `judge.decide` (rules 1, 4 and 5) |
| Switch (default) | `routing.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED = False` | `judge.THIN_CONTRADICTION_RULE = False` |
| When on | The budget runs out with the critic still objecting. The judge keeps the stored verdict, and the critic's issues are added to the verdict's limitations. Review reason: `second_check_disagreed:<cid>`. Withdrawal stays only for hard failures: a cited record that was not retrieved for the claim, a `guardrail:` error for the claim, or a retryable verifier error. | An ENDORSES or REFUTES + CONTRADICTED claim decides only if its contradicting records include ≥2 that pass T49's on-topic check, or ≥1 systematic review / RCT / guideline. Otherwise the verdict stays but the claim does not decide, and the label falls through. Review reason: `judge:thin_contradiction:<cid>`. |
| Plain text | "A second automated check still disagreed with the verdict on this claim…" (backend `REASON_TEXT`, frontend `REVIEW_REASONS`) | "The evidence against this claim is too thin to decide the label on its own…" |

**Change 3: `analysis_incomplete` (lead addendum, ~23:00 UTC)**
- **Where:** `judge.analysis_incomplete`, checked in `judge.decide` before rule 1.
- **Switch:** `judge.ANALYSIS_INCOMPLETE_RULE = True`, i.e. on.
- **Rule:** the verifier failed (`verification_failed`: a retryable `verify_claims` error, the same signal as the existing `verification_failed:<cid>` flag) for ≥50% of the verifiable claims. The label is then CANNOT_RECOGNIZE, with rule `analysis_incomplete` and the video-level review reason `judge:analysis_incomplete`. Other rule reasons are still collected.
- **Plain text:** "The evidence check could not run for at least half of the claims, so the video could not be assessed…" (backend, frontend reason and decision-rule text).
- **Regression, production job 3d48e75e:** `backend/app/tests/fixtures/prod_3d48e75e/vitamin_k_verifier_down.report.json` (commit 033dbed).
  - The fixture is the coordinator's. Its provenance says it was **built from the exported report, not raw DB rows**: the coordinator's DB access had been revoked.
  - It is used as committed: claim text, stance, verdict, cited record, and `verification_failed` mapped to the retryable verifier error the pipeline records. No other field is invented.
  - Without the rule it reproduces production: NO_MISINFO by `judged_nothing_false_endorsed`, decided by c3 (SUPPORTED).
  - With the rule: **CANNOT_RECOGNIZE (`analysis_incomplete`)**, 10 of 11 claims failed, sent to review.

## Gate: offline replay (`backend/scripts/t67_label_rules_replay.py`)

- **A. T66 stored states:** the 18 finished videos in `evals/reports/T66/videos/*.json` on `origin/auto/T66` @ 72633ea (PR #146), copied read-only.
  - **v21 is excluded.** It is partial: the spend cap stopped it mid-video, so it counts as not run.
  - The states come from the pipeline at **3372ef3** (pre-T64 upstream).
  - The replay re-applies only the T64 guard (`apply_unproven_guard` on stored UNSUPPORTED verdicts, then `apply_sibling_rule`), the judge, and the review rule.
  - Extraction, retrieval, verification, the critic and validation are **not** re-run. The stored `validation_errors` are kept.
- **B. Golden claims:** all 48 in-scope tune videos, using golden stances and verdicts.
  - The T64 guard re-checks golden UNSUPPORTED claims on the T38 frozen evidence, as T64's replay did.
  - Cited records come from the golden set's offline `evidence_cache`, so the thin check sees real titles, abstracts and publication types. 5 reference IDs (CDC/USDA URLs, v68 c2 and v70 c2, none CONTRADICTED) are not in the cache.
  - The golden set has no critic, so change 1 cannot fire on B: (b) = (a) and (d) = (c).
- **Sanity check:** baseline (a) reproduces T66's stored label on all 18 A videos, and T64's committed `after.json` (frozen evidence) on all 48 B videos.
- **What counts as "worse":** a video that matched gold and no longer does, or a gold-MISINFO video that moves further from MISINFO. Distance from MISINFO: MISINFO 0, CANNOT_RECOGNIZE 1, NO_MISINFO or DEBUNKING 2.

### Accuracy vs gold

| config | A: 18 T66 videos | B: 48 golden tune videos | A: videos sent to review | B: videos sent to review |
|---|---|---|---|---|
| (e) T64 + change 3 | 7/18 = 0.389 (no change) | 43/48 = 0.896 (no change) | 17/18 (0 `analysis_incomplete`) | 24/48 (0) |
| (a) T64 only | 7/18 = 0.389 | 43/48 = 0.896 | 17/18 | 24/48 |
| (b) T64 + change 1 | **11/18 = 0.611** | 43/48 = 0.896 | 17/18 (+43 `second_check_disagreed` reasons, 0 new videos) | 24/48 |
| (c) T64 + change 2 | 7/18 = 0.389 | **41/48 = 0.854** | 17/18 (+2 `thin_contradiction`, 0 new videos) | 31/48 (+10 `thin_contradiction`; +7 videos: v78, v87, v88, v109, v111, v119, v177) |
| (d) T64 + both | 10/18 = 0.556 | 41/48 = 0.854 | 17/18 (+43, +3) | 31/48 (+10) |

(e) is listed first because it ships. It fires on no scored video: the only T66 state with verifier errors is the excluded v21 (5 calls refused by the spend guard), and the golden set has none. Its pass is real but vacuous, and its only positive evidence is 3d48e75e. The confusion matrices for (a)–(e) are in `replay.md`. Raw output is in `results.json`.

### Every label change vs (a) ((e) changes none)

| input | video | gold | (a) | (b) | (c) | (d) | verdict |
|---|---|---|---|---|---|---|---|
| A | v71 | NO_MISINFO | CANNOT_RECOGNIZE | **NO_MISINFO** | CANNOT_RECOGNIZE | **NO_MISINFO** | fixed by 1 |
| A | v78 | MISINFO | CANNOT_RECOGNIZE | **MISINFO (contradicted)** | CANNOT_RECOGNIZE | **MISINFO (contradicted)** | fixed by 1 |
| A | v87 | MISINFO | NO_MISINFO | **MISINFO (denies_supported)** | NO_MISINFO | **MISINFO (denies_supported)** | fixed by 1 |
| A | v122 | MISINFO | CANNOT_RECOGNIZE | **MISINFO (contradicted)** | CANNOT_RECOGNIZE | **MISINFO (contradicted)** | fixed by 1 |
| A | v11 | CANNOT_RECOGNIZE | DEBUNKING | MISINFO (contradicted) | DEBUNKING | MISINFO (contradicted) | wrong before and after |
| A | **v114** | MISINFO | CANNOT_RECOGNIZE | **DEBUNKING** | CANNOT_RECOGNIZE | **DEBUNKING** | **worse by 1** |
| A | v65 | CANNOT_RECOGNIZE | MISINFO (contradicted) | MISINFO (contradicted) | **CANNOT_RECOGNIZE** | DEBUNKING | fixed by 2 (alone) |
| A | **v88** | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | **CANNOT_RECOGNIZE** | **CANNOT_RECOGNIZE** | **worse by 2** |
| B | **v119** | MISINFO | MISINFO (contradicted) | same | **CANNOT_RECOGNIZE** | **CANNOT_RECOGNIZE** | **worse by 2** |
| B | **v177** | MISINFO | MISINFO (contradicted) | same | **NO_MISINFO** | **NO_MISINFO** | **worse by 2** |

### Why each change was dropped

- **Change 1: dropped because of v114.** It fixes v71, v78, v87 and v122 (+4) and makes one video worse.
  - v114 is the T66 stance error. Its c1 ("Eliminar toda la sal sube la presión arterial…") merged gold c1 and c2, and the stance step read it as REFUTES where gold says ENDORSES.
  - Withdrawing the verdict hid that error behind CANNOT_RECOGNIZE. Keeping the stored CONTRADICTED verdict turns it into DEBUNKING.
  - The critic's objection on c1 was arguably right: "the cited papers discuss salt reduction, not elimination".
  - No hard failure applies to c1: all three cited records were retrieved for it, and there were no guardrail or verifier errors.
- **Change 2: dropped because of v88 (A), v119 and v177 (B).** All three are gold MISINFO. The rule relies on T49's intervention-term check, which was built for "X cures Y" claims. On Spanish or non-intervention claims it falls back to junk terms, so contradictions cited from relevant papers read as thin:
  - v177 c2 "And multiple personality. Yes": the terms come out as `multiple, personality, yes`, all required. All 3 contradicting papers (split personality / dissociative identity vs schizophrenia) fail.
  - v119 c4 "El Cancer es un hongo": the terms are `el, es, un, hongo`. Both papers (cancer evolution, hallmarks of cancer) fail.
  - v88 c3 (A, and B's c3) "si las relaciones ocurren 3 días antes…": the terms are `si, las, relaciones, ocurren 3`. B's v88 keeps MISINFO only because c2 cites a meta-analysis.
  - It does fix T66 v65, where one peripheral claim on one record decided MISINFO.

## Left for a person (lead)

- **Change 1 trades +4 correct for 1 worse** on A, and it adds no review load: the same 17 of 18 videos go to review, with 43 more reasons. Whether v114 (DEBUNKING on a stance error, sent to review either way) should block it is a policy call. Turning it on is a one-line change, `KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED = True`, covered by `test_label_rules_t67.py`.
- **Change 2 needs a topic check that works on non-efficacy and non-English claims** before it can be re-gated. The T49 check is the wrong tool here.
- **n is small.** A has 18 videos from one partial run at pre-T64 upstream. B uses golden verdicts, not pipeline verdicts.
