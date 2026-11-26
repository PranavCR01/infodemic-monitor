# T50 paid run (T53): model helpers on, tune split and the vitamin K job

Approved by the project lead on 2026-11-26, with a hard cap of $5.00 total. Run on 2026-11-26 from `auto/T50-paid`, which is `origin/langgraph-build` at d13f7b8 with #124 (T50) merged.
Helpers: `plan_search`, `translate_claim` and `find_study` all on `claude-haiku-5-5` (routing_v1). Web search costs $0.01 per search, and the gpt-4o fallback was never used.
Test split: not read. `TuneSet` drops non-tune rows before anything else sees them.

## Spend

| run | cap passed | spent | of which tokens | of which web search fees | stopped |
| --- | --- | --- | --- | --- | --- |
| 2: vitamin K job (13 claims) | $1.50 | **$0.0903** | $0.0103 | $0.08 (8 searches) | no |
| 3: tune split (187 claims) | $4.85 | **$1.0421** | $0.1521 | $0.89 (89 searches) | no |
| **total** | | **$1.1324** | $0.1624 | $0.97 | |

- These figures are the run's own spend counter: the router's per-call token cost at the `routing.yaml` prices, plus $0.01 per web search. The configured Haiku 5.5 price ($0.10/$0.50 per M tokens, prompts under 100K) matches the current list price. No prompt here exceeded about 24K tokens.
- Run 3's cap: the formula gives $3.50 + $1.4097 unspent = $4.9097. I passed $4.85 because the pre-call check sizes each call at the Haiku price and does not cover a gpt-4o fallback. The cap was not reached.
- Web search fees are about 86% of the spend. Tokens are cheap: Haiku find_study calls average about 23K input tokens and cost about $0.0026–0.0036 each in tokens.
- The first attempt at run 2 crashed while building its clients, before any model call. The OpenAI SDK refuses to start without a key, and the router builds that client only as the fallback. It spent $0 and wrote no output. I reran it once with a placeholder `OPENAI_API_KEY` for that command; the environment's proxy supplies the real OpenAI credential. No key was printed, logged or written.

## Vitamin K job, c2–c5 (pass = PMID 42986716 kept; JAMA 2026, doi:10.1001/jama.2026.21764)

| claim | text (start) | proposed? | verified? | kept? | result | failed at | web queries | cost | latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c2 | "a JAMA study published November 5th examined more than 5.2 million infants…" | yes | yes (efetch) | yes | **PASS** | – | 2 | $0.0224 | 5.5 s |
| c3 | "the percentage of newborns not receiving vitamin K more than doubled from 3.1%…" | no | – | no | **FAIL** | **proposal** | 2 | $0.0226 | 5.6 s |
| c4 | "babies who didn't receive vitamin K had a 47% higher risk of bleeding…" | yes | yes (efetch) | yes | **PASS** | – | 2 | $0.0226 | 5.4 s |
| c5 | "babies who didn't receive vitamin K had a higher risk of death associated with bleeding…" | no | – | no | **FAIL** | **proposal** | 2 | $0.0226 | 3.5 s |

On c3 and c5 the finder ran two relevant searches each, for example "newborns not receiving vitamin K 3.1% 2017 6.8% 2025 study" and "vitamin K omission infants death bleeding cohort study". It returned no candidate at all, so no verification or reranker step was involved.
Neither claim names the journal. The finder receives only the claim text and its citation cue, not the video context ("a JAMA study…" is in c2). Passing the job's cited study to the sibling claims is the obvious next step, but that is a design change, not part of this run.
On c3, c4 and c5 the reranker still kept 10 PubMed records from the rules search. The full candidate lists, plans and kept ids are in `vitk_paid.json`.

## Recall on the tune split (187 claims; 128 English, 59 non-English)

Three records, all with live PubMed and 3 rounds per claim:
- **old rules-only**: b52e952, `t50_search_recall.py record`. This is the baseline the task asked for.
- **new rules-only**: current code, recorded again in this run. It is free and isolates what the helpers add.
- **helpers on**: `tune_paid.json`.

Strict = a golden-cited PMID is kept (118 claims have one). Lenient = strict, or a kept record is on topic.

| set | yardstick | old rules-only | new rules-only | helpers on |
| --- | --- | --- | --- | --- |
| all (187) | lenient, T49 intervention | 51 (27.3%) | 113 (60.4%) | **119 (63.6%)** |
| all (187) | lenient, claim-concept | 74 (39.6%) | 149 (79.7%) | **156 (83.4%)** |
| all (118 w/ golden) | strict | 4 (3.4%) | 16 (13.6%) | **18 (15.3%)** |
| English (128) | lenient, intervention | 50 (39.1%) | 87 (68.0%) | **92 (71.9%)** |
| English (128) | lenient, claim | 66 (51.6%) | 107 (83.6%) | **113 (88.3%)** |
| English (84) | strict | 4 (4.8%) | 12 (14.3%) | **14 (16.7%)** |
| non-English (59) | lenient, intervention | 1 (1.7%) | 26 (44.1%) | **27 (45.8%)** |
| non-English (59) | lenient, claim | 8 (13.6%) | 42 (71.2%) | **43 (72.9%)** |
| non-English (34) | strict | 0 (0.0%) | 4 (11.8%) | **4 (11.8%)** |

D8 target (lenient ≥ 80%): met with the helpers on, on the claim-concept yardstick only (83.4%). It is not met on the T49 intervention yardstick (63.6%). Non-English claims remain the weak spot at 45.8% and 72.9%.

**Where the helpers' gain comes from.** Every claim that turned lenient comes from **find_study**: 6 on the intervention yardstick (v36:c7, v36:c9, v36:c16, v69:c2, v79:c2, v111:c1), plus v69:c7 on the claim yardstick. Both strict gains (v36:c9, v36:c16) are find_study too. Compared with new rules-only, no claim was lost.
Translation (56 claims translated) and plan_search (30 claims) changed no claim's lenient or strict outcome. The rules already reach those claims, or the helpers' queries reach the same records.
Caveat: live PubMed is not frozen, so the rules-only and helpers-on runs can differ slightly for reasons other than the helpers.

`recall_paid.md` is the scorer's output for old rules-only → helpers on. I edited its title and target lines because the template says "rules only".

## Cost and latency per helper (tune run)

| helper | calls | errors | fallback | token cost | per call | latency median / p90 / max |
| --- | --- | --- | --- | --- | --- | --- |
| plan_search | 31 | 0 | 0 | $0.0074 | $0.00024 | 1.1 / 1.5 / 1.7 s |
| translate_claim | 59 | 0 | 0 | $0.0025 | $0.00004 | 0.4 / 1.0 / 1.8 s |
| find_study | 40 | 0 | 0 | $0.1422 + $0.89 search fees | $0.0258 incl. fees (max $0.0359) | model turn 5.1 / 7.0 / 7.9 s; with verification 5.5 / 7.0 / 7.9 s (min 2.6 s) |

Per claim, over the whole tune run: $0.0056 on average. Claim latency covers planning, 3 PubMed rounds, the rerank and find_study when it fires. Median 1.8 s, p90 8.5 s, max 14.7 s.
find_study fired on 40 claims: 38 for `nothing_on_topic` and 2 for `cites_study`. That matches the dry-run estimate of 40.
Vitamin K run: 4 find_study calls (forced on c2–c5), with a model-turn median of 3.3 s and a mean of $0.0226 per claim including fees. No plan_search or translate_claim call fired on that job.

## Helper failures (tune run)

No timeouts, refusals, 5xx errors or fallbacks. No PubMed round failed.

- **translate_claim, empty output (3):** v114:c5, v167:c2, v167:c3. Those claims fell back to rules on the original text.
- **plan_search (1):** v176:c2. The call was made but no assisted query was used, and no error was recorded. That is silent. The other 30 calls produced a query.
- **find_study, no candidate proposed (21):** v23:c1, v36:c1, v68:c1, v69:c6, v71:c6, v86:c1, v86:c3, v100:c3, v109:c10, v109:c11, v119:c2, v120:c2, v121:c2, v121:c3, v135:c1, v135:c2, v135:c3, v167:c1, v167:c2, v167:c3, v177:c3.
- **find_study, proposed but dropped by verification as off topic (9 candidates):**
  - v27:c6: 27959714
  - v36:c2: 5641253
  - v58:c1: 29207043
  - v88:c1: 11472331
  - v110:c1: 33484383
  - v111:c2: 9685468
  - v111:c4: 28682366
  - v120:c4: 19724266
  - v167:c4: 41525571
  All have `mismatch` with "not about the claim's topic". Each is a real PMID/DOI that resolved, but its topic didn't match.
- **find_study, verified:** 11 candidates on 9 claims (v24:c2, v36:c7, v36:c9, v36:c16, v65:c3, v69:c2, v69:c7, v79:c2, v111:c1).
- **Invalid output or invented ids:** none. Every proposed PMID/DOI existed.

Out of 40 find_study claims, 9 got a verified record (22%), and 7 of those improved the claim's outcome.

### Crossref-only cases (not counted as helper failures)

Crossref is blocked from these containers.
- v86:c4: DOI 10.1101/2025.02.17.638720 (a bioRxiv preprint, not in PubMed). Outcome `error` (ProxyError) on the Crossref lookup.

Vitamin K run: none.

## Changes made for this run

`backend/scripts/t50_paid_run_live.py`: a failed PubMed round is now recorded and skipped, as `record()` already does. The record is also written on an unexpected crash, so money spent is never lost with no output. Model calls, the cap logic and the claim order are unchanged.
`backend/scripts/t53_paid_report.py`: an offline summariser for the paid-run records. It produced the helper tables and failure lists above.

## Files

- `vitk_paid.json`, `tune_paid.json`: per-claim records. They hold the plan, rounds, PubMed records (abstracts up to 3000 characters), find_study candidates and outcomes, kept ids, latency and cost, plus every router call. The `golden_cited` field contains public USDA FoodData URLs with `api_key=DEMO_KEY` from the golden dataset, which is not a secret.
- `recall_paid.md`: the scorer output, old rules-only → helpers on.
- The baseline and new rules-only records (5–8 MB each) are not committed. Rebuild them with `t50_search_recall.py record`: on a b52e952 checkout with the current script copied in, and on this branch.
