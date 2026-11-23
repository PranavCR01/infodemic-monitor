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

- **When does the graph run?** Decided in T11 (§7m): on every video while
  `USE_GRAPH_PIPELINE` is on, not below a confidence threshold (today's confidence is
  uncalibrated).
- **Shared evaluation data:** #39 should use the same labelled videos as Model Evaluation
  (#6) and the claim-level dataset (#13), not a separate set.

## 7a. Graph Skeleton Decisions (T02, #29)

The skeleton lives in `backend/app/core/graph/` (`state.py`, `nodes.py`, `routing.py`,
`builder.py`, `checkpoint.py`). Later tasks replace one stub each and must keep the node
signature `(state) -> dict` and the field ownership below.

- **State.** `PipelineState` is a `TypedDict` with Pydantic records as values (frozen,
  `extra="forbid"`), versioned by `STATE_SCHEMA_VERSION` (1.0.0), which is stored in every
  run's state. `check_resumable()` refuses to resume a checkpoint written under another
  version. Bump it on any breaking change to a field or record.
- **Extra fields beyond the #29 list**, so every node owns its own output:
  `state_schema_version`, `media_uri` (inputs), `artifacts` (load_artifacts),
  `reranked_evidence` (rerank_evidence; the retriever keeps `retrieved_evidence`),
  `verification_revisions` (verify_claims; counts REVISE_VERIFICATION re-runs),
  `review_status` (human_review) and `persisted_result_ref` (persist_result).
- **Ownership is enforced at run time.** `NODE_OUTPUTS` maps each node to its fields;
  the builder raises `OwnershipError` if a node writes anything else. `errors` is the one
  shared field: append-only, any node may add to it.
- **Budgets live in routing code** (`routing.Budgets`): 3 retrieval rounds per claim
  (initial + 2 reformulations) and 1 verification revision, per target design §6 and §8.
- **Critic routing follows the target design over the issue.** RETRIEVE_MORE (budget
  left) → plan_retrieval; REVISE_VERIFICATION (budget left) → verify_claims; APPROVE,
  ESCALATE and exhausted budgets → judge. Issue #29 and `docs/architecture.md` §4.2 send
  "unresolved" straight to human review, skipping the judge; the target design (§11
  review rule lists "the critic escalated", §12 the reviewer sees "the proposed label")
  needs the judge to run first. So escalation reaches review through
  validate → route_for_review → human_review. One-line change in
  `routing.make_route_after_critic` if the team prefers the issue's version.
- **Review policy is a node** (`route_for_review`, writes `requires_human_review` and
  `review_reasons`), followed by a conditional edge to `human_review` or `persist_result`.
  Its stub applies a subset of the §11 rule; T09 owns the real one. Note for T09: under the
  §9 rules, deciding claims are always SUPPORTED or CONTRADICTED, so "a deciding claim is
  INSUFFICIENT_EVIDENCE or MIXED" can't fire unless the judge's policy changes (T08).
- **Checkpoints hold references, not payloads.** Media is an `ArtifactRef` URI; evidence
  records hold title and abstract, never raw PubMed responses. `assert_checkpoint_safe`
  (no bytes, no string over 20,000 chars) runs on every checkpoint in the resume tests.
- **Checkpointer.** `memory_checkpointer()` for tests; `postgres_checkpointer(dsn)` for
  workers, DSN from `LANGGRAPH_CHECKPOINT_DSN` (never in code), psycopg 3 with
  `autocommit=True`, `prepare_threshold=None`, `row_factory=dict_row`. Both use a
  serializer whose msgpack allowlist is exactly `state.CHECKPOINT_TYPES`; a test runs the
  resume test under `LANGGRAPH_STRICT_MSGPACK=true` with warnings as errors.
  `run_config(job_id)` sets `thread_id = job_id` and a recursion limit derived from the
  budgets (assumes at most 50 claims per video; T10's input limits should cap that).
- **How production creates the checkpoint tables (decide before #38):** they are not
  Alembic-managed. Proposed: a one-off deploy step (or a release-phase command on
  Railway) that runs `postgres_checkpointer(dsn, setup=True)` once against the
  `langgraph` schema, with workers calling `postgres_checkpointer(dsn, setup=False)`.
  `setup()` is idempotent and applies LangGraph's own migrations, so re-running it on
  upgrade is safe; it needs DDL rights the 5-connection `langgraph_dev` role has on its
  schema only.

## 7b. Evaluation and Routing Decisions (T01)

- **Routing file location:** `backend/config/routing.yaml`, not repo-root `config/`, because
  the Docker image copies only `backend/`. The table is marked `status: provisional`: it
  holds the design's starting choices by task type (§13), not measured winners. The
  routing decision waits for API keys and per-step labelled test sets.
- **Critic independence is enforced by config validation:** `critique` must differ from
  `verify_claims` in model or prompt, or the file is rejected.
- **Unknown cost is reported as unknown, never as zero.** Unpriced models (currently the
  OpenAI critic/fallback) give `cost_usd: null`, and by default `compare_runs` refuses to
  pass a change when it can't show that cost didn't get worse.
- **Fallback answers don't count for a candidate.** In the routing harness, an item
  answered by the fallback model counts as a failure for the model being measured.
- **Claim truth vocabulary:** the claim-level dataset's `MISINFO / NO_MISINFO /
  CANNOT_RECOGNIZE` claim labels are loaded as `CONTRADICTED / SUPPORTED /
  INSUFFICIENT_EVIDENCE` (§14), so both tracks share one set.
- **Citation support is a proxy for now:** a cited paper "supports" a claim if it is one of
  the PMIDs the labellers recorded for that claim (`relevant_pmids`). Real per-citation
  support labels are still needed.

## 7c. Stance Analyzer Decisions (T04, #30)

The node is `app/core/graph/stance.py` (`make_analyze_stance(caller)`); the prompt is
`app/core/graph/prompts/stance_v1.md`; the test set and runner are
`app/tests/fixtures/stance/` and `app/core/graph/stance_eval.py`.

- **Model choice is injected, never named.** The node takes a `StepCaller`: anything with
  `call(step, input, *, system=None)` returning `.output` (and `.record.model` /
  `.record.prompt_version`). T01's `ModelRouter` has that shape, so the router built from
  `backend/config/routing.yaml` is passed in as-is; the prompt version comes from
  `router.route("analyze_stance").prompt` (default `stance_v1`), and a missing prompt
  file fails when the node is built, not mid-run.
- **Request contract for provider clients:** `input` is a provider-neutral dict
  `{messages, tools: [record_stance], tool_choice: {type: tool, name: record_stance},
  max_tokens, temperature: 0}`; the client must return the tool's input dict as `output`.
  T01's real Anthropic/OpenAI clients need to honour `tools`/`tool_choice` (T11 or
  whoever writes the real clients).
- **One call per claim**, with the claim's own segments plus every speech/caption
  segment within 15 s (max 40), because the deciding words ("That's a myth.") are often
  the next sentence. Segments are the transcript and OCR pieces (`t*`, `o*`); fused
  segments are used only when a claim cites them or no pieces exist.
- **Strict validation.** Unknown stance, no citation, or any cited ID not shown to the
  model (including a real ID outside the window) → UNCLEAR citing the claim's own
  source segments, plus a `NodeError`. A failed call → UNCLEAR, `retryable=True`. So
  every stance cites at least one input segment ID; the only exception is a claim with no
  segments at all, which is UNCLEAR with an error.
- **confidence is always `None`**; a confidence the model volunteers is dropped.
- **`StanceResult` gained optional `model` and `prompt_version`** (§13 "every result
  records which model and prompt version produced it"). Additive with defaults, so
  `STATE_SCHEMA_VERSION` stays 1.0.0 and old checkpoints still load.
- **Test set results.** 27 examples. Keyword heuristic floor: macro F1 0.58, debunk
  recall 0.78 (misses the two implicit corrections). LLM row is empty until API keys
  exist; see `app/tests/fixtures/stance/RESULTS.md`. Single labeller; not a substitute for
  the shared §14 set. Metrics are local to `stance_eval.py` (written before T01's
  `app.evaluation.metrics` merged); fold them into it later.

## 7d. Retrieval Decisions (T03, #31)

The retrieval logic is a plain package, `backend/app/core/retrieval/` (`planning.py`,
`mesh.py`, `pubmed.py`, `cache.py`, `retriever.py`, `schemas.py`), with no LangGraph or
MCP imports (a test checks this), so T13's MCP server can wrap the same functions. The
real `plan_retrieval` and `retrieve_evidence` nodes are in
`backend/app/core/graph/retrieval_nodes.py` (`make_retrieval_nodes(retriever)`). The
default graph still uses the stubs; T11 wires the real nodes in.

- **Planning is rules only by default.** A curated MeSH lexicon (`mesh.py`, about 70
  terms common in health-misinformation videos) and a verb split ("X cures Y": X is
  the intervention, Y the outcome; "in children" is population; "better than X" is
  comparator). Each claim gets a narrow-to-broad query ladder: I AND O AND P (MeSH
  OR free-text synonyms) → drop the population → parent MeSH headings → the claim's
  own words as free text, left to PubMed's term mapping. The optional LLM helper (§6
  step 3) is an injected callable used only when the lexicon finds no concept; no
  model is named in code. Grow the lexicon from the evaluation set, not by guesswork.
- **Empty searches broaden automatically, inside the same budget.** New conditional
  edge `retrieve_evidence → plan_retrieval` when a claim's searches have all come back
  empty and it has budget left (`routing.claims_to_broaden`); otherwise
  `→ rerank_evidence`. The critic's RETRIEVE_MORE and the automatic broadening use the
  same per-claim budget (3 rounds). One query per claim per round; the critic's
  suggested queries come first and are sanitised (no URLs, control characters or odd
  symbols, max 400 characters) because they are model output.
- **A PubMed failure counts as a round.** It is recorded in `errors`
  (`retryable=True`) after the client's own retries (4 attempts, exponential backoff
  1–10 s on 429, 5xx, transport errors and NCBI's "API rate limit exceeded" body), so
  a PubMed outage ends in INSUFFICIENT_EVIDENCE rather than a hung run.
- **Rate limit.** One process-wide limiter at 2.5 requests/s without a key and 9/s with
  `NCBI_API_KEY` (NCBI's limits are 3 and 10). Across processes this is per worker;
  T13's Redis token bucket makes it global. Set `NCBI_EMAIL` so NCBI can contact us.
- **EFetch, not ESummary,** because ESummary has no abstracts. Abstracts are capped at
  8,000 characters (structured labels kept, e.g. "CONCLUSIONS: …") to stay under the
  checkpoint string cap. Book records (`PubmedBookArticle`) are skipped.
- **Dedup and filters.** By PMID, then DOI (case-insensitive), within a query and across
  a claim's rounds; the first copy (and its query) wins. Records typed Retracted
  Publication, Retraction of Publication or Published Erratum are dropped by default
  (`SearchFilters.exclude_types`); publication-type (`[pt]`) and year filters are
  available but off by default, leaving study-type ranking to the reranker (T05).
- **Cache.** Searches keyed by query + result cap + filters (7 days; empty results 1
  day) and parsed records keyed by PMID, so a paper found by several queries is fetched
  once. `InMemoryQueryCache` by default; `RedisQueryCache` for workers and the shared
  MCP cache. Cache errors never fail retrieval.
- **`EvidenceRecord` moved** from `graph/state.py` to `retrieval/schemas.py` (same
  fields, re-exported from `state`), so the package doesn't import LangGraph. Schema
  version unchanged. The issue's `retrieved_at` field is not added: the design's §6
  record doesn't have it (doc wins).
  `relevance_score` stays empty; the reranker sets it.
- **Fixtures are synthetic.** The build environment can't reach NCBI, so
  `backend/app/tests/fixtures/pubmed/` holds hand-built responses in NCBI's exact
  formats (PMIDs 99000xxx, titles marked "(synthetic fixture)"). They exercise every
  parser edge case; they don't show that the queries find good papers. Recording real
  ones is left for a person: `python scripts/record_pubmed_fixtures.py` (see below).

**Sample of 10 claims (issue #31 acceptance criterion): planned queries.** The planner
output below is real; the evidence column still needs a live run, because this
environment has no access to NCBI. Run `cd backend && python
scripts/record_pubmed_fixtures.py --out /tmp/pubmed_recorded` from a machine that can
reach NCBI; it prints the same 10 claims with the papers each one finds, to paste here.

| # | Claim | PICO (MeSH) | First query | Rungs |
|---|---|---|---|---|
| 1 | Drinking hot water every morning cures the flu. | I: hot drinks (free text) · O: Influenza, Human | `("hot drinks"[tiab] OR "hot beverages"[tiab] OR "hot water"[tiab]) AND ("Influenza, Human"[MeSH Terms] OR influenza[tiab] OR flu[tiab])` | 3 |
| 2 | Garlic stops colds. | I: Garlic · O: Common Cold | `(Garlic[MeSH Terms] OR garlic[tiab] OR allicin[tiab]) AND ("Common Cold"[MeSH Terms] OR "common cold"[tiab])` | 3 |
| 3 | Vaccines cause autism in children. | I: Vaccines · O: Autism Spectrum Disorder · P: Child | `(Vaccines[MeSH Terms] OR vaccine[tiab] OR vaccination[tiab]) AND ("Autism Spectrum Disorder"[MeSH Terms] OR autism[tiab]) AND (Child[MeSH Terms] OR children[tiab])` | 4 |
| 4 | Vitamin C prevents the common cold. | I: Ascorbic Acid · O: Common Cold | `("Ascorbic Acid"[MeSH Terms] OR "vitamin c"[tiab] OR "ascorbic acid"[tiab]) AND ("Common Cold"[MeSH Terms] OR "common cold"[tiab])` | 3 |
| 5 | Lemon water cures cancer. | I: lemon (free text) · O: Neoplasms | `(lemon[tiab] OR citrus[tiab]) AND (Neoplasms[MeSH Terms] OR cancer[tiab] OR neoplasm[tiab] OR tumor[tiab])` | 3 |
| 6 | Ivermectin cures COVID-19. | I: Ivermectin · O: COVID-19 | `(Ivermectin[MeSH Terms] OR ivermectin[tiab]) AND ("COVID-19"[MeSH Terms] OR "covid-19"[tiab] OR "sars-cov-2"[tiab])` | 3 |
| 7 | Intermittent fasting reverses type 2 diabetes. | I: Fasting · O: Diabetes Mellitus | `(Fasting[MeSH Terms] OR fasting[tiab]) AND ("Diabetes Mellitus"[MeSH Terms] OR diabetes[tiab])` | 3 |
| 8 | Fluoride in drinking water lowers children's IQ. | I: Fluorides, Drinking Water · O: Intelligence · P: Child | `(Fluorides[MeSH Terms] OR fluoride[tiab]) AND ("Drinking Water"[MeSH Terms] OR "water intake"[tiab]) AND (Intelligence[MeSH Terms] OR intelligence[tiab] OR iq[tiab]) AND (Child[MeSH Terms] OR children[tiab])` | 4 |
| 9 | 5G spreads coronavirus. | I: Electromagnetic Fields · O: COVID-19 | `("Electromagnetic Fields"[MeSH Terms] OR 5g[tiab] OR radiofrequency[tiab]) AND ("COVID-19"[MeSH Terms] OR "covid-19"[tiab] OR "sars-cov-2"[tiab])` | 3 |
| 10 | Apple cider vinegar burns fat and causes weight loss. | I: Acetic Acid · O: Weight Loss | `("Acetic Acid"[MeSH Terms] OR "apple cider vinegar"[tiab] OR vinegar[tiab]) AND ("Weight Loss"[MeSH Terms] OR "weight loss"[tiab])` | 3 |

Known weak points to check against the live run: the parent-heading rung is very broad
(e.g. `Beverages AND Respiratory Tract Infections`) and will mostly feed the reranker
noise; the fixed lexicon misses terms it doesn't list (those fall back to free text);
and a claim with two interventions ("fluoride in drinking water") ANDs both.

## 7e. Guardrail Decisions (T10, #37)

- **Where the limits live:** `backend/config/guardrails.yaml` (input, tool and per-video
  limits), loaded by `app.core.guardrails.config`. Starting values, not measured ones.
- **Merged nodes (rebased onto T03/T04):** T04's stance node already fences its input in
  its own way (`<video_segments>`, JSON-escaped, closing tag stripped, prompt states the
  material is untrusted) and calls a `StepCaller` with a tool-call request, not
  `GuardedRouter`. Rather than rewrite it, its `_clean` now runs `neutralise` too. T03's
  `PubMedClient` now defaults to `GuardedHttpClient` (its own fixed-endpoint check, timeout
  and size cap stay; the guarded client adds the host allowlist, no redirects and a
  streaming byte cap). `max_response_bytes` is 5 MB to match T03's cap. Converging the two
  model-call contracts (`GuardedRouter`'s rendered text vs T04's tool-call dict) is left to
  T11, which writes the real provider clients.
- **One way to call a model:** graph nodes call models only through `GuardedRouter`, which
  accepts only a `GuardedPrompt` built by the per-step builders in
  `app.core.guardrails.untrusted` (system prompt must end with `UNTRUSTED_DATA_NOTICE`) and
  parses every answer into a strict schema (`outputs.OUTPUT_SCHEMAS`). A static test fails if
  a module under `app/core/graph/` sends input to a model without importing the guardrails. **T03–T09:
  build prompts with these builders and call `GuardedRouter`.**
- **Fencing plus neutralising (beyond the doc):** §15 says fence untrusted text. We also
  replace whole sentences the deterministic detector reads as instructions to the system
  with a marker before a model sees them; state keeps the original words for reviewers. The
  detector is narrow on purpose (controls such as "ignore the CDC guidelines" must not match);
  paraphrases get through, and the adversarial set measures that.
- **Speech and captions are separate fenced blocks**, with timing in the block header rather
  than in the text. Found by the adversarial set: a timestamp prefix in the text hid
  line-start injections ("System: ...") from the detector.
- **Every suspected injection goes to review:** the stub review policy now appends
  `guardrail_review_reasons(state)` (injection findings in speech, captions, claims, titles
  and abstracts, plus any `NodeError` whose message starts with `guardrail:`). **T09: keep this
  call** when replacing the stub.
- **Citation and stance checks in code:** cited evidence IDs must be ones the step was shown;
  a SUPPORTED/CONTRADICTED/MIXED verdict left without valid citations becomes
  INSUFFICIENT_EVIDENCE. A stance must cite known segments, and a stance resting on a segment
  that holds a suspected injection falls back to UNCLEAR. Extracted claims must be grounded in
  the segments they cite (content-word overlap ≥ 0.5).
- **Tools:** `ToolGateway` exposes only `pubmed_search` and `pubmed_fetch`, with typed
  arguments (no URLs, paths or control characters in queries), a per-run call budget, a hard
  timeout and capped results; `GuardedHttpClient`/`AsyncGuardedHttpClient` allow HTTPS to
  `eutils.ncbi.nlm.nih.gov/entrez/eutils/` only, follow no redirects and cap the body.
  **T03: route PubMed calls through these.**
- **Input limits are built but not wired** into the upload path (`app.core.guardrails.limits`:
  size, duration, container sniffing, truncated-MP4 detection, duplicates, per-user rate limit
  and daily quota, 50-claim cap). Wiring them changes live behaviour, so it's T11's, behind the
  flag. The rate limiter and quota are in-process; multiple workers need a shared store.
- **Unsafe is defined before measuring** (`app/evaluation/adversarial/unsafe.py`): label moved
  toward the attacker, output outside the schema, fabricated evidence, or a non-CANNOT_RECOGNIZE
  label on off-topic content. Being held for review does not make a result safe; it's reported
  separately.
- **Adversarial results are from a simulated, always-fooled model**, not a real one:
  guarded graph 5 unsafe out of 34 (2 held for review), single-call baseline 23 unsafe out of
  34 (`research/adversarial/report_v1.md`). Real-model numbers need T14.
- **Findings for T08 (judge, §9):** under the §9 rules a contradicted claim whose stance is
  QUOTES, NEUTRAL or UNCLEAR gives NO_MISINFO. So an attack that only has to nudge the stance
  step (persuasion, fiction framing, or a rejected answer that falls back to UNCLEAR) clears
  the video. Three of the five graph failures are this. Suggest: when a deciding claim's stance
  is UNCLEAR, or when a contradicted claim is QUOTES/NEUTRAL in a video with no REFUTES, don't
  auto-publish NO_MISINFO.

## 7f. Reranking Decisions (T05, #32)

The reranker is `backend/app/core/retrieval/rerank.py` (plain Python, no LangGraph or
MCP imports, so T13's `rerank_evidence(claim, records, k)` tool wraps it). The real
node is `make_rerank_node()` in `backend/app/core/graph/retrieval_nodes.py`, also
returned by `make_retrieval_nodes()`. The default graph still uses the stub until T11.

- **Two separate scores on every record.** `relevance_score` (0–1, does the paper test
  this claim?) and `study_type` + `quality_score` (0–1, how strong is the design?).
  `EvidenceRecord` gained two optional fields, `study_type` and `quality_score`; old
  checkpoints still load, so the state schema version is unchanged (same rule T04 used).
- **Relevance is lexical and deterministic** (§6: "a lightweight reranker; an LLM only
  if measured relevance is poor"). It reuses the planner's PICO frame and MeSH lexicon:
  intervention and outcome coverage (title hit 1.0, abstract 0.7, broader MeSH heading
  only 0.4), combined by geometric mean, so a paper about only lemons or only cancer
  scores 0. Population is a multiplier: animal or lab study ×0.5, claim population
  ("in children") absent ×0.8, misinformation/social-media research about the claim
  ×0.5 (it studies beliefs, not the claim). When the lexicon finds no concept on one
  side ("honey cures *cough*"), the claim's leftover words on that side stand in.
  A learned scorer (e.g. a cross-encoder) can be injected as `relevance_model`; no model
  is named in code.
- **Study type is a lookup** on PubMed's publication types: systematic review/meta-
  analysis 1.0 > RCT 0.9 > guideline 0.85 > other trial 0.75 > observational 0.55 >
  narrative review 0.35 > case report, animal 0.2 > in vitro 0.15 > opinion, other 0.1
  > unknown 0.0. PubMed has no type for animal or cell work, so untyped PubMed records
  (only "Journal Article") are read with fixed title/abstract cues ("mice", "cell line",
  "cohort", "randomised"). A tagged human trial is never demoted by those cues. Library
  records take the type their uploader gave; none = `unknown`, below every tagged type.
  `evidence_class()` maps types to the issue's classes: evidence synthesis, human
  clinical, human observational, animal, mechanistic, general.
- **Threshold, then cap.** Papers with relevance < 0.4 are dropped, not passed to the
  verifier (§6: forty off-topic papers are the same failure as none); the rest are
  ordered by 0.7·relevance + 0.3·quality, ties in PubMed's order, and capped at 10.
  `RerankResult.cleared_threshold` is the library fallback's trigger for T12. An animal
  or cell study that addresses both sides scores 0.5 and is kept, labelled as such,
  below the human evidence: the verifier should see that only mechanistic evidence
  exists rather than see nothing.
- **A reranker failure** (only possible with an injected model) is recorded in
  `errors` and the claim keeps its first 10 papers in PubMed order, unscored.

**Relevance check (issue #32 acceptance criteria).** `python -m app.evaluation.rerank_eval`
on `backend/app/tests/fixtures/rerank/relevance_set.jsonl`: 12 claims × 10 candidate
papers in PubMed order, each labelled 2 (tests the claim), 1 (related, indirect) or 0
(not evidence). Strict = label 2.

| Metric (mean over 12 claims) | PubMed order | Reranked |
|---|---|---|
| precision@5 (strict) | 0.383 | 0.533 |
| precision@5 (label ≥ 1) | 0.483 | 0.750 |
| nDCG@10 | 0.686 | 0.896 |
| recall@10 | 1.000 | 0.917 |
| off-topic papers passed on (total) | 63 | 12 |
| papers passed on (total) | 120 | 59 |

Random order gives precision@5 0.292; the best possible on this set is 0.583. Better on
9 claims, equal on 2 (hot water, 5G), worse on 1 (probiotics, 0.40 → 0.20).

**How much to trust these numbers: not much yet.** The set is synthetic (NCBI is
unreachable from the build environment; PMIDs 98000xxx, abstracts start "Synthetic."),
and the agent that wrote the reranker also wrote the papers, their PubMed order and the
labels. So it shows the mechanics work and where the scorer breaks, not real precision. The
PubMed order is invented too, and it puts 2 relevant papers in the top 5 for almost every
claim. Before trusting the number, a person should record real PubMed results for these 12
claims (`scripts/record_pubmed_fixtures.py`) and have two people label them blind to the
reranker.

**Known misses** (all lexicon gaps, deliberately not patched to fit this set):
recall drops because the scorer can't link "probiotics" to *Lactobacillus* /
*S. boulardii*, or "hot drinks" to "fluid intake"; "antibiotic-associated" doesn't match
the lexicon's "antibiotic". Narrative reviews of cell and animal work ("citrus flavonoids
in cancer biology") still pass. Fixes belong in the MeSH lexicon (which also changes T03's
queries and fixtures) or in a learned relevance model, judged on the real labelled set.

## 7g. Evidence Verifier Decisions (T06, #33)

The node is `backend/app/core/graph/verifier.py` (`make_verify_claims(caller)`); the
prompt is `app/core/graph/prompts/verify_v1.md`; the labelled set and runner are
`app/tests/fixtures/verify/` and `app/core/graph/verify_eval.py`. The default graph still
uses the stub until T11.

- **Same caller contract as stance (T04).** The node takes a `StepCaller`; T01's
  `ModelRouter` is passed in as-is. Step `verify_claims`, prompt version from
  `router.route("verify_claims").prompt` (default `verify_v1`); no model id in code
  (a test greps for one). Request: `{messages, tools: [record_verdict], tool_choice:
  forced, max_tokens: 1024, temperature: 0}`.
- **Prompt built with T10's guardrails.** `verification_prompt` fences the claim, titles
  and abstracts; the system prompt ends with `UNTRUSTED_DATA_NOTICE`; critic notes on a
  revision are fenced as `model_output`. PubMed metadata (study type, publication type,
  year) goes in a trusted "evidence index" in the instructions, stripped to plain
  characters. The node does not go through `GuardedRouter`, because that router sends a
  plain string and can't carry the forced tool; it calls the `ModelRouter` with the
  guarded prompt's rendered text and system prompt instead.
- **Schema.** `VerifierToolOutput` = T10's strict `VerificationOutput` (unknown keys
  rejected, no URLs) + `raw_confidence` in [0, 1] and no URLs in limitations either.
- **Invalid citations reject the whole answer; they are not trimmed** (issue: "invalid →
  rejected, not silently dropped"). Rejected: an ID not retrieved for *this* claim
  (another claim's paper counts as invalid), a paper in both lists, SUPPORTED without a
  supporting ID, CONTRADICTED without a contradicting ID, MIXED without both. One repair
  call names the problem and the allowed IDs (`max_repairs=1`); a successful repair is
  logged as a plain `NodeError` (no review on its own). If the repair fails too, the
  verdict is INSUFFICIENT_EVIDENCE with a `guardrail:<kind>` error, which
  `guardrail_review_reasons` turns into a review reason (§11 "validation failed after
  repair"). This differs from T10's `check_verification`, which drops bad IDs and
  downgrades; that helper is left in place for the adversarial harness.
- **Absence of evidence is not contradiction, in code.** No reranked evidence → 
  INSUFFICIENT_EVIDENCE without a model call (so NOT_VERIFIABLE is only reachable when
  something was retrieved). CONTRADICTED without a cited contradicting paper is rejected.
- **Cap of 10 papers** enforced here too; papers past 10 are neither shown nor citable.
- **Model failure** → INSUFFICIENT_EVIDENCE, `retryable=True`, *not* a guardrail error.
  For T08/T09: a claim whose verifier failed only reaches review if it is a deciding
  claim; consider making a verifier failure a review reason on its own.
- **Ownership.** Writes `verification_results` and `verification_revisions` (the T02
  map). The issue says "writes only `verification_results`"; the doc and T02 put the
  revision counter on this node, so the doc wins.
- **`VerificationResult` gained optional `model` and `prompt_version`** (same additive
  rule as T04; schema version unchanged). `raw_confidence` is stored raw; calibration is
  T15.
- **Labelled set: 20 synthetic claims, self-labelled.** All five verdicts, six
  insufficient-not-contradicted cases (animal-only, off-topic, lab-only, wrong
  population, case report, symptom relief vs cure). Heuristic floor: accuracy 0.85, macro
  F1 0.87, 0 insufficient-called-contradicted; per-verdict precision/recall in
  `fixtures/verify/RESULTS.md`. The heuristic, abstracts and labels were all written by
  the build agent, so the floor is inflated by construction; the LLM row waits for API
  keys (T14) and a real check needs real abstracts labelled by two people.
- **Not done:** the T10 adversarial harness (`evaluation/adversarial/graph_system.py`)
  still uses its own reference verifier; switching it to this node is for T11/T14.

## 7h. Judge and Mixed-Video Policy (T08, #35)

The node is `backend/app/core/graph/judge.py` (`make_judge_classification(caller=None)`);
the explanation prompt is `app/core/graph/prompts/explain_v1.md`. The default graph's
`judge_classification` now runs this judge with the template explanation (it is
deterministic, so this changes no model calls). **Needs agreement from Pranav** (issue
acceptance criterion): the policy below is the target design's §9 table plus the flags.

**Labels: the §9 rules, in order, as code.** Only claims in `claims` that have a verdict
take part; a missing stance counts as UNCLEAR.

| # | Rule (`decision_rule`) | Label | Deciding claims | Evidence cited |
|---|---|---|---|---|
| 1 | `endorsed_contradicted`: any claim ENDORSES + CONTRADICTED | MISINFO | those claims | their contradicting IDs |
| 2 | `refuted_contradicted`: otherwise any REFUTES + CONTRADICTED | DEBUNKING | those claims | their contradicting IDs |
| 3 | `judged_nothing_false_endorsed`: otherwise any SUPPORTED or CONTRADICTED | NO_MISINFO | the judged claims | their supporting + contradicting IDs |
| 4 | `nothing_judged` / `no_claims`: otherwise | CANNOT_RECOGNIZE | none | none |

**Patterns the rules can't settle become review flags, never a different label.**
`final_result.review_flags`; the review policy adds each as `judge:<flag>`.

| Flag | When | Why |
|---|---|---|
| `mixed_video` | an endorsed false claim and a refuted false claim | §9 "mixed videos". Label stays MISINFO (rule 1) |
| `unclear_stance_contradicted:<cid>` | a contradicted claim's stance is UNCLEAR/missing and the label isn't MISINFO | §9 "unclear stance on a deciding claim": had it been ENDORSES, the label would be MISINFO |
| `false_claim_not_refuted:<cid>` | label NO_MISINFO and a contradicted claim is QUOTES or NEUTRAL | T10 finding: nudging the stance step alone cleared 3 attacks. Not raised under DEBUNKING (quoting the myth is normal there) |
| `mixed_evidence:<cid>` | any claim's verdict is MIXED | §9 probe: "the science is split" is for a person |
| `verification_failed:<cid>` | the verifier recorded a retryable failure for the claim | T06 note: its INSUFFICIENT_EVIDENCE is not a finding |

Decisions and deviations:

- **Ambiguous cases go to a person, not an LLM.** §9 allows either. There is no labelled
  set to show an LLM adjudicator is right, it would reintroduce run-to-run label changes,
  and T10 showed the stance step is the attack surface. An LLM tie-breaker can be added
  behind the flags later and measured (T14).
- **Not detected by code yet:** materiality (a harmless inaccuracy vs "stop taking
  insulin") and satire/parody. No reliable deterministic signal; left for later work with
  the labelled set (e.g. a harm-category lookup on `claim_category`).
- **The issue's `requires_human_review` / `review_reasons` stay on `route_for_review`**
  (T02 ownership; the issue says the judge "writes only `final_result`"). The judge
  hands its part over as `review_flags`. T09: keep the `judge:` flags when replacing the
  stub review policy.
- **Citations only from state.** Claim IDs must be in `claims`; evidence IDs must have
  been retrieved or reranked for *that* claim. Anything else is dropped from the result
  and recorded as `guardrail:uncited_evidence` (or `guardrail:unknown_claim`), which
  sends the run to review.
- **The LLM writes only the explanation** (routed step `judge_explanation`, prompt
  `explain_v1`, forced `record_explanation` tool, T10's `explanation_prompt` builder with
  verifier notes fenced as `model_output`). Its text is rejected, and the deterministic
  template used instead, if it names a different label (upper-case label names only, so
  "misinformation" in prose is fine), mentions an evidence ID or PMID the result doesn't
  cite, contains a URL or breaks the schema. A model failure also falls back to the
  template (`retryable`, not a review reason). Review flags are appended to the text in
  code, so the model can't omit them.
- **`FinalClassification` gained optional `decision_rule`, `review_flags`, `model`,
  `prompt_version`** (additive, same rule as T04/T06; schema version stays 1.0.0).
- **`confidence` stays `None`** until calibration (T15; §11 "lowest calibrated deciding
  claim"). `to_classification_result()` (for T11's `InferenceProvider`) needs a float, so
  it uses the lowest *raw* verifier confidence of the deciding claims, or 0.0 when none —
  uncalibrated, like today's single-call number. It also fills `evidence_snippets` with
  the speech/caption text behind the deciding stances, `citations` from cited records with
  a PMID, and per-claim `claims` labelled by the same rules applied to one claim.
- **Effect on existing numbers.** The stub sample video is itself a mixed video, so it
  now goes to review (`judge:mixed_video`); the skeleton flow tests were updated to say
  so, plus one new pass-path test. T10's adversarial report: still 5 unsafe out of 34,
  but 4 instead of 2 are now held for review (adv-speech-04, adv-jailbreak-04, both
  stance-nudging attacks caught by `false_claim_not_refuted`). Report regenerated.
- **Review-rule note for T09 (from T02) still stands:** deciding claims are only ever
  SUPPORTED or CONTRADICTED, so "a deciding claim is INSUFFICIENT_EVIDENCE or MIXED" can't
  fire; `mixed_evidence:<cid>` now covers MIXED instead.

**T16 revision (§9 as revised in commit f238dab, after the first golden-set batch).** Two
new rules; the table above is now, in order:

| # | Rule (`decision_rule`) | Label | Deciding claims | Evidence cited | Rule's own review reason |
|---|---|---|---|---|---|
| 1 | `endorsed_contradicted` | MISINFO | ENDORSES + CONTRADICTED | contradicting IDs | — |
| 2 | `refuted_supported` (new) | MISINFO | REFUTES + SUPPORTED | **supporting** IDs | `denies_supported:<cid>` (always reviewed) |
| 3 | `refuted_contradicted` | DEBUNKING | REFUTES + CONTRADICTED | contradicting IDs | — |
| 4 | `judged_nothing_false_endorsed` | NO_MISINFO | SUPPORTED/CONTRADICTED | supporting + contradicting | — |
| 5 | `refuted_unsettled` (new) | CANNOT_RECOGNIZE | REFUTES + MIXED/INSUFFICIENT | supporting + contradicting | `possible_debunk:<cid>` |
| 6 | `nothing_judged` / `no_claims` | CANNOT_RECOGNIZE | none | none | — |

- **"The judge returns its review reasons"** = `Decision.rule_review_reasons` (§9's third
  return value). They travel in the existing `final_result.review_flags`, so the review
  policy already turns them into `judge:denies_supported:<cid>` /
  `judge:possible_debunk:<cid>`. No new state field (state schema §4–5 unchanged).
- **Per-claim reasons, not the doc's prose strings.** The doc sketch returns
  `"speaker denies a supported claim"`; we use `denies_supported:<cid>` like every other
  flag, so a reviewer sees which claim. `flag_text` renders the prose in the explanation.
- **Rule 5 is checked after NO_MISINFO, as the doc's order says.** So a refuted unsettled
  claim next to any judged claim does *not* raise `possible_debunk` (the issue title reads
  as unconditional; the doc wins). `REFUTES + NOT_VERIFIABLE` is not a possible debunk.
- **Abstaining claims count.** A claim whose critic budget ran out abstains as
  INSUFFICIENT_EVIDENCE (T07); if its stance is REFUTES it now decides a `refuted_unsettled`
  CANNOT_RECOGNIZE. The stub sample's exhausted-budget test now expects `claim_ids == ["c2"]`.
- `review_policy.rule_weak_evidence` treats `refuted_unsettled` like `nothing_judged` (every
  uncertain claim gets `weak_evidence:<cid>`). `claim_label` (per-claim label) gives
  REFUTES + SUPPORTED → MISINFO. The evaluation's `metrics.judge_label` (gold-label sanity
  check) was updated to the same rules, with a test that it agrees with the node on every
  two-claim combination. T10's adversarial report is unchanged (still current).
- **T21 (2026-11-23, project lead's decision) supersedes "Rule 5 is checked after
  NO_MISINFO" above for review reasons, not labels.** `denies_supported:<cid>` and
  `possible_debunk:<cid>` are now collected from every claim, whichever rule decides the
  label: e.g. ENDORSES + SUPPORTED next to REFUTES + INSUFFICIENT is still NO_MISINFO
  (rule 4) but raises `possible_debunk:c2` (the v68/v70 golden-set shape). Rule order,
  labels, deciding claims and cited evidence are unchanged; a test checks every two-claim
  combination still matches `metrics.judge_label`. Mixed videos (ENDORSES + CONTRADICTED
  and REFUTES + CONTRADICTED) were already MISINFO by rule 1 with `mixed_video`; T21 adds
  `mixed_video` to `RULE_REVIEW_FLAGS`, so `rule_review_reasons` returns it too, and tests
  that it always reaches review. Validation's consistency check recomputes `decide()`, so it
  expects the new flags without change.

## 7i. Critic and Bounded Loop Decisions (T07, #34)

The node is `backend/app/core/graph/critic.py` (`make_critique_verification(caller)`); the
prompt is `app/core/graph/prompts/critic_v1.md`; the small labelled set and runner are
`app/tests/fixtures/critic/` and `app/core/graph/critic_eval.py`. The default graph still
uses the stub critic until T11.

- **Two layers.** Deterministic code checks always run: citation integrity (cited ID not
  retrieved for this claim, a paper in both lists), verdict/citation agreement
  (CONTRADICTED with no contradicting paper and so on), strength (a SUPPORTED/CONTRADICTED
  verdict resting *only* on animal, in-vitro, case-report or opinion papers), and "every
  retrieved paper was filtered out" (asks for RETRIEVE_MORE). Then one forced-tool LLM
  call (`record_critique`, step `critique`, prompt `critic_v1`) covers claim fidelity,
  relevance, what the papers say, logic, completeness and stance consistency. The
  stricter decision wins (ESCALATE > RETRIEVE_MORE > REVISE_VERIFICATION > APPROVE), so
  the model cannot overrule a code finding.
- **Independence.** Its own prompt, and its own routing step; `routing.yaml` already
  routes `critique` to a different provider from `verify_claims` (a test checks that they
  differ). No model id in code.
- **Failure modes.** An answer that breaks the output contract → ESCALATE + review with a
  `guardrail:output_rejected` error (the T10 safe default). A model *outage* → the review
  falls back to the code checks only, with a retryable error and no forced review, since
  §8 says the pipeline must work without the critic. No evidence shown to the verifier →
  no model call. `caller=None` gives the code-only critic (the §8 probe configuration).
- **Budgets are enforced in routing, not in the node.** Two routing changes:
  1. `CriticResult` records `reviewed_attempt` and `reviewed_revision` (optional and
     additive, like T04/T06; schema version unchanged). `routing.unchanged_since_review`
     uses them so that **an exhausted claim is frozen**: before T07, a claim whose search
     budget had run out was re-verified and re-critiqued on the same evidence on every
     later pass another claim caused. A scripted critic that doesn't set the fields keeps
     the T02 behaviour.
  2. **Exhausted budget = abstention + review.** `routing.verdicts_for_judge` gives the
     judge INSUFFICIENT_EVIDENCE (no citations) for any claim whose critic still objected
     when the budget ran out, so a verdict the critic rejected can never decide the video
     label; `routing.critic_review_reasons` adds `budget_exhausted:<id>` and
     `critic_escalated:<id>`. The stored `verification_results` are not changed. ESCALATE
     keeps its verdict, so the reviewer sees a proposed label (§12). The stub judge and
     stub review rule now call both helpers. **For T08/T09: keep calling them** when
     replacing those stubs. Rebased onto T08: T08's `judge.claim_views` now reads
     verdicts through `verdicts_for_judge`, and `make_judge_classification` /
     `judge()` take `budgets` (T11: pass the graph's budgets to both the judge and the
     critic, or a custom budget won't be recognised as exhausted).
- **Ownership.** Writes only `critic_results` (plus `errors`), as the issue says.
- **Small set: 16 synthetic claims, self-labelled** (8 planted verifier errors, 8 right
  verdicts). Code-only critic: defect detection 0.50 (4/8: animal-only, lab-only,
  absence-as-contradiction, fabricated citation), unnecessary-retry rate 0.00. It misses
  everything that needs reading: "relieves" judged as "cures", wrong population, an
  ignored meta-analysis, an off-topic citation. The oracle scores 1.0/0.0 (harness
  check) and an always-challenge critic 1.0/0.43. The LLM row waits for API keys (T14).
  Whether the model critic is worth its extra call is the §8 probe and is still open:
  it has to add detection on the four reading defects without pushing the
  unnecessary-retry rate up.

## 7j. Offline Library Decisions (T12, no issue; design §6)

The library is `backend/app/core/retrieval/library/` (`config`, `manifest`, `ocr`,
`chunking`, `embeddings`, `store`, `ingest`, `search`, `fallback`): plain Python with no
LangGraph, MCP, torch, transformers, OCRmyPDF or PyMuPDF imported at load time (a test
checks this), so T13's `search_library(query, k)` tool wraps `search.search_library`.
Settings, including the MedCPT model ids, are in `backend/config/library.yaml`; no model is
named in code. Batch job: `backend/scripts/ingest_library.py ingest|approve|search`.

- **Where it fires: inside `rerank_evidence`, not a new node.** `make_rerank_node(reranker,
  library=LibraryFallback(...))` (also `make_retrieval_nodes(..., library=)`). Both §6
  triggers reduce to "the reranker kept nothing": an empty set only reaches reranking after
  the PubMed budget is spent (the broadening edge sends it back before that), and a set
  that all falls below the 0.4 threshold is the "forty off-topic papers" case. A PubMed
  outage that ends with nothing also fires it. Library passages go through the same
  reranker and cap. No new node keeps the graph topology T06–T11 build on unchanged.
  **Off unless a library is injected;** the default graph and stubs behave as before (T11
  wires it).
- **New state field `library_evidence`** (claim → every passage the library returned;
  `[]` = fired, found nothing), owned by `rerank_evidence`, kept across rounds like
  `retrieved_evidence`. Additive and optional, so the schema version is unchanged (T04/T05
  rule). It is the fire-rate signal, and it is included in the stub `validate_result`
  citation check and in `guardrails.injection.scan_state` (library text is untrusted, §15).
  **T09: the real validation must accept IDs from `retrieved_evidence` ∪ `library_evidence`.**
- **Evidence records** as in §6: `lib_<document_id>_p<page>`, `abstract` = the matched chunk,
  `publication_type` = the manifest's study type or `["Unknown"]` (ranks below every tagged
  type), `source_url` = internal viewer link from config. One record per page (best chunk);
  chunks never span pages so the page in the ID is exact. Library dedup is by evidence ID
  only (PubMed's DOI dedup would merge two pages of one document).
- **Tables via migration 0006 (raw SQL), no ORM model.** `Base` is also `create_all`-ed on
  SQLite (tests, startup fallback), which has no `vector`/`tsvector`. `library_chunks` has
  `vector(768)` + HNSW (`vector_cosine_ops`) and a generated `tsvector` + GIN. The vector
  query is a bare `ORDER BY embedding <=> q LIMIT 4n` subquery, then filtered (embedding
  model/version, document status); filters on the join made Postgres skip the HNSW index
  (checked with EXPLAIN, now a test). `hnsw.ef_search` is raised to the over-fetch. The
  migration needs pgvector: on Supabase enable the `vector` extension before running it.
- **Full-text is OR, not AND:** `plainto_tsquery` with `&` turned into `|`, ranked by
  `ts_rank_cd`, so a chunk naming the drug but not the outcome still ranks. Vector search
  only matches chunks embedded with the current model+version; full-text matches all, so a
  model change degrades to full-text until the library is re-embedded. If the query encoder
  fails, search degrades to full-text and records it in `errors`.
- **IDs:** `document_id` = first 16 hex of the file's SHA-256 (the same scan always gets the
  same ID); chunk ID `<document_id>_<position>`.
- **PubMed dedup:** a manifest PMID → linked (`status = linked_pubmed`, no chunks) with no
  lookup; a DOI → optional PubMed ESearch on `[doi]` (`PubMedDoiLookup`, exactly one hit
  counts). If that check fails (NCBI down) the document is indexed anyway, with a note.
  A second scan with a DOI/PMID already in the library is reported as a duplicate.
- **OCR confidence** (§6 "pages with low OCR confidence are flagged"): OCRmyPDF doesn't
  report one, so a second Tesseract pass (`tsv`) over each OCRed page gives the mean word
  confidence; a word-shape ratio is a second, engine-free check. Thresholds 70 and 0.6 are
  starting values. Flagged pages' text is held in `library_documents.ocr_quality.held_text`
  (JSON; the doc's "OCR quality" column, made per-page) and indexed only by
  `approve_pages(doc, pages, reviewer, corrected_text=)`; the document is `needs_review`
  meanwhile and its other pages are searchable.
- **Paragraphs are rebuilt from line geometry**, because OCRmyPDF's text layer is one
  block per line: a gap clearly wider than the in-paragraph line gap, a jump back up (next
  column) or a short sentence-ending line starts a paragraph. Reading order is Tesseract's.
- **Chunking:** ~400 tokens / ~50 overlap, counted as words + punctuation (approximate;
  MedCPT's WordPiece count is higher, and the encoder truncates at 512). References are
  skipped from a "References"/"Bibliography" heading until an appendix/table/figure heading,
  plus stray reference-like paragraphs.
- **MedCPT** (`MedCptEmbedder`): article encoder on `[title, chunk]` pairs, query encoder for
  queries, CLS pooling, via `transformers` loaded lazily (`pip install -e ".[library]"`).
  Not run in the build (no weights, no network); tests use a fake loader.
  `HashingEmbedder` is a model-free stand-in for tests and trials only.
- **Library query** = the planner's intervention, outcome and population terms (matched
  text, label, two synonyms) as plain words, plus uncovered claim words.
- **Measurement:** `app/evaluation/library_fallback.py` — `fallback_stats(states)` (fire
  rate, fired-and-kept) and `verdict_changes(pubmed_only, with_library)`.
- **Tested on generated sample scans only** (reportlab → image → skewed/blurred image-only
  PDF, `app/tests/library_samples.py`; nothing binary committed). Real OCRmyPDF/Tesseract
  ran in the build: WER 0.000 and reading order 1.00 on 5 generated pages including a
  two-column page and 2° skew (`scripts/compare_library_ocr.py --samples`); a blurred 100 dpi
  page scored confidence ~45 and was flagged. Clean generated pages are easy, so this says
  the plumbing works, not that real scans will. Postgres tests ran on a local Postgres 16 +
  pgvector 0.6 (`LIBRARY_TEST_PG_DSN`, a throwaway DB: the test drops its schema).

**Left for a person:** run `scripts/compare_library_ocr.py --dir` on ~20 real scanned pages
with hand transcripts (Tesseract vs EasyOCR; EasyOCR wasn't installed here) and set the OCR
thresholds from it; download MedCPT and check retrieval on real library documents; enable
pgvector on Supabase and run migration 0006; build the internal viewer the `source_url`
points at (`/library/documents/{id}?page=&chunk=`, not built) and the analyst UI label for
library sources; decide who may upload (copyright: T13 gives `search_library` its own scope).
## 7k. Validation and Human-Review Routing (T09, #36)

Validation is `backend/app/core/graph/validation.py`; the review rule is
`backend/app/core/graph/review_policy.py` with thresholds in
`backend/config/review_policy.yaml`; persistence is `app/db/models/review.py`,
migration `0007` and `app/services/review_service.py`. Both nodes are deterministic, so
the default graph now uses them instead of the T02 stubs (no model calls change; the
graph is still not wired into `run_pipeline`).

**Validation (§10): eight checks, one issue string each,**
`"<check>:<step>[:<claim_id>]: <message>"` in `validation_errors`: `schema` (every record
re-validated against its Pydantic model, labels from the allowed set, `video_id`,
non-empty explanation, `decision_rule` present), `citation_membership` (every evidence ID a
verdict or the result cites was retrieved for *that* claim; a paper retrieved for another
claim is misattributed), `quote_membership`, `source_ids`, `merge_plausibility`,
`timestamps`, `consistency` (re-runs the §9 rules and compares label, rule, deciding claims
and judge flags) and `length_limits`. A check that crashes is itself a failure.

- **Repair: only the judge is re-run.** Every issue names the step that produced the bad
  output. If any issue is in `final_result`, `validate_result → judge_classification` runs
  once more (`validation_attempts` bounds it: one repair, new conditional edge
  `routing.route_after_validation`). On the repair run the judge recomputes the label from
  state and uses the deterministic template instead of the LLM explanation (the only model
  output in the result), so a repair never costs a model call and always produces valid
  text. §10 says "the failing step is re-run with the error message"; for the judge the
  error message adds nothing, because its rules are deterministic and the template is
  always valid. Upstream faults (claims, stance, verdicts) are **not** re-run here: those
  nodes already did their own repair (verifier: one re-ask, T06; stance: UNCLEAR, T04),
  and re-entering the retrieval loop from validation would be a second, unbudgeted loop. They go
  straight to review.
- **Validation can't be bypassed:** if `validation_errors` was never written, the review
  rule adds `validation_failed:not_run`.
- **Quote membership** accepts the transcript, OCR text *and claim texts*, case-, accent-
  and punctuation-insensitive, with the judge's "…" truncation matched as a prefix.
  Claim texts count because the template explanation quotes claims and T10 already checks
  claims are grounded in their segments. Quotes under 12 characters are not checked.
- **Merge plausibility:** a claim's source segments must chain in time with gaps of at
  most 2 s, and the claim's own span must overlap them.
- **Timestamps:** new optional input `video_duration_seconds` (`initial_state(...,
  video_duration_seconds=)`); without it only sign and order are checked. Zero-length
  segments are allowed (Whisper emits them); zero-length claims are not.
- **New state fields** (additive, optional; schema version stays 1.0.0):
  `video_duration_seconds` (input) and `validation_attempts` (owned by `validate_result`).
  `recursion_limit` gained the 2 repair steps.

**Review rule (§11): named rules in `review_policy.REVIEW_RULES`**, each unit-tested;
`evaluate()` also returns which rule gave which reasons (`fired`), and `rule_of(reason)`
maps a stored reason back to its rule, for §12's per-rule review counts and overturn rates.

| Rule | Reason | Notes |
|---|---|---|
| `validation_failed` | `validation_failed:<check>[:<cid>]` | after the repair; `:not_run` if validation was skipped |
| `weak_evidence` | `weak_evidence:<cid>` | deciding claim INSUFFICIENT/MIXED, **and** every INSUFFICIENT/MIXED claim when the label is CANNOT_RECOGNIZE because nothing could be judged |
| `conflicting_evidence` | `conflicting_evidence:<cid>` | deciding verdict cites both supporting and contradicting papers |
| `weak_study_types` | `weak_study_types:<cid>` | every paper a deciding verdict cites is in vitro, animal or case report (reranker's `study_type`, else looked up from the publication type); `unknown` is not weak |
| `unclear_stance` | `unclear_stance:<cid>` | deciding claim UNCLEAR or with no stance |
| `critic_escalated` | `critic_escalated:<cid>` | ESCALATE or `requires_review` (from T07's `routing.critic_review_reasons`) |
| `budget_exhausted` | `budget_exhausted:<cid>` | same source (§11 "Effort"); the rules read T07's `verdicts_for_judge`, so an exhausted claim counts as INSUFFICIENT_EVIDENCE |
| `low_confidence` | `low_confidence` | calibrated confidence < 0.70. **Dormant**: confidence is `None` until T15 and an uncalibrated number is never compared |
| `high_risk_uncertain` | `high_risk_uncertain:<cid>` | issue #36: an *endorsed* claim in a high-risk category whose verdict is INSUFFICIENT/MIXED/NOT_VERIFIABLE, deciding or not |
| `judge_flags` | `judge:<flag>` | T08's flags, kept |
| `guardrails` | `guardrail:...`, `prompt_injection_suspected:...` | T10's reasons, kept |

Decisions and deviations:

- **Abstentions now go to review.** The T02 note said "a deciding claim is
  INSUFFICIENT_EVIDENCE or MIXED" can never fire under the §9 rules. §1 says that when the
  evidence is too weak to decide the system "hands the case to a person instead of
  guessing", so a CANNOT_RECOGNIZE caused by insufficient or mixed evidence is reviewed. A
  video with no checkable claims (`no_claims`) or only NOT_VERIFIABLE claims is not. One
  T02 skeleton test was changed to match. This will raise the review share; the
  evaluation should report it (§12).
- **High-risk categories are a provisional list** in `review_policy.yaml` (there is no
  agreed `claim_category` taxonomy yet; it includes `treatment_efficacy`, which most
  claims will carry). Align it with the claim-level track's categories.
- **Not implemented:** "content outside validated capabilities" (issue #36; needs a
  language or domain signal the state doesn't have yet), materiality and satire (T08
  note). The quantity and relevance signals of §11 (one paper after reranking, low
  relevance) are not review rules on their own, because §11's rule list doesn't include
  them and the reranker already drops papers below relevance 0.4; they feed
  `weak_evidence` through the verifier's INSUFFICIENT verdict.
- **The review step doesn't pause the graph.** `human_review` marks the run
  `REVIEW_REQUIRED` and the run continues to `persist_result`, which (T11) calls
  `review_service.open_review_case`. The reviewer acts on the stored case days later;
  keeping a LangGraph interrupt open that long would tie review to checkpoint retention.
  "Request re-analysis" starts a new job.
- **Persistence (`0007`; `0006` is T12's library tables).** `JobStatus.REVIEW_REQUIRED` (Postgres `ALTER TYPE ... ADD
  VALUE`, run in an autocommit block) and a `human_reviews` table (§17): reasons,
  rules fired, validation errors, proposed label and result, policy and pipeline version,
  and the reviewer's action, reason, corrected label/claim corrections and time.
  `record_review_decision` requires a reviewer and a written reason for every action:
  APPROVE/CORRECT/MARK_INSUFFICIENT → job SUCCESS (a stored `Result` takes the corrected
  label), REJECT → FAILED with `error_code=REVIEW_REJECTED`, REQUEST_REANALYSIS → stays
  REVIEW_REQUIRED. `GET /jobs/{id}/result` already requires SUCCESS, so a case in review
  is never served as a final result. No reviewer UI or API endpoint (out of scope).
  Migration number coordinated in `context/PRODUCTION.md` §6a (per-user isolation moves
  to `0008`). Upgrade/downgrade tested on SQLite (in the suite) and once by hand on a local
  Postgres 16 (0001–0005, `0006` stamped because pgvector was missing, then `0007` up,
  down with a REVIEW_REQUIRED job moved to FAILED, and up again). Not run on Supabase.
- **For T11:** call `open_review_case` from `persist_result` when
  `requires_human_review`; pass `video_duration_seconds` into `initial_state`; the jobs
  router's duplicate check (`PENDING/STARTED/SUCCESS`) doesn't include REVIEW_REQUIRED, so
  a re-upload of a video in review starts a new job; decide whether that's wanted.
- **Rebased onto T07 and T12:** citation membership accepts `library_evidence`; the
  consistency check and the review rule use T07's `verdicts_for_judge` with the graph's
  budgets. One T12 test fixture placed a claim at 0–1 s while citing a segment at 3.5–8 s;
  the new merge check flagged it, so the fixture now uses the segment's span.
- **Effect on existing numbers:** T10's adversarial report is unchanged (5 unsafe out of
  34, 4 held for review); the sample video still goes to review only for
  `judge:mixed_video`.

## 7l. Retrieval MCP Server Decisions (T13, no issue; design §6, §15)

- **Package:** `backend/app/mcp_server/`, a thin wrapper over `app.core.retrieval` (which
  still has no MCP or LangGraph imports; a test checks it, and that nothing in `app/core`
  or the worker imports the server). `service.py` holds access control, limits and dispatch
  with no MCP code; `server.py` is the MCP layer. The live pipeline is unchanged.
- **SDK: `mcp>=2.0,<3`, `MCPServer`.** The doc names FastMCP; in the SDK's 2.x line it was
  renamed `MCPServer` (same decorator API). Optional extra `[mcp]` (and in `[test]`), not
  in `requirements.txt`, so the API/worker images don't change. Streamable HTTP, stateless,
  JSON responses (no sticky sessions across replicas), Host-header allowlist.
- **Tools** are the five of the §6 table, names as in the doc. Tool parameters reuse the
  input models' `FieldInfo`, so the published JSON Schema carries the same hard caps
  (query 300 chars, `max_results` ≤ 100, ≤ 50 PMIDs, library `k` ≤ 10, ≤ 100 rerank
  records, rerank `k` ≤ 10). Outputs are Pydantic models (structured content). Outputs with
  third-party text carry `untrusted_fields` and a notice; the server instructions and tool
  descriptions say the same.
- **Auth:** static bearer tokens, one per client, stored only as SHA-256 hashes in
  `MCP_CLIENTS` / `MCP_CLIENTS_FILE` (never in the repo); `scripts/mcp_client_token.py`
  makes one. One scope per tool (`retrieval:<tool>`), so `search_library` is its own scope.
  No clients configured = every call refused. Not OAuth: the SDK's `AuthSettings` needs an
  issuer URL, so it is set to the server's own URL; a real authorization server can replace
  the verifier later without changing tools.
- **NCBI quota:** `quota.py` — token buckets, Redis (one Lua script, Redis's clock, both
  buckets taken atomically or neither) and in-memory. Each PubMed request takes from
  `ncbi:global` and from the client's own bucket at `ncbi_share` × the rate (9/s with a key,
  2.5/s without). Shares + `pipeline_share` (0.5) must be ≤ 1 or the server won't start.
  Share 0 = cache hits only. Waits up to 5 s, then `ncbi_quota` with `retry_after`. Redis is
  required in deployment (fails closed rather than letting replicas each keep a quota).
  Also a per-client calls-per-minute bucket (default 120).
- **Our pipeline doesn't use the shared bucket yet.** The doc says one Redis bucket spaces
  *all* PubMed calls; the graph still uses its per-process `RateLimiter`.
  `quota.pipeline_ncbi_limiter(store, has_api_key=)` is the drop-in (`PubMedClient(rate_limiter=)`),
  left for T11 to wire behind its flag. Until then the pipeline and the server's clients
  together can exceed NCBI's limit only if both run at full rate at once.
- **Shared query cache:** the server uses `RedisQueryCache` (same `retrieval:` prefix);
  sharing it with the pipeline's workers is also a T11 wiring decision.
- **Limits:** per-call timeout 20 s (tool code runs in a thread under `anyio.fail_after`;
  PubMed retries cut to 3 attempts / 4 s max backoff to fit), request body 1 MB (413),
  response 2 MB, unknown errors return a generic message (no DSNs or stack traces).
- **Contract:** `contract/tools.json` snapshot; the CI test fails on any schema change and
  says whether it is additive (refresh the snapshot) or breaking (ship a new tool name).
  `breaking_changes` inlines `$ref`s, so a change inside `EvidenceRecord` is caught.
- **Tested** with recorded PubMed fixtures, an in-memory library, the in-process MCP client,
  HTTP through an ASGI transport (401 without/with a forged token, scopes per client, 413,
  bad Host), and a real local `redis-server` for the Lua bucket and shared cache. A real
  `python -m app.mcp_server` was started and called over localhost HTTP.

**Left for a person:** create the Railway service (`backend/Dockerfile.mcp`, health
`/health`; not added to `railway.toml` on purpose), set `MCP_PUBLIC_URL`,
`MCP_ALLOWED_HOSTS`, `REDIS_URL`, `NCBI_API_KEY`, `DATABASE_URL_SYNC`; issue the other
team's token and agree their scopes and NCBI share (and whether they get `search_library`,
given library copyright); add the contract check against `main`'s snapshot to CI if CI
gains a job for it.

## 7m. Integration Decisions (T11, #38)

The graph runs in production code behind `USE_GRAPH_PIPELINE` (default **off**). With it
off, `run_pipeline()`, `get_provider()` and the Celery task behave exactly as before
(a test checks that the single-call path asks for no segments and never builds the graph).

- **Where things are.** `GraphProvider` (`app/core/inference/providers/graph_provider.py`)
  implements `InferenceProvider.classify(fusion)`; `run(...)` also returns the final
  state and the fallback record. Real claim extractor `app/core/graph/claims.py`
  (prompt `extract_v1`). Provider clients for `ModelRouter`
  (`app/core/routing/clients.py`, Anthropic + OpenAI, forced tool calls, error kinds
  mapped to the router's fallback policy). Worker path `run_graph_pipeline()` +
  `tasks._run_graph_job`; persistence `app/services/pipeline_result_service.py`.
- **Trigger decision: the graph runs on every video while the flag is on**, not only
  below a single-call confidence threshold (the old #21 plan, 0.60). Today's confidence is
  the single call's own, uncalibrated number (§11), so a threshold on it is not a
  measured gate; and gating would let the single call, the step the graph replaces,
  decide which videos get evidence, while paying for both calls on every gated video. If
  T14 shows the graph is too slow or costly for every video, revisit with a calibrated
  signal (T15), not the raw one.
- **Fallback to the single call, recorded on the result** (`results.pipeline =
  graph_fallback`, `results.fallback_reason`): graph exception (`graph_error:<Type>: …`),
  wall-clock timeout (`GRAPH_TIMEOUT_SECONDS`, default 900; checked between graph steps,
  each provider call has its own `GRAPH_MODEL_TIMEOUT_SECONDS`), a run that ends without
  `final_result` (`no_result`), the extractor's model unreachable
  (`extraction_unavailable`; otherwise "no claims" would be published as "no checkable
  health claims"), and claims extracted but every later model call failed
  (`models_unavailable`). **An abstention is not a failure:** a graph that ran and said
  CANNOT_RECOGNIZE or sent the case to review keeps its answer; replacing it with the
  single call would undo §1 "scientific uncertainty: abstain". If the fallback itself
  fails, the job fails as today (`INFERENCE_ERROR`). The fallback answer gets the single
  call's own post-hoc PubMed grounding, so it looks like a single-call result.
- **Claim extraction (§4) was built here.** No task owned it and the stub made one claim
  per segment. Forced `record_claims` call on the routed `extract_claims` step, fenced with
  T10's `extraction_prompt`; cited block IDs (`f1`, `f1.screen1`) map back to `t*`/`o*`
  pieces, timestamps are computed from them, ungrounded claims (content-word overlap
  < 0.5) are dropped with a `guardrail:` error (review), one repair on malformed output,
  T10's 50-claim cap, windows of 240 s with 20 s overlap for long videos. **Deviation from
  §4:** dedup uses a lexical, negation-aware similarity (Jaccard ≥ 0.85) because no
  embedding model is wired into the worker; an embedding similarity can be injected.
  It wraps none of the claim-level track's #12 prototype; swap in their extractor when it
  lands, keeping the node contract.
- **Timestamps.** The single-call fusion keeps only text, so the graph path calls
  `MultimodalFusion.fuse(keep_segments=True)` (Whisper segments; `verbose_json` for the
  hosted API). If segments are missing, sentences get estimated timing
  (`GraphOutcome.timing_estimated`). `video_duration_seconds` is not passed yet (the
  worker doesn't know the duration), so the §10 check compares order only.
- **Persistence is in the worker, not the `persist_result` node** (deviation from the
  "Persist" box in §4): one transaction writes `results` (new columns `pipeline`,
  `pipeline_version`, `fallback_reason`, `decision_rule`, `deciding_claim_ids`), the
  claim-level rows, `model_runs`, and the job state, for both the graph and its fallback,
  and the checkpointed state never holds a DB session. `persist_result` stays
  reference-only. `open_review_case` (T09) is called there when `requires_human_review`.
- **Migration `0008`** adds §17's `transcript_segments`, `ocr_segments`, `claims`,
  `claim_stances`, `evidence_records`, `claim_evidence` (SUPPORTS / CONTRADICTS /
  CONSIDERED), `verification_results`, `critic_reviews`, `model_runs`. **Deviations from
  §17:** evidence records are per job, not shared across jobs; the video label stays in
  `results` (no separate `classifications` table). Per-user isolation moves to `0009`
  (PRODUCTION.md §6a updated). Tested up/down on SQLite (suite) and by hand on a local
  Postgres 16 (0001–0005, 0006 stamped, 0007–0008 up, down, up). Not run on Supabase.
- **Idempotency.** Thread ID = job ID: an unfinished checkpoint is resumed, a finished
  one reused without model calls. Claim-level rows are replaced per job and the result
  row is updated in place, so a second delivery leaves one copy. With the flag on, the
  task skips a job that is already `SUCCESS`/`REVIEW_REQUIRED` with a result. Postgres
  checkpoints need `LANGGRAPH_CHECKPOINT_DSN` and the one-off setup step from §7a; without
  it, checkpoints are in memory and a retried task starts over.
- **API and frontend.** `GET /jobs/{id}/result` also serves `REVIEW_REQUIRED` jobs and adds
  `pipeline`, `fallback_reason`, `review` (status and reasons) and `claims` (empty for
  single-call results). The job page shows a "Provisional: awaiting human review" banner,
  per-claim stance/verdict/papers when present, and an "In review" badge in the list.
  `tsc --noEmit` passes; not checked in a browser. The duplicate-job check now includes
  `REVIEW_REQUIRED` (a video in review is not analysed again; T09's question).
- **Not wired (left for a person or a later task):** T10's upload-path input limits
  (size, duration, container sniffing, rate limit, quota) — they are upload rules, not
  graph rules, so they need their own flag and a shared store for multi-worker rate
  limits; the offline library fallback (T12; needs a deployed library + embedder); an
  LLM assistant for query planning; **T13's shared NCBI token bucket** — it lives in
  `app.mcp_server.quota`, and T13's test forbids `app.core`/`app.worker` importing the
  MCP server, so wiring it means moving the bucket into `app.core.retrieval` first. Until
  then workers keep the per-process limiter.
- **Wired from T13:** with `GRAPH_SHARED_RETRIEVAL` (default on) and `REDIS_URL`, the
  workers use the MCP server's Redis query cache (`retrieval:` prefix); cache errors are
  swallowed, so a Redis outage only costs extra NCBI calls.
- **Nothing here was run against real models or PubMed.** Tests use a scripted
  `ModelClient` behind the real `ModelRouter` + `routing.yaml`, and T03's synthetic
  PubMed fixtures. The provider clients are tested against fake SDK objects; their first
  real call (and whether the Anthropic/OpenAI request shapes are accepted as written)
  happens in T14 with keys.

## 7n. Reference Sources and claim_kind (T17, no issue; design §4, §6)

Design §6 "Trusted sources beyond PubMed" and §4 `claim_kind`, added after the first
golden-set batch (commit f238dab). Code: `app/core/retrieval/references/`,
`app/core/retrieval/claim_kind.py`, `config/reference_sources.yaml`.

- **`claim_kind` on every claim.** `GraphClaim.claim_kind` is `research_question` (default,
  so pre-T17 checkpoints load) or `fact_of_record`. The extractor asks the model for it
  (new prompt `extract_v2`, tool enum; `routing.yaml` now names `extract_v2`); a missing or
  unknown value costs no repair round: fixed rules decide (`infer_claim_kind`). Rules:
  `statistic` category or a population-count cue ("100,000 people every year", "leading
  cause of death") → fact; an efficacy/causation verb → research; a schedule, limit,
  composition or physiology cue → fact; otherwise research. When unsure the claim stays a
  research question, which keeps PubMed-only retrieval.
- **The allow-list is the config.** `config/reference_sources.yaml` lists each source's
  exact hosts and path prefixes; loading fails if a catalogue URL is outside its source's
  list, a host has a wildcard, or a URL isn't HTTPS. The fetcher re-checks every URL,
  follows no redirects (a redirect off the list would be a way out), has a timeout and a
  3 MB cap, and reads only text types. Models never see or name a URL.
- **Two backends, no web search.** *catalogue*: a fixed list of pages per source (CDC/WHO
  schedules, FDA/EFSA caffeine, WHO fact sheets, NHS), matched by keyword phrase in the
  claim; *bookshelf*: NCBI Bookshelf via E-utilities `db=books` (ESearch + ESummary, then
  the `NBK…` chapter page), sharing PubMed's NCBI rate limiter. A malformed accession is
  never turned into a URL. **Deviation:** the doc lists WHO GHO, national statistics
  offices and USDA FoodData Central; their sources are in the allow-list but have no
  catalogue pages yet (GHO and FoodData have APIs — FoodData's needs a key — which would
  be a third backend). Left for a person to add pages from the golden-set claims.
- **Cited like papers.** `EvidenceRecord.source` gains `"reference"` plus optional
  `publisher`, `retrieved_at`, `snapshot_sha256`. `abstract` holds the quoted passage —
  the page's own paragraph (≤ 1,200 chars) with the most claim content words, numbers as
  a tie-break bonus; no passage sharing ≥ 30 % of the claim's words → no record (an
  off-topic official page is not evidence). `evidence_id` = `ref_` + first 16 hex of
  SHA-256(URL, snapshot hash, passage): stable for the same page version, new when the
  page changes.
- **Snapshots.** The full fetched text is stored once per distinct text, keyed by its
  SHA-256: `InMemorySnapshotStore` for tests, `SqlSnapshotStore` → new table
  `reference_snapshots` (migration **0009**, which also adds the three evidence columns
  and `claims.claim_kind`). State holds only the hash. Per-user job isolation, planned as
  0009, is now **0010**.
- **Alongside PubMed, not a fallback.** `retrieve_evidence` searches references once per
  `fact_of_record` claim, in its first round, and merges them into `retrieved_evidence`,
  so citation membership, the judge, validation, injection scanning and persistence treat
  them like papers with no special case. Research questions never touch references. A
  reference failure is a `NodeError`; PubMed still runs. The library fallback is unchanged
  and still fires when no PubMed paper clears the threshold, for both kinds.
- **Ranking.** New study type `reference` (evidence class `authoritative_reference`,
  not on the weak list). `Reranker.rerank(..., claim_kind)` puts references ahead of every
  study for facts of record and after the studies otherwise (also when no kind is given,
  e.g. via MCP). Reference relevance = share of the claim's content words in title and
  passage (the PICO intervention/outcome test doesn't fit a schedule); same 0.4 threshold
  and the same cap of 10 in total.
- **Same verdict rules.** Rules stay in the prompt and the existing checks: new verifier
  prompt `verify_v2` (routing now names it) tells the model a reference supports
  CONTRADICTED only when it states the claim is false or gives a conflicting figure, and
  that "no evidence that X works" stays INSUFFICIENT_EVIDENCE. The evidence index shows
  publisher and retrieval date. The judge's explanation check now recognises `ref_` (and
  `lib_`, previously missed) IDs. Judge rules untouched (T16 owns them).
- **MCP contract unchanged.** The MCP tools publish their own v1 `EvidenceRecord`
  (identical schema to before), converted at the boundary, so `contract/tools.json` did
  not change. Records with `source: reference` are refused by the MCP tools; exposing
  references would be a new tool name. Nulls for the new fields are accepted on input.
- **Off by default.** `USE_REFERENCE_SOURCES` (default false, read only when
  `USE_GRAPH_PIPELINE` is on). With it off, claims still carry `claim_kind` (and the new
  prompts run when the graph is on) but retrieval is PubMed-only, as before.
- **Not verified live.** No outbound network in the build environment: the catalogue URLs
  were written from the publishers' site structure and were never fetched; the test
  fixtures are synthetic pages (`app/tests/fixtures/references/README.md`), not the
  publishers' text, and the Bookshelf ESummary field names (`chapteraccessionid`,
  `accessionid`) are from memory of the API. Left for a person: open each catalogue URL,
  record real pages, check a real `db=books` ESummary, run migration 0009 on Supabase,
  then turn `USE_REFERENCE_SOURCES` on.

## 7o. First Real-Model Smoke Run (T18, no issue; design §13, §14)

Graph (all real nodes, references on) and the single-call baseline on 10 golden-set
transcripts (v07, v12, v20, v30, v41, v52, v60, v70, v75, v80; speech only, as the live
worker sends it; OCR off). Harness: `backend/scripts/smoke_run.py` (never reads labels).
**No accuracy numbers**: the labels are still being relabelled and reviewed.

- **Spend: $6.66 in total** ($5.45 for the 10-video run, $1.19 re-running v07 and
  v12 after the fixes, about $0.01 of probes, rounded up), under the $15 cap.
- **Cost and latency per video (graph):** median $0.41 / 76 s, mean $0.54 / 90 s, max
  $1.24 / 184 s (18 claims). Baseline (gpt-4o single call): median $0.0026 / 1.5 s, so the
  graph costs about 190× as much. Cost grows with the number of claims (4 → 23 per video).
  Split by step over the run: verify (Opus 5.5) 67%, critic (gpt-4o) 19%, stance
  (Sonnet 5.5) 11%, judge explanation 1.4%, extraction (Haiku 5.5) 0.2%. The verifier is
  the place to cut cost (per-step routing evaluation, §13), and the critic re-reads the
  whole evidence set on every claim (404k input tokens for 5k out).
- **Integration bugs found and fixed (each with tests):**
  1. The Anthropic client sent `temperature`; the installed SDK (2.x; `anthropic` is
     unpinned in requirements) no longer accepts it and current Claude models reject it.
     **Every** Anthropic step failed, so the graph would have fallen back on every video.
     The client no longer sends sampling parameters (OpenAI still gets `temperature: 0`).
  2. Sonnet 5.5 and Opus 5.5 refuse a forced `tool_choice` (400), which broke stance,
     verify and the judge explanation. The client now retries once with `tool_choice: auto`,
     one tool call allowed, an instruction naming the tool, and `max_tokens` raised to at
     least 8192 (thinking is always on for these models and counts against the cap). It
     remembers which models need this. A reply without the tool still parses as None (the
     node's safe default). Haiku 5.5 accepts the forced call and keeps it.
  3. §10 quote check: speech segments were joined with newlines, so a quote crossing a
     Whisper segment boundary (Whisper cuts mid-sentence) failed and forced review. Speech
     is now matched as one running text. Also accepts an elided quote ("a ... b") when
     every piece appears in order in one source.
  4. The judge's "Not judged (no usable evidence): c1 INSUFFICIENT_EVIDENCE, ..." line
     went over its own 300-character validation limit on any video with roughly 13 or more
     unjudged claims, so long videos always failed validation. Now grouped by verdict
     (`INSUFFICIENT_EVIDENCE c2, c4; NOT_VERIFIABLE c3`), with counts when even that is too long.
  5. PubMed EFetch: single records with consortium author lists are about 2 MB, so a
     20-PMID batch passed the 5 MB response cap and the claim lost all its papers (seen on the
     query `cops lie`). An oversized batch is now split in half and retried; a single
     record over the cap is skipped.
  6. Reference catalogue: WHO moved the salt fact sheet (`.../salt-reduction` → 301 →
     `.../sodium-reduction`); the fetcher rightly refuses redirects, so the entry had been
     dead since T17. URL updated.
  7. `scripts/record_pubmed_fixtures.py` crashed on NCBI's first 429 (its recording hook
     parsed the error body as XML). It now skips non-200 replies, so the client's retry runs.
  Also: the single-call providers record `last_usage` (tokens) so the baseline can be
  costed, and `gpt-4o-2024-08-06` is priced in `routing.yaml` (the critic and fallback
  were unpriced, so the graph's cost would have been reported as unknown).
- **Verified live, previously unverified:** references work end to end. WHO, FDA, EFSA,
  NHS and NCBI Bookshelf (ESearch/ESummary field names included) returned passages. The
  PubMed planner and retriever ran against real NCBI. No graph fell back to the single
  call and no model call failed after the fixes.
- **Real PubMed fixtures:** recorded for the script's 10 default claims (10 searches, 199
  records, 21 requests, at most 2.5/s). Committed trimmed to `app/tests/fixtures/pubmed_live`
  (top 3 records per query, `<ReferenceList>` removed: 30 records, about 300 KB), with a
  parser and retriever test. The full table is in the T18 PR.
- **Left for a person:**
  - CDC pages answer "Access Denied" (Akamai bot block) from this environment. Check from
    production before relying on the CDC catalogue entries.
  - Copyright: the committed fixtures are real abstracts. Decide whether they may stay in the repo.
  - NCBI returned 429 at 2.5 requests/s from the shared egress IP. Get an NCBI key
    (10/s) before running at volume.
  - Pin `anthropic` (and `openai`) in requirements. The temperature break came from an
    unpinned major upgrade.
  - The stance model "corrects" Whisper errors and adds editorial brackets in its
    quotes ("nanosink" → "nano zinc", "insinuate[s]"), which the §10 check rightly flags.
    That needs a prompt change ("quote verbatim, transcription errors included"); prompts
    are versioned, so it should go through evaluation.
  - `merge_plausibility` flags claims whose segments are 3–6 s apart. Real speech has
    pauses that long, so the gap threshold needs tuning on real data. One 23 s merge was a
    real extractor error.
  - Retrieval yield: most claims ended INSUFFICIENT_EVIDENCE, and every video was sent to
    review (mostly `weak_evidence` and `budget_exhausted`). That is not an accuracy result, but
    it is the first thing T14 should look at. One query for "5G spreads coronavirus" found
    unrelated papers (hyperthyroidism).
  - The `extract_v2` reply once included an extra field (`requirement_placeholder`),
    which was caught by schema validation and repaired. `strict: true` on the tool could
    prevent it.
  - The legacy single-call `OpenAIProvider` defaults to the floating alias `gpt-4o`
    (resolved today to `gpt-4o-2024-08-06`), against §13's pinned-ID rule. Live default
    unchanged.

## 7q. Production Reference Retrieval (T19, no issue; design §6)

Found while labelling the golden set: www.cdc.gov answers 403 to scripted requests from
cloud hosts and the NCBI Bookshelf website serves a reCAPTCHA. Code:
`app/core/retrieval/references/{search,stored,refresh,passages}.py`,
`scripts/refresh_reference_snapshots.py`, `data/reference_snapshots/`.

- **Bookshelf through E-utilities only.** Checked live (2026-11-23): `efetch` on
  `db=books` returns no text (only an ID list; `rettype=full&retmode=xml` is refused with
  HTTP 400), and `www.ncbi.nlm.nih.gov/books/NBK…` returns a captcha page. **Deviation
  from the task wording ("db=books, esearch/efetch"):** chapters are found the way PubMed
  indexes them: ESearch `db=pubmed` with `(<terms>) AND booksdocs[filter]`,
  `sort=relevance`, then EFetch `db=pubmed` XML, whose `PubmedBookArticle` gives the
  chapter's own `bookaccession` (`NBK…`), title, book and summary text. Two requests per
  claim (was 2 + one page fetch per chapter), no website request. The Bookshelf URL is
  the citation link only; it is built from a checked accession and never fetched. The
  design doc's "searched through the same E-utilities API" still holds. `NCBI_API_KEY`
  is now passed to these calls too (it wasn't), and 429/5xx are retried with backoff (3
  attempts) under the shared NCBI limiter; T18 saw 429s from the shared egress IP.
- **Limitation:** the quoted text is the chapter's PubMed summary (for StatPearls, the
  chapter overview), not the full chapter. Full text is not available through
  E-utilities. Good for "normal temperature is about 37 °C"; a fact deep in a chapter
  body will not be found.
- **Stored, versioned snapshots.** A source or catalogue page can be
  `retrieval: stored` (CDC is). Claims never request those pages: the searcher reads the
  current version from `data/reference_snapshots/` (committed: `index.json` with each
  page's URL, current hash and history, plus one immutable `<page_id>/<sha256>.json` per
  distinct text) and cites it like a live page: same passage choice, same `ref_<hash>` id
  rule (URL, snapshot hash, passage), `retrieved_at` = the capture date, `query` =
  `stored:<page_id>@<sha12>`, and a copy saved to the `reference_snapshots` table on use.
  Every read re-checks that the text hashes to its name; a tampered, missing or
  wrong-URL snapshot is an error (a `NodeError`, as T17), never a request. A snapshot
  older than `stored_snapshot_max_age_days` (180) is still cited (dated) but reported as
  stale on every use. Committed files rather than a DB table so every change to cited text
  goes through a reviewed PR and production needs no migration or network; CDC text is
  U.S. federal government work (public domain).
- **Refresh script** `scripts/refresh_reference_snapshots.py`: fetches every stored page
  through the same allow-listed fetcher (honest User-Agent, no redirects, size cap) and adds
  a version only when the text changed; `--import PAGE=file.html` takes a copy a person
  saved in a browser when the publisher refuses the script too; `--set-current
  PAGE=<sha>` rolls back; `--check` verifies the archive and shows ages (no network; a
  test runs it on the committed archive). Nothing tries to look like a browser.
- **CDC snapshots captured 2026-11-23** (CDC answered 200 from this build host that day,
  unlike T18's run): child/adolescent schedule, the new adult schedule page
  (`cdc_adult_schedule`), and the measles vaccination page. 3 requests.
- **Passages on real pages.** Real CDC text splits one statement over many short blocks
  ("Doses are given at:" / "12–15 months old" / "1st dose"), and T17's stemmer turned
  "doses"/"vaccines" into "dos"/"vaccin", which never matched "dose"/"vaccine". Fixed the
  stemmer (plural endings only) and let a passage be a window of up to 6 consecutive whole
  paragraphs (≤ 600 chars), quoted verbatim (still a substring of the snapshot); equal
  scores go to the shorter candidate. For "The MMR vaccine is given at 12 months" the CDC
  quote is now "All children are recommended to have 2 doses of MMR vaccines. Doses are
  given at: 12–15 months old". Verdict rules untouched.
- **Tests:** fixtures only. The Bookshelf replies are recorded (2 requests, trimmed); the
  fake www.cdc.gov answers 403 and the fake Bookshelf website a captcha, and tests assert
  neither is ever requested. CDC pages in tests come from an archive built from T17's
  synthetic pages; one test checks the committed real archive.
- **Left for a person:**
  - The schedule grids (child/adult tables) come out as one cell per paragraph, so a
    claim that turns on one grid cell ("shingles vaccine at 50") rarely gets a precise
    quote. The measles page's prose is fine. A table-aware extractor or more prose pages
    (e.g. CDC's per-vaccine "who should get" pages) would fix it; add them as stored pages.
  - Re-run the refresh script on a schedule (e.g. monthly) from a host CDC accepts, or
    import browser copies, and review the diff in a PR. `--check --strict` fails on stale.
  - Copyright of the committed StatPearls summary in the Bookshelf fixture (same
    question as T18's PubMed fixtures).
  - `bookshelf_query` ANDs every content word, so long claims often find no chapter
    (unchanged from T17); a narrower query (PICO terms) would help.
## 7p. Upload Safeguards and Signed Uploads (T20, no issue; design §1, §15)

- **Signed flow (new, always on):** `POST /v1/videos/uploads` `{filename, size_bytes?,
  content_type?}` checks the declared type/size, the per-user rate limit and spends one unit
  of the daily quota (each URL lets the caller write one object), then returns a Supabase
  signed upload URL for `uploads/<sub>/<upload_id hex32>/<sanitised filename>`.
  `POST /v1/videos` `{storage_key, filename?}` refuses keys outside the caller's prefix with
  404 (same as missing, §15), downloads the object once, runs T10's `validate_media`
  (size, sniffed container, extension/content agreement, truncated-MP4 check) and the
  duration limit, hashes it and registers the video (`file_path = storage_key`; the worker
  already downloads by `storage_key`). A known SHA-256 returns the earlier video with
  `duplicate: true` and the new copy is deleted; a rejected file is deleted too.
- **Legacy `POST /videos/upload`:** unchanged unless `UPLOAD_SAFEGUARDS=true` (default off).
  With it on: rate limit, media + duration checks, then quota; response shape unchanged.
- **Error codes:** `InputRejected.code` in `detail.code`: 413 `file_too_large`; 415
  `unsupported_media`/`media_mismatch`; 422 `empty_file`/`corrupt_media`/`too_short`/
  `too_long`; 429 `rate_limited`/`quota_exceeded`. 501 when the backend is local (no signed
  URLs), 503 when storage can't sign.
- **Duration:** read from the MP4/MOV `mvhd` box in pure Python; WebM/MKV via `ffprobe`
  (in the image). Unreadable duration = `corrupt_media` (a file ffprobe can't read isn't
  worth a worker).
- **Deviation from §1:** the doc says large files never pass through the API; registration
  still downloads the object into the API once to check and hash it (§1 step 3 needs the
  hash). Up to 100 MiB in memory per request; a streaming hash or a storage-side check is
  the fix if that matters.
- **Routes live under `/v1`** (§17); the existing routes have no prefix and are unchanged.
- **Left for a person:** (1) `videos` has no owner column, so a duplicate on register (and
  on the legacy route, as before) returns another user's `video_id`: §15 per-object
  authorization needs an owner column + migration. (2) Rate limiter and quota are
  in-process (T10): with N API workers the effective limit is N x the configured one;
  move to Redis. (3) Uploaded-but-never-registered objects aren't cleaned up; add a
  bucket lifecycle rule or sweeper. (4) The bucket must be private with the service key
  only on the server; check in Supabase. (5) `app.main` imports the async health check,
  which needs `greenlet` (not in requirements; tests mount the video routers alone).

## 7t. Backend CI (T23, no issue; design §14, §16)

- **Workflow:** `.github/workflows/backend-tests.yml` runs `python -m pytest` in `backend/` on
  every PR to `langgraph-build` and `main` (plus manual `workflow_dispatch`). Python 3.11 to
  match `backend/Dockerfile`. No repository secrets, no model API keys; `permissions:
  contents: read`. Actions are pinned to commit SHAs (checkout v4.2.2, setup-python v5.6.0).
- **Postgres:** a `pgvector/pgvector:0.8.0-pg16` service. Two throwaway databases:
  `library_test` (`LIBRARY_TEST_PG_DSN`, psycopg 3 SQLAlchemy URL) and `checkpoint_test`
  (`LANGGRAPH_TEST_PG_DSN`, plain libpq URL). Separate because the library test drops its
  database's `public` schema, which would take the checkpointer's tables with it.
- **Every optional test runs:** apt installs `redis-server`, `tesseract-ocr` and `ghostscript`;
  pip installs `requirements.txt`, `-e ".[test]"` and `ocrmypdf` on its own (the `[library]`
  extra would also pull torch and transformers, which no test needs). That un-skips the MCP
  Redis test and the four library OCR tests as well as the three Postgres tests.
- **Zero skips enforced:** a final step reads the JUnit report and fails the run if any test
  skipped, so a missing service or package can't quietly switch these tests off again. A
  new test that legitimately needs something CI lacks must add it to the workflow.
- **`backend/*.egg-info`** is no longer tracked (it was committed before the `*.egg-info/`
  ignore rule existed). Eleven `__pycache__/*.pyc` files are still tracked the same way and
  get dirtied by any local test run; left for a follow-up since T23 only covered egg-info.

## 8. Team

| Person | Current issue | Notes |
|---|---|---|
| Automated build (T02) | #29 LangGraph skeleton | Taken over from Jared by decision of the project lead (2026-11-21); merged into `langgraph-build` |
| Pranav | #31 Retrieval planning and PubMed evidence retriever | Issue assignee. The automated build (T03) built and merged the code into `langgraph-build` on 2026-11-22; the live 10-claim evidence sample is still open (§7d) |

**Update this table as issues are picked up**; this file is the source of truth for who
owns which issue.

## 9. Superseded Plan

The original proposal (an AutoGen group chat with Extractor, Verifier, Critic and a
Coordinator, triggered only below 0.60 confidence) was replaced by the LangGraph design.
The issues that tracked it (#14, #15, #16, #19, #20, #21) are closed; each links to its
replacement.

## 10. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

- **2026-11-23**: T23 (no issue; design §14, §16) backend CI by the automated build:
  GitHub Actions on PRs to `langgraph-build`/`main` with a pgvector Postgres service, Redis
  and OCR tools, failing on any skipped test; `backend/*.egg-info` untracked. Locally on a
  fresh Python 3.11 env with Postgres 16 + pgvector: 952 passed, 0 skipped (was 945 passed,
  7 skipped without the services). Decisions in §7t.

- **2026-11-23**: T19 (no issue; design §6) production reference retrieval by the
  automated build. Bookshelf now goes through E-utilities only (ESearch/EFetch on
  `db=pubmed` with `booksdocs[filter]`, because `efetch db=books` returns no text: checked
  live). CDC pages are `retrieval: stored`: committed, versioned snapshots
  (`data/reference_snapshots/`, 3 CDC pages captured 2026-11-23), cited by snapshot hash
  with the same `ref_<hash>` rule, refreshed by `scripts/refresh_reference_snapshots.py`.
  Fixed the passage stemmer and added short-paragraph windows for real CDC text. 903
  passed, 8 skipped. Details in §7q.
- **2026-11-23**: T21 (#35; design §9, §11) by the automated build: the judge collects
  review reasons (`denies_supported`, `possible_debunk`) from every claim, not only when
  their rule decides the label, so v68/v70-style videos (NO_MISINFO plus a refuted claim the
  evidence can't settle) go to review again. Mixed videos stay MISINFO and are always
  reviewed. Labels unchanged. Judge tests updated; full backend suite passes. Details in §7h.
- **2026-11-23**: T20 (no issue; design §1, §15) upload safeguards by the automated build:
  T10's input limits wired to uploads (`app/services/upload_service.py`), signed-upload
  endpoints `POST /v1/videos/uploads` and `POST /v1/videos`, legacy route unchanged unless
  `UPLOAD_SAFEGUARDS` is on. Storage mocked in tests. Decisions and open items in §7p.

- **2026-11-22**: T18 (no issue; design §13, §14) first real-model smoke run by the
  automated build: graph (references on) and baseline on 10 golden-set transcripts,
  **$6.66 spent** in total. Graph median $0.41 and 76 s per video, against $0.0026 and
  1.5 s for the baseline. Found and fixed 7 integration bugs, each with tests; the
  first two would have made every graph run fall back. Recorded real PubMed fixtures and
  verified references live. No accuracy numbers (labels still under review).
  Details in §7o.

- **2026-11-22**: T17 (no issue; design §4, §6) built by the automated build:
  `claim_kind` on every claim (model via `extract_v2`, fixed rules as fallback);
  allow-listed authoritative references (config catalogue + NCBI Bookshelf) searched
  alongside PubMed for facts of record, cited as `ref_<hash>` with stored text snapshots
  (migration 0009); references rank first for facts of record; `verify_v2` states the same
  verdict rules for references. Behind `USE_REFERENCE_SOURCES` (default off). Synthetic
  fixtures only; catalogue URLs not fetched. Decisions in §7n.
- **2026-11-22**: T16 (#35) judge updated to the revised §9 rules by the automated build:
  REFUTES + SUPPORTED → MISINFO (`refuted_supported`, always reviewed via
  `denies_supported:<cid>`); REFUTES + MIXED/INSUFFICIENT → CANNOT_RECOGNIZE
  (`refuted_unsettled`, `possible_debunk:<cid>`), checked after NO_MISINFO per the doc's
  order; `Decision.rule_review_reasons` returns the rule's reasons. Eval `judge_label` and
  per-claim `claim_label` aligned. Decisions in §7h. Needs Pranav's agreement with the rest
  of the §9 policy.

- **2026-11-22**: T11 (#38) integration built by the automated build: `GraphProvider`
  behind `USE_GRAPH_PIPELINE` (default off; single-call path unchanged), graph on every
  video when on, fallback to the single call on exception / timeout / no result /
  unreachable extractor / all later model calls failing, recorded on the result. Real
  claim extractor (`extract_v1`), Anthropic/OpenAI clients for the router, migration
  0008 with §17's claim-level tables, idempotent persistence and resume per job, API and
  job page serve both paths and `REVIEW_REQUIRED`. Mocked models and synthetic PubMed
  fixtures only. Decisions in §7m.
- **2026-11-22**: T13 retrieval MCP server built by the automated build (no issue; design
  §6, §15): `app/mcp_server` wraps `app.core.retrieval` with the five §6 tools over
  Streamable HTTP (MCP SDK 2.x `MCPServer`), hashed per-client bearer tokens with one scope
  per tool, a Redis token bucket for the shared NCBI quota plus per-client shares, the
  shared Redis query cache, call/size/timeout limits, and a schema contract snapshot checked
  in tests. Not deployed; the pipeline doesn't use the shared bucket yet (T11). Decisions in §7l.
- **2026-11-22**: T12 offline library fallback built by the automated build (no issue;
  design §6): manifest CSV upload, OCRmyPDF/Tesseract + PyMuPDF with per-page confidence
  and held-back low-confidence pages, SHA-256 and PubMed DOI/PMID dedup, paragraph chunking
  (~400/50, references skipped), MedCPT embedder (config-named, lazy), pgvector tables
  (migration 0006, HNSW cosine + GIN full-text), hybrid search with RRF, and the fallback in
  `rerank_evidence` behind an injected `library` (off by default) with new state field
  `library_evidence`. Tested on generated sample scans and a local Postgres + pgvector only.
  Decisions in §7j.
- **2026-11-22**: T07 (#34) critic built by the automated build: code checks plus a
  forced `record_critique` call on the routed `critique` step (prompt `critic_v1`).
  Budgets stay in routing; exhausted claims are now frozen (not re-verified or
  re-reviewed) and abstain (INSUFFICIENT_EVIDENCE for the judge) as well as going to
  review. 16-claim synthetic set: code-only defect detection 0.50, unnecessary retries
  0.00; LLM run waits for API keys. Decisions in §7i.
- **2026-11-22**: T09 (#36) validation and review routing built by the automated build:
  eight §10 checks in code (schema, citation and quote membership, source IDs, merge
  plausibility, timestamps, label consistency, length limits), one repair by re-running
  the judge with the template explanation, then review; the §11 review rule as named,
  separately tested rules (plus high-risk-uncertain from the issue; abstentions caused
  by weak evidence now go to review); `REVIEW_REQUIRED` job state and a `human_reviews`
  table (migration 0007) with reasons and reviewer decisions. Decisions in §7k.

- **2026-11-22**: T08 (#35) judge built by the automated build: the §9 rules as code
  (`decision_rule` recorded), citations limited to IDs in state, code-detected review
  flags for mixed videos, unclear stance on a false claim, false claims quoted but not
  refuted (T10's finding), mixed evidence and verifier failures; the LLM only writes the
  explanation and is checked against the label. `to_classification_result()` maps onto
  `ClassificationResult` for T11. Policy needs Pranav's agreement. Decisions in §7h.

- **2026-11-22**: T06 (#33) evidence verifier built by the automated build: forced
  `record_verdict` tool call through the routed `verify_claims` step, prompt `verify_v1`
  fenced with T10's builders, invalid citations reject the answer (one repair, then
  INSUFFICIENT_EVIDENCE + review), no evidence → INSUFFICIENT_EVIDENCE without a model
  call. 20-claim synthetic, self-labelled set; heuristic floor macro F1 0.87 (inflated by
  construction); LLM run waits for API keys. Decisions in §7g.

- **2026-11-22**: T05 (#32) reranker built by the automated build: deterministic lexical
  relevance over the claim's PICO frame, plus a study-type lookup kept as a separate
  quality score; threshold 0.4, cap 10; real `rerank_evidence` node. On a 12-claim
  synthetic, self-labelled set, precision@5 is 0.53 vs 0.38 for PubMed order (ceiling
  0.58). Real-data labels are left for a person. Decisions in §7f.

- **2026-11-22** (T10, automated): Built the guardrails (`backend/app/core/guardrails/`,
  `backend/config/guardrails.yaml`): fencing and neutralising of untrusted text, a narrow
  injection detector feeding the review policy, `GuardedRouter` with strict output schemas and
  citation checks, the PubMed tool gateway and HTTP allowlist, and input limits (not yet
  wired). Committed a 34-case adversarial set with expected outcomes
  (`research/adversarial/adversarial_v1.yaml`) and a harness that runs it on the guarded graph
  and today's single-call classifier: 5 vs 23 unsafe out of 34 with a simulated, always-fooled
  model. Next: real nodes adopt the builders and router (T03–T09), T08 judge policy on
  QUOTES/UNCLEAR, a held-out red-team set, and a paid run (T14). Decisions in §7e.

- **2026-11-22**: T04 (#30) stance analyzer built by the automated build: forced
  `record_stance` tool call through an injected router, versioned prompt `stance_v1`,
  invalid output → UNCLEAR, every stance cites an input segment, confidence left empty.
  27-example test set with debunk recall reported separately; keyword floor 0.78 debunk
  recall, LLM run waits for API keys. Decisions in §7c.

- **2026-11-22** (T01, automated): Built the evaluation framework (`backend/app/evaluation/`:
  dataset loader with versions, hashes, by-video splits, hard-case coverage and Cohen's kappa;
  per-step metrics; tracked failure modes; run records; baseline comparison) and the
  config-driven model router with retry/fallback (`backend/app/core/routing/`,
  `backend/config/routing.yaml`), plus a per-step model-selection harness. Everything is tested
  with mocks; no paid runs. Next: paid baseline run and routing decision once API keys and
  labelled data exist (T14).
- **2026-11-22**: T03 (#31) retrieval built by the automated build: rule-based PICO
  planning with a MeSH lexicon and a narrow-to-broad query ladder; PubMed ESearch
  (`sort=relevance`) + EFetch abstracts; PMID/DOI dedup; query and per-PMID cache
  (in-memory or Redis); shared rate limiter and tenacity backoff; real
  `plan_retrieval` / `retrieve_evidence` nodes and an automatic broadening edge after
  an empty search. 57 new tests on synthetic fixtures in NCBI's format (no network).
  NCBI is unreachable from the build environment, so the live 10-claim sample still
  needs a person to run `scripts/record_pubmed_fixtures.py`. Decisions in §7d.
- **2026-11-22**: T02 (#29) LangGraph skeleton built by the automated build: typed,
  versioned `PipelineState`; 16 stub nodes; conditional edges for no-claims, critic
  decisions and the review policy; run-time field-ownership check; InMemorySaver and
  Postgres checkpointers. 39 graph tests; the resume test passed on InMemorySaver (also
  under strict msgpack) and once on a local Postgres 16. Not yet run against the Supabase
  `langgraph` schema (needs the #47 login). Decisions in §7a.
- **2026-10-28**: Moved the track to the LangGraph architecture. Added
  `docs/architecture.md`, opened #29–#39, closed the superseded issues, and rewrote this
  file (#43, #44).

## 11. PR Requirements

- All code goes up as PRs, using `.github/ISSUE_TEMPLATE/multi-agent.md` for the
  originating issue.
- Reference the GitHub issue (`Closes #N`).
- Update this file as decisions are made (who owns which issue, trigger decision, budget changes),
  so it reflects the *current* design.
