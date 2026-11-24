# T38 routing experiment: Claude candidates (Option C, 2026-11-24)

**These are tune-split numbers (55 videos), not the held-out test, so they are not the
system's accuracy.** They choose models. They don't measure the product.

Option C (project lead, 2026-11-24): run the Claude candidates now with `--live --max-usd 25`
and leave the OpenAI candidates out. gpt-5.6-luna and gpt-5.6-terra run later on the **same**
frozen evidence, once the Responses-API client (T41) lands.

## What ran

```
python -m app.evaluation.routing_experiment run --live --max-usd 25 \
  --candidates evals/reports/T38_routing/candidates_claude.yaml \
  --frozen-evidence frozen_evidence_tune.json \
  --out evals/reports/T38_routing/claude/
```

- Golden set: `origin/data/golden-label-set@0fbc68a05a7d`, split **tune** only (test split not read).
- Items: extract_claims 48, analyze_stance 174, verify_claims 174 (evidence mode `retrieved+cited`).
- Candidates: `candidates_claude.yaml`, which is `backend/config/routing_experiment.yaml` (unchanged)
  with every `provider: openai` entry removed. The dry run confirmed no OpenAI candidate remained.
- **Frozen evidence.** The later OpenAI run must use exactly this file:
  - source: `git show origin/data/t38-frozen-evidence:frozen_evidence_tune.json` (commit `96f5e23`)
  - git blob: `5af42593b985e28fd510dc47b77d87b35b8b054e`
  - **sha256: `c4ff82bf69dc85c3b80503a2b7d559b820255b1a90ac3a3fc069593e8d4d4ca5`** (2,124,308 bytes)

## Results per step

| step | candidate | metric | score | failed | cost/item | step cost | p50 / p95 latency (ms) | calls |
|---|---|---|---|---|---|---|---|---|
| extract_claims | claude-haiku-5-5 | claim_f1 | 0.3601 | 0/48 | $0.00124 | $0.06 | 2,678 / 5,503 | 50 |
| extract_claims | **claude-sonnet-5-5** | claim_f1 | **0.4193** | 0/48 | $0.02510 | $1.20 | 4,639 / 10,415 | 50 |
| analyze_stance | claude-haiku-5-5 | stance_macro_f1 | 0.5230 | 0/174 | $0.00040 | $0.07 | 947 / 1,199 | 174 |
| analyze_stance | **claude-sonnet-5-5** | stance_macro_f1 | **0.6436** | 0/174 | $0.00805 | $1.40 | 2,042 / 3,951 | 174 |
| verify_claims | claude-sonnet-5-5 | verification_macro_f1 | 0.6073 | 0/174 | $0.01777 | $3.09 | 3,707 / 6,539 | 146 |
| verify_claims | **claude-opus-5-5** | verification_macro_f1 | **0.6759** | 0/174 | $0.03441 | $5.99 | 6,113 / 9,556 | 135 |

Secondary metrics:
- Stance: debunk recall haiku 0.67, sonnet 0.80 (n_refutes = 15). Each read one debunk as "endorses".
- Verify: both models had unsupported recall 1.0 (n = 5) and called "insufficient" "contradicted" 4 times.

Every call reported the model id it was asked for. There were 0 fallbacks, 0 provider errors and
0 reasoning tokens. Sonnet verify made 146 calls for 135 batches; the 11 extra are the runner's repair retries.

## Best Claude model per step (provisional)

| step | winner | margin over the other Claude candidate | cost ratio |
|---|---|---|---|
| extract_claims | claude-sonnet-5-5 | +0.059 claim_f1 | 20× haiku |
| analyze_stance | claude-sonnet-5-5 | +0.121 macro-F1 | 20× haiku |
| verify_claims | claude-opus-5-5 | +0.069 macro-F1 | 1.9× sonnet |

Written to `routing_v2.yaml`, marked **"provisional: OpenAI candidates not yet run"**.
`config/routing.yaml` is unchanged.

### Caveats
- **No confidence intervals.** The runner keeps no per-item predictions, so I couldn't run a paired
  bootstrap. The minority classes the macro-F1s hinge on are small (15 refutes, 5 unsupported), so
  margins of 0.06–0.07 (extract, verify) may be within noise. The stance margin (0.12) is more
  likely real, but that's not tested.
- Extraction is weak for both models (claim F1 ≤ 0.42). Model choice isn't the main lever there.
- The selection rule only prefers the cheaper model within `tie_margin` 0.01, so it will pay 20× for
  any gain larger than that. Whether +0.06 F1 is worth 20× cost on extraction is a person's call.
- 1 tune split, 1 run per candidate, temperature as configured. Run-to-run variance wasn't measured.

## Cost

| provider | this run | notes |
|---|---|---|
| Anthropic | **$11.8135** (haiku $0.13, sonnet $5.70, opus $5.99) | 729 calls, 0 refused, not stopped at cap |
| OpenAI | **$0.00** | no OpenAI candidates in this run |
| **Total this run** | **$11.81** of $25 cap | |

Dry-run estimate was $8.54 expected / $26.17 upper bound. Actual cost was 1.38× expected, in line with
the smoke test's 1.26–1.40× (the estimator undercounts input tokens by about 30%).

**Total T38 spend so far:** $12.08 actual ($0.27 smoke + $11.81). SpendGuard booked $12.29
($0.48 smoke, including failed-call reservations, + $11.81).

## Deviations to know about
1. **Upper-bound gate.** The instructions said to confirm the dry-run upper bound was under $25. It was
   $26.17. I ran anyway for three reasons. SpendGuard refuses any call whose worst case would cross the
   cap, so overspending isn't possible. The smoke test's actual Claude costs were ≤ 0.7× the upper bound
   for every candidate. And the projected cost was about $12. The only risk was a partial run, and that
   didn't happen.
2. **Dummy OpenAI key.** `default_clients()` builds the OpenAI SDK client even when no candidate uses
   it, and the SDK refuses to start without a key. The first attempt crashed at startup before any call
   ($0). The real run passed `OPENAI_API_KEY=dummy-unused` to the runner process only. No OpenAI call
   was made (the per-model spend lists only Claude models). No code changed. A small follow-up: build
   provider clients lazily.
3. No new smoke test. PR #104's smoke test already showed all six Claude candidates returning valid output.

## Files
- `candidates_claude.yaml`: the candidate set that ran
- `claude/report.md`: the runner's own report, including the estimate table
- `claude/report.json`: summary with per-call records removed (17 KB), plus the frozen-evidence hash
- `routing_v2.yaml`: provisional proposed routing
