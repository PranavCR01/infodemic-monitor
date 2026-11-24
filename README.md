# Frozen retrieval for the routing experiment (T38)

`frozen_evidence_tune.json` is the evidence every verify_claims candidate sees in the
routing experiment (design §13, §14; `backend/app/evaluation/routing_experiment/`).
Recorded once, on 2026-11-24, with
`python -m app.evaluation.routing_experiment freeze-evidence` (free: PubMed E-utilities at
<= 2.5 requests/second and the §6 reference allow-list; no model calls) from the golden
set's **tune split only** (`data/golden-label-set` @ 022ac44).

174 claims; per claim: the planner's queries (full 3-round budget), the reranked
retrieved records, the records the gold label cites (abstracts from PubMed, reference
passages from `reference_citations.csv`), search errors (none) and the claim_category
rule's output.

Use it without checking this branch out:

    git fetch origin data/t38-frozen-evidence
    git show origin/data/t38-frozen-evidence:frozen_evidence_tune.json > /tmp/frozen_evidence_tune.json
    cd backend && python -m app.evaluation.routing_experiment run --frozen-evidence /tmp/frozen_evidence_tune.json

Do not re-record it for a paid run unless the golden set's tune claims changed: the point
is that every candidate, in every run, sees identical evidence.
