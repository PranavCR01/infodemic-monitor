# Routing experiment (live)

Golden set: `git:origin/data/golden-label-set@0fbc68a05a7d:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `retrieved+cited`

Spend: **$0.4769** of cap $1.00 in 21 calls

Model id: extract_claims: openai/gpt-5.6-luna@extract_v2: 1 calls reported no model id

Model id: analyze_stance: openai/gpt-5.6-luna@stance_v1: 3 calls reported no model id

Model id: verify_claims: openai/gpt-5.6-terra@verify_v3: 3 calls reported no model id

## extract_claims (1 items)

Chosen: **anthropic/claude-sonnet-5-5@extract_v2** (best claim_f1 (0.5000) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5-5@extract_v2 | claim_f1 | 0.4444 | 0/1 | $0.00093 | 1887.0 | claude-haiku-5-5 (1) | 0 |
| anthropic/claude-sonnet-5-5@extract_v2 | claim_f1 | 0.5000 | 0/1 | $0.01948 | 10765.0 | claude-sonnet-5-5 (1) | 0 |
| openai/gpt-5.6-luna@extract_v2 | claim_f1 | 0.0000 | 1/1 | n/a | 1383.0 | unreported (1) | 0 |

Excluded: {"openai/gpt-5.6-luna@extract_v2": "failure rate 1/1 over budget (0 served by the fallback model)"}

## analyze_stance (3 items)

Chosen: **anthropic/claude-haiku-5-5@stance_v1** (within 0.01 of the best stance_macro_f1; cheapest/fastest of 2 wins)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5-5@stance_v1 | stance_macro_f1 | 1.0000 | 0/3 | $0.00040 | 975.3 | claude-haiku-5-5 (3) | 0 |
| anthropic/claude-sonnet-5-5@stance_v1 | stance_macro_f1 | 1.0000 | 0/3 | $0.00787 | 8984.0 | claude-sonnet-5-5 (3) | 0 |
| openai/gpt-5.6-luna@stance_v1 | stance_macro_f1 | 0.0000 | 3/3 | n/a | 399.7 | unreported (3) | 0 |

anthropic/claude-haiku-5-5@stance_v1: {"debunk_recall": null, "debunk_read_as_endorses": 0, "n_refutes": 0}

anthropic/claude-sonnet-5-5@stance_v1: {"debunk_recall": null, "debunk_read_as_endorses": 0, "n_refutes": 0}

openai/gpt-5.6-luna@stance_v1: {"debunk_recall": null, "debunk_read_as_endorses": 0, "n_refutes": 0}

Excluded: {"openai/gpt-5.6-luna@stance_v1": "failure rate 3/3 over budget (0 served by the fallback model)"}

## verify_claims (3 items)

Chosen: **anthropic/claude-opus-5-5@verify_v3** (best verification_macro_f1 (1.0000) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@verify_v3 | verification_macro_f1 | 0.6667 | 0/3 | $0.02451 | 6309.4 | claude-sonnet-5-5 (3) | 0 |
| anthropic/claude-opus-5-5@verify_v3 | verification_macro_f1 | 1.0000 | 0/3 | $0.05002 | 11810.2 | claude-opus-5-5 (3) | 0 |
| openai/gpt-5.6-terra@verify_v3 | verification_macro_f1 | 0.0000 | 3/3 | n/a | 428.4 | unreported (3) | 0 |

anthropic/claude-sonnet-5-5@verify_v3: {"insufficient_called_contradicted": 0, "unsupported_recall": null, "n_unsupported": 0}

anthropic/claude-opus-5-5@verify_v3: {"insufficient_called_contradicted": 0, "unsupported_recall": null, "n_unsupported": 0}

openai/gpt-5.6-terra@verify_v3: {"insufficient_called_contradicted": 0, "unsupported_recall": null, "n_unsupported": 0}

Excluded: {"openai/gpt-5.6-terra@verify_v3": "failure rate 3/3 over budget (0 served by the fallback model)"}

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 1 | anthropic/claude-haiku-5-5@extract_v2 | 1 | 4,378 | 600 | 0 | 2,048 | $0.00 | $0.00 |
| extract_claims | 1 | anthropic/claude-sonnet-5-5@extract_v2 | 1 | 4,378 | 600 | 0 | 2,048 | $0.01 | $0.06 |
| extract_claims | 1 | openai/gpt-5.6-luna@extract_v2 | 1 | 4,378 | 600 | 1,500 | 3,548 | $0.00 | $0.01 |
| analyze_stance | 3 | anthropic/claude-haiku-5-5@stance_v1 | 3 | 7,095 | 450 | 0 | 1,536 | $0.00 | $0.00 |
| analyze_stance | 3 | anthropic/claude-sonnet-5-5@stance_v1 | 3 | 7,095 | 450 | 0 | 1,536 | $0.02 | $0.03 |
| analyze_stance | 3 | openai/gpt-5.6-luna@stance_v1 | 3 | 7,095 | 450 | 2,400 | 3,936 | $0.00 | $0.01 |
| verify_claims | 3 | anthropic/claude-sonnet-5-5@verify_v3 | 3 | 20,724 | 1,200 | 0 | 3,072 | $0.05 | $0.17 |
| verify_claims | 3 | anthropic/claude-opus-5-5@verify_v3 | 3 | 20,724 | 1,200 | 0 | 3,072 | $0.11 | $0.33 |
| verify_claims | 3 | openai/gpt-5.6-terra@verify_v3 | 3 | 20,724 | 1,200 | 7,500 | 10,572 | $0.15 | $0.36 |

extract_claims: 1 items; priced candidates total $0.02

analyze_stance: 3 items; priced candidates total $0.02

verify_claims: 3 items; priced candidates total $0.31

Total expected (priced candidates): **$0.35**; upper bound (every call at its output cap, every repair fired): $0.97.

Warning: verify_claims candidate openai/gpt-5.6-terra@verify_v3 shares the critic's provider (openai, gpt-4o-2024-08-06); if it wins, change the critic to another provider (§13)
