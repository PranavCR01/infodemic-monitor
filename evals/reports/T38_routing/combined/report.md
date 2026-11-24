# T38 routing experiment: combined results, Claude + OpenAI (tune split), 2026-11-24

**These are tune-split numbers (55 videos: 48 extraction items, 174 stance/verify claims). They
are NOT from the held-out test split and are NOT the system's accuracy.** They exist only to choose
a model per step; the chosen table still has to be evaluated against the baseline (§14) on held-out data.

Golden set: `origin/data/golden-label-set@0fbc68a05a7d` (tune split only). Evidence mode
`retrieved+cited`. Both runs used the same frozen evidence
(`origin/data/t38-frozen-evidence:frozen_evidence_tune.json`, sha256
`c4ff82bf69dc85c3b80503a2b7d559b820255b1a90ac3a3fc069593e8d4d4ca5`, checked on both sides before
any paid call). Selection: `app.evaluation.selection.select_model`, max failure rate 0.05,
tie margin 0.01 (within 0.01 of the best, the cheaper/faster wins), applied to the merged results.

Sources: Claude run `auto/T38-live` → `evals/reports/T38_routing/claude/report.json` (PR #104);
OpenAI run `openai/full/report.json` (this branch). Machine-readable: `report.json` here.

## Results per step

Latency is per call in ms (p50 / p95). "Items" = items completed / items. Bold = winner.

### extract_claims (metric: claim_f1, 48 items)

| provider | candidate | claim_f1 | items | cost/item | total cost | latency p50 / p95 | calls |
|---|---|---|---|---|---|---|---|
| Anthropic | claude-haiku-5-5 | 0.3601 | 48/48 | $0.00124 | $0.06 | 2,678 / 5,503 | 50 |
| Anthropic | **claude-sonnet-5-5** | **0.4193** | 48/48 | $0.02510 | $1.20 | 4,639 / 10,415 | 50 |
| OpenAI | gpt-5.6-luna | 0.3237 | 48/48 | $0.00200 | $0.10 | 7,067 / 17,577 | 50 |

Winner: **claude-sonnet-5-5** (best claim_f1, 0.096 above the next; no tie).

### analyze_stance (metric: stance_macro_f1, 174 claims)

| provider | candidate | stance_macro_f1 | items | cost/item | total cost | latency p50 / p95 | calls | debunk recall (n=15 refutes) |
|---|---|---|---|---|---|---|---|---|
| Anthropic | claude-haiku-5-5 | 0.5230 | 174/174 | $0.00040 | $0.07 | 947 / 1,199 | 174 | 0.667 |
| Anthropic | **claude-sonnet-5-5** | **0.6436** | 174/174 | $0.00805 | $1.40 | 2,042 / 3,951 | 174 | 0.800 |
| OpenAI | gpt-5.6-luna | 0.4977 | 174/174 | $0.00046 | $0.08 | 1,521 / 1,885 | 174 | 0.600 |

Winner: **claude-sonnet-5-5** (best stance_macro_f1). Each candidate read 1 debunk as "endorses".

### verify_claims (metric: verification_macro_f1, 174 claims)

| provider | candidate | verification_macro_f1 | items | cost/item | total cost | latency p50 / p95 | calls | insufficient called contradicted |
|---|---|---|---|---|---|---|---|---|
| Anthropic | claude-sonnet-5-5 | 0.6073 | 174/174 | $0.01777 | $3.09 | 3,707 / 6,539 | 146 | 4 |
| Anthropic | **claude-opus-5-5** | **0.6759** | 174/174 | $0.03441 | $5.99 | 6,113 / 9,556 | 135 | 4 |
| OpenAI | gpt-5.6-terra | 0.4919 | 174/174 | $0.00973 | $1.69 | 3,337 / 6,412 | 135 | 2 |

Winner: **claude-opus-5-5** (best verification_macro_f1). Unsupported recall was 1.0 (n=5) for all three.

No candidate in any step had a failed item, a fallback, a refused call or a truncated reply.
Every OpenAI response reported its model id (`gpt-5.6-luna`, `gpt-5.6-terra`).

## Proposed routing (`routing_v2.yaml`)

| step | proposed | same as current `config/routing.yaml`? |
|---|---|---|
| extract_claims | anthropic / claude-sonnet-5-5 / extract_v2 | no (current: claude-haiku-5-5) |
| analyze_stance | anthropic / claude-sonnet-5-5 / stance_v1 | yes |
| verify_claims | anthropic / claude-opus-5-5 / verify_v3 | yes |

It matches the provisional Claude-only table on `auto/T38-live`: the OpenAI candidates won no step.
The verifier stays Anthropic, so the critic (openai/gpt-4o) is still from a different provider (§13).
`config/routing.yaml` was not changed. Status stays `provisional` because critique and
judge_explanation were not part of this experiment.

## Spend (actual, provider-billed)

| run | Anthropic | OpenAI | total | cap |
|---|---|---|---|---|
| First smoke test (PR #104, v11) | $0.27 | $0.00 (7 × HTTP 400, no tokens) | $0.27 | $1 |
| Claude full run (Option C) | $11.8135 | — | $11.8135 | $25 |
| OpenAI smoke test (v11, this branch) | — | $0.0498 | $0.0498 | $1 |
| OpenAI full run (this branch) | — | $1.8693 | $1.8693 | $27.86 |
| **Total** | **$12.08** | **$1.92** | **$14.00** | **$40** |

By model, full runs: haiku $0.13, sonnet $5.70, opus $5.99, gpt-5.6-luna $0.18, gpt-5.6-terra $1.69.
Neither full run stopped at its cap; all items ran.

## Caveats (read before acting on this)

1. **The OpenAI models barely reasoned.** Effort was `medium` on every call, but gpt-5.6-luna
   produced reasoning tokens on only 1 of 174 stance calls and 20 of 50 extraction calls;
   gpt-5.6-terra on 114 of 135 verify calls (max 422 reasoning tokens). The client forces a tool
   choice on the Responses API, and that may suppress reasoning. So this measured the OpenAI models
   largely *without* their reasoning. It is a fair test of the configuration as shipped, not of
   what these models can do. Higher effort or an unforced tool choice is untested.
2. **The prompts were developed against Claude.** extract_v2 / stance_v1 / verify_v3 were never
   tuned for the OpenAI models, which biases the comparison toward Claude by an unknown amount.
3. **Small samples, no confidence intervals computed.** 48 extraction items and 15 refutes in
   stance. The verify and stance gaps (0.18 and 0.15 macro-F1) are large for 174 items. The
   extraction gap (0.096 on 48 items) is the least certain. A bootstrap over items would settle
   this cheaply, with no new calls, if the per-item outputs are kept.
4. **Cost trade-off.** gpt-5.6-terra is 3.5× cheaper per item than claude-opus-5-5 but
   0.18 macro-F1 lower. claude-sonnet-5-5 sits between them in both cost and score.
