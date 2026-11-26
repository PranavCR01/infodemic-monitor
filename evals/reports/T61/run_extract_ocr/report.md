# Routing experiment (live)

Golden set: `git:92a731e@92a731e7f954:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `n/a`

Spend: **$2.4613** of cap $6.63 in 100 calls

## extract_claims (48 items)

Chosen: **anthropic/claude-sonnet-5-5@extract_v3** (best claim_f1 (0.5276) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@extract_v2 | claim_f1 | 0.4364 | 0/48 | $0.02499 | 10043.65 | claude-sonnet-5-5 (50) | 0 |
| anthropic/claude-sonnet-5-5@extract_v3 | claim_f1 | 0.5276 | 0/48 | $0.02628 | 8844.4 | claude-sonnet-5-5 (50) | 0 |

Claim matching, strict (token Jaccard >= 0.5; the selection metric) next to meaning-based (T43 content-word overlap; text only):

| candidate | strict P | strict R | strict F1 | meaning P | meaning R | meaning F1 | gold | predicted |
|---|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@extract_v2 | 0.3306 | 0.6417 | 0.4364 | 0.4132 | 0.8021 | 0.5455 | 187 | 363 |
| anthropic/claude-sonnet-5-5@extract_v3 | 0.3893 | 0.8182 | 0.5276 | 0.4326 | 0.9091 | 0.5862 | 187 | 393 |

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v2 | 50 | 235,832 | 30,000 | 0 | 102,400 | $0.77 | $3.23 |
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v3 | 50 | 274,360 | 30,000 | 0 | 102,400 | $0.85 | $3.42 |

extract_claims: 48 items; priced candidates total $1.62

Total expected (priced candidates): **$1.62**; upper bound (every call at its output cap, every repair fired): $6.65.
