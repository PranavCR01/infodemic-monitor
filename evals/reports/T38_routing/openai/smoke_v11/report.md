# Routing experiment (live)

Golden set: `git:origin/data/golden-label-set@0fbc68a05a7d:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `retrieved+cited`

Spend: **$0.0498** of cap $1.00 in 7 calls

**WARNING:** chosen verifier openai/gpt-5.6-terra@verify_v3 and the configured critic openai/gpt-4o-2024-08-06 come from the same provider; §13 wants them from different providers: change the critic before adopting routing_v2

## extract_claims (1 items)

Chosen: **openai/gpt-5.6-luna@extract_v2** (best claim_f1 (0.5000) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-luna@extract_v2 | claim_f1 | 0.5000 | 0/1 | $0.00177 | 10212.0 | gpt-5.6-luna (1) | 453 |

## analyze_stance (3 items)

Chosen: **openai/gpt-5.6-luna@stance_v1** (best stance_macro_f1 (1.0000) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-luna@stance_v1 | stance_macro_f1 | 1.0000 | 0/3 | $0.00048 | 2091.4 | gpt-5.6-luna (3) | 0 |

openai/gpt-5.6-luna@stance_v1: {"debunk_recall": null, "debunk_read_as_endorses": 0, "n_refutes": 0}

## verify_claims (3 items)

Chosen: **openai/gpt-5.6-terra@verify_v3** (best verification_macro_f1 (0.3333) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-terra@verify_v3 | verification_macro_f1 | 0.3333 | 0/3 | $0.01554 | 8869.4 | gpt-5.6-terra (3) | 685 |

openai/gpt-5.6-terra@verify_v3: {"insufficient_called_contradicted": 0, "unsupported_recall": null, "n_unsupported": 0}

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 1 | openai/gpt-5.6-luna@extract_v2 | 1 | 4,378 | 600 | 1,500 | 3,548 | $0.00 | $0.01 |
| analyze_stance | 3 | openai/gpt-5.6-luna@stance_v1 | 3 | 7,095 | 450 | 2,400 | 3,936 | $0.00 | $0.01 |
| verify_claims | 3 | openai/gpt-5.6-terra@verify_v3 | 3 | 20,724 | 1,200 | 7,500 | 10,572 | $0.15 | $0.36 |

extract_claims: 1 items; priced candidates total $0.00

analyze_stance: 3 items; priced candidates total $0.00

verify_claims: 3 items; priced candidates total $0.15

Total expected (priced candidates): **$0.15**; upper bound (every call at its output cap, every repair fired): $0.37.

Warning: verify_claims candidate openai/gpt-5.6-terra@verify_v3 shares the critic's provider (openai, gpt-4o-2024-08-06); if it wins, change the critic to another provider (§13)
