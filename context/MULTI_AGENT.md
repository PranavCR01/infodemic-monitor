# Multi-Agent Track Context

## 1. What This Role Is

Pranav and Jared are building the **evidence-grounded LangGraph pipeline**. Jared starts
with the shared graph skeleton (#29) that every node plugs into.

The design is set out in [`docs/architecture.md`](../docs/architecture.md). Issues #29–#39
refer to its sections as "Proposed architecture §N"; read those sections before starting
your issue.

## 2. The Problem This Solves

Today `run_pipeline()` classifies the whole video in **one LLM call**, then queries PubMed
afterwards, and only for `MISINFO` / `DEBUNKING`. The classifier never sees the papers, so
the citations cannot inform the verdict, and a `NO_MISINFO` result has no evidence at all.

The LangGraph pipeline reverses that order: extract the specific claims, decide what the
speaker does with each one, retrieve and verify evidence, challenge the result with a
critic, and only then decide the video's label.

## 3. Target Pipeline

```
Transcribe + OCR → Fuse → Extract claims → Analyze stance → Retrieve evidence → Rerank
  → Verify → Critic ─┬─ approve ──────────────→ Judge → Validate → Persist
                     ├─ more evidence (within budget) → back to Retrieve
                     └─ unresolved ────────────→ Human review
```

Full diagram and node inventory: `docs/architecture.md` §4. State schema: §5. Agent
specifications: §6.

## 4. Design Rules (apply to every issue)

- **Deterministic code** for ingestion, retrieval, validation, routing and persistence;
  LLMs only for claims, stance, verification, critique and judgment.
- **Typed Pydantic schemas**; each node writes only its own state fields (§5.1).
- **Citations come from tools:** PMIDs, DOIs, titles and URLs come from PubMed responses,
  never from the model.
- **Insufficient evidence is its own outcome**, not a contradiction.
- **Bounded loops:** every loop has a budget and every claim reaches a terminal state
  (initially 2 retrieval reformulations and 1 verification revision per claim, §6.5).
- **Untrusted inputs:** transcripts and abstracts are data, never instructions (§7.4).
- **Compatible output:** the final result maps onto `ClassificationResult` and the four
  labels (`MISINFO`, `NO_MISINFO`, `DEBUNKING`, `CANNOT_RECOGNIZE`).
- **No regressions:** the single-LLM path keeps working; the graph sits behind a flag with a
  fallback to it.

## 5. Issues

| Issue | Work | Depends on |
|---|---|---|
| #29 | Skeleton: typed state, stub nodes, conditional edges, Postgres checkpointing (Jared) | — |
| #30 | Stance Analyzer node (`ENDORSES` / `REFUTES` / `NEUTRAL` / `QUOTES` / `UNCLEAR`) | #29 |
| #31 | Retrieval planning and PubMed evidence retriever (abstracts, PMID dedup, cache) | #29 |
| #32 | Rerank and filter evidence | #31 |
| #33 | Evidence Verifier node (`SUPPORTED` / `CONTRADICTED` / `MIXED` / `INSUFFICIENT_EVIDENCE` / `NOT_VERIFIABLE`) | #31, #32 |
| #34 | Critic node and bounded retrieval loop | #33 |
| #35 | Judge node and mixed-video classification policy | #30, #33 |
| #36 | Deterministic validation and human-review routing | #35 |
| #37 | Guardrails: prompt injection, tool limits, adversarial test set | #29 |
| #38 | Integrate the graph into `run_pipeline` behind a flag, with fallback | #29–#36 |
| #39 | Evaluate the graph against the single-LLM baseline | #38, labelled data |

Nodes can be designed before #29 lands: draft the prompt, the output schema and the test
cases against the state schema in `docs/architecture.md` §5, then plug in once the skeleton
is merged.

**Claim extraction is not a separate issue here.** The Claim Extractor node wraps the
claim-level track's work: the `Claim` schema (#11, merged) and the prototype (#12, Kiara).
See `context/CLAIM_LEVEL.md`.

## 6. System Context

Read `context/PRODUCTION.md` and `context/PROJECT_CONTEXT.md` first.

- **Interface:** the graph is exposed to the pipeline as an `InferenceProvider`
  (`backend/app/core/inference/classifier.py`): `classify(fusion: FusionResult) ->
  ClassificationResult`. That lets it slot into `run_pipeline` like the Anthropic and
  OpenAI providers (#38).
- **Schemas:** `Claim`, `PubMedCitation` and `ClassificationResult` live in
  `backend/app/core/schemas/pipeline.py`.
- **PubMed:** `backend/app/core/grounding/pubmed.py` is today's retrieval code (ESearch with
  `sort=relevance`, titles only). #31 replaces it for the graph.
- **Tests:** `backend/app/tests/` (pytest, SQLite and fakes, no external services). New nodes
  come with tests that don't call real APIs.

## 7. Open Decisions

- **When does the graph run?** On every video (as `docs/architecture.md` describes), or only
  when the single-LLM confidence is below a threshold (the original plan used 0.60)? Note
  that today's confidence is the model's own, uncalibrated estimate. Decide before #38.
- **Shared evaluation data:** #39 should use the same labelled videos as Model Evaluation
  (#6) and the claim-level dataset (#13), not a separate set.

## 8. Team

| Person | Current issue | Notes |
|---|---|---|
| Jared | #29 LangGraph skeleton | Start after agreeing the `PipelineState` schema with Pranav |
| Pranav | #31 Retrieval planning and PubMed evidence retriever | Designed against the agreed state schema with recorded PubMed responses; plugs in once #29 merges |

**Update this table as issues are picked up**; this file is the source of truth for who
owns which issue.

## 9. Superseded Plan

The original proposal (an AutoGen group chat with Extractor, Verifier, Critic and a
Coordinator, triggered only below 0.60 confidence) was replaced by the LangGraph design.
The issues that tracked it (#14, #15, #16, #19, #20, #21) are closed; each links to its
replacement.

## 10. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

- **2026-10-28**: Moved the track to the LangGraph architecture. Added
  `docs/architecture.md`, opened #29–#39, closed the superseded issues, and rewrote this
  file (#43, #44).

## 11. PR Requirements

- All code goes up as PRs, using `.github/ISSUE_TEMPLATE/multi-agent.md` for the
  originating issue.
- Reference the GitHub issue (`Closes #N`).
- Update this file as decisions are made (who owns which issue, trigger decision, budget changes),
  so it reflects the *current* design.
