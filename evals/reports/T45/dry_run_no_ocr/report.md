# Routing experiment (dry_run)

Golden set: `git:948b1c2@948b1c2badfc:research/claim-level/dataset`, split **tune** only.
Evidence mode (verify_claims): `n/a`

**extract_claims ran WITHOUT on-screen text** (`extraction.use_ocr: false`, config/pipeline.yaml ablation). Stance still sees OCR.

| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |
|---|---|---|---|---|---|---|---|---|---|
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v2 | 47 | 144,713 | 28,200 | 0 | 96,256 | $0.57 | $2.65 |
| extract_claims | 48 | anthropic/claude-sonnet-5-5@extract_v3 | 47 | 180,932 | 28,200 | 0 | 96,256 | $0.64 | $2.83 |

extract_claims: 48 items; priced candidates total $1.22

Total expected (priced candidates): **$1.22**; upper bound (every call at its output cap, every repair fired): $5.48.
