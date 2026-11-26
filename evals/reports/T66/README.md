# T66 — End-to-end label accuracy and error attribution (tune split)

> **Development numbers on the TUNE split, not product accuracy.** This is a PARTIAL run:
> the $25 cap allowed **18 of the 48** in-scope tune videos to finish. The test split
> was never read (it stays reserved for T14). n = 18 makes every interval wide; read the
> error attribution (§2) as the main result, not the point estimates.

## Setup

| | |
|---|---|
| Code | `langgraph-build` @ `3372ef33460eb7ff78c5e2989767905b68daddf2`. Product code, config and prompts were not changed. The second `run.json` names `b509336`: that is this branch after my first commit, which added only files under `evals/reports/T66/`. |
| Routing | `backend/config/routing.yaml` as merged: extract `claude-sonnet-5-5@extract_v3`, stance `sonnet@stance_v1`, verify `claude-opus-5-5@verify_v3`, critic `gpt-4o-2024-08-06@critic_v1`, judge `sonnet@explain_v2`, find_study `haiku@find_study_v1` |
| Pipeline | `backend/config/pipeline.yaml` as merged: OCR on for extraction; find_study and crossref on; search assistant and translator off |
| Golden set | `origin/data/golden-label-set` @ `92a731e7f9548221635c8b9b99e098cbe0e6699a`, using its stored transcripts and OCR. The tune-only copy has dataset hash `a776687a…f470`. |
| Runner | `app.evaluation.runner.run_evaluation`, called by `run_t66.py`. The CLI's `run` command only wires the baseline, so this small script supplies the graph system. |
| Wiring | Same as `build_graph_provider`, with these differences: references on (as in T18), an in-memory snapshot store, no Redis, and an Anthropic key from `EVAL_ANTHROPIC_API_KEY`. Every provider client is wrapped in the routing experiment's `SpendGuard`, which also counts the web-search fees ($0.01 per search). |
| Single-call fallback | **Not called.** If the graph fell back, the video was to be recorded as `graph_fallback`. This never happened (0 of 18). |
| Order | Seeded shuffle (seed 66) of the 48 in-scope ids, declared in `order.json` before any paid call |

Scripts in this directory (report-only, no product code): `run_t66.py` (materialize, dry run, run) and
`analyze_t66.py` (every number below → `analysis.json`; side-by-side material → `wrong_cases.md`).

### Spend guard and what ran

- **Dry run (no calls)** (`dryrun.json`): expected **$14.37**, upper bound **$160.46** for 48 videos. The upper bound exceeded the budget, so the run used the declared order and a hard stop. The estimate assumed the gold claim count (76 claims on the 18 finished videos). The pipeline extracted **162**, and the critic sent many verdicts back for revision. The real mean was $1.13 per video, so 48 videos would have cost about $54.
- **Smoke test:** 1 video (v95), $1.53. My wrapper raised an `AttributeError` after the video's state had already been saved. The fix was in the wrapper only, and v95 was not re-run or re-paid. In that run's `runs/…a7b4d9/` folder, `predictions.jsonl` shows the error; `videos/v95.json` is the real output.
- **Main run:** the 47 remaining videos in order, with the $1.53 counted toward the cap and a $1.50 reserve required before starting a video. 17 finished. Then **v21 hit the cap mid-video** after spending $2.48: the guard refused 5 calls, so v21 counts as **not run**, never as wrong. The other 29 were not started.
- **Total spend: $22.91 of the $25.00 cap**, as booked by SpendGuard: Opus $14.46, GPT-4o $4.03, Sonnet $2.24, Haiku $0.09, web search $0.57 (`spend.json`).
  - Of that, **$20.43** went to the 18 finished videos and **$2.48** to v21.
  - $2.09 was left. The next video in the declared order was v21 again, which needs about $2.50, so I did not run anything further.
- **No credit or billing error occurred.**
- **The runner's own `run.json` metrics (0.36 / 0.30) are not the result.** The runner scores not-run videos as `CANNOT_RECOGNIZE`. Use the numbers below.

## 1. Video labels vs golden (18 finished videos)

Rows are gold labels, columns are ours:

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **2** | 2 | 0 | 3 | 7 |
| **NO_MISINFO** | 0 | **1** | 0 | 2 | 3 |
| **DEBUNKING** | 1 | 0 | **1** | 0 | 2 |
| **CANNOT_RECOGNIZE** | 2 | 0 | 1 | **3** | 6 |

| metric | value | 95% CI (bootstrap over videos, B = 10,000, seed 66) |
|---|---|---|
| Accuracy | **0.389** (7/18) | [0.167, 0.611] |
| Macro-F1 (4 labels) | **0.399** | [0.134, 0.624] |

Per-class F1: MISINFO 0.33 (precision 0.40, recall 0.29); NO_MISINFO 0.33; DEBUNKING 0.50; CANNOT_RECOGNIZE 0.43.

**MISINFO basis.** There were 9 videos where the gold label or our label was MISINFO. In the 2 videos where both said MISINFO, the basis agreed in both (`contradicted→contradicted` and `unproven→unproven`). The other 7:
- Gold `contradicted`, we did not say MISINFO: ×5.
- We said MISINFO where gold did not:
  - `contradicted` (v65)
  - `denies_supported` (v23)
  - `unproven` (v92)

**Paired bootstrap vs the single-call baseline: not possible.** T18 stored no baseline predictions in the repo (it reported cost and latency only), so there is nothing paired to compare against. I did not run the baseline: it was not in the approved spend.

**Review routing** (gold "sent to review" = the golden `review_reasons` is not empty; ours = `requires_human_review`):

| | ours: review | ours: no review |
|---|---|---|
| **gold: review** | 10 | 0 |
| **gold: no review** | 7 | 1 |

- Agreement is 11/18 = **0.61** [0.39, 0.83]; Cohen's κ = 0.14.
- We sent **17 of 18** videos to review. The only one not sent was v150, which has no claims.
- **All 11 wrong labels were sent to review**, so none of the errors in this sample would have been published unchecked.
- The flip side: routing is so broad that it hardly separates hard videos from easy ones.
- The most frequent reason is `budget_exhausted`, raised on 105 claims across the 18 videos.

## 2. Every wrong label, and its cause

Material: `wrong_cases.md` (gold and our claims side by side, with stored and judge-effective verdicts), from `videos/<id>.json`.

**Check:** re-applying the §9 order to the verdicts the judge actually used reproduces all 18 of our labels (`analysis.json → budget_abstention.recomputed_rule_matches_actual`).

**The dominant mechanism is not one of the four model steps.** It is the **§8 critic-budget abstention** (`routing.verdicts_for_judge`):
- When the critic still objects after the loop budget runs out, the claim's verdict goes to the §9 rules as INSUFFICIENT_EVIDENCE.
- This hit **43 of 162 claims, in 13 of 18 videos**.
- I file it under "§9 policy effect" because it decides what the rules see, but it is §8 code.

**Counterfactual (diagnostic only, not a re-run):** if the §9 rules are applied to the *stored* verdicts instead:
- v71, v122, v78 and v87 become correct.
- v11 and v114 stay wrong, with a different wrong label.
- Accuracy would be 11/18 = 0.61.

The critic's objections might have been right, so this does not mean abstention is wrong. It shows where the label is being decided.

| video | gold → ours | cause | claim and step |
|---|---|---|---|
| v71 | NO_MISINFO → CANNOT_RECOGNIZE | **§8/§9 policy (critic-budget abstention)** | Stored SUPPORTED verdicts on c8, c9 (= gold c3, the hormone/stroke claim), c15 and c20 were all withdrawn. Nothing judged was left, so the rule was `nothing_judged`. |
| v122 | MISINFO → CANNOT_RECOGNIZE | **§8/§9 policy** | c1 ("statins harm the heart", = gold c1) and c3 (= gold c3) were CONTRADICTED by verify, then withdrawn → `nothing_judged`. |
| v78 | MISINFO → CANNOT_RECOGNIZE | **§8/§9 policy**, plus a verdict miss | c1 ("vaccine linked to miscarriage", = gold c1) was CONTRADICTED, then withdrawn. c5 (= gold c2, "82% miscarriage") was INSUFFICIENT_EVIDENCE with 4 records, where gold says CONTRADICTED. The label came from c3 under `refuted_unsettled`. |
| v87 | MISINFO → NO_MISINFO | **§8/§9 policy**, plus a verdict miss | c6 ("fluoride in water is good for teeth", stance REFUTES, stored SUPPORTED) was withdrawn; it would have given MISINFO `denies_supported`. c3 (= gold c1, blood–brain barrier) was INSUFFICIENT_EVIDENCE, where gold says CONTRADICTED. NO_MISINFO was then decided by the minor claim c4, "fluoride can cross the BBB" (SUPPORTED). |
| v95 | NO_MISINFO → CANNOT_RECOGNIZE | **verdict** | c4 (= gold c2, tumour types) and c7 (= gold c3, ionizing radiation) came out INSUFFICIENT_EVIDENCE with 10 on-topic records kept; gold says SUPPORTED. Extraction also produced 13 claims vs 4 in gold, but that did not decide the label. |
| v109 | MISINFO → NO_MISINFO | **verdict** | The side-effect claims gold calls CONTRADICTED came out differently: c6 (pancreatitis) MIXED and withdrawn; c7 (diabetes) and c8 (stroke) INSUFFICIENT_EVIDENCE. Gold c7 (seizures) was not extracted (a minor extraction miss). NO_MISINFO was decided by c3 (SUPPORTED). |
| v92 | CANNOT_RECOGNIZE → MISINFO (unproven) | **verdict** (at the §9 "unproven" boundary) | c2 ("a grounded body cannot sustain chronic inflammation") was UNSUPPORTED with 10 records kept; gold says INSUFFICIENT_EVIDENCE. The T30 unproven rule then fired. Whether this claim should count as unproven is a policy-definition question, not clearly a model error. |
| v114 | MISINFO → CANNOT_RECOGNIZE | **stance** (plus extraction merge and the abstention) | c1 merged gold c1 and c2 ("removing all salt raises BP / heart attacks"). Its stance came out REFUTES where gold says ENDORSES. The stored CONTRADICTED verdict was withdrawn → `refuted_unsettled`. Without the abstention it would have been DEBUNKING, still wrong because of the stance. |
| v65 | CANNOT_RECOGNIZE → MISINFO | **extraction (extra claim)**, then a §9 effect | MISINFO was decided by one peripheral, non-gold claim, c11 ("heart disease takes up more medical expense than anything"), ENDORSES/CONTRADICTED on **1** record. Also: c1 and c3 (REFUTES, CONTRADICTED; would be DEBUNKING) and five SUPPORTED claims were withdrawn by the abstention. 18 claims vs 3 in gold. |
| v23 | DEBUNKING → MISINFO (denies_supported) | **ambiguous: extraction (extra claim) + stance** | Decided by the extra claim c5, "[proven cancer treatments are] toxic", with stance REFUTES and verdict SUPPORTED. It is a phrase from a report about the podcaster, so the claim boundary and the stance are both doubtful. Separately, c2 and c6 (= gold c2 and c3) were INSUFFICIENT_EVIDENCE where gold says CONTRADICTED, so dropping c5 alone would still give `refuted_unsettled`, not DEBUNKING. |
| v11 | CANNOT_RECOGNIZE → DEBUNKING | **ambiguous: extraction (extra claim) vs golden-set granularity** | Decided by c1, "seed oils are bad for you", REFUTES/CONTRADICTED. Gold has no such claim (all 3 gold claims are MIXED), but the speaker does refute that popular claim, so the extra claim is defensible. The stored verdicts on c2–c4 were withdrawn; without that, the label would be MISINFO through c2 ("saturated fat is totally fine", CONTRADICTED), still wrong against gold MIXED. |

**Tally of primary causes (11 wrong):**

| cause | videos | count |
|---|---|---|
| §8/§9 policy effect (critic-budget abstention) | v71, v122, v78, v87 | 4 |
| verdict | v95, v109, v92 | 3 |
| extraction (extra claim) | v65 clearly; v23 and v11 ambiguous | 3 |
| stance | v114 (v23 also) | 1 |
| retrieval gap | — | 0 |

- **Retrieval gap is 0 as a primary cause, but this is weak evidence.** Almost every claim kept 10 records judged on-topic by `find_study.topic_match`, a lenient concept-match check. That is not a relevance judgement, so retrieval quality is not measured here.
- **Extraction over-generates:** 162 claims vs 76 in gold on the same videos, a median of 7.5 per video. This also drives the cost (see §4).

## 3. Policy gaps (a)–(e)

Operational definitions (code in `analyze_t66.py → gaps`):
- **(a)** MISINFO with exactly one deciding claim while more than half the claims with a verdict are SUPPORTED. Whether the deciding claim is "peripheral" is judged by hand in §2.
- **(b)** NO_MISINFO, with at least one ENDORSES claim about treatment or prevention (keyword regex) that is INSUFFICIENT_EVIDENCE, and the video **not** sent to review.
- **(c)** MISINFO while at least one claim is REFUTES and CONTRADICTED (a debunk lost to a side claim).
- **(d)** Two claims share an intervention concept (`frame_claim`) and an outcome concept (or one names no outcome), and one is SUPPORTED while the other is CONTRADICTED or UNSUPPORTED.
- **(e)** An UNSUPPORTED claim with fewer than 3 on-topic kept records. Gold has no kept records, so for gold this counts *cited* evidence. Gold UNSUPPORTED claims cite almost nothing by definition, so the gold column for (e) is close to "every UNSUPPORTED claim".

"Ours, judge-effective" uses the verdicts the judge saw; "ours, stored" uses the verdicts verify/critic produced, before the abstention. Counts are videos where the gap fires (claims or pairs in brackets).

| gap | gold claims, all 48 tune | gold claims, 18 finished | ours, judge-effective (18) | ours, stored verdicts (18) |
|---|---|---|---|---|
| (a) single claim decides MISINFO, majority SUPPORTED | 0 | 0 | 0 | 0 |
| (b) silent NO_MISINFO with endorsed treatment/prevention claim INSUFFICIENT_EVIDENCE | 0 | 0 | 0 | — |
| (c) DEBUNKING lost to a side claim | 0 | 0 | 0 | 2 (v65, v11) |
| (d) conflicting sibling verdicts, same intervention and outcome | 2 (3 pairs: v122, v79) | 1 (v122) | 0 | 3 (14 pairs: v65 ×12, v11, v122) |
| (e) UNSUPPORTED on fewer than 3 on-topic records | 6 (11 claims; 10 of them deciding) | 1 (v120 c1) | 0 | 0 |

How to read the table:
- **(b) is 0 for us by construction, not by luck.** 17 of 18 of our videos go to review, so none is "silent". Dropping the review condition, the pattern appears in 3 of our videos:
  - v69: c15, c17, c19, c20
  - v109: c2, c4
  - v87: c8, c9

  It appears in 1 gold video, v71 c6, which gold does send to review.
- **(a) never fires as defined.** The case that matches its intent is v65, where one peripheral claim (c11) decided MISINFO. Most of that video's SUPPORTED verdicts had been withdrawn, so the "majority SUPPORTED" condition fails on the effective verdicts.
- **(c) and (d) appear only in our stored verdicts.** The abstention withdraws the conflicting verdicts before §9, so it hides these gaps, at the price of the 4 policy errors in §2.
- **(e) matters for the golden set's own labels**, 10 deciding claims across 48 videos. It does not fire on ours because our UNSUPPORTED claims kept 10 records each, and that record count is only a lenient on-topic measure.

## 4. Cost and latency

Over the 18 finished videos, from `videos/*.json`:

| | median | p90 | max | total |
|---|---|---|---|---|
| Cost per video (USD) | **$0.76** | $2.30 | $3.07 (v71) | $20.43 |
| Latency per video (s) | **111** | 311 | 411 (v71) | 2,777 |

- Model calls per video: median 34.5. Claims per video: median 7.5.
- Cost by step, from the recorded model calls:
  - verify (Opus): $13.75, **67%** of model-call spend
  - critic (GPT-4o): $3.76
  - stance: $1.58
  - extract: $0.52
  - judge: $0.16
  - find_study: $0.09, plus $0.57 in web-search fees across the run
- **Total spend: $22.91 of the $25.00 cap**: $20.43 on finished videos plus $2.48 on v21, which was not run.
- **Cost is driven by claim count × verify revisions.** The cost estimate from the T18 smoke run ($0.41 per video median) no longer holds at this routing: Opus verify plus extract_v3 over-generation.

## Files

| file | contents |
|---|---|
| `videos/<id>.json` | Full final graph state per video that ran (18 finished, plus v21 not run): claims, stances, verdicts, critic results, kept and retrieved evidence, search trail, find-study trail, final result (rule, deciding claims, basis), review reasons, errors, every model call. Transcript, OCR and fused segments are omitted; they are in the golden set and their counts are kept. |
| `runs/<run_id>/` | The runner's `run.json`, `predictions.jsonl` and `traces.jsonl`, plus `status.json` per video. |
| `dryrun.json`, `order.json`, `spend.json` | Pre-run estimate, the declared order, and the final SpendGuard summary. |
| `analysis.json`, `wrong_cases.md` | Every number above, and the material for the attribution. |
| `../../registry/T66-*.json` | Eval registry records (T63 rule). |

To reproduce, from `backend/`:

```
python ../evals/reports/T66/run_t66.py materialize --out <dir>
python ../evals/reports/T66/analyze_t66.py --data <dir>
```

No model calls are needed to reproduce the analysis.
