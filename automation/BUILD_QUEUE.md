# Automated build queue

The automated build of the target system (`docs/target-system-design.md`) works through
this list one task at a time. The orchestrator session reads this file every hour,
starts the next ready task, and records progress here.

- **Integration branch:** `langgraph-build`. Every task merges into it. `main` is never touched.
- **One task at a time.** A task is *ready* when it is `todo` and every dependency is `done`.
- **Statuses:** `todo` · `in_progress` · `done` · `blocked` (with the reason in Notes).
- **People merge `langgraph-build` into `main`**, in reviewed chunks. Automation never does.

| ID | Task | Issue | Doc § | Depends on | Status | Session | Started (UTC) | PR | Notes |
|---|---|---|---|---|---|---|---|---|---|
| T01 | Evaluation framework and routing harness (mocked models; no paid runs) | new | 13, 14 | — | todo | | | | Paid runs and the routing decision wait for API keys; build and test everything with mocks |
| T02 | LangGraph skeleton: typed state, stub nodes, Postgres checkpointing | #29 | 4, 5 | — | todo | | | | Taken over from Jared by decision of the project lead; checkpoint tests use InMemorySaver plus local Postgres in Docker if available |
| T03 | Retrieval planning and PubMed evidence retriever | #31 | 6 | T02 | todo | | | | Record PubMed responses as fixtures; tests make no network calls |
| T04 | Stance analyzer node | #30 | 5 | T02 | todo | | | | |
| T05 | Rerank and filter evidence | #32 | 6 | T03 | todo | | | | |
| T06 | Evidence verifier node | #33 | 7 | T03, T05 | todo | | | | |
| T07 | Critic node and bounded retrieval loop | #34 | 8 | T06 | todo | | | | |
| T08 | Judge node and mixed-video policy | #35 | 9 | T04, T06 | todo | | | | |
| T09 | Deterministic validation and human-review routing | #36 | 10, 11, 12 | T08 | todo | | | | |
| T10 | Guardrails: prompt injection, tool limits, adversarial tests | #37 | 15 | T02 | todo | | | | |
| T11 | Integrate the graph into run_pipeline behind a flag, with fallback | #38 | 4 | T02–T10 | todo | | | | Must keep the single-call path working when the flag is off |
| T12 | Offline library fallback (OCR, embeddings, pgvector, hybrid search) | new | 6 | T03, T05 | todo | | | | Library ingestion tested on generated sample PDFs only |
| T13 | Retrieval MCP server | new | 6, 15 | T03, T05, T12 | todo | | | | |
| T14 | Evaluate the graph against the single-call baseline | #39 | 14 | T01, T11 | blocked | | | | Needs API keys and the golden label set (data/golden-label-set) |
| T15 | Confidence calibration (Platt scaling) and the review rule | new | 11 | T14 | blocked | | | | Needs T14 results and human-verified labels |

## Log

Newest first. One line per event: date, task, what happened.
