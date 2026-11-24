# Routing experiment (live)

Golden set: `git:origin/data/golden-label-set@0fbc68a05a7d:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `retrieved+cited`

Spend: **$1.8693** of cap $27.86 in 359 calls

**WARNING:** chosen verifier openai/gpt-5.6-terra@verify_v3 and the configured critic openai/gpt-4o-2024-08-06 come from the same provider; §13 wants them from different providers: change the critic before adopting routing_v2

## extract_claims (48 items)

Chosen: **openai/gpt-5.6-luna@extract_v2** (best claim_f1 (0.3237) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-luna@extract_v2 | claim_f1 | 0.3237 | 0/48 | $0.00200 | 17577.099999999995 | gpt-5.6-luna (50) | 7,175 |

## analyze_stance (174 items)

Chosen: **openai/gpt-5.6-luna@stance_v1** (best stance_macro_f1 (0.4977) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-luna@stance_v1 | stance_macro_f1 | 0.4977 | 0/174 | $0.00046 | 1884.5 | gpt-5.6-luna (174) | 436 |

openai/gpt-5.6-luna@stance_v1: {"debunk_recall": 0.6, "debunk_read_as_endorses": 1, "n_refutes": 15}

## verify_claims (174 items)

Chosen: **openai/gpt-5.6-terra@verify_v3** (best verification_macro_f1 (0.4919) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-5.6-terra@verify_v3 | verification_macro_f1 | 0.4919 | 0/174 | $0.00973 | 6412.199999999999 | gpt-5.6-terra (135) | 13,694 |

openai/gpt-5.6-terra@verify_v3: {"insufficient_called_contradicted": 2, "unsupported_recall": 1.0, "n_unsupported": 5}

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 48 | openai/gpt-5.6-luna@extract_v2 | 50 | 235,832 | 30,000 | 75,000 | 177,400 | $0.17 | $0.54 |
| analyze_stance | 174 | openai/gpt-5.6-luna@stance_v1 | 174 | 399,881 | 26,100 | 139,200 | 228,288 | $0.28 | $0.37 |
| verify_claims | 174 | openai/gpt-5.6-terra@verify_v3 | 135 | 833,182 | 54,000 | 337,500 | 475,740 | $6.36 | $15.58 |

extract_claims: 48 items; priced candidates total $0.17

analyze_stance: 174 items; priced candidates total $0.28

verify_claims: 174 items; priced candidates total $6.36

Total expected (priced candidates): **$6.82**; upper bound (every call at its output cap, every repair fired): $16.50.

Warning: verify_claims candidate openai/gpt-5.6-terra@verify_v3 shares the critic's provider (openai, gpt-4o-2024-08-06); if it wins, change the critic to another provider (§13)
