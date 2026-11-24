# T38 routing experiment: OpenAI candidates (2026-11-24)

Approved by the project lead after #108 (T41, Responses-API client) merged.
Candidates: `../candidates_openai.yaml` (gpt-5.6-luna for extract_claims and analyze_stance,
gpt-5.6-terra for verify_claims; `backend/config/routing_experiment.yaml` unchanged). The dry run
listed only these three, with no Anthropic candidate. Tune split only.

Frozen evidence: `origin/data/t38-frozen-evidence:frozen_evidence_tune.json`, sha256
`c4ff82bf69dc85c3b80503a2b7d559b820255b1a90ac3a3fc069593e8d4d4ca5`. This matches the Claude run
(`auto/T38-live` report and the orchestrator's message) and was checked before any paid call.

## Step 1: smoke test (`smoke_v11/`): clean

`run --live --max-usd 1 --videos v11` (1 extraction, 3 stance, 3 verify items). **$0.0498**, 7 calls.

| step | model id returned | input | output | reasoning | output ≥ reasoning | error |
|---|---|---|---|---|---|---|
| extract_claims | gpt-5.6-luna | 4,732 | 689 | 453 | yes | none |
| analyze_stance | gpt-5.6-luna | 2,033 | 63 | 0 | yes | none |
| analyze_stance | gpt-5.6-luna | 2,232 | 81 | 0 | yes | none |
| analyze_stance | gpt-5.6-luna | 1,601 | 82 | 0 | yes | none |
| verify_claims | gpt-5.6-terra | 3,215 | 319 | 147 | yes | none |
| verify_claims | gpt-5.6-terra | 6,568 | 665 | 432 | yes | none |
| verify_claims | gpt-5.6-terra | 5,787 | 305 | 106 | yes | none |

No ModelTruncatedError, no 400s, and every output parsed. Effort was `medium` on every call.

## Step 2: full tune split (`full/`)

**Cap $27.86** = 40 − 0.27 (first smoke test) − 11.8135 (Claude run actual: `claude/report.json`
on `auto/T38-live`, `spend.spent_usd` 11.813504) − 0.0498 (this smoke test) = 27.8667, rounded
down. The Claude figure was read from the branch, not assumed. The dry-run upper bound was $16.50
(expected $6.82), under the cap.

Result: **$1.8693**, 359 calls, 0 refused, not stopped at cap, and every item run. There were 0 errors,
0 truncations and 0 calls with output < reasoning. `full/report.json` has the per-call lists
replaced by a per-candidate summary (`calls_summary`); scores and costs are unchanged.

| step | candidate | metric | score | items | cost/item | p95 ms |
|---|---|---|---|---|---|---|
| extract_claims | gpt-5.6-luna | claim_f1 | 0.3237 | 48/48 | $0.00200 | 17,577 |
| analyze_stance | gpt-5.6-luna | stance_macro_f1 | 0.4977 | 174/174 | $0.00046 | 1,885 |
| verify_claims | gpt-5.6-terra | verification_macro_f1 | 0.4919 | 174/174 | $0.00973 | 6,412 |

Reasoning was rare even at `medium` effort: luna reasoned on 1/174 stance calls and 20/50
extraction calls, terra on 114/135 verify calls. See `../combined/report.md`, caveat 1.

The `routing_v2.yaml` this run wrote on its own (OpenAI-only winners) is not committed: it
compared nothing. The cross-provider proposal is `../combined/routing_v2.yaml`.
