# Routing experiment (live)

Golden set: `git:92a731e@92a731e7f954:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `n/a`

Spend: **$3.3656** of cap $10.00 in 374 calls

## analyze_stance (187 items)

Chosen: **anthropic/claude-sonnet-5-5@stance_v1** (best stance_macro_f1 (0.5463) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@stance_v1 | stance_macro_f1 | 0.5463 | 0/187 | $0.00840 | 3312.7999999999997 | claude-sonnet-5-5 (187) | 0 |
| anthropic/claude-sonnet-5-5@stance_v2 | stance_macro_f1 | 0.4561 | 0/187 | $0.00960 | 3669.2999999999943 | claude-sonnet-5-5 (187) | 0 |

anthropic/claude-sonnet-5-5@stance_v1: {"debunk_recall": 0.8125, "debunk_read_as_endorses": 1, "n_refutes": 16}

anthropic/claude-sonnet-5-5@stance_v2: {"debunk_recall": 0.875, "debunk_read_as_endorses": 1, "n_refutes": 16}

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| analyze_stance | 187 | anthropic/claude-sonnet-5-5@stance_v1 | 187 | 451,775 | 28,050 | 0 | 95,744 | $1.18 | $2.09 |
| analyze_stance | 187 | anthropic/claude-sonnet-5-5@stance_v2 | 187 | 539,981 | 28,050 | 0 | 95,744 | $1.36 | $2.31 |

analyze_stance: 187 items; priced candidates total $2.54

Total expected (priced candidates): **$2.54**; upper bound (every call at its output cap, every repair fired): $4.39.
