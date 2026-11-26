# T61: T45 prompt re-run (paid, tune split only) — IN PROGRESS, waiting on the lead

Approved by the project lead 2026-11-26 (cap $10.00). Golden set `data/golden-label-set`
@ **`92a731e`** (T47; the T45 commands said 948b1c2, superseded), **tune split only**
(test split not read). Sonnet only. `config/routing.yaml` is not changed by this PR.

## Status

| # | comparison | dry-run upper bound @92a731e | started? | spend |
|---|---|---|---|---|
| 1 | stance_v1 vs stance_v2 | $4.39 | yes, complete pair (187 + 187 claims, 0 failures) | **$3.3656** |
| 2 | extract_v2 vs extract_v3, with OCR | $6.65 | **no**: $3.37 spent + $6.65 = $10.02 > $10 cap; asked the lead | $0 |
| 3 | extract_v2 vs extract_v3, no OCR | $5.48 | no (runs in order, after 2) | $0 |

Total so far: **$3.3656** of $10 (SpendGuard, 374 calls, 0 refused). One earlier launch of
run 1 failed at start-up (the OpenAI SDK client refuses to construct without a key, even
though no OpenAI candidate runs) before any model call: $0. The retry passed a placeholder
string as `EVAL_OPENAI_API_KEY` for that unused client; no OpenAI call was made.

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

## Files

- `run_stance/`: runner output (`report.md`, `report.json`, `per_item.json` = stance per
  claim with `video:claim` ids, and the runner's own `routing_v2.yaml`, not adopted).
- `paired_bootstrap.py`, `bootstrap_stance.json`: the CI computation and its output.

## Commands

```
git fetch origin data/golden-label-set data/t38-frozen-evidence
git show origin/data/t38-frozen-evidence:frozen_evidence_tune.json > $S/frozen_evidence_tune.json
cd backend
# dry run (no calls)
python -m app.evaluation.routing_experiment run --golden-ref 92a731e \
    --candidates ../evals/reports/T45/candidates_rerun.yaml --steps analyze_stance \
    --frozen-evidence $S/frozen_evidence_tune.json --out $S/dry/stance
# paid
EVAL_OPENAI_API_KEY=<placeholder, unused> python -m app.evaluation.routing_experiment run \
    --golden-ref 92a731e --candidates ../evals/reports/T45/candidates_rerun.yaml \
    --steps analyze_stance --frozen-evidence $S/frozen_evidence_tune.json \
    --out ../evals/reports/T61/run_stance --live --max-usd 10
PYTHONPATH=. python ../evals/reports/T61/paired_bootstrap.py --B 10000 --seed 61 \
    ../evals/reports/T61/run_stance/per_item.json --out ../evals/reports/T61/bootstrap_stance.json
```
