# T50 dry-run cost estimate (no model was called)

Routing: `routing_v1`; plan_search claude-haiku-5-5, translate_claim claude-haiku-5-5, find_study claude-haiku-5-5 with web search ($0.010/search, max 3 searches per claim).

Expected: one attempt, typical output, 2 searches x 3000 result tokens. Upper bound: every call retried once, output at its cap, 3 searches x 8000 result tokens. The router's fallback model (gpt-4o) is not in the bound: it is only used after the primary times out or fails twice, and the paid run's cap still applies.

## vitamin K job (13 claims; find-the-study forced on c2-c5)

| step | calls | expected USD | upper bound USD |
| --- | --- | --- | --- |
| plan_search | 0 | 0.0000 | 0.0000 |
| translate_claim | 0 | 0.0000 | 0.0000 |
| find_study | 8 | 0.1664 | 0.5243 |
| **total** | 8 | **0.1664** | **0.5243** |

Per claim: expected 0.01280 USD, upper 0.04033 USD on average; max upper for one claim 0.06554 USD.

find_study triggers: {'forced': 4, 'nothing_on_topic': 4}.

## tune split recall (187 claims)

| step | calls | expected USD | upper bound USD |
| --- | --- | --- | --- |
| plan_search | 31 | 0.0045 | 0.0167 |
| translate_claim | 59 | 0.0030 | 0.0143 |
| find_study | 38 | 0.7903 | 2.4907 |
| **total** | 128 | **0.7978** | **2.5216** |

Per claim: expected 0.00427 USD, upper 0.01348 USD on average; max upper for one claim 0.06633 USD.

find_study triggers: {'nothing_on_topic': 36, 'cites_study': 2}.

## Latency (expected, per claim that calls the step)

- translate_claim, plan_search: one cheap-model call each, about 1-2 s.
- find_study: one model turn with up to 3 server-side searches, about 5-15 s; then our verification, about 0.4 s per candidate on E-utilities (2.5 requests/s, 1-3 requests each) and up to 0.5 s per Crossref lookup.

