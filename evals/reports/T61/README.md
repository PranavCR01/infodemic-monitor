# T61: T45 prompt re-run (paid, tune split only)

Approved by the project lead 2026-11-26 (hard cap $10.00). After run 1 the budget rule
stopped run 2 (spend + run 2's dry-run upper bound = $10.02 > $10); the lead then
approved run 2 and run 3 under the same $10 cap, each with --max-usd = remaining budget.

Golden set `data/golden-label-set` @ **`92a731e`** (T47: sarcastic debunks with a clear
target are REFUTES; the T45 commands said 948b1c2, which it supersedes). **Tune split
only**; the test split was not read. Sonnet (`claude-sonnet-5-5`) only. Every successful
call reported `claude-sonnet-5-5`. `config/routing.yaml` is not changed by this PR.

## Summary

| # | comparison | items | complete pair? | headline difference (T45 prompt − current) | 95% CI | counts? |
|---|---|---|---|---|---|---|
| 1 | stance_v1 vs stance_v2 | 187 claims | yes, 0 failures | macro-F1 −0.090 | [−0.270, +0.027] | yes: **no demonstrated difference** |
| 2 | extract_v2 vs extract_v3, OCR on | 48 videos | yes, 0 failures | strict claim F1 **+0.091**; meaning F1 +0.041 | [+0.040, +0.155]; [−0.001, +0.092] | yes: strict excludes 0, meaning **just includes 0** |
| 3 | extract_v2 vs extract_v3, OCR off | 48 videos | **no**: extract_v3 failed 34/48 (provider account out of credit) | — | — | **no, incomplete; not rerun** |

Paired percentile bootstrap, B = 10,000, seed 61; videos resampled for extraction, claims
for stance (`paired_bootstrap.py`). "Includes 0" = no demonstrated difference.

## Spend

| run | --max-usd | SpendGuard booked | token-priced actual | calls | stopped at cap? |
|---|---|---|---|---|---|
| (run 1, first launch) | 10 | $0 | $0 | 0 (crashed at start-up: OpenAI SDK needs a key to construct the unused client) | — |
| 1 stance | 10.0000 | **$3.3656** | $3.3656 | 374 | no |
| 2 extract, OCR | 6.6344 | **$2.4613** | $2.4613 | 100 | no |
| 3 extract, no OCR | 4.1731 | **$2.1411** | $1.0172 | 94 (34 refused by the provider) | no |
| **total** | | **$7.9680** | **$6.8442** | 568 | |

SpendGuard books a failed call's worst-case reservation when the provider reports no
usage; the 34 credit-balance 400s returned no tokens, so ~$1.12 of run 3's booked figure
was probably never billed. The token-priced column is input×$2 + output×$10 per million
from each call's recorded usage. Both totals are under $10. Actual/expected vs the dry
run: stance 1.32×, extract (OCR) 1.52×.

**Provider account:** run 3's extract_v3 calls failed with HTTP 400 "Your credit balance is
too low to access the Anthropic API" after 13 videos. The account behind
`EVAL_ANTHROPIC_API_KEY` needs credit before any further paid run.

## 1. Stance: stance_v1 vs stance_v2 (187 tune claims)

Frozen evidence: T38's recorded freeze, `origin/data/t38-frozen-evidence` @ 96f5e23,
sha256 `c4ff82bf…d4ca5` (matches T38's record), passed with `--frozen-evidence`; not
re-frozen. Note: stance items do not read the frozen evidence (that file feeds verify_claims
only); a stance item is the gold claim plus the transcript/OCR segments of its time range,
built deterministically from the golden set, so both prompts saw identical inputs.

Note: T47 also added the sarcasm rule to **stance_v1** (the live prompt), so this compares
T47's stance_v1 with stance_v2, not T38's stance_v1.

Paired bootstrap over claims, B = 10,000, seed 61, percentile 95% CI of (v2 − v1):

| metric | stance_v1 | stance_v2 | v2 − v1 | 95% CI | CI includes 0? |
|---|---|---|---|---|---|
| macro-F1 (labels present in gold) | 0.546 | 0.456 | −0.090 | [−0.270, +0.027] | **yes: no demonstrated difference** |
| recall ENDORSES (n=167) | 0.988 | 0.976 | −0.012 | [−0.036, +0.012] | yes |
| recall REFUTES (n=16) | 0.813 | 0.875 | +0.063 | [−0.154, +0.286] | yes |
| recall QUOTES (n=3) | 0.333 | 0.000 | −0.333 | [−1.000, 0.000] | yes (upper end 0) |
| recall UNCLEAR (n=1) | 0.000 | 0.000 | 0.000 | [0, 0] (6,324 of 10,000 resamples contain it) | yes |
| recall NEUTRAL (n=0) | — | — | — | not defined | — |

Discordant claims: only v1 correct 5, only v2 correct 3. Failures: 0 / 0.
Debunks read as ENDORSES: 1 for each prompt.

Confusion (gold → predicted):
- stance_v1: ENDORSES→ENDORSES 165, →UNCLEAR 2; REFUTES→REFUTES 13, →QUOTES 2, →ENDORSES 1;
  QUOTES→QUOTES 1, →ENDORSES 2; UNCLEAR→REFUTES 1.
- stance_v2: ENDORSES→ENDORSES 163, →REFUTES 2, →UNCLEAR 1, →QUOTES 1; REFUTES→REFUTES 14,
  →UNCLEAR 1, →ENDORSES 1; QUOTES→ENDORSES 3; UNCLEAR→REFUTES 1.

Reading: macro-F1 is driven by the three tiny classes (QUOTES 3, UNCLEAR 1, REFUTES 16);
the −0.09 point gap is mostly v2 losing the one QUOTES hit (QUOTES F1 0.5 → 0). The data
cannot tell the two prompts apart. stance_v2 does not earn a routing change.

## 2. Extraction with OCR: extract_v2 vs extract_v3 (48 tune videos, 187 gold claims)

`config/pipeline.yaml` (use_ocr: true). Both candidates: 48/48 items, 50 calls, 0 failures.

| metric | extract_v2 | extract_v3 | v3 − v2 | 95% CI | includes 0? |
|---|---|---|---|---|---|
| strict precision | 0.331 | 0.389 | +0.059 | [+0.012, +0.117] | no |
| strict recall | 0.642 | 0.818 | +0.176 | [+0.104, +0.251] | no |
| **strict F1** (runner's selection metric) | 0.436 | 0.528 | **+0.091** | **[+0.040, +0.155]** | **no** |
| meaning precision | 0.413 | 0.433 | +0.019 | [−0.026, +0.067] | yes |
| meaning recall | 0.802 | 0.909 | +0.107 | [+0.041, +0.181] | no |
| **meaning F1** | 0.545 | 0.586 | +0.041 | [−0.001, +0.092] | **yes (barely)** |

Counts (matched / gold / predicted): strict v2 120/187/363, v3 153/187/393; meaning v2
150/187/363, v3 170/187/393. Claims dropped by the grounding guardrail
(`claim_ungrounded`): v2 44, v3 10, consistent with v3's "quote in the original
language, never translate" rule.

Reading: v3 finds more of the gold claims under both matchers (recall CIs exclude 0).
Precision improves only under the strict matcher, and the meaning-F1 CI touches 0. So part
of the strict gain is v3 writing claims in the gold's wording conventions (quoting,
brackets, positive form of the myth), which is what v3 was designed to do but is not the
same as finding different claims. Both prompts still over-extract (precision 0.33–0.43).
Cost per video: v2 $0.02499, v3 $0.02628 (+5%).

## 3. Extraction without OCR: incomplete, not counted

`evals/reports/T45/pipeline_no_ocr.yaml` (use_ocr: false). extract_v2 completed 48/48
(strict F1 0.414, meaning F1 0.540, $0.01578/video). extract_v3 completed 14 of 48
videos (13 model calls answered) before the provider refused every further call
for lack of credit; the runner scored the 34 failed videos as empty and excluded
the candidate (failure rate over budget). The bootstrap output
(`bootstrap_extract_no_ocr.json`) is kept for the record but **means nothing about the
prompt**: v3's apparent −0.15 strict F1 is the failed items. Per the lead, not rerun.

What this run can and can't say about use_ocr: on extract_v2 alone, with OCR vs without,
strict F1 0.436 vs 0.414 and meaning F1 0.545 vs 0.540. These are two different runs, not
a paired comparison with a CI, and they show no clear benefit from dropping OCR.

## Limits

- One tune split (48 videos, 187 claims), one run per candidate; run-to-run variance was not
  measured. Tune numbers choose prompts and are not the system's accuracy (test split = T14).
- Stance macro-F1 hinges on QUOTES (n=3), UNCLEAR (n=1) and REFUTES (n=16); NEUTRAL has no
  gold claims. Per-label CIs for these are very wide or degenerate.
- The extraction metric matches text only (gold items have no spans here); the meaning
  matcher is ASCII-only and cannot match Devanagari claims (T45 note).
- These numbers are not comparable with T38's (golden set, matcher and stance_v1 all changed).

## Files

- `run_stance/`, `run_extract_ocr/`, `run_extract_no_ocr/`: runner output per run:
  `report.md`, `report.json` (per-call usage, spend), `per_item.json` (stance per claim with
  `video:claim` ids; extraction per video with each claim's text, span, source segments,
  category and node errors), and the runner's own `routing_v2.yaml` (not adopted).
- `paired_bootstrap.py`; `bootstrap_stance.json`, `bootstrap_extract_ocr.json`,
  `bootstrap_extract_no_ocr.json` (the last one is from the incomplete run).
- No keys or secrets are in any file (checked by grep).

## Commands

```
git fetch origin data/golden-label-set data/t38-frozen-evidence
git show origin/data/t38-frozen-evidence:frozen_evidence_tune.json > $S/frozen_evidence_tune.json
cd backend
# dry runs (no calls): the same commands without --live/--max-usd, --out $S/dry/...
# The OpenAI SDK refuses to construct without a key, so the unused OpenAI client gets a
# placeholder string; no OpenAI candidate is in candidates_rerun.yaml.
EVAL_OPENAI_API_KEY=<placeholder> python -m app.evaluation.routing_experiment run \
    --golden-ref 92a731e --candidates ../evals/reports/T45/candidates_rerun.yaml \
    --steps analyze_stance --frozen-evidence $S/frozen_evidence_tune.json \
    --out ../evals/reports/T61/run_stance --live --max-usd 10
EVAL_OPENAI_API_KEY=<placeholder> python -m app.evaluation.routing_experiment run \
    --golden-ref 92a731e --candidates ../evals/reports/T45/candidates_rerun.yaml \
    --steps extract_claims --out ../evals/reports/T61/run_extract_ocr --live --max-usd 6.6344
EVAL_OPENAI_API_KEY=<placeholder> python -m app.evaluation.routing_experiment run \
    --golden-ref 92a731e --candidates ../evals/reports/T45/candidates_rerun.yaml \
    --steps extract_claims --pipeline-options ../evals/reports/T45/pipeline_no_ocr.yaml \
    --out ../evals/reports/T61/run_extract_no_ocr --live --max-usd 4.1731
for r in run_stance run_extract_ocr run_extract_no_ocr; do
  PYTHONPATH=. python ../evals/reports/T61/paired_bootstrap.py --B 10000 --seed 61 \
      ../evals/reports/T61/$r/per_item.json --out ../evals/reports/T61/bootstrap_${r#run_}.json
done
```
