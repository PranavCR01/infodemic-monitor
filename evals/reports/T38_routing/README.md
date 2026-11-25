> **Update (2026-11-24, Option C):** the Claude candidates ran over the full tune split ($11.81). See
> [`report.md`](report.md). The smoke-test notes below are kept for history.

# T38 routing experiment: live run (2026-11-24) — STOPPED AT SMOKE TEST

Approved by the project lead (smoke cap $1, full-run cap $40). **The full tune-split run
was not started**, because every OpenAI candidate failed the smoke test.

## Smoke test

`run --live --max-usd 1 --videos v11 --frozen-evidence frozen_evidence_tune.json`
(tune video v11: 1 extraction item, 3 stance items, 3 verify items, all 3 claims with evidence).
Frozen evidence: `origin/data/t38-frozen-evidence` (174/174 tune claims, claim text unchanged
on golden @ 0fbc68a, so no re-freeze was needed).

| step | candidate | result |
|---|---|---|
| extract_claims | claude-haiku-5-5 | ok, 1/1, model id reported |
| extract_claims | claude-sonnet-5-5 | ok, 1/1, model id reported |
| extract_claims | **gpt-5.6-luna** | **FAILED 1/1 (HTTP 400)** |
| analyze_stance | claude-haiku-5-5 | ok, 3/3 |
| analyze_stance | claude-sonnet-5-5 | ok, 3/3 |
| analyze_stance | **gpt-5.6-luna** | **FAILED 3/3 (HTTP 400)** |
| verify_claims | claude-sonnet-5-5 | ok, 3/3 |
| verify_claims | claude-opus-5-5 | ok, 3/3 |
| verify_claims | **gpt-5.6-terra** | **FAILED 3/3 (HTTP 400)** |

Exact error, identical on all 7 OpenAI calls (model name varies):

> Error code: 400 - Function tools with reasoning_effort are not supported for gpt-5.6-luna
> in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.

So the OpenAI responses carried no model id and no reasoning-token counts (nothing was returned).
The Anthropic candidates all returned valid, parsed output and reported their model ids.
Scores in `smoke_v11/report.md` are from 1 video and mean nothing; its routing_v2.yaml is not
committed for that reason.

## Spend

| | booked by SpendGuard | actual (provider-billed) |
|---|---|---|
| Anthropic (haiku, sonnet, opus) | $0.2688 | $0.2688 |
| OpenAI (7 calls, all 400) | $0.2081 | ~$0.00 (400s return no tokens) |
| **Total** | **$0.4769** | **~$0.27** |

SpendGuard books a failed call's worst-case reservation, so its total overstates real OpenAI
spend. Both figures are within the $1 smoke cap. Full run: $0 (not started).

## Why not fixed here

The run rules allow fixing an *obvious* bug and re-running the smoke test once. Neither fix is
that; both are a person's decision:

1. **Set `reasoning_effort: none`** for gpt-5.6-luna/terra (config only). This changes the
   approved candidates (no reasoning at all), and the `reasoning_tokens` allowances and the
   dry-run estimate no longer describe what is being measured.
2. **Send OpenAI tool calls through `/v1/responses`** in `OpenAIModelClient` when a reasoning
   model gets tools. Keeps medium effort but is a real client change (request/response shape,
   usage fields, reasoning tokens, forced tool choice) that needs tests before paid calls.

After either fix: re-run this smoke test (~$0.35 expected) before the full run
($15.36 expected / $42.67 upper bound by the dry run — note the upper bound is above $40, so the
runner's cap could stop the full run).
