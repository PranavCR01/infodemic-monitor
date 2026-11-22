# Automated build queue

The automated build of the target system (`docs/target-system-design.md`) works through
this list one task at a time. The orchestrator session reads this file every hour,
starts the next ready task, and records progress here.

- **Integration branch:** `langgraph-build`. Every task merges into it. `main` is never touched.
- **Up to 3 tasks at a time.** A task is *ready* when it is `todo` and every dependency is `done`. Ready tasks start immediately; nobody waits for the hourly wake-up.
- **Statuses:** `todo` · `in_progress` · `done` · `blocked` (with the reason in Notes).
- **People merge `langgraph-build` into `main`**, in reviewed chunks. Automation never does.

| ID | Task | Issue | Doc § | Depends on | Status | Session | Started (UTC) | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| T01 | Evaluation framework and routing harness (mocked models; no paid runs) | new | 13, 14 | — | done | session_013cWxpykbHfbgKcp3qazzmb | 2026-11-21 23:51 | https://github.com/PranavCR01/infodemic-monitor/pull/50 | Built and tested with mocks only. Routing table is provisional; paid runs, the routing decision, real provider clients for ModelRouter and checking model ids/prices are left for T14 / a person |
| T02 | LangGraph skeleton: typed state, stub nodes, Postgres checkpointing | #29 | 4, 5 | — | done | session_013cWxq2fmACtMefWPTdEkMT | 2026-11-21 23:53 | https://github.com/PranavCR01/infodemic-monitor/pull/49 | Taken over from Jared by decision of the project lead. Resume test passed on InMemorySaver and local Postgres 16; Supabase `langgraph` schema run left for a person (#47) |
| T03 | Retrieval planning and PubMed evidence retriever | #31 | 6 | T02 | done | session_013cWxpzsTJuP1VYHqJT9oWT | 2026-11-22 00:02 | https://github.com/PranavCR01/infodemic-monitor/pull/52 | NCBI unreachable from the build env: fixtures are synthetic in NCBI's format; the live 10-claim evidence sample is left for a person (`scripts/record_pubmed_fixtures.py`, MULTI_AGENT §7d) |
| T04 | Stance analyzer node | #30 | 5 | T02 | done | session_013cWxpyUeq4YuAXTpZfndft | 2026-11-22 00:02 | https://github.com/PranavCR01/infodemic-monitor/pull/51 | 27-example stance set; keyword floor debunk recall 0.78; LLM run waits for API keys |
| T05 | Rerank and filter evidence | #32 | 6 | T03 | done | session_013cWxq2fKcmqBDmwsYQQwEz | 2026-11-22 00:16 | https://github.com/PranavCR01/infodemic-monitor/pull/54 | Deterministic lexical reranker + study-type lookup; precision@5 0.53 vs 0.38 PubMed order on a 12-claim synthetic, self-labelled set. Real PubMed labels by two people left for a person (MULTI_AGENT §7f) |
| T06 | Evidence verifier node | #33 | 7 | T03, T05 | done | session_013cWxpycmynMxF5EZ63Zwu8 | 2026-11-22 00:28 | https://github.com/PranavCR01/infodemic-monitor/pull/55 | Invalid citations reject the answer (1 repair, then INSUFFICIENT + review). 20-claim synthetic self-labelled set; heuristic floor macro F1 0.87 (inflated by construction). LLM run waits for keys (T14) |
| T07 | Critic node and bounded retrieval loop | #34 | 8 | T06 | done | session_013cWxq2XBiK43SY2483SMcs | 2026-11-22 00:36 | https://github.com/PranavCR01/infodemic-monitor/pull/57 | Code checks + routed LLM critic; exhausted claims frozen, abstain and go to review. 16-claim synthetic set: code-only defect detection 0.50, unnecessary retries 0.00. LLM critic run (the §8 probe) waits for keys (T14) |
| T08 | Judge node and mixed-video policy | #35 | 9 | T04, T06 | done | session_013cWxq2Zswh882KuYh6rskc | 2026-11-22 00:36 | https://github.com/PranavCR01/infodemic-monitor/pull/56 | §9 rules as code + review flags (mixed video, unclear stance, false claim not refuted, mixed evidence, verifier failure); LLM writes only the explanation. Policy needs Pranav's agreement (MULTI_AGENT §7h). Adversarial: still 5/34 unsafe, 4 held for review (was 2) |
| T09 | Deterministic validation and human-review routing | #36 | 10, 11, 12 | T08 | done | session_013cWxq229Tx4MC9VDko4wL3 | 2026-11-22 00:46 | https://github.com/PranavCR01/infodemic-monitor/pull/59 | 8 §10 checks + one judge repair; §11 review rule as named rules (+ high-risk-uncertain); abstentions on weak evidence now go to review. REVIEW_REQUIRED + `human_reviews` (migration 0007). High-risk category list provisional; 0007 not run on Supabase |
| T10 | Guardrails: prompt injection, tool limits, adversarial tests | #37 | 15 | T02 | done | session_013cWxq2Ly4NrwzhcpZMfmkx | 2026-11-22 00:04 | https://github.com/PranavCR01/infodemic-monitor/pull/53 | Simulated always-fooled model: graph 5/34 unsafe, baseline 23/34. Input limits built but not wired (T11). Judge-policy finding for T08 (QUOTES/UNCLEAR + CONTRADICTED gives NO_MISINFO). Held-out red-team set and real-model run (T14) left for people |
| T11 | Integrate the graph into run_pipeline behind a flag, with fallback | #38 | 4 | T02–T10 | in_progress | session_013cWxpyExKRkmyakBC2CXtt | 2026-11-22 01:01 | | Must keep the single-call path working when the flag is off |
| T12 | Offline library fallback (OCR, embeddings, pgvector, hybrid search) | new | 6 | T03, T05 | done | session_013cWxpyUoGG8c62ETqy3AJX | 2026-11-22 00:28 | https://github.com/PranavCR01/infodemic-monitor/pull/58 | Library ingestion tested on generated sample PDFs only (real OCRmyPDF/Tesseract; local Postgres + pgvector). Fallback off unless a library is injected (T11). Real-scan OCR comparison, MedCPT weights, Supabase pgvector + migration 0006 and the viewer left for a person (MULTI_AGENT §7j) |
| T13 | Retrieval MCP server | new | 6, 15 | T03, T05, T12 | done | session_013cWxq1buhzDtq2Ys6KF232 | 2026-11-22 00:54 | https://github.com/PranavCR01/infodemic-monitor/pull/60 | `app/mcp_server` (MCP SDK 2.x MCPServer, Streamable HTTP): 5 tools, hashed per-client tokens, one scope per tool, Redis NCBI bucket + per-client shares, shared cache, schema contract test. Not deployed (Railway service, tokens, env left for a person). T11: pipeline should use `quota.pipeline_ncbi_limiter` for the shared NCBI bucket |
| T14 | Evaluate the graph against the single-call baseline | #39 | 14 | T01, T11 | blocked | | | | Needs API keys and the golden label set (data/golden-label-set) |
| T15 | Confidence calibration (Platt scaling) and the review rule | new | 11 | T14 | blocked | | | | Needs T14 results and human-verified labels |

## Log

Newest first. One line per event: date, task, what happened.

- 2026-11-22 UTC — T13 done: PR #60 squash-merged into langgraph-build (727 passed, 7 skipped; Redis bucket tested on a local redis-server). Not deployed. Also resolved conflict markers T09 left in context/MULTI_AGENT.md (T09's section renamed 7k; T13 is 7l).
- 2026-11-22 01:01 UTC — T11 started in session session_013cWxpyExKRkmyakBC2CXtt.
- 2026-11-22 UTC — T09 done: PR #59 squash-merged into langgraph-build (673 passed, 8 skipped). T11 now waits only on T07–T10 (all done). Migration renumbered to 0007 (T12 took 0006); per-user isolation should be 0008.
- 2026-11-22 00:54 UTC — T13 started in session session_013cWxq1buhzDtq2Ys6KF232.
- 2026-11-22 UTC — T12 done: PR #58 squash-merged into langgraph-build (626 passed, 3 skipped; 55/55 library tests incl. Postgres + pgvector). T13 now unblocked. Tested on generated sample scans only.
- 2026-11-22 UTC — T07 done: PR #57 squash-merged into langgraph-build (573 passed, 1 skipped). T09/T11 note: keep `critic_review_reasons` and pass budgets to critic and judge. Critic metrics are on a synthetic self-labelled set.
- 2026-11-22 00:46 UTC — T09 started in session session_013cWxq229Tx4MC9VDko4wL3.
- 2026-11-22 UTC — T08 done: PR #56 squash-merged into langgraph-build (527 passed, 1 skipped). T09 now unblocked. Aggregation policy still needs Pranav's agreement.
- 2026-11-22 00:36 UTC — T08 started in session session_013cWxq2Zswh882KuYh6rskc.
- 2026-11-22 00:36 UTC — T07 started in session session_013cWxq2XBiK43SY2483SMcs.
- 2026-11-22 UTC — T06 done: PR #55 squash-merged into langgraph-build (460 passed, 1 skipped). T07 and T08 now unblocked. Verifier metrics are on a synthetic self-labelled set; a real labelled check is left for a person.
- 2026-11-22 00:28 UTC — T12 started in session session_013cWxpyUoGG8c62ETqy3AJX.
- 2026-11-22 00:28 UTC — T06 started in session session_013cWxpycmynMxF5EZ63Zwu8.
- 2026-11-22 UTC — T05 done: PR #54 squash-merged into langgraph-build (418 passed, 1 skipped). T06 and T12 now unblocked. Relevance numbers are on synthetic self-labelled data; a real labelled check is left for a person.
- 2026-11-22 UTC — T10 done: PR #53 squash-merged into langgraph-build (374 passed, 1 skipped). Adversarial set: 5 unsafe out of 34 (guarded graph) vs 23 out of 34 (single-call baseline), simulated model.
- 2026-11-22 00:16 UTC — T05 started in session session_013cWxq2fKcmqBDmwsYQQwEz.
- 2026-11-22 UTC — T03 done: PR #52 squash-merged into langgraph-build (250 passed, 1 skipped). T05 now unblocked. Live PubMed sample still needs a person (no NCBI access in the build env).
- 2026-11-22 00:10 UTC — T04 done: PR #51 squash-merged into langgraph-build (193 passed, 1 skipped).
- 2026-11-22 00:04 UTC — T10 started in session session_013cWxq2Ly4NrwzhcpZMfmkx.
- 2026-11-22 UTC — T01 done: PR #50 squash-merged into langgraph-build (144 passed, 1 skipped). T14 still blocked on API keys and the golden label set.
- 2026-11-22 00:02 UTC — T04 started in session session_013cWxpyUeq4YuAXTpZfndft.
- 2026-11-22 00:02 UTC — T03 started in session session_013cWxpzsTJuP1VYHqJT9oWT.
- 2026-11-22 00:01 UTC — T02 done: PR #49 squash-merged into langgraph-build (67 passed, 1 skipped). T03, T04, T10 now unblocked.
- 2026-11-21 23:53 UTC — T02 started in session session_013cWxq2fmACtMefWPTdEkMT (parallel with T01, per 23d9d35).
- 2026-11-21 23:51 UTC — T01 started in session session_013cWxpykbHfbgKcp3qazzmb.
