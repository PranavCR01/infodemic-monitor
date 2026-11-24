# Routing experiment (live)

Golden set: `git:origin/data/golden-label-set@0fbc68a05a7d:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `retrieved+cited`

Spend: **$11.8135** of cap $25.00 in 729 calls

## extract_claims (48 items)

Chosen: **anthropic/claude-sonnet-5-5@extract_v2** (best claim_f1 (0.4193) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5-5@extract_v2 | claim_f1 | 0.3601 | 0/48 | $0.00124 | 5503.349999999999 | claude-haiku-5-5 (50) | 0 |
| anthropic/claude-sonnet-5-5@extract_v2 | claim_f1 | 0.4193 | 0/48 | $0.02510 | 10414.8 | claude-sonnet-5-5 (50) | 0 |

## analyze_stance (174 items)

Chosen: **anthropic/claude-sonnet-5-5@stance_v1** (best stance_macro_f1 (0.6436) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5-5@stance_v1 | stance_macro_f1 | 0.5230 | 0/174 | $0.00040 | 1198.85 | claude-haiku-5-5 (174) | 0 |
| anthropic/claude-sonnet-5-5@stance_v1 | stance_macro_f1 | 0.6436 | 0/174 | $0.00805 | 3950.7 | claude-sonnet-5-5 (174) | 0 |

anthropic/claude-haiku-5-5@stance_v1: {"debunk_recall": 0.6666666666666666, "debunk_read_as_endorses": 1, "n_refutes": 15}

anthropic/claude-sonnet-5-5@stance_v1: {"debunk_recall": 0.8, "debunk_read_as_endorses": 1, "n_refutes": 15}

## verify_claims (174 items)

Chosen: **anthropic/claude-opus-5-5@verify_v3** (best verification_macro_f1 (0.6759) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@verify_v3 | verification_macro_f1 | 0.6073 | 0/174 | $0.01777 | 6539.25 | claude-sonnet-5-5 (146) | 0 |
| anthropic/claude-opus-5-5@verify_v3 | verification_macro_f1 | 0.6759 | 0/174 | $0.03441 | 9556.2 | claude-opus-5-5 (135) | 0 |

anthropic/claude-sonnet-5-5@verify_v3: {"insufficient_called_contradicted": 4, "unsupported_recall": 1.0, "n_unsupported": 5}

anthropic/claude-opus-5-5@verify_v3: {"insufficient_called_contradicted": 4, "unsupported_recall": 1.0, "n_unsupported": 5}

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 48 | anthropic/claude-haiku-5-5@extract_v2 | 50 | 235,832 | 30,000 | 0 | 102,400 | $0.04 | $0.16 |
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v2 | 50 | 235,832 | 30,000 | 0 | 102,400 | $0.77 | $3.23 |
| analyze_stance | 174 | anthropic/claude-haiku-5-5@stance_v1 | 174 | 399,881 | 26,100 | 0 | 89,088 | $0.05 | $0.09 |
| analyze_stance | 174 | anthropic/claude-sonnet-5-5@stance_v1 | 174 | 399,881 | 26,100 | 0 | 89,088 | $1.06 | $1.89 |
| verify_claims | 174 | anthropic/claude-sonnet-5-5@verify_v3 | 135 | 833,182 | 54,000 | 0 | 138,240 | $2.21 | $6.93 |
| verify_claims | 174 | anthropic/claude-opus-5-5@verify_v3 | 135 | 833,182 | 54,000 | 0 | 138,240 | $4.41 | $13.86 |

extract_claims: 48 items; priced candidates total $0.81

analyze_stance: 174 items; priced candidates total $1.11

verify_claims: 174 items; priced candidates total $6.62

Total expected (priced candidates): **$8.54**; upper bound (every call at its output cap, every repair fired): $26.17.
