# Routing experiment (live)

Golden set: `git:92a731e@92a731e7f954:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `n/a`

**extract_claims ran WITHOUT on-screen text** (`extraction.use_ocr: false`, config/pipeline.yaml ablation). Stance still sees OCR.

Spend: **$2.1411** of cap $4.17 in 94 calls

Model id: extract_claims: anthropic/claude-sonnet-5-5@extract_v3: 34 calls reported no model id

## extract_claims (48 items)

Chosen: **anthropic/claude-sonnet-5-5@extract_v2** (best claim_f1 (0.4142) within budget)

| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |
|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@extract_v2 | claim_f1 | 0.4142 | 0/48 | $0.01578 | 7540.9 | claude-sonnet-5-5 (47) | 0 |
| anthropic/claude-sonnet-5-5@extract_v3 | claim_f1 | 0.2617 | 34/48 | n/a | 6184.3 | claude-sonnet-5-5 (13), unreported (34) | 0 |

Claim matching, strict (token Jaccard >= 0.5; the selection metric) next to meaning-based (T43 content-word overlap; text only):

| candidate | strict P | strict R | strict F1 | meaning P | meaning R | meaning F1 | gold | predicted |
|---|---|---|---|---|---|---|---|---|
| anthropic/claude-sonnet-5-5@extract_v2 | 0.3281 | 0.5615 | 0.4142 | 0.4281 | 0.7326 | 0.5404 | 187 | 320 |
| anthropic/claude-sonnet-5-5@extract_v3 | 0.3514 | 0.2086 | 0.2617 | 0.4144 | 0.2460 | 0.3087 | 187 | 111 |

Excluded: {"anthropic/claude-sonnet-5-5@extract_v3": "failure rate 34/48 over budget (0 served by the fallback model)"}

## Estimate before the run

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v2 | 47 | 144,713 | 28,200 | 0 | 96,256 | $0.57 | $2.65 |
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v3 | 47 | 180,932 | 28,200 | 0 | 96,256 | $0.64 | $2.83 |

extract_claims: 48 items; priced candidates total $1.22

Total expected (priced candidates): **$1.22**; upper bound (every call at its output cap, every repair fired): $5.48.
