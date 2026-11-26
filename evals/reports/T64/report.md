# T64: unproven-label fixes (a, b, c, e, f)

Built: (a) `search_too_thin`, (b) `contradicted_by_sibling_claim`, (c) `outcome_unspecified`,
(e) reranker demotes "vitamin K antagonist(s)"-only records, (f) `main_claims_unchecked`.
(d) extraction context resolution: **deferred** (lead decision 2026-11-26). No model calls,
no migration, test split not read.

## Production regression: job d2bf4179 (vitamin K re-analysis)

Real production rows, `backend/app/tests/fixtures/prod_d2bf4179/vitamin_k_rerun.real.json`
(commit 90823dc), used as-is (`backend/app/tests/test_unproven_fixes_t64.py`):

| run | label | c12 verdict | review reasons added |
| --- | --- | --- | --- |
| production (main 91a7a13) | MISINFO (unproven), decided by c12 | UNSUPPORTED | `unproven_claim:c12` |
| replay without T64 | MISINFO (unproven), decided by c12 (reproduced) | UNSUPPORTED | |
| replay with T64 (real verify node + judge) | **NO_MISINFO** | INSUFFICIENT_EVIDENCE | `judge:main_claims_unchecked` |
| (c) alone, c12's record on topic as in prod | NO_MISINFO | INSUFFICIENT_EVIDENCE `outcome_unspecified` | `main_claims_unchecked` |
| (a) alone, same | NO_MISINFO | INSUFFICIENT_EVIDENCE `search_too_thin` | `main_claims_unchecked` |
| (b) alone, same | NO_MISINFO | INSUFFICIENT_EVIDENCE `contradicted_by_sibling_claim` | `main_claims_unchecked`, `unproven_claim:c12` (kept) |

The fixture has titles, not abstracts. On titles alone c12's one record (brodifacoum case
report) fails T49's on-topic check, so the full T64 node turns c12 to INSUFFICIENT_EVIDENCE
via `search_found_nothing_on_topic` first. In production the abstract named vitamin K and
the record passed. The "alone" rows therefore treat c12's record as on topic, as production
did, so each new rule is shown to clear the label on its own.

(e) on the real c13 rows: the three papers whose only vitamin K mention is "vitamin K
antagonist(s)" were kept at relevance 1.0 in production. On their titles they now score 0
for vitamin K and are dropped. A record that also names vitamin K plainly ("reversal of
vitamin K antagonists with intravenous vitamin K") still counts.

## Tune replay (T49 replay extended): label changes, before → after

Before: code a67f8ca97bb8 (langgraph-build). After: code af6e54d5d27c (auto/T64). Golden set: in-repo `research/claim-level/dataset`, tune split only; golden stances and verdicts, with each golden UNSUPPORTED claim re-checked by the guard on the evidence the verifier would see. No model calls.

## Evidence `frozen`

Tune unproven videos keeping MISINFO (unproven): before 0/5 (none), after 0/5 (none).

Videos whose label changes: 0 of 55 tune videos.

Every golden UNSUPPORTED claim whose verdict changes (label may not):

- none

`main_claims_unchecked` (f) raised on: v22, v141 (categories from the frozen recording; golden claims have none).

## Evidence `live`

Tune unproven videos keeping MISINFO (unproven): before 4/5 (v22, v36, v141, v143), after 4/5 (v22, v36, v141, v143).

Videos whose label changes: 0 of 55 tune videos.

Every golden UNSUPPORTED claim whose verdict changes (label may not):

- v36:c6 "Irish Sea Moss: Cures Thyroid Issues": UNSUPPORTED → INSUFFICIENT_EVIDENCE `search_too_thin` (2 kept, 2 on topic, types ['other'])

`main_claims_unchecked` (f) raised on: none (categories from the frozen recording; golden claims have none).

Evidence sources: `frozen` = T38 frozen evidence (`origin/data/t38-frozen-evidence`, what the
pipeline's retrieval kept), re-ranked by the code under test. `live` = a fresh rules-only
recording (planner queries against live PubMed, 3 rounds, no model; recorded
2026-11-26T21:15:05Z with code 23f6f2ffb158). It is the same source as the T50 replay and is
not committed because it contains PubMed abstracts; re-record with
`scripts/t64_unproven_replay.py --record`. Both versions were run on the same evidence:
before = a worktree of origin/langgraph-build a67f8ca, after = this branch. Results are in
`before.json` and `after.json`.

**Unproven tune videos: 4/5 keep MISINFO (unproven) on live evidence (unchanged:
v22, v36, v141, v143; v120 stays CANNOT_RECOGNIZE as before), and 0/5 on the T38 frozen
evidence (unchanged; T49 explains why).** No tune video changes label. One claim changes
verdict, v36:c6 (sea moss / thyroid: 2 on-topic records of type `other`) → `search_too_thin`.
v36 stays MISINFO (unproven) through c10 and c14.

### Rule (b) as written in the queue row vs as built

The queue row's literal rule (same intervention only) changes **one** tune label: **v22
MISINFO (unproven) → NO_MISINFO**. Its c2 "eggs ... prevent macular degeneration"
(UNSUPPORTED, 10 on-topic records) was demoted because c3 "eggs ... prevent a fatty liver"
is SUPPORTED. That is 3/5. A supported claim about one outcome says nothing about another,
so (b) is built narrower. The sibling must also not name a *different* outcome
(`unproven_guard.same_outcome`): the UNSUPPORTED claim names no outcome (vitamin K c12, "a
potentially devastating condition"), or the two share one. Literal-rule results:
`after_literal_b.json`.

## Judge cross-check

Re-run on the committed fixture and on `origin/data/golden-label-set` (both at 92a731e).
The report is **byte-identical** before and after: label 162/162, basis 162/162, deciding
162/162, sent to review 162/162, review reasons exact 149/162 (13 videos, all
`weak_evidence_covered_by_judge_reason`, as before), golden judge reproduces videos.csv
181/181. **No re-pinning is needed.** (a), (b), (c) and (e) live in the verify step and the
reranker, not the judge, as T49's guard does. (f) needs claim categories, and the golden
set has none: `build_state` gives only UNSUPPORTED claims an efficacy category, so no
INSUFFICIENT_EVIDENCE claim is ever a main claim there. The cross-check documents the
backend-only kind `main_claims_unchecked_not_in_golden_judge` for when categories arrive.
