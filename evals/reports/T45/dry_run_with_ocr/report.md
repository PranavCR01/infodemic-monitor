# Routing experiment (dry_run)

Golden set: `git:948b1c2@948b1c2badfc:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `n/a`

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v2 | 50 | 235,832 | 30,000 | 0 | 102,400 | $0.77 | $3.23 |
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v3 | 50 | 274,360 | 30,000 | 0 | 102,400 | $0.85 | $3.42 |
| analyze_stance | 187 | anthropic/claude-sonnet-5-5@stance_v1 | 187 | 430,614 | 28,050 | 0 | 95,744 | $1.14 | $2.03 |
| analyze_stance | 187 | anthropic/claude-sonnet-5-5@stance_v2 | 187 | 522,354 | 28,050 | 0 | 95,744 | $1.33 | $2.26 |

extract_claims: 48 items; priced candidates total $1.62

analyze_stance: 187 items; priced candidates total $2.47

Total expected (priced candidates): **$4.09**; upper bound (every call at its output cap, every repair fired): $10.94.
