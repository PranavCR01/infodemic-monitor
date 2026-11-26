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
## 7s. Judge Cross-Check Against the Golden Set (T24, no issue; design §9, §14)

- **What is compared.** The backend judge (`judge.decide`, then the review rule
  `review_policy.evaluate`) and the golden set's own `scripts/judge.py` (`judge`,
  `review_reasons`, branch `data/golden-label-set` @ 45244b0) on the same claim-level
  inputs: recorded stance, verdict and cited evidence IDs. No model calls.
  Code: `backend/app/evaluation/judge_crosscheck.py`; script
  `backend/scripts/judge_crosscheck.py` (reads the branch with `git show`, never checks it
  out); test `app/tests/test_judge_crosscheck.py`.
- **Offline fixture.** The golden `judge.py` is vendored verbatim
  (`app/tests/fixtures/golden_judge/judge.py`, git blob sha checked by the test) with a
  claim-level JSON fixture (no claim text, transcripts or media). A freshness test
  compares it with the branch commit when that commit is available locally and skips
  otherwise. Regenerate with `--write-fixture`.
- **One reason vocabulary.** Both sides' review reasons are mapped to
  `<kind>[:<claim_id>]` (table in the module docstring). Backend reasons whose signals a
  hand-labelled set can't carry (critic, validation, budget, calibrated confidence, study
  type, high-risk category, guardrails) are left out of the comparison.
- **Result.** Same video label on 82/82 videos (66 in scope, 16 out_of_scope) and the
  same deciding claims on 66/66. Review reasons agree exactly on 48/66; the 18 others
  differ in four classified kinds, all on review reasons only. Three match §9/§11 on the
  backend side (reasons collected from every claim, MIXED as a trigger on any claim, no
  `deciding or claims` fallback for UNCLEAR/conflict); one (`weak_evidence` on
  non-deciding uncertain claims in the possible-debunk case) is a documented backend
  extension that §11 doesn't state, left for the project lead. The backend never drops a
  review the golden judge asks for. **No backend change**: nothing in it contradicts §9.
- **Why the golden judge differs.** It transcribes §9's pseudocode, whose third return
  value holds only the deciding rule's reason; §9's prose says reasons are
  collected from every claim and mixed videos are always reviewed. The pseudocode and prose
  in §9 should be reconciled by a person (not edited here).
- The test pins the difference counts per kind, so a change to either judge that adds or
  removes a difference fails until it's reclassified.
## 7r. Severity for Review Priority (T22, no issue; design §11, §12)

Built by the automated build on 2026-11-23 (project lead's decision). Severity orders the
review queue; it never changes a label, verdict, proposed result, reviewer decision or
job state (tested).

- **Table:** `backend/config/severity.yaml`, `status: draft`, `version: severity_v0_draft`,
  with `sign_off` flags for the project lead, Dr. Brooks and WHO all `false`. The loader
  (`app/core/graph/severity.py`) refuses `status: approved` unless all three are true.
  Not for real triage until signed off.
- **Seeding:** every category in `review_policy.yaml` `high_risk_categories` (T09) is
  HIGH (a test keeps them in sync). The extractor's other categories: safety, prevention,
  causation, diagnosis, nutrition MEDIUM; statistic, other LOW.
- **"Topic" is keyword matching on the claim text** (whole words, `*` = rest of word),
  because there is no topic field and the extractor's categories are too broad
  ("causation" covers "the MMR causes autism"). Topics: cancer, vaccines,
  medication/doses, pregnancy and children, self-harm and eating disorders (HIGH);
  supplements and detox (MEDIUM). A claim's severity is the highest of its category and
  every matching topic. Weakest part of the design: keyword lists miss paraphrases and
  over-fire (e.g. "children" in a harmless claim). Owners should review them.
- **Unmapped category → MEDIUM** (`default_severity`), not LOW: an unknown category
  shouldn't be buried at the bottom of the queue.
- **Known over-ranking:** `treatment_efficacy` is HIGH because T09 put it in the
  high-risk list, so "hot water soothes a sore throat" ranks HIGH. Left as seeded; the
  owners decide.
- **MISINFO-relevant claims** (video severity = highest among them): endorsed +
  CONTRADICTED; endorsed + MIXED / INSUFFICIENT_EVIDENCE / NOT_VERIFIABLE (same
  "uncertain" set as `high_risk_uncertain`); **and refuted + SUPPORTED** (speaker denies
  a supported claim). The last is a deviation from §12's parenthetical, which lists only
  endorsed claims; §9 makes that case MISINFO, and leaving it out would give "vaccines
  don't prevent measles, that's a lie" no severity. Verdicts are the judge's view
  (`routing.verdicts_for_judge`), as in the review rule.
- **No relevant claim → severity null**; the queue puts null after LOW.
- **Storage (migration 0010):** `human_reviews.severity` (indexed), `claim_severities`
  (per claim: table severity, basis, stance, verdict, relevant, override),
  `severity_table_version`; new `audit_events` table (§17). Per-user isolation, planned
  as 0010, moves to 0011. Not run on Supabase.
- **Service (`app/services/review_service.py`):** `open_review_case` stores severity;
  `review_queue` sorts severity (HIGH, MEDIUM, LOW, null) then `created_at` oldest first;
  `override_claim_severity` needs a reviewer and a reason, keeps the table value next to
  the override, recomputes the video severity and writes an `audit_events` row
  (`action=severity_override`, from/to, video before/after, table version);
  `severity_overrides` reads the log. Overrides are allowed on resolved cases (the log is
  for correcting the table) and survive a refresh of an open case.
- **Not built:** no API endpoint or UI for the queue or overrides (none exist for review
  yet), no alerts (§12 mentions severity ordering alerts; there is no alerting).

## 7u. Review HTTP API and Roles (T27, no issue; design §12, §15, §17)

- **Routes** (`backend/app/api/routers/reviews.py`, typed Pydantic responses, mounted in
  `app.main`; nothing existing changed): `GET /v1/me` (caller id, server-decided role,
  permission hints); `GET /v1/reviews` (queue: severity HIGH→MEDIUM→LOW→none, then oldest
  first; `status=OPEN|RESOLVED|ALL`, `severity=` HIGH/MEDIUM/LOW/NONE repeated or
  comma-separated, `reason=` rule name, reason prefix or exact reason, `limit` 1–100,
  `offset`; returns `items`, `total`); `GET /v1/reviews/{review_id}` (full case +
  `audit_trail`); `POST /v1/reviews/{review_id}/decision`;
  `POST /v1/reviews/{review_id}/claims/{claim_id}/severity`.
- **Roles** (`backend/app/auth/roles.py`): analyst < reviewer < admin, read only from the
  verified Supabase JWT's `app_metadata.role` / `app_metadata.roles` (writable only with
  the service key). `user_metadata` (user-editable) and the top-level `role` claim
  (Postgres role, e.g. `authenticated`) are ignored; no claim = analyst. No roles table and
  no migration: roles are set in Supabase (`auth.admin.updateUserById(id, {app_metadata:
  {role: "reviewer"}})`). With `REQUIRE_AUTH` off the dev user takes `DEV_USER_ROLE`
  (default analyst).
- **Rules:** every review route needs reviewer or admin (admin ⊇ reviewer; no admin-only
  review action yet). Analysts get 403 before any lookup, so existence isn't revealed.
  The reviewer recorded is always the token's `sub`; request bodies forbid extra fields,
  so a `reviewer_id` or `role` in the body is a 422. Reason required (blank = 422).
  Errors: unknown case 404, decided case 409, unchanged severity 409, claim not in case
  404 (override) / 422 (correction), bad body 422.
- **Decisions:** APPROVE, CORRECT (`corrected_label` and/or `claim_corrections`
  `[{claim_id, verdict?, stance?}]`, values from the §5/§7 enums, each must change
  something), MARK_INSUFFICIENT, REJECT, REQUEST_REANALYSIS. Claim corrections are stored
  on the case as `{"claims": {cid: {"verdict"|"stance": {"from", "to"}}}}`; the model's
  stored stance/verdict rows are not overwritten (provenance; §12 feedback loop). Changing
  claim verdicts does not recompute the label: the reviewer sets `corrected_label`.
  REQUEST_REANALYSIS starts a new PENDING job for the same video through the worker
  (dispatcher injectable); a failed dispatch leaves that job FAILED/`DISPATCH_FAILED` and
  the decision stands. The old job keeps REVIEW_REQUIRED (T09 behaviour).
- **Service changes** (`review_service`): `record_review_decision` now locks the row
  (`SELECT … FOR UPDATE` on Postgres) so two reviewers can't both resolve a case, and
  writes a `review_decision` audit event; new `review_queue_page`,
  `build_claim_corrections`, `review_audit_trail`, `start_reanalysis`. The reason filter
  runs in Python (reasons are a JSON list); fine at current queue sizes, move to SQL
  (Postgres JSON operators) if the queue grows large.
- **Tests:** `test_review_api.py`, 85 tests, real HS256 JWTs with a test secret through the
  real `get_current_user`; each runs on SQLite and, when `LIBRARY_TEST_PG_DSN` is set (CI),
  on a throwaway Postgres database.
- **Left for a person:** (1) per-user ownership still doesn't exist: `videos` has no owner
  column, and the existing `/jobs/*` and legacy routes don't check ownership (§15, §17
  "every endpoint checks the object belongs to the caller"). T28's migration 0011 adds
  `jobs.user_id`; the coordinating session also asked T27 for owner columns, which would
  have duplicated it, so T27 adds none. Suggested follow-up: 0012 `videos.owner_id`, read
  checks with reviewer/admin exceptions, and `submitted_by` on review responses
  (`decided_by` is already `decision.reviewer_id`). Until then a reviewer could decide a
  case on their own video. (2) Assign
  reviewer/admin roles in Supabase `app_metadata`. (3) After REQUEST_REANALYSIS the old
  job still reads as "in review" on the legacy result route; T26's resolved status should
  cover it. (4) Admin-only actions (e.g. reopening a case) aren't defined in the doc.
## 7v. Result API Fields (T26, no issue; design §12, §17)

Built by the automated build on 2026-11-24, from the frontend session's API map. Exposes
data already stored but not returned. Additive: every existing field keeps its name and
shape; no label, verdict or stored row changes.

- **Where:** `GET /jobs/{job_id}/result` (existing, now `response_model=JobResultResponse`)
  gains the fields; new §17 reads in `app/api/routers/results.py`:
  `GET /v1/videos/{video_id}/results` (same body, caller's latest job on the video),
  `GET /v1/videos/{video_id}/claims`, `GET /v1/claims/{id}/evidence` (`id` = the claim's
  stable row id, returned as `claims[].id`; graph claim ids like `c1` are only unique per
  job). Models in `app/api/result_models.py`; builders in
  `app/services/result_view_service.py`. `claim_level_view` now uses the same builder.
- **New fields:** claims: `id`, `claim_kind`, `requires_verification`,
  `source_segment_ids`, `modality` (speech / screen / both, from which stored segment table
  holds each id, falling back to the `t*`/`o*` naming), `stance_rationale`,
  `stance_segment_ids`, `stance_quotes` (the stored segments those ids name, with
  timestamps: "the words behind" the stance), `retrieval_attempts`, `critic`
  (decision, issues, requires_review), `severity` (effective, table value, basis,
  override). Evidence: `source_kind` (pubmed / reference / library / other), `doi`,
  `year`, `publisher`, `publication_type`, `abstract_snippet` (300 chars at a word
  boundary), `relevance_score`, `rank`, `retrieved_at`, `snapshot_sha256`. Result:
  `video_id`, `status`, `pipeline_version`, `decision_rule`, `deciding_claim_ids`,
  `transcript_segments`, `ocr_segments`. Review: `review_id`, `case_status`, `resolved`,
  `action`, `reason_details`, `rules_fired`, `severity`, `claim_severities`,
  `severity_table_version`, `proposed_label`, `corrected_label`, `decision_reason`,
  `created_at`, `decided_at`.
- **`review` no longer becomes null once resolved.** `status` is `REVIEW_REQUIRED` while
  open (unchanged), then APPROVE → `VERIFIED`, CORRECT / MARK_INSUFFICIENT → `CORRECTED`,
  REJECT → `REJECTED`, REQUEST_REANALYSIS → `REANALYSIS_REQUESTED`. The current frontend
  showed its "awaiting human review" banner whenever `review` was set, so its check is now
  `result.review?.status === "REVIEW_REQUIRED"` (one line in `JobDetailClient.tsx`).
- **Reasons:** `reasons` stays the stored strings (the current frontend prints them);
  `reason_details` is `{code, rule, claim_id, detail, text, raw}` with `text` from
  `REASON_TEXT` in `app/services/review_reasons.py`, the one wording table for every
  rule, judge flag and guardrail code; unknown codes get a generic sentence. The judge's
  own `_FLAG_TEXT` (used inside explanations) is left alone so explanations don't change.
- **Ownership (§15, §17): a seam, not a column.** The queue (2026-11-24) gave the owner
  column to T27 and told T26 not to add one. A first version of T26 added `jobs.user_id`
  (migration 0011) before that note was seen; it was removed before the PR. Every T26 read
  (`GET /jobs/{id}`, `GET /jobs/{id}/result`, the three `/v1` reads) now goes through
  `app/api/ownership.py` (`can_view_job`, `visible_jobs`, `owned_job_or_404`), which today
  checks only auth + existence and answers 404 for anything the caller may not see. T27
  fills in those two functions (owner, or reviewer/admin; legacy NULL rows admin only) and
  every T26 endpoint follows. A test plugs in a rule and checks each endpoint gives 404.
- **Rejected results:** the legacy route still answers 202 for a FAILED job, as before;
  `/v1/videos/{id}/results` shows a reviewer-rejected result (`error_code =
  REVIEW_REJECTED`) with its review, answers 202 while pending and 409 for other failures.
- **Not exposed on purpose:** the reviewer's id (in severity overrides and on the case);
  the audit trail and reviewer access are T27's.
- **Left for a person / other tasks:** (1) T27: implement `can_view_job` / `visible_jobs`
  with its owner column and roles (until then any signed-in user can read any job, as
  before T26); (2) the reason wording is a draft for the project lead to edit (one table,
  `REASON_TEXT`). No migration in T26.

## 7z. Unproven-Claim Verdict (T30, decision D1 = B; design §7, §9, §11, §12)

Built by the automated build on 2026-11-23 (queue date 2026-11-24). Additive: the four
labels are unchanged; existing responses keep every field.

- **Where UNSUPPORTED comes from.** `Verdict.UNSUPPORTED` is new. Code decides when it is
  possible, the model only proposes it: `routing.unproven_eligible` = the claim's
  `claim_category` is `treatment_efficacy` or `prevention` (`routing.UNPROVEN_CATEGORIES`)
  **and** no plan/retrieve/rerank error was recorded for it (an outage must never read as
  "nothing was found"). For an eligible claim with no evidence at all the verifier sets
  UNSUPPORTED without a model call; with papers, `verify_v3` lets the model answer
  UNSUPPORTED (cite nothing). For any other claim the instructions say it is not allowed
  and a model UNSUPPORTED is stored as INSUFFICIENT_EVIDENCE.
- **"Full retrieval budget", read literally.** §6 only broadens a search on *empty*
  results, so a claim whose first search returned off-topic papers would otherwise be
  called unproven after one round. The critic's code checks now ask RETRIEVE_MORE for an
  UNSUPPORTED verdict while search rounds are left (`code:search_budget`), so the
  existing loop runs the remaining broader searches. `routing.verdicts_for_judge` then
  passes UNSUPPORTED to the judge only if `unproven_allowed` holds (eligible, nothing
  cited, `retrieval_attempts >= max_retrieval_attempts`); otherwise the judge sees
  INSUFFICIENT_EVIDENCE with a limitation saying why. An UNSUPPORTED claim whose critic
  still wanted more search when the budget ran out keeps its verdict (it is exactly "the
  full search found nothing") instead of abstaining. Cost: up to two more PubMed rounds
  and verifier/critic calls per such claim.
- **Judge.** New rule `unproven` (the `decision_rule` value the frontend adapter expects) after `refuted_supported`, before DEBUNKING:
  MISINFO with `misinfo_basis = unproven`, review reason `unproven_claim:<cid>` from
  every such claim whichever rule wins, `mixed_video` also for unproven + refuted-false.
  `FinalClassification.misinfo_basis` (contradicted / denies_supported / unproven) is set
  for every MISINFO. Per-claim label (`claim_label`) ENDORSES + UNSUPPORTED → MISINFO.
- **Deviation from §9's pseudocode:** `refuted_open` also includes UNSUPPORTED. A speaker
  refuting an untested cure is the clearest possible debunk; leaving it out would drop
  the `possible_debunk` flag such a claim raised as INSUFFICIENT_EVIDENCE before T30. It
  only adds review; labels are as the pseudocode gives them.
- **Review (§11):** UNSUPPORTED joins `UNCERTAIN_VERDICTS`, so `weak_evidence` fires on
  the deciding claim and every "MISINFO (unproven)" video is reviewed (also via
  `judge:unproven_claim`). Severity counts ENDORSES + UNSUPPORTED as MISINFO-relevant.
- **Stored and returned:** `results.misinfo_basis` (migration **0013**, nullable; chained to 0010 until T28's 0011 and T31's 0012 merge, then `down_revision` becomes "0012"). `GET
  /jobs/{id}/result` and `GET /jobs` add `misinfo_basis` and `label_display` ("MISINFO
  (unproven)", "CANNOT RECOGNIZE"...) from `schemas.pipeline.display_label` (kept out of
  the graph package so the jobs list doesn't import LangGraph). `label` is unchanged.
- **Wording (frontend finding):** the judge's template no longer starts with label/enum
  names ("CANNOT_RECOGNIZE:") or names claims by ID; claims are "the first claim" (by
  extraction order) plus their text where they decide the label. Review notes in the
  explanation use the same names. Unproven text: "no evidence supports this claim", never
  "false". `explain_v2` tells the model the same rules, and `check_explanation` rejects a
  model text with enum names, claim IDs, or "false" for an unproven label (template used).
  Limitations (`c1: ...`, "Not judged: INSUFFICIENT_EVIDENCE c2") were left as they were.
- **Review-reason text (queue row, added during the build):** `reason_details[].text`
  (`app/services/review_reasons.py`) says "this claim" instead of a claim ID (the UI adds
  the number from `claim_id`); `GENERIC_TEXT` is a plain sentence with no rule code;
  validation and guardrail texts no longer show check or node names, and the
  prompt-injection text names the place in plain words ("the speech transcript"). The
  internal names stay in `detail` and `raw`. New text for `unproven_claim`.
- **Prompts:** `verify_v3`, `explain_v2` (routing.yaml updated); v2/v1 files kept.
- **Eval data:** two synthetic UNSUPPORTED examples (v21, v22) added to the verifier set
  so it covers every verdict; heuristic baseline regenerated (the floor never answers
  UNSUPPORTED). `metrics.VERDICTS` and `dataset.CLAIM_TRUTHS` accept UNSUPPORTED.
- **Judge cross-check (T24), re-pinned to the golden set @ 022ac44** (D1 re-derivation,
  at the coordinating session's request): fixture and vendored `judge.py` regenerated with
  `scripts/judge_crosscheck.py --write-fixture`. The harness reads the new golden judge
  (4 return values, `<kind>:<cid>` reasons) and old one, carries `claim_category`, treats
  golden verdicts as final (full search done), and now compares `misinfo_basis` too.
  Result: 181 videos (162 in scope); label, basis and deciding claims agree on all 162;
  33 MISINFO on both sides (25 contradicted, 7 unproven, 1 denies_supported). Remaining
  differences are backend-only review reasons: `weak_evidence_on_non_deciding_claim` (77
  reasons, 35 videos; the documented D4 extension) and the new
  `weak_evidence_covered_by_judge_reason` (17 / 8: §11's weak-evidence trigger on a
  deciding UNSUPPORTED or MIXED claim, which the golden judge covers with its
  `unproven_claim` / `mixed_evidence` reason). The refuted-UNSUPPORTED possible-debunk
  deviation does not occur in the golden set; it is pinned by a synthetic test.
- **`decision_rule`:** the new rule's value is `"unproven"`, the string the frontend
  adapter expects (the constant is still `RULE_ENDORSED_UNSUPPORTED`).
- **Left for a person:** (1) migration 0013 follows 0010 until #81 (0011) and #84
  (0012) merge; then set its down_revision to "0012" (pointing at "0012" now would break
  `alembic upgrade head` and CI on this branch); (2) the frontend should show
  `label_display`; (3) whether limitations should also drop claim IDs.
## 7y. Request Review (T32, no issue; design §11, §12, §17)

Built by the automated build on 2026-11-24 at the frontend session's request (lead, D7).
Additive: no migration, no existing field or response changes shape.

- **Route:** `POST /v1/jobs/{job_id}/review-request` with body `{"note": "..."}` (in
  `app/api/routers/reviews.py`; service `review_service.request_review`). 201 with
  `created: true` when a case is opened; 200 with `created: false` and the existing case
  when the job already has one (opened by the review rule or by an earlier request, open
  or resolved); nothing is logged or changed on that path, and the first request's note
  stands. Keyed by job, not video: the result payload already carries `job_id`.
- **Who:** anyone who may read the job through `app/api/ownership.owned_job_or_404`
  (owner, or reviewer/admin, per T27/T33), else 404, same as a missing job. No separate
  role check in the route, so T28/T33's owner rule (including "NULL-owner rows admin only")
  applies here unchanged. **Until T28/T33 fill in `can_view_job`, any signed-in user can
  request review on any job**: same gap as every other read.
- **Note:** required, stripped, 1–2000 characters (`REQUEST_NOTE_MAX`); the body forbids
  extra fields, so the requester can't be named in it. Stored as the `reason` of a
  `review_requested` audit event (actor = token subject, requester role, job status
  before, proposed label). No column was added for it: reviewers get it as
  `request {requested_by, note, requested_at}` on `GET /v1/reviews/{id}` (null for
  rule-opened cases) and in the audit trail.
- **Which jobs:** status SUCCESS with a stored result; anything else (pending, running,
  failed, no result) is 409. The job moves to REVIEW_REQUIRED (§12: review is a state),
  so the reviewer decision flow from T27 works unchanged (approve/correct → SUCCESS, etc.).
  The label and verdicts are not touched.
- **The case:** reason `user_requested` (rule `user_requested`; `rule_of` maps it, but it
  is not in `REVIEW_RULES`: no automatic rule raises it). Proposed result = the stored
  result row (`source: "stored_result"`), since there's no graph state to dump. Severity
  is computed from the stored claim/stance/verification rows with the same table as
  `assess`, so the case sorts in the queue like any other and claims can be overridden;
  no claim rows (single-call path) → no severity. An unknown stored verdict counts as not
  MISINFO-relevant rather than erroring.
- **Wording:** `REASON_TEXT["user_requested"]` = "Someone asked for a person to check this
  result." (plain, no rule code; T30 is reworking the rest of that table).
- **Race:** two concurrent first requests: the unique `human_reviews.job_id` makes the
  second insert fail; it rolls back and returns the winner's case.
- **The requester's response** omits the proposed result and audit trail (reviewer data).
## 7x. Signed Playback URL (T29, no issue; design §12, §15, §17)

- **Endpoint:** `GET /v1/jobs/{job_id}/playback` returns `PlaybackUrlResponse`
  (`job_id`, `video_id`, `url`, `expires_in_seconds`, `expires_at`, `filename`) with a
  signed read URL for the job's video. Keyed by job because the result page is a job page
  and duplicate uploads share one video row, so the job's access rule is the one to apply.
  New router `app/api/routers/playback.py`; nothing existing changes.
- **Short-lived:** `PLAYBACK_URL_TTL_SECONDS` (default 600). Long enough to start and seek a
  3-minute video; `expires_at` (computed from a time taken *before* signing, so never later
  than the real expiry) tells the player when to ask again. A fresh URL per request,
  `Cache-Control: no-store`, and the URL is never logged (only the job id). The legacy
  `get_download_url` keeps its 1 h expiry for the worker.
- **Ownership:** every lookup goes through `app/api/ownership.py::owned_job_or_404`, a
  shared with T26 (merged in #76; this branch added the identical file before that merge). A job the caller may
  not see answers 404 with the same body as a missing job and no URL is signed. **Until the
  owner column lands (T28 / T33 per the queue; T27 shipped without it) `can_view_job`
  allows any authenticated user**, so per-user restriction is not enforced in production
  yet; the tests install an owner rule through that hook and prove the route obeys it.
  No owner column added here: the queue gives it to T28 (jobs.user_id) and T33
  (videos.user_id, roles); once they fill in `can_view_job` this route follows unchanged.
- **Errors:** no storage object (legacy local uploads) 404 "No playable video for this
  job"; local storage backend 501; storage failure or empty URL 503.
- **Storage:** `StorageBackend.create_signed_download_url(key, expires_in)`; Supabase via
  `create_signed_url` (accepts `signedURL`/`signedUrl`/`signed_url` or an object);
  `LocalBackend` raises `SignedUrlUnsupported`.
- **Export dropped:** the task brief asked for an export endpoint; the queue row was trimmed
  by the lead (D7, 2026-11-24: the frontend builds the export client-side from the result
  payload), so none was built.
## 7w. "How we searched" per Claim (T31, no issue; design §6, §8, §12)

Built by the automated build on 2026-11-23 (requested by the frontend session; lead
decision D7). Additive: no existing field, label, verdict or retrieval result changes.

- **Recorded during the run, by code.** `retrieve_evidence` now also owns a new state
  channel `search_trail: dict[claim_id, list[SearchRound]]` (in `NODE_OUTPUTS`), one
  `SearchRound` per claim per round: the PubMed query actually run, PMIDs ESearch
  returned, records left after the type/year filters, what the round added after
  PMID/DOI dedup, whether it was served from the query cache, and, in a fact of record's
  first round, every allow-listed reference page / stored snapshot / Bookshelf search
  tried (`ReferenceConsulted`: source id, name, publisher and host from
  `config/reference_sources.yaml`, page id or NBK accession, mode, outcome).
  `ReferenceSearcher.search` reports these as `ReferenceResult.consulted` (new, additive).
  The node only observes: a test runs the whole mocked graph with and without the
  channel and compares queries, evidence, reranking, verdicts, critic, judge and review.
  No `STATE_SCHEMA_VERSION` bump: the field is optional, older checkpoints load.
- **Summarised at persist time** by `app/services/search_trail.py::build_search_trail`
  onto a new nullable JSON column `claims.search_trail` (migration **0012**; T28 #81 owns 0011), in the
  shape `app/core/schemas/search_trail.py::SearchTrailView` (version 1). It is returned on
  every claim (`ClaimView.search_trail`) by `GET /jobs/{id}/result`,
  `GET /v1/videos/{id}/results` and `GET /v1/videos/{id}/claims`; null for claims never
  searched, single-call/fallback results and rows written before 0011. A stored trail
  that no longer parses is returned as null rather than failing the result.
- **Count definitions** (the frontend's "retrieved / screened / kept"):
  `retrieved` = results the searches returned: PMIDs from each distinct PubMed query
  (a repeated query, when the planner's ladder ran out, is flagged `repeat` and not
  counted twice) + reference passages + library passages; `screened` = distinct records
  the reranker scored (after filters and dedup, library included); `kept` = what went to
  the verifier (≤ 10). `budget` = rounds used of `Budgets.max_retrieval_attempts` (3:
  the initial search + 2 reformulations, shared with critic RETRIEVE_MORE rounds, §8),
  `exhausted`, and the 10-paper cap. `library` is null when no library was configured,
  else `{fired, passages}`.
- **Never in the trail:** API keys, E-utilities request URLs (Bookshelf is recorded by
  its chapter pages, not its API calls), prompts, exception messages (a failed PubMed or
  reference search stores the exception type only, since an httpx error message can
  carry the request URL and key). Tests feed a fake key through PubMed and the
  references and check it never appears.
- **Fallback for older checkpoints:** with no per-round record, the trail is rebuilt from
  `retrieval_queries` with unknown per-query counts (`recorded: "queries_only"`,
  `counts.retrieved: null`).
- **Deviations / limits:** the persisted budget uses `DEFAULT_BUDGETS` (the worker never
  passes custom budgets today); query origin (planner rule vs critic suggestion) is not
  recorded; the MCP server's tool outputs are unchanged.
## 7w. Job Progress Events, §1 States and Job Ownership (T28, no issue; design §1, §16, §17)

- **Two state fields, side by side.** `jobs.status` keeps the five values the current
  frontend reads (PENDING, STARTED, SUCCESS, FAILED, REVIEW_REQUIRED); nothing that set
  it changed. New `jobs.state` holds the §1 state (PENDING, QUEUED, RUNNING,
  RETRY_PENDING, REVIEW_REQUIRED, COMPLETED, FAILED, REJECTED). Responses show the stored
  state only while it agrees with `status`, otherwise it is derived from `status`
  (`job_events.effective_state`, same rule in SQL for the filter), so a writer that only
  sets `status` can't leave a stale state. A reviewer's rejection (legacy FAILED +
  `error_code=REVIEW_REJECTED`) reads as REJECTED.
- **When states are written:** PENDING (step `uploaded`) when the job is created; QUEUED
  just before `.delay()` (so a fast worker's RUNNING comes after it; a failed hand-off
  logs PENDING with `dispatch_failed`); RUNNING when a worker starts (`jobs.attempts`
  +1); RETRY_PENDING first when the worker finds the job still STARTED (an earlier worker
  died, Celery redelivered) or Celery reports a retry; COMPLETED / REVIEW_REQUIRED /
  FAILED (with `error_code`) after the existing writes; COMPLETED / REJECTED after a
  review decision (`review_service.record_review_decision`). A re-analysis job
  (`review_service.start_reanalysis`, T27) takes the original job's owner (not the
  reviewer's) and gets its own PENDING/QUEUED (or FAILED on dispatch failure) history. **No retry policy was
  added:** the task still doesn't call `self.retry`; RETRY_PENDING is logged when a retry
  happens. The §1 retry table (backoff on LLM 5xx etc.) is still to build.
- **Steps** (`app/core/progress.py`): uploaded, transcribing, reading_on_screen_text,
  finding_claims, checking_stance, searching_evidence, verifying, final_checks, with
  plain-language labels. The pipeline calls `report_step()`; it is a no-op unless the
  worker installs a reporter (a context variable), and a reporter that raises is logged
  and ignored. Graph path: `GraphProvider.run` now streams with `stream_mode="tasks"`
  (was `"values"`), which yields each node *as it starts* in the calling thread; nodes
  map to steps (`NODE_STEPS`), and the critic's loop moves the stepper back to
  "searching evidence". The final state is still read with `get_state`, so results are
  unchanged (tested: same classification with and without a reporter). Single-call path:
  uploaded, transcribing, verifying (the one model call), searching_evidence (only for
  MISINFO/DEBUNKING grounding); the events response lists the steps that apply
  (`pipeline_steps`). Consecutive repeats of a step are not logged.
- **Recording is best effort:** each event is its own small commit on the worker's
  session; a failed write rolls back and logs. Steps are recorded from the worker's
  thread only (LangGraph's parallel nodes run in a pool, but "tasks" chunks arrive in the
  calling thread).
- **Ownership (§15, §17; PRODUCTION.md §6a):** `jobs.user_id` = JWT `sub` on create.
  On rebase T28's owner check went into T26's `app/api/ownership.py`: `can_view_job` /
  `visible_jobs` / `owned_job_or_404` (T26's names, which T33 extends) now compare
  `jobs.user_id` with the caller's `sub` instead of allowing every signed-in user, so
  T26's result endpoints (`/v1/videos/{id}/results`, `/claims`, `/v1/claims/{id}/evidence`)
  enforce it too; T26's tests now give their jobs an owner, and its "allows authenticated
  callers" test became "owner check is live". 404 for another user's
  job. Applied to GET /jobs, /jobs/{id}, /jobs/{id}/result, /jobs/create's reuse of an
  existing job (only the caller's own job is reused, so two users analysing the same
  video each get a job: deliberate double work over leaking a job id) and the new /v1
  routes. **Jobs created before 0011 have no owner:** hidden from every signed-in user;
  visible only with `REQUIRE_AUTH` off (local dev, one dev user).
- **API (additive):** `GET /v1/jobs/{id}/events` (state, step, attempts,
  `processing_finished` for polling, the 8 steps with labels, `pipeline_steps`, events
  oldest first); `GET /v1/jobs/{id}` (= `GET /jobs/{id}`); `GET /v1/jobs` →
  `{items, total, limit, offset}` with `q` (filename substring, case-insensitive, or
  exact job/video id), `status` (repeat or comma-separated; legacy and §1 values; a value
  in both vocabularies such as PENDING matches the §1 state; unknown → 422) and `label`.
  `GET /jobs` stays a bare list (current frontend) and gains the same `q`/`status`
  params plus an `X-Total-Count` header. Rows and `GET /jobs/{id}` gain `state`, `step`
  (+ `step_label`, `attempts`); all old fields are unchanged. Typed Pydantic models.
- **Migration 0011** (`down_revision 0010`): `jobs.user_id`, `state`, `current_step`,
  `attempts` and the `job_events` table. Checked up/down on SQLite and Postgres 16. Must
  run before this code is deployed (the ORM selects the new columns).
- **Left for a person:** (1) run 0011 on Supabase and assign `jobs.user_id` on old jobs
  (e.g. from upload logs) or they disappear from users' lists; (2) `videos` still has no
  owner (T20's note), so `POST /jobs/create` doesn't check the caller owns the video;
  (3) the §1 outbox (job row + dispatch event in one transaction) and POST /v1/jobs with
  an idempotency key are not built; (4) a real retry policy (§1 table) would make
  RETRY_PENDING more common; (5) the new frontend's stepper should read
  `/v1/jobs/{id}/events`.

## 7z. Per-User Ownership on Every Read (T33, no issue; design §15, §17)

- **Rule** (`backend/app/api/ownership.py`, the only place it lives): a row's owner sees
  it; reviewers see every row that has an owner; admins see everything, including
  legacy rows with no owner; analysts never see other users' rows. Roles come from
  `app.auth.roles` (JWT `app_metadata` only); a token with a role but no `sub` sees
  nothing. Hidden = 404 with the same body as missing. With `REQUIRE_AUTH` off the one
  dev user still sees NULL-owner rows (unchanged from T28).
- **Videos:** migration **0014** adds `videos.user_id` (nullable, indexed, JWT `sub`), set
  by `POST /videos/upload` and `POST /v1/videos`. `can_view_video` = the rule above on the
  video's owner, **or** the caller may see some job on it (so users who shared one video
  row under the old global duplicate check keep their own results; they never see each
  other's jobs). `POST /jobs/create` and `/v1/videos/{id}/results|claims` check the video.
- **Duplicate detection is per user now** (decision): the unique index on
  `videos.file_hash` became a plain index plus unique (`user_id`, `file_hash`). Otherwise
  user B uploading A's file would get A's video id and filename back (a leak) and then a
  404 on starting a job. Cost: the same file uploaded by two users is analysed twice.
- **Lists:** `GET /jobs` and `GET /v1/jobs` return every job the caller may see
  (reviewers/admins see other users' jobs, admins also legacy ones, so production jobs
  don't vanish for the lead) and take `mine=true` for only the caller's own. Rows,
  `GET /jobs/{id}` and `/v1/jobs/{id}` gain `submitted_by` (= `jobs.user_id`). Job reuse
  in `POST /jobs/create` stays strictly the caller's own job (`own_jobs`), so a reviewer
  starting a job on someone's video gets their own job.
- **Results:** `JobResultResponse.submitted_by` on `/jobs/{id}/result` and
  `/v1/videos/{id}/results`.
- **Reviews:** queue (`visible_jobs` joined in `review_queue_page`, totals included),
  case, decision and severity override all check the case's job (404 otherwise).
  Reviewers see cases on owned jobs; admins also legacy ones. Queue items and cases carry
  `submitted_by`; the decider stays `decision.reviewer_id`. **Nobody decides or re-rates
  a case on their own video** (job submitter or video owner), admins included: 403
  (not 404, since they can already read the case); nothing is written.
- **Other routes:** T29's `/v1/jobs/{id}/playback` (merged) and T32's open
  `/v1/jobs/{id}/review-request` call `owned_job_or_404`, so they follow the new rule
  unchanged; both are in the route table and the cross-user matrix. (Checked by merging
  #83 onto this branch: the matrix passes; T32's own tests seed jobs with no owner and
  need `user_id="analyst-1"` in their fixture on rebase.)
- **Migration numbering:** 0012 is T31's (merged, #84); 0013 is reserved by T30 (#86,
  open), so 0014 chains onto 0012 (`alembic heads` = one head). If #86 lands a 0013
  first, set 0014's `down_revision` to "0013". 0014 backfills a video's owner when all
  its owned jobs agree on one user.
- **Legacy owners:** `backend/scripts/assign_owners.py` (admin only: direct DB access,
  no API route): `list`, `infer` (video from its jobs' single owner, job from its
  video), `set --user <sub> --job/--video [--with-jobs]`, `csv kind,id,user_id`. Dry run
  unless `--apply`; never replaces an owner without `--force`; every change is an
  `audit_events` row (`owner_assigned`, actor `admin-script:<--actor>`).
- **Tests** (`test_ownership_t33.py`, SQLite + Postgres): the route table must name every
  route in the app's OpenAPI schema (a new route fails until classified); every object
  route × owner / other analyst / reviewer / admin × owner's / legacy / missing object;
  hidden == missing byte for byte; lists and totals; queue visibility; submitted_by; own
  video 403 for reviewer and admin; forged roles; per-user dedup on both upload paths;
  migration up/down/backfill on SQLite and Postgres; the script.
- Also: the 11 tracked `__pycache__/*.pyc` files are removed from git (`.gitignore`
  already covered them); `health.py` imports SQLAlchemy's asyncio lazily so the app
  loads without greenlet (the route-table test imports `app.main`).
- **Left for a person:** (1) run 0014 (after 0011) on Supabase, then
  `assign_owners.py infer` and `list`, and assign the rest; (2) give reviewer/admin roles
  in Supabase `app_metadata`; (3) the current frontend's history page now shows other
  users' jobs to reviewers/admins: use `mine=true` for a "my jobs" view; (4) T34's
  `is_own` can use `ownership.is_own`.

## 7aa. Traceable Analysis Version (T36, no issue; design §12, §14)

Built by the automated build on 2026-11-24 (requested by the frontend session for
printed reports). Additive only.

- **Format.** Graph results now store `pipeline_version` =
  `graph_v1+<short git sha>+p<8-char routing hash>`, e.g. `graph_v1+3f9c2ab+p1a2b3c4d`
  (~26 chars, fits the existing String(64)). Built once in `build_graph_provider` by
  `app.core.routing.version.analysis_version`; `GRAPH_PIPELINE_VERSION` (`graph_v1`)
  stays the base.
- **Git sha.** `RAILWAY_GIT_COMMIT_SHA`, else `GIT_SHA`, else `unknown`; first 7 chars,
  lower-cased. Only a hex value is accepted, so a misconfigured variable can never put
  arbitrary environment text into a report. These two are the only env values read.
- **Hash.** sha256 of canonical JSON (sorted keys, no whitespace) over each LLM step's
  provider / model / prompt version (plus a per-step fallback and non-secret `params`)
  and the global fallback policy (`on`, `retries`, `use`). Prices and the routing file's
  `version` label are left out: they don't change what the analysis does. Key-like
  `params` entries (key/token/secret/password/credential/auth) are dropped; routing.yaml
  holds no keys anyway.
- **Snapshot.** New nullable JSON column `results.routing_snapshot` (migration 0015):
  `{schema, routing_version, routing_status, steps{step:{provider,model,prompt}},
  fallback, hash}`; returned as `routing_snapshot` on `GET /jobs/{id}/result`. The
  `model_runs` rows already record the per-call model and prompt version.
- **Which version is stored.** The run's state wins (a run resumed from a checkpoint
  keeps the version it started with); the provider's version covers a fallback that
  failed before any state existed (previously NULL). The snapshot is stored only when
  its hash equals the hash in the stored version, so a row never pairs a version with a
  routing table it wasn't produced by (old `graph_v1` checkpoints, routing changed
  between start and resume): then the snapshot is NULL.
- **Old rows.** Keep `graph_v1`; `parse_analysis_version` reads both forms (old = base
  only, `traceable` false). `model_used` keeps its pre-T36 `graph_v1/<routing version>`.
- **Migration numbering.** 0015 chains on T33's 0014 (#94, merged before this PR);
  `alembic heads` shows one head.
- **For a person.** Railway sets `RAILWAY_GIT_COMMIT_SHA` on deploys built from git;
  anywhere else (local docker, a CLI deploy without git metadata) set `GIT_SHA` or
  versions read `+unknown+`.

## 7ab. Review Reason Codes, Blind HIGH Step, Reviewer Names (T34, decision D7; design §12, §15, §17)

- **Reason codes.** `DecisionRequest.reason_code` (`ReviewReasonCode`: CLAIM_OVERGENERALISED,
  EVIDENCE_MISREAD, STANCE_MISREAD, MISSING_SOURCE, SYSTEM_CORRECT, OTHER) next to `reason`,
  which must now be at least 10 characters once trimmed (API only; the service still just
  needs a non-blank reason). Stored on `human_reviews.reason_code` and in the decision's audit
  details. **Missing code → OTHER** with `reason_code_defaulted: true` in the audit event, so
  pre-T34 clients keep working and those decisions can be told apart. SYSTEM_CORRECT only with
  APPROVE (422 otherwise). MARK_INSUFFICIENT is kept (D7 said "no separate MARK_INSUFFICIENT"
  for the UI; removing an action isn't additive).
- **Blind step** (`app/services/blind_review.py`). Applies to an OPEN case whose severity is
  HIGH **or whose table severity (overrides ignored) is HIGH**, so overriding a claim down
  can't skip it; overriding up to HIGH starts it. `POST /v1/reviews/{id}/pre-reveal` takes a
  stance and verdict for **every** claim of the case (enums; extra fields forbidden), the
  server sets the time; one per reviewer per case (unique constraint, 409 on a second); 409 on
  a resolved or non-HIGH case; 403 on your own video; same 404 rules as T33. Stored in
  `review_pre_reveals` and as a `review_pre_reveal` audit event.
- **How the view is split.** A caller is blind when the case needs the step, they have no
  pre-reveal on it, and it isn't their own job/video. Blind callers get, from `GET
  /v1/reviews/{id}`, the queue and the severity-override response: metadata, severity, and the
  new `claims` list (text, category, times, severity) with `stance`/`verdict` null; and no
  proposed label/result, reasons, rules fired, validation errors, claim stance/verdict/MISINFO
  relevance in `claim_severities`, request note, or audit `reason`/`details` (others'
  pre-reveals and notes included). `system_view_withheld` and `blind_step_required` say which.
  The queue's reason filter never matches blind cases (no probing). Outside the review router:
  `/v1/videos/{id}/results`, `/v1/videos/{id}/claims`, `/v1/claims/{id}/evidence` and
  `/jobs/{id}/result` answer 403 `PRE_REVEAL_REQUIRED` (after the ownership 404), and the job
  lists blank the label fields of blind jobs and leave them out of label-filtered pages. The
  video's severity stays visible (it orders the queue).
- **Decision.** On a case that needs the step, a decision without the deciding reviewer's own
  pre-reveal is 409 `PRE_REVEAL_REQUIRED` (another reviewer's doesn't count). With one, the
  audit event carries `pre_reveal_id`, `pre_reveal_at` and per-claim `pre_reveal_agreement`
  (stance/verdict matched the system's). Enforced in the router; `record_review_decision`
  itself doesn't check (its service-level callers are tests).
- **Names.** New `users` table (§17): id = JWT `sub`, email, display name (from
  `user_metadata.display_name|full_name|name`, whitespace-collapsed, 200 chars). Filled by
  `users_service.remember` from the verified token on `/v1/me`, every review route and
  `POST /jobs/create`; writes only on change, never fails the request. **No role column**:
  roles only come from the token. No Supabase call anywhere: users the API hasn't seen since
  T34 have no name. Views: `actor_name/actor_email` on audit entries,
  `reviewer_name/reviewer_email` (+ `reason_code`) on decisions, `submitted_by_name/
  submitted_by_email` and `is_own` on queue items and cases, `requested_by_name/
  requested_by_email` on the request, `display_name` on `/v1/me`. `*_name` is the display
  name, else the email when the viewer may see it. **Another user's email only for
  reviewers/admins**: an analyst (the T32 review-request response) sees display names only.
  Display names are user-editable, so reviewer views also carry the verified email.
- **Migration 0016** (`human_reviews.reason_code`, `review_pre_reveals`, `users`) on T36's
  0015; one head.
- **Tests:** `test_review_blind_t34.py` (review router), `test_review_blind_routes_t34.py`
  (results/jobs routes, whole app); T27/T33 tests updated (10-char notes, pre-reveals seeded
  for their reviewers, the new route classified).
- **Left for a person:** run 0016 on Supabase; the frontend can
  drop its client-side gating and use `system_view_withheld`, `claims` and `/pre-reveal`;
  optional backfill of names for users who never call the API (an admin script with the
  Supabase service key; not done, no network in the build).
## 7ab. Routing Experiment Runner (T38, no issue; design §13, §14)

Built by the automated build on 2026-11-24. **Build only: no model API was called.**
The paid run is a separate step the project lead approves with a USD cap.

- **Code.** `app/evaluation/routing_experiment/` (`golden`, `items`, `frozen`, `runners`,
  `cost`, `experiment`, `cli`); candidates in `config/routing_experiment.yaml`, the lead's
  set (relayed by the coordinating session): extract_claims and analyze_stance = haiku,
  sonnet, GPT-5 mini; verify_claims = sonnet, opus, GPT-5; critic and judge not in this run.
  **The OpenAI ids are TODO placeholders** (OpenAI's docs hosts are not reachable from the
  build environment): the lead replaces them with pinned dated ids and adds their prices to
  `routing.yaml` (marked TODO there); a live run refuses TODO ids and unpriced models.
  Each candidate may carry `reasoning_tokens` (expected hidden reasoning per call), which
  the estimate bills as output. If a verify_claims candidate (dry run) or the chosen
  verifier (live run) shares the configured critic's provider, the report flags it (§13). `selection.evaluate_candidate`
  gained two optional hooks: `run_item` (drive an item through the real node; an item is
  failed if any of its calls errored or used the fallback) and `after_item` (may raise to stop).
- **Tune split only.** The golden set is read with `git show origin/data/golden-label-set:...`.
  `TuneSet` drops non-tune rows of `videos.csv` / `claims.csv` / `reference_citations.csv` as
  they are parsed, and `transcript()` raises `TestSplitError` for any non-tune id before
  reading; tests prove no test-split transcript is ever opened. Out-of-scope videos give no
  items (§14). Items: extract_claims 48 (in-scope tune videos), analyze_stance 174 and
  verify_claims 174 (tune claims).
- **Real nodes, not bare requests.** Each candidate runs `make_extract_claims` /
  `make_analyze_stance` / `verifier.verify_claim` with a router pointed at it, so prompts,
  fencing, forced tool calls, output checks, the repair attempt and the safe defaults are
  production's. Fallbacks are switched off for the experiment (a fallback answer doesn't
  measure the candidate and selection discards it anyway).
- **Inputs.** Whisper segments plus on-screen captions collapsed from the raw EasyOCR
  detections (watermarks = text in >= 40% of frames dropped; consecutive similar frames
  merged), fused by overlap. Gold claims get the transcript/caption segments their time
  range covers.
- **Frozen retrieval.** `freeze-evidence` runs the §6 retrieval once per claim with the full
  budget (3 planner rungs, references for facts of record, reranker) and also stores the
  papers/reference passages the gold label cites (abstracts fetched from PubMed; the side
  they were cited for is never shown to the model). Default evidence mode
  `retrieved+cited` keeps every cited item in the capped set of 10 so the step metric
  measures verification; `--evidence-mode retrieved` measures retrieval + verification.
  Recorded on 2026-11-24 from golden @ 022ac44: 174 claims, 775 retrieved + 192 cited
  records, 0 search errors (one 502 re-recorded with `--resume`), 2.1 MB; pushed to branch
  `data/t38-frozen-evidence` (not langgraph-build). Findings: the reranker keeps nothing for
  87 of 174 claims (`retrieved` mode); 39 claims have no evidence even with the cited items,
  so the verifier answers them in code (no call), identically for every candidate.
- **claim_category** (needed for UNSUPPORTED eligibility) is labelled only on UNSUPPORTED
  rows, so using it would leak the answer. A fixed cue-word rule (`items.efficacy_category`,
  English/French/Spanish) is applied to every claim instead and frozen with the evidence:
  15 tune claims are eligible, including all 5 gold UNSUPPORTED.
- **Money safeguards.** Paid calls need `--live` AND `--max-usd`; refused before any call
  when the expected cost exceeds the cap, a candidate model has no price in
  `routing.yaml`, or no frozen evidence is given. Every client is wrapped in `SpendGuard`:
  each call reserves its worst case (estimated input x the largest reported/estimated
  ratio seen, >= 1.25, plus `max_tokens` output) and is refused if that could cross the
  cap; actual usage is booked after the call (a failed call books its reservation); the
  run stops at the first refusal and writes a partial report. The total can pass the cap
  only if a provider reports far more input than estimated on one call, by at most that
  call. Keys are read from the environment only inside the live path
  (`EVAL_ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY`, `EVAL_OPENAI_API_KEY` / `OPENAI_API_KEY`).
- **Outputs.** `report.json`, `report.md` (per step: metric, score, failures, cost/item, p95
  latency, chosen model and why; stance debunk recall; verification
  insufficient-called-contradicted and UNSUPPORTED recall) and `routing_v2.yaml`, the current
  table with winners applied, status `provisional` (critic and judge are not measured). The
  runner refuses to write `config/routing.yaml`.
- **Dry-run estimate** (retrieved+cited, chars/3.5 tokens) for the six priced candidates:
  $8.54 expected, $26.17 upper bound (every call at `max_tokens`, every repair fired); the
  three OpenAI candidates are unpriced until their ids and prices are filled in.
- **OpenAI client caveat for the paid run.** `OpenAIModelClient` sends `max_tokens` and
  reads `completion_tokens` (which includes reasoning, so booked spend is right). GPT-5-class
  models expect `max_completion_tokens`, and the step caps (stance 512) leave little room
  for reasoning: check this before a paid run with the GPT-5 candidates, or they will fail
  or be truncated (and be excluded by the failure-rate budget).
  **Fixed by T39 (§7ac).**
- **For a person.** Approve a cap and run the paid step (command in the T38 PR). The token
  estimate is not a provider tokenizer. The judge-explanation and critic steps are not in
  this experiment. Check `routing.yaml`'s prices against the providers' lists first.

## 7ac. OpenAI Reasoning Models: max_completion_tokens and Output Caps (T39, no issue; design §13, §14)

Fixes the T38 caveat above before the paid routing run. **No paid calls; mocked clients only.**

- **Per-model settings live in `config/routing.yaml`**, under `models:` (by exact model
  id; no name-sniffing in node or client code). `reasoning: true` makes the router send,
  for that model only: `token_param: max_completion_tokens` (GPT-5-class models reject
  `max_tokens`), the step cap raised by the step's `reasoning_allowance`, and no
  `temperature` (reasoning models accept only the default; this was not checked against
  current OpenAI docs, which were unreachable). `token_param` alone renames the cap
  without the other changes. A model not listed gets exactly the pre-T39 request.
- **Applied per attempt in `ModelRouter.prepare`**, so a reasoning primary and a plain
  fallback (or the reverse) each get their own settings. The request goes to the client
  through `request.params` (`token_param`, `max_output_tokens`, `send_temperature`);
  `OpenAIModelClient` reads them, `AnthropicModelClient` only reads the cap.
- **Caps.** Nodes keep their visible caps (extract 2048, stance 512, verify 1024, critic
  1024, judge 600). `reasoning_allowance` (T38's numbers: extract 1500, stance 800,
  verify 2500) is added for reasoning models: 3548 / 1312 / 3524. A config routing a
  reasoning model (primary, step or global fallback) to a step with no allowance fails to
  load, so critique/judge get no invented number until someone measures one. The
  Anthropic path and the live pipeline are unchanged: nothing routed today is a reasoning
  model (`gpt-4o-2024-08-06` is listed as `reasoning: false`, which sends the same request).
- **Cost.** `SpendGuard` reserves the cap the client will actually send
  (`request_output_cap`). The dry run's upper bound uses visible cap + allowance for
  reasoning candidates, and reports `output_cap_tokens`, `upper_bound_input_tokens` and
  `upper_bound_output_tokens` per row so unpriced candidates can be priced by hand. A
  candidate with `reasoning_tokens > 0` that routing.yaml doesn't mark `reasoning: true`
  is listed under `reasoning_config_problems` and refused by a live run.
- **Dry run after T39:** priced candidates unchanged at $8.54 expected / $26.17 upper bound
  (Anthropic caps unchanged). OpenAI candidates (token totals; multiply by per-1M prices):
  GPT-5 mini (extract+stance) expected 635,713 in / 270,300 out, upper 1,089,432 in /
  583,088 out; GPT-5 (verify) expected 833,182 in / 391,500 out, upper 2,082,955 in /
  951,480 out.
- **Reasoning effort** (follow-up from the coordinating session after PR #102 named the
  OpenAI candidates `gpt-5.6-luna` and `gpt-5.6-terra`): `reasoning_effort`
  (none/low/medium/high/xhigh/max) is sent explicitly on every reasoning-model call. Order:
  experiment candidate / routing step override (primary model only, never the fallback),
  then the model's `reasoning_effort` under `models:`, then `medium`. Effort on a
  non-reasoning candidate is a config problem a live run refuses. A winner's effort is
  written into the proposed `routing_v2.yaml`; the candidate key shows it (`...@prompt~high`).
- **Reported model id and reasoning usage on every call.** `ModelResponse`/`CallRecord`
  carry `response_model` (the provider's `response.model`; None if absent, never guessed)
  and `reasoning_tokens` (OpenAI `completion_tokens_details.reasoning_tokens`; already
  included in `output_tokens`), plus the effort sent. `CandidateResult` adds
  `response_models` (count per reported id, "unreported" when none), `reasoning_tokens`,
  `output_tokens` and a per-call `calls` list; report.md shows reported ids and reasoning
  tokens per candidate and notes an alias that resolved to another id or changed mid-run.
- **Aliases, not pinned ids.** §13 asks for pinned ids; OpenAI publishes only aliases for
  the 5.6 models, so reproducibility rests on the recorded response ids. If the alias moves
  mid-run, the report says so; results across that change are not comparable.
- **Models marked.** `gpt-5.6-luna` and `gpt-5.6-terra` are under `models:` as
  `{reasoning: true, reasoning_effort: medium}` (on the coordinating session's word that
  both are reasoning models; not checked against OpenAI docs). Their prices and candidate
  entries come from PR #102, which merges cleanly with this branch. With both applied, the
  dry run (frozen evidence) is **$15.36 expected / $42.67 upper bound** (all nine candidates
  priced; no reasoning-config problems). PR #102's $23.00 / $60.05 used assumed evidence sizes.
- **For a person before the paid run:** merge PR #102 (ids + prices). Nothing else is a
  TODO. Check the lead's prices and that both models accept `reasoning_effort` and
  `max_completion_tokens` on Chat Completions (one cheap manual call is the only way to be sure).

## 7ad. Blind-Step Material for HIGH Review Cases (T40, decision D7 Q1; design §12, §15, §17)

T34 makes a blind reviewer's result, claims and evidence routes answer 403, so the blind
step had nothing to judge from. Additive only; no migration.

- **Route:** `GET /v1/reviews/{review_id}/blind-material` (reviewer/admin; built in
  `app/services/blind_material.py`). Allowed **only while the caller is blind** on the
  case (`blind_review.is_blind`): an open HIGH case, no pre-reveal by the caller, not their
  own video. Anyone else who may see the case gets 403 `BLIND_STEP_NOT_ACTIVE` (detail has
  `code`, `review_id`, `message`); analysts 403 before lookup; not-visible 404 (T33).
- **Response:** `review_id, job_id, video_id, material: "blind"`; `claims[]` with
  `claim_id, text, category, start_seconds, end_seconds, source_segment_ids` (the
  extractor's quoted segments, not the stance's) and `references[]`; `transcript_segments`
  and `ocr_segments` (T26 `SegmentView`). A reference has `evidence_id, source_kind, rank,
  title, year, publisher, study_type, abstract_snippet, url, pmid, doi`; library documents
  carry only id, kind, rank and title. No relation, cited/deciding marker, verdict,
  stance, label, reasons, rules, critic notes, confidence, relevance score, severity or
  search-trail field.
- **Which papers (leak fix):** `claim_evidence` stores the reranked set (ranks 1..K) and
  then any record the verifier *cited* that the reranker did not keep. Those trailing rows
  would reveal a citation, so only ranks <= K are shown, K = the claim's
  `search_trail.counts.kept` (= `len(reranked_evidence)`). Ranks are renumbered 1..n.
- **Ordering:** claims by start time then id; references by stored rerank rank then id;
  segments by start then id. Never by relation or citation.
- **Tests** (`test_blind_material_t40.py`): two databases identical except for verdicts,
  stances, relations (in an order that would differ if sorted by relation), labels,
  deciding, critic, confidence, scores and reasons, plus a cited non-reranked paper in one:
  byte-identical responses (with and without a library document). Forbidden keys/values
  scan; schema has no system fields; access matrix (blind reviewer/admin 200, pre-revealed,
  own-video, non-HIGH, resolved 403; analysts 403; legacy for reviewer 404). T33's route
  table classifies the route.
- **Residuals for a person:** (1) rows stored before T31 have no search trail, so K is
  unknown and every stored link is shown, which can include a cited non-reranked record;
  (2) the amount of material can reflect a retrieval retry, which correlates weakly with an
  INSUFFICIENT verdict; (3) the claim list comes from the case and the stored rows, and
  severity is not shown here (the case view already shows table severity).

## 7ae. OpenAI Responses-API Client for Reasoning Models (T41, no issue; design §13, §14)

The T38 smoke test (PR #104) got a 400 on every GPT-5.6 call: Chat Completions refuses
function tools together with `reasoning_effort`. The lead chose a Responses-API client so
the candidates run with reasoning on. **No paid calls; mocked SDK only.**

- **Which API.** `ModelRouter.prepare` now also passes `params["reasoning"]` from
  routing.yaml's `models:` entry. `OpenAIModelClient` sends `reasoning: true` models to
  `client.responses.create`; every other OpenAI model (gpt-4o critic and fallback,
  unlisted models) stays on Chat Completions with the exact T39 request. No model-name
  checks anywhere.
- **Request mapping (Responses).** `model`; `input` = the node's messages (string content
  passes through; text blocks become `input_text`/`output_text` parts); `instructions` =
  the system prompt; `max_output_tokens` = node cap + step reasoning allowance (3548 /
  1312 / 3524), no `max_tokens`/`max_completion_tokens`; `reasoning: {effort}` (step
  override, else model setting, else medium, as T39); no `temperature`; tools flattened to
  `{type: function, name, description, parameters, strict: false}` (strict off: the nodes'
  schemas aren't strict-mode schemas and their parsers validate anyway); forced choice
  `{type: function, name}`; `store: false` (nothing kept server-side; we never chain).
- **Response mapping.** The first `function_call` item with the forced name → its parsed
  `arguments` (bad JSON / wrong tool / text only → `None`, the node's safe default). Text
  requests: the `output_text` parts of `message` items, joined. Usage: `input_tokens`,
  `output_tokens` (taken as including reasoning, as Chat Completions' `completion_tokens`
  does; the SDK's docstring doesn't say, so check `output_tokens >= reasoning_tokens` in the
  first paid reply), `output_tokens_details.reasoning_tokens`, and `response.model`.
- **Truncation.** No truncation error existed, so T41 adds `ModelTruncatedError`
  (kind `truncated`): raised for status `incomplete` with reason `max_output_tokens`. It is
  not a fallback kind, so no retry and no fallback; the item counts as failed in the
  experiment. The error carries the billed usage, which the router writes onto the failed
  `CallRecord` (tokens, reasoning, reported model, cost) and `SpendGuard` books instead of
  the worst-case reservation. Other `incomplete` reasons parse normally; status `failed` is
  a plain `ModelCallError`.
- **Errors.** Same `map_provider_error` as before (timeout / 429 / 5xx / connection; other
  4xx a plain `ModelCallError` with its status), tested with the real SDK exception types
  and with the real SDK over an `httpx.MockTransport`.
- **Dependency.** `openai>=1.66` (the Responses API); written against the installed 3.58.
- **Dry run after T41** (frozen evidence): unchanged at **$15.36 expected / $42.67 upper
  bound**; OpenAI candidates $6.81 / $16.49 (luna extract $0.17 / $0.54, luna stance
  $0.28 / $0.37, terra verify $6.36 / $15.58). The upper bound is still above the $40 cap.
- **For a person before the paid run:** re-run the smoke test (~$0.35). Watch for
  `truncated` errors (the allowances are T38's guesses) and that the Responses API accepts
  `reasoning.effort: medium` with forced function tools for both models.

## 7af. Deliberate Re-Analysis and Versioned Results (T55, backend; design §1, §11, §12, §17)

Built by the automated build on 2026-11-26 (lead approved). Backend only; the frontend
session builds the UI from the API note below. Migration **0017** (single head).

- **Why.** A video could only be re-run through a reviewer's REQUEST_REANALYSIS (blocked
  for the uploader by the self-review rule), and POST /jobs/create returns the caller's
  PENDING/STARTED/SUCCESS/REVIEW_REQUIRED job (T11/T28), so pipeline changes couldn't be
  checked on old videos. That reuse and duplicate-upload reuse are **unchanged**: they
  guard against accidental double runs. Re-analysis is a separate, deliberate route.
- **Lineage.** A video's versions are the jobs on it owned by the video owner
  (`jobs.user_id`). A re-run started by an admin still belongs to the owner (shows in
  their job list), like `start_reanalysis`. Each re-run links to the newest job of that
  lineage through `jobs.previous_job_id` (nullable FK, indexed). A reviewer's
  REQUEST_REANALYSIS now also sets it.
- **Who.** Video owner (`videos.user_id == sub`) or admin. A reviewer who may see the
  video gets 403 `REANALYSIS_FORBIDDEN`; anyone who can't see it gets 404 (§15). Legacy
  videos with no owner: admin only (with REQUIRE_AUTH off, the dev user). Classified in
  T33's route table as `OWNER_OR_ADMIN`.
- **Rate limits.** Two, both per rolling `REANALYSIS_WINDOW_HOURS` (24), counted from
  `audit_events` (`reanalysis_requested`, entity = the video, actor = the caller):
  `REANALYSIS_MAX_PER_VIDEO` (3) per caller per video, and `REANALYSIS_MAX_PER_USER`
  (20) per caller across all videos (added by the lead on 2026-11-26). **Admins count
  against the per-user limit too**: no setting exempts any role from a limit, so there
  was no pattern to follow. Retry-After is when the request that frees a slot leaves the
  window; if both limits block, the later of the two (both must free up), and
  `limit_kind` names that one. A re-run whose dispatch failed doesn't count. 0 in either
  setting turns the route off (403 `REANALYSIS_DISABLED`). A Postgres advisory lock per
  caller plus the video row lock stop two requests at once from both taking the last
  slot.
- **Open review case.** OPEN cases of the lineage become `SUPERSEDED` (new
  `reviewcasestatus` value) with `human_reviews.superseded_by_job_id`, and a
  `review_superseded` audit event (actor, reason, new job). They leave the default OPEN
  queue (`GET /v1/reviews?status=SUPERSEDED` or `ALL` lists them) and can't be decided
  (409). The old job keeps REVIEW_REQUIRED: its result was never reviewed. The new job
  has no case; its result goes through §11 from scratch.
- **Versions.** The video's current result is its **newest finished job** (SUCCESS,
  REVIEW_REQUIRED, or rejected by a reviewer, with a stored result).
  `GET /v1/videos/{id}/results` and `/claims` now pick that job, not the newest job.
  **Behaviour change:** a newer job that is running or failed no longer turns that route
  into 202/409; it's reported in `latest_job`. With no finished job, 202/409 as before
  (T26's test updated).
- **Downgrade** of 0017 rebuilds the Postgres enum; SUPERSEDED cases become RESOLVED
  with no action (pre-0017 code shows that as REANALYSIS_REQUESTED) and the link to the
  new job is lost.
- **Not done / open:** a re-run is allowed while another run of the video is still
  in flight (the spec says "always creates"; the rate limit bounds it). The frontend
  confirm dialog should say it costs one more analysis.

### API note for the frontend session

**`POST /v1/videos/{video_id}/reanalyse`** (auth required)

Request body (optional; `{}` or no body is fine):
```json
{"reason": "pipeline v2 shipped"}       // optional, at most 2000 characters
```
`202 Accepted`, header `X-Reanalyses-Remaining: <n>`:
```json
{
  "job_id": "…", "video_id": "…",
  "status": "PENDING",          // FAILED with error_code DISPATCH_FAILED if queuing failed
  "state": "QUEUED",            // §1 state (FAILED if queuing failed)
  "error_code": null,
  "celery_task_id": "…",
  "previous_job_id": "…",       // the job this re-runs (null if the video had none)
  "superseded_review_ids": ["…"],  // open review cases closed by this re-run
  "reanalyses_remaining": 2,    // left in the window: the smaller of the per-video and per-user allowances
  "created_at": "…"
}
```
Then poll `GET /v1/jobs/{job_id}` as for any job.

| Status | When | Body |
|---|---|---|
| 401 | not signed in | |
| 403 | caller may see the video but is neither its owner nor an admin | `detail.code = "REANALYSIS_FORBIDDEN"` |
| 403 | re-analysis turned off (`REANALYSIS_MAX_PER_VIDEO=0`) | `detail.code = "REANALYSIS_DISABLED"` |
| 404 | no such video, or the caller can't see it | `detail = "Video not found"` |
| 422 | reason longer than 2000 characters | |
| 429 | over a limit: 3 per video or 20 in total per caller per 24 h (admins included) | header `Retry-After: <seconds>`; `detail = {code: "REANALYSIS_RATE_LIMITED", limit_kind: "per_video" \| "per_user", message, retry_after_seconds, limit, window_hours}`. If both limits block, `limit_kind` and `Retry-After` are for the one that frees up later |

Show the button when `GET /v1/me` says the caller is an admin, or the result's
`submitted_by` is the caller (the server checks again).

**Result payload additions** (`GET /v1/videos/{id}/results` and `GET /jobs/{job_id}/result`):
```json
{
  "previous_jobs": [            // earlier finished analyses of this video, newest first
    {"job_id": "…", "finished_at": "…", "label": "MISINFO", "label_display": "MISINFO (unproven)",
     "pipeline_version": "graph_v1+abc1234+p…", "status": "SUCCESS"}   // status may be REVIEW_REQUIRED or FAILED (rejected)
  ],
  "previous_job_id": "…",       // the job this one re-analysed, or null
  "current_job_id": "…",        // the video's current result (newest finished job)
  "is_current": true,           // false on an older version: link to current_job_id
  "latest_job": null            // or {job_id, status, state, error_code, created_at}: a newer run that is still running or failed
}
```
Older versions open with `GET /jobs/{job_id}/result`; their `previous_jobs` lists only
what came before them.

**Review case** (`review` in the result payload, and the review API): new
`status`/`case_status` value `"SUPERSEDED"`, `resolved: false`, and
`review.superseded_by_job_id` → show "Superseded by a newer analysis" with a link.
`GET /v1/reviews` takes `status=SUPERSEDED` (default `OPEN` leaves them out).

## 7ah. Research Dashboard Stats API (T62, backend; design §12, §16, §17)

Built by the automated build on 2026-11-26 (lead approved). Backend only; the frontend
session builds `/dashboard` from the API note below. **No migration**, no new table.
(§7ag is taken by T63's open PR.)

- **Route.** `GET /v1/stats?window=7d|30d|90d|all` (default `30d`; anything else 422).
  Any signed-in user, any role (analyst, reviewer, admin) gets the **same** body; no
  token or a bad one is 401. Classified in T33's route table as `AGGREGATE`. Code:
  `app/services/stats_service.py`, `app/api/routers/stats.py`.
- **Aggregates only.** The body holds counts, two shares/medians and category names.
  No video, job, claim, review or user id, file name, hash or claim text (a test greps
  the body for every such value in the database).
- **Cache.** Per window, process-wide, `STATS_CACHE_SECONDS` (60; 0 = off); the figures
  are the same for everyone, so one cache serves all callers. Response header
  `Cache-Control: private, max-age=60`. With several API replicas each has its own cache.
- **What is counted.**
  - *Videos*: each video once, with its **newest result created in the window** (a
    re-analysis replaces, doesn't add). Only the four canonical labels; a legacy row
    with any other label is left out of the whole population.
  - *Per week*: ISO weeks (Monday, UTC) from the window start's week (for `all`, the
    first result's week) to the current week, empty weeks included; a video falls in
    the week of the result counted, so the weeks add up to `videos.total`.
  - *Labels*: the **system** label (`results.label`), not a reviewer's correction (that
    is what `reviews.changed_label` measures). MISINFO split by `misinfo_basis`;
    `unspecified` = no basis (rows before T30, single-call/fallback path).
  - *Jobs*: `pending_now` (§1 state PENDING/QUEUED/RETRY_PENDING, or status PENDING on
    pre-T28 rows) and `running_now` (RUNNING / STARTED) are **snapshots of now**, not
    windowed, so a job stuck since before the window still shows. `failed` = status
    FAILED created in the window, excluding reviewer rejections (`REVIEW_REJECTED`).
  - *Reviews*: `backlog_now` = OPEN cases now. `decisions` = RESOLVED cases with
    `decided_at` in the window (SUPERSEDED cases are not decisions). A decision
    *changed the label* when `corrected_label` is set and differs from
    `proposed_label`; every other decision (approve, claim-only correction, insufficient,
    re-analysis request, reject) *kept* it. `median_hours_to_decision` = median of
    `decided_at - created_at`.
  - *Top categories*: up to 10 `claims.category` values (lower-cased), counted as
    **videos** with at least one claim in the category, not claims, so one upload with
    many claims can't reach the threshold alone.
- **Small cells.** Every count under 5, **zero included**, is published as the string
  `"<5"`. Zero is suppressed too because the queue row says "any count < 5", and a
  visible 0 next to a `"<5"` would narrow the hidden cell.
- **Differencing.** Groups whose cells add up to a published total: weeks and labels
  (total `videos.total`), MISINFO basis (total: the MISINFO cell), changed/kept (total
  `reviews.decisions`). In each group, after the primary suppression more cells are
  hidden, smallest first (ties by name), until nothing is hidden or **at least two cells
  are hidden and the hidden cells add up to 5 or more**; so total minus the shown cells
  never pins one cell down and is never itself a small number. A hidden total hides its
  whole group; a hidden MISINFO hides the whole basis split. `changed_label_share` is
  null unless both changed and kept are shown; `median_hours_to_decision` is null under
  5 decisions. Groups with no total (jobs, backlog, categories) get primary suppression
  only; categories under 5 are **left out** of the list (their names are model text and
  a rare one could describe a single video). Tested on fixed cases, a seeded sweep of
  3000 random groups, and every group of real responses.
- **Not covered (for the lead).** Differencing **between** responses: 30-day minus
  7-day figures, or the figures just before and after one video finishes (someone who
  knows a colleague just uploaded could see which label moved by one). Each response is
  safe on its own; closing this needs rounding or noise on every figure, which the queue
  row didn't ask for. The 60 s cache only coarsens the timing. Also not covered:
  several videos from **one uploader** can together reach 5 (the unit is the upload, as
  the queue row says, not the person).
- **Deviations.** No `classifications` table exists (§7k), so labels come from
  `results`. Aggregation runs in Python over the window's rows (cheap at this volume,
  and the same on SQLite and Postgres); move it into SQL if the `all` window gets slow.

**Response shape** (`StatsResponse` in `app/api/routers/stats.py`; a *cell* is an
integer ≥ 5 or the string `"<5"`):

```jsonc
{
  "window": "30d",
  "window_start": "2026-10-27T12:00:00+00:00",   // null for "all"
  "window_end": "2026-11-26T12:00:00+00:00",
  "generated_at": "2026-11-26T12:00:00+00:00",
  "cache_seconds": 60,
  "min_cell": 5,
  "note": "These figures describe videos uploaded to this tool, not how common misinformation is online.",
  "videos": {
    "total": 30,
    "per_week": [{"week_start": "2026-10-26", "videos": "<5"}, {"week_start": "2026-11-23", "videos": 19}]
  },
  "jobs": {"pending_now": 5, "running_now": "<5", "failed": 6},
  "labels": {
    "MISINFO": 12, "NO_MISINFO": 7, "DEBUNKING": 5, "CANNOT_RECOGNIZE": 6,
    "misinfo_basis": {"contradicted": 6, "unproven": "<5", "denies_supported": "<5", "unspecified": "<5"}
  },
  "reviews": {
    "backlog_now": "<5", "decisions": 8, "changed_label": "<5", "kept_label": "<5",
    "changed_label_share": null,          // 0..1, 3 decimals, or null
    "median_hours_to_decision": 4.5       // hours, 1 decimal, or null
  },
  "top_categories": [{"category": "treatment_efficacy", "videos": 6}]
}
```

Frontend notes: show `note` as the fixed caption; render `"<5"` as text (not 0) and
leave it out of chart scales or draw it as a hatched "under 5" bar; `window` is the only
query parameter; `pending_now`, `running_now` and `backlog_now` are "now" whatever the
window.

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

- **2026-11-26**: T62 backend (research dashboard stats, design §12, §16, §17) built by the automated
  build: `GET /v1/stats?window=7d|30d|90d|all` for any signed-in user, totals across all users only,
  cached 60 s; videos per week, jobs pending/running/failed, label mix with the MISINFO basis split,
  review backlog / median time to decision / share that changed the label, top claim categories.
  Every count under 5 (zero included) is `"<5"`, with secondary suppression so no hidden cell can be
  recovered from a total. No migration. 21 new tests; full suite 1909 passed, 198 skipped (stats
  tests also pass on a local Postgres 16). Cross-window / before-and-after differencing is not
  covered and needs a lead decision. Frontend next, from the §7ah API note.
- **2026-11-26**: T51 (design §4, §7) design/quality/quantity statements are not efficacy claims, no
  spend. New claim_category `evidence_meta` (chosen over a claim_kind `not_verifiable`: claim_kind picks
  the sources, and the golden guide verifies such statements, e.g. tune v79 c3 SUPPORTED) for statements
  that assert no effect ("these studies are observational", "only one study", "not randomised").
  Narrowed after the PR #122 review: "the evidence for X is strong/overwhelming/clear/proven" keeps the
  implied efficacy category and stays eligible for UNSUPPORTED (T49's guard stops empty searches).
  Prompt `extract_v4` (v3 kept, routing.yaml untouched); rules in `app/core/claim_category.py` override
  the model for every prompt version and are rechecked in `routing.unproven_category`. Job 5cc07f48
  (real rows from T50): c12 evidence_meta; c13 stays efficacy and the T49 guard downgrades it (video
  NO_MISINFO via c8, CANNOT_RECOGNIZE without c8). Severity `evidence_meta: LOW`. Golden tune: 2/187 match (v79 c2, c3; SUPPORTED),
  0/11 UNSUPPORTED; no disagreement. Cross-check and T49 replay identical. Branch `auto/T51`.
- **2026-11-26**: T50 (design §6, §13) search planning rewrite and find-the-study step, no paid
  calls. (a) term-aware content words (`vitamin k`, `type 2 diabetes`, never `vitamin`); (b) 88
  lexicon entries added (vitamin K, VKDB, newborns, breast milk, coagulation, intracranial
  haemorrhage + tune-split gaps, es/fr surface forms); (c) `plan_search` assistant wired behind
  `config/routing.yaml` + `config/pipeline.yaml`, output sanitised; (d) each round a distinct,
  broader rung, `ladder_exhausted` instead of repeats (intervention never broadened to its parent);
  (e) citation lookup (`"JAMA"[ta] AND 2026[dp] AND topic`); (f) keyword fallback <= 3 terms, no
  filler; (g) screened-out papers in the search trail / result API; (h) language detection +
  `translate_claim`, rules-only fallback with that language's stop words; (i) `find_study`
  (web-search model proposes ids; we verify via EFetch / ESearch `[doi]` / Crossref; only verified
  PubMed or `journal_doi` records become evidence), run from `rerank_evidence`, records pinned.
  JAMA DOI verified to PMID 42986716 via E-utilities. Crossref blocked from the build env
  (synthetic fixture). D8 tune recall, rules only: strict (golden PMID kept) 4/118 → 16/118;
  lenient 52/187 → 113/187 (T49 intervention yardstick) or 75/187 → 149/187 = 79.7% (claim-concept
  yardstick): target 80% not met without the model helpers; non-English lenient 1/59 → 26/59 (42/59
  claim yardstick); repeated rounds 253 → 0. D8 CI regression set: `fixtures/pubmed_regression/`
  (job 5cc07f48, real E-utilities answers). After coordinator review: the T49 reconstructed fixture
  is replaced by the real production rows (`vitamin_k_job.real.json`); on them the guard gives
  NO_MISINFO, not CANNOT_RECOGNIZE (stored SUPPORTED c8 decides), and CANNOT_RECOGNIZE + nothing_judged
  without c8. Real vitamin K claims: 8/8 expected (c1, c3-c7, c9, c12) keep vitamin K / VKDB papers;
  c2's citation lookup retrieves the JAMA paper (PMID 42986716) but only find-the-study (paid) pins
  it. "Vitamin K antagonist" no longer counts as on topic; non-Latin claims record
  `no_query_reason: needs_translation`. T49 replay on T50 evidence: 4/5 tune unproven videos regain
  MISINFO (unproven) (v120 stays CANNOT_RECOGNIZE: seawater not recognised as the intervention
  rules-only). Dry-run paid estimate: vitamin K ~$0.12 (upper $0.39), tune ~$0.84 (upper $2.65). Cross-check unchanged. Report `evals/reports/T50/`. Branch `auto/T50`.
- **2026-11-26**: T49 (design §7; §9 unchanged) unproven guard, urgent, no spend. After the vitamin K
  production job 5cc07f48 (accurate video labelled MISINFO (unproven) from an empty and an off-topic
  search), `app.core.graph.unproven_guard` runs in the `verify_claims` node right after each verdict
  (and in the routing experiment's verify runner): UNSUPPORTED stands only if the claim's reranked
  evidence holds a record on topic for its intervention (verifier-cited, or the intervention terms in
  title/abstract: a recognised lexicon concept's names, else the claim's intervention-side words, all
  required, "vitamin k" kept whole); otherwise INSUFFICIENT_EVIDENCE + `search_found_nothing_on_topic`.
  Replay of the job (fixture RECONSTRUCTED from the queue text, no prod access; lead to swap in real
  rows) gives CANNOT_RECOGNIZE + `nothing_judged`; without the guard it reproduces MISINFO (unproven).
  Tune frozen evidence (T38): 0/5 tune golden unproven videos keep the label (the other 7 of 12 are
  test split, not read): empty search (v22, v120), cancer-only search for a "soap" (v141, v143), no
  recorded search (v36). T50 is what restores them. Judge cross-check unchanged (162/162, 149/162
  exact). Report `evals/reports/T49/`. Branch `auto/T49`.
- **2026-11-25**: T48 (design §15, §17) Supabase asymmetric JWT verification, no spend.
  `app/auth/dependencies.py` now verifies ES256/RS256 tokens against the project JWKS
  (`SUPABASE_URL/auth/v1/.well-known/jwks.json`, new `app/auth/jwks.py`): key chosen by
  `kid`, algorithm pinned per key type (EC P-256 → ES256, RSA → RS256; `oct`/private/other
  keys dropped), cache 10 min, unknown kid → at most one refetch per 30 s, stale keys kept
  1 h if the JWKS is unreachable, then 401. HS256 only with `SUPABASE_JWT_SECRET`, never with a
  JWKS key; `none` and other algs refused. Every token needs `aud=authenticated` and `exp`;
  `iss` must be `SUPABASE_URL/auth/v1` (checked for HS256 too when `SUPABASE_URL` is set).
  Roles still from `app_metadata` only; `REQUIRE_AUTH=false` unchanged. 46 new tests (local
  keys, faked JWKS, no network); two T33 test tokens gained `aud`. Full suite 1811 passed,
  0 skipped (local Postgres 16 + pgvector, Redis, OCR). Branch `auto/T48`.
- **2026-11-25**: T45 (design §4, §5, §13, §14) accuracy fixes from T43, no paid calls. Unicode-aware
  tokens (`app/core/text_tokens.py`) in the grounding guardrail, claim dedup and the strict matcher: v167's
  4 Devanagari tune claims are no longer dropped as ungrounded, and Devanagari pairs no longer score
  similarity 1.0; ASCII tokenisation is unchanged (tested), accented words are now one token. Meaning-based
  claim P/R/F1 is reported next to strict in the routing report and the eval scorer (selection stays
  strict). New candidate prompts `extract_v3` and `stance_v2` (T43 §8) added for sonnet in
  `config/routing_experiment.yaml` only; `config/routing.yaml` and the live defaults are unchanged.
  Dry-run estimate for the proposed re-run (sonnet extract v2/v3 + stance v1/v2, plus the use_ocr=false
  extraction ablation, tune @ 948b1c2): $5.31 expected, $16.42 upper bound. Open for the lead: stance_v2
  treats a clear sarcastic debunk as REFUTES where the guide says UNCLEAR. Report
  `evals/reports/T45/README.md`. Branch `auto/T45`.
- **2026-11-25**: T46 (design §14) evaluation loader for the golden label set, no spend. Branch
  `auto/T46` from `integrate/golden-set` (dataset byte-identical to `data/golden-label-set` @ 948b1c2).
  `app/evaluation/dataset.py` now reads the golden schema (`claim_verdict` incl. UNSUPPORTED,
  `claim_kind`, evidence columns, `misinfo_basis`, `review_reasons`, `split`, review fields);
  `out_of_scope` videos sit on `Dataset.excluded`, outside every split and count; inputs come from
  `transcripts/` when there is no `inputs.jsonl`. `metrics.judge_label` gained the §9 unproven rule.
  Verified: 162 in-scope videos (19 excluded), 550 claims, 48 tune / 114 test, labels
  NO_MISINFO 47 / CANNOT_RECOGNIZE 59 / MISINFO 39 / DEBUNKING 17, bases 26/12/1, zero §9
  inconsistencies. Nothing predicted or scored on the test split. Next: T14.

- **2026-11-25**: T47 (design §5, §9, §12) sarcastic debunks are REFUTES (lead decision 2026-11-25), no
  spend. Golden-set guide (README §5, REVIEW.md step 4, PLAN.md, design doc §5): a sarcastic or mocking
  debunk with a clear target is REFUTES with the sarcasm noted; UNCLEAR keeps genuinely ambiguous tone,
  disagreeing speakers, self-contradiction and jokes with no claim being rejected. All 4 UNCLEAR stances
  re-checked by rule, no model output consulted: tune 1 of 2 relabelled (v86 c3 -> REFUTES; v121 c1 stays,
  a joke with no claim being rejected), test 0 of 2. No video label changed; v86 gains
  `denies_supported:c3`. Golden set `data/golden-label-set` @ 92a731e (fast-forward from 948b1c2), copied
  byte-identical into `research/claim-level/dataset`. `stance_v1` (live, edited in place, as T30 did) and
  `stance_v2` say REFUTES for a sarcastic debunk and start the rationale with "Sarcasm:"; the judge carries
  the stance rationale on `ClaimView`, and the explanation says "Debunked (the speaker uses sarcasm): ..."
  (template) or is told via a `sarcasm: yes` claim-table column and `explain_v2` (model). T38/T43 reports
  measured the earlier `stance_v1` text. Cross-check re-pinned to 92a731e: 162/162 labels, 149/162 exact
  reasons, unchanged; no judge changed. Branch `auto/T47`.
- **2026-11-24**: T43 (design §13, §14) routing error analysis, no paid calls. T38 kept no per-item
  outputs, so per-claim error review, confusion matrices, bootstrap CIs and the dcf77b0 re-score were
  stopped; the runner now writes `per_item.json` and `app.evaluation.error_analysis` does all of it from
  that. Found: blind two-pass extraction ceiling on tune is strict F1 0.68 / meaning F1 0.79 (Sonnet
  0.42 strict); grounding guardrail and strict matcher drop/mis-score non-Latin claims (v167); extract_v2
  lacks the gold's original-language/bracket conventions (35% of tune claims non-English). dcf77b0 vs
  0fbc68a: 11 tune claims changed (948b1c2, now current: 21), no stance labels; stance winner can't
  flip, extract/verify could.
  New `config/pipeline.yaml` `extraction.use_ocr` (default true) for the no-OCR ablation. Report
  `evals/reports/T43_error_analysis.md`. Branch `auto/T43`.
- **2026-11-24**: T44 (design §9, §11, §14) re-pinned the judge cross-check to the golden
  set after the A2-A4 rule sweep (data/golden-label-set 948b1c2: 550 claims; in scope
  NO_MISINFO 47 / CANNOT_RECOGNIZE 59 / MISINFO 39 (26 contradicted, 12 unproven, 1
  denies_supported) / DEBUNKING 17; 71 videos in review; all match the queue's numbers).
  Labels, bases, deciding claims and review routing agree on 162/162 in-scope videos;
  exact review reasons on 149/162 (152 @ dcf77b0). The only difference kind is still
  `weak_evidence_covered_by_judge_reason`: 25 reasons on 13 videos (20 on 10 @ dcf77b0;
  +3 from v22/v35/v161 becoming MISINFO/unproven, +2 from v36's new deciding screen-only
  claims c10/c14). `nothing_judged` is shared on 24 videos (26; v35 and v161 now decide).
  The golden judge.py is byte-identical to dcf77b0's. Neither judge changed. CI's golden
  fetch reads the pin from the fixture, so it follows automatically.
- **2026-11-24**: T42 (design §9, §11, §14) re-pinned the judge cross-check to the
  adjudicated golden set (data/golden-label-set dcf77b0: 538 claims; in scope NO_MISINFO
  48 / CANNOT_RECOGNIZE 61 / MISINFO 36 (26 contradicted, 9 unproven, 1 denies_supported)
  / DEBUNKING 17; 69 videos in review). Labels, bases, deciding claims and review routing
  agree on 162/162 in-scope videos; exact review reasons on 152/162. The golden judge now
  raises `nothing_judged` (26 videos, shared), so that difference kind is 0. The only kind
  left is `weak_evidence_covered_by_judge_reason` (20 reasons, 10 videos: the backend's
  extra `weak_evidence` on deciding UNSUPPORTED/MIXED claims the golden judge already sends
  with `unproven_claim`/`mixed_evidence`). Neither judge changed. CI's golden fetch reads
  the pin from the fixture, so it follows automatically.
- **2026-11-24**: T38 OpenAI candidates (paid, lead-approved): smoke test on v11 clean
  ($0.0498; model ids reported, output ≥ reasoning on every call, no truncation); full tune
  split $1.8693 of a $27.86 cap, 359 calls, 0 errors. OpenAI won no step (luna 0.32 / 0.50,
  terra 0.49 vs Claude winners sonnet 0.42 / sonnet 0.64 / opus 0.68). Combined report and
  proposed `routing_v2.yaml` (sonnet / sonnet / opus; `config/routing.yaml` unchanged) in
  `evals/reports/T38_routing/combined/`. Total T38 spend $14.00 of $40 (Anthropic $12.08,
  OpenAI $1.92). Tune-split numbers only. Caveat: luna/terra rarely reasoned at `medium`
  effort with the forced tool choice. Branch `auto/T38-openai`.
- **2026-11-24**: T41 (design §13, §14) OpenAI Responses-API client by the automated
  build: `reasoning: true` models now call `responses.create` with `reasoning.effort`,
  `max_output_tokens` (node cap + allowance), flat function tools and a forced tool choice;
  other OpenAI models keep Chat Completions unchanged. Incomplete-at-cap replies raise the
  new `ModelTruncatedError` with billed usage recorded. Dry run unchanged ($15.36 / $42.67;
  OpenAI $6.81 / $16.49). Mocked tests only, no spend. Decisions in §7ae.
- **2026-11-24**: T40 (decision D7 Q1; design §12, §15, §17) blind-step material by the
  automated build: `GET /v1/reviews/{id}/blind-material`, only for a caller blind on an open
  HIGH case (else 403 `BLIND_STEP_NOT_ACTIVE`); claims, segments and retrieved papers in
  rerank order with no relation/verdict/stance/label/critic/confidence; cited papers outside
  the reranked set left out. Byte-identical no-leak test. No migration, no spend. Decisions in §7ad.
- **2026-11-24**: T39 (no issue; design §13, §14) OpenAI reasoning-model fix by the
  automated build, **no paid calls**: `models:` + `reasoning_allowance:` in routing.yaml;
  reasoning models get `max_completion_tokens` at visible cap + allowance (stance
  512 -> 1312, extract 2048 -> 3548, verify 1024 -> 3524) and no temperature; spend guard
  and dry-run bound use the raised caps; live run refuses unmarked reasoning candidates.
  Follow-up: explicit `reasoning_effort` (default medium, per candidate/step/model) and the
  response's model id + reasoning tokens recorded on every call and shown in the report.
  Dry run with PR #102's candidates: $15.36 expected / $42.67 upper bound (frozen evidence).
  1545 passed, 0 skipped (local Postgres 16 + pgvector), also with #102 merged. Decisions in §7ac.
- **2026-11-24**: T38 Option C paid run (lead-approved, cap $25): **done**, Claude candidates
  only over the full tune split (48 extract / 174 stance / 174 verify items). Spend $11.81 Anthropic,
  $0 OpenAI (729 calls, 0 failed, 0 fallbacks); T38 total so far $12.08 actual. Best Claude per step:
  extract sonnet-5-5 (F1 0.42), stance sonnet-5-5 (macro-F1 0.64), verify opus-5-5 (macro-F1 0.68).
  Tune-split numbers, not held-out test. Provisional `routing_v2.yaml` (OpenAI not yet run);
  config/routing.yaml unchanged. Frozen evidence sha256 c4ff82bf…4ca5 (full hash in the report);
  gpt-5.6-luna/terra must reuse it after T41. Report in `evals/reports/T38_routing/report.md`.
- **2026-11-24**: T38 paid run (lead-approved; caps $1 smoke / $40 full) **stopped at the smoke
  test**: on tune video v11 all six Anthropic candidates returned valid output, but every OpenAI
  call (gpt-5.6-luna extract/stance, gpt-5.6-terra verify) got HTTP 400 "Function tools with
  reasoning_effort are not supported ... in /v1/chat/completions; use /v1/responses or set
  reasoning_effort to 'none'". Full run not started. Spend: Anthropic $0.27, OpenAI ~$0 actual
  ($0.21 booked by SpendGuard as failed-call reservations); $0.48 booked / ~$0.27 actual total.
  Report in `evals/reports/T38_routing/`. Needs a person: choose effort `none` or a Responses-API client.
- **2026-11-24**: T34 (decision D7; design §12, §15, §17) review decision completeness by the
  automated build: `reason_code` + 10-char note on decisions (missing code → OTHER, flagged);
  the blind HIGH step `POST /v1/reviews/{id}/pre-reveal`, enforced on the case view, queue,
  result/claims/evidence routes, job lists and decisions; `users` table and names/emails
  (emails only to reviewers/admins) plus `is_own` on review views. Migration 0016 on 0015. 1519 passed, 5 skipped (OCR/PDF tools) locally with
  Postgres 16 + pgvector; no spend. Decisions in §7ab.
- **2026-11-24**: T38 (no issue; design §13, §14) routing experiment runner by the
  automated build, **no paid calls**: tune-split items for extract_claims (48),
  analyze_stance (174) and verify_claims (174) through the real nodes; retrieval frozen
  once (174 claims, free PubMed/reference calls, on branch `data/t38-frozen-evidence`);
  dry run $8.54 expected / $26.17 upper bound for the priced candidates (lead's set; the
  GPT-5 / GPT-5 mini ids are TODO placeholders); `--live` needs
  `--max-usd`, refuses over-cap estimates and stops at the cap. Decisions in §7ab.
- **2026-11-24**: T37 (no issue; design §9, §11, §12) `nothing_judged` review reason by
  the automated build. In the judge's last branch (nothing could be judged), any
  INSUFFICIENT_EVIDENCE claim adds `nothing_judged` (stored `judge:nothing_judged`); no
  claims or only NOT_VERIFIABLE claims add nothing. Labels unchanged. Text: "No claim in
  this video could be checked against the evidence." Per the design as revised in dcbc97e,
  the reason never lowers a case's severity (the first version's LOW pin and last-place
  sort were removed). D4 dropped (0606f51): `weak_evidence` fires only for deciding claims
  (§11 as written); reasons the judge collects from every claim are unchanged. Cross-check:
  the backend now sends 68/162 in-scope golden videos to review (was 135), equal to the
  golden judge at data/golden-label-set 0fbc68a, where `nothing_judged` matches on all 28
  videos and exact reasons agree on 154/162. The pinned fixture (022ac44) is not re-pinned
  in this change; against it `nothing_judged` is the expected difference (28 videos).
- **2026-11-24**: T36 (no issue; design §12, §14) traceable analysis version by the
  automated build: graph results store `graph_v1+<short sha>+p<routing hash>` and a
  `routing_snapshot` JSON column (migration 0015, chained on T33's 0014). Old `graph_v1` rows still read. 1467 passed locally with Postgres 16 +
  pgvector (4 OCR-tool skips only). Decisions in §7aa.
- **2026-11-24**: T33 (no issue; design §15, §17) per-user ownership on every read by
  the automated build: `videos.user_id` (migration 0014, chained on T31's 0012), owner or
  reviewer/admin rule in `ownership.py` for every job, video, result and review route
  (404 for others), legacy NULL-owner rows admin only, per-user duplicate detection,
  `submitted_by` on jobs, results and review cases, own-video decisions refused,
  `scripts/assign_owners.py` for legacy rows. 1270 passed, 0 skipped. Decisions in §7z.
- **2026-11-24**: T32 (no issue; design §11, §12, §17) request review by the automated
  build: `POST /v1/jobs/{job_id}/review-request` opens a `user_requested` case with a
  required note (audit-logged), idempotent per job, access via `ownership.py` (404 for
  others). No migration. 1204 passed, 0 skipped locally with Postgres 16 + pgvector.
  Real per-user restriction waits for T28/T33. Decisions in §7y.
- **2026-11-23**: T31 (no issue; design §6, §8, §12) "How we searched" per claim by the
  automated build: `retrieve_evidence` records a `search_trail` per round (queries run,
  hits, filters, dedup, cache, references consulted); persisted to `claims.search_trail`
  (migration 0012) with retrieved / screened / kept counts and budget used; returned as
  `claims[].search_trail` by every result endpoint. No keys, request URLs or prompts in it;
  retrieval and verdicts unchanged (tested). 1155 passed, 4 skipped (OCRmyPDF/Tesseract)
  locally with Postgres 16 + pgvector; no spend. Decisions in §7w.
- **2026-11-23**: T28 (no issue; design §1, §16, §17) job progress for the stepper by the
  automated build: `job_events` + §1 states next to the legacy status, 8 pipeline steps
  logged from the worker (graph via LangGraph "tasks" streaming), per-user job ownership
  (`jobs.user_id`, 404 for others' jobs), `GET /v1/jobs/{id}/events`, jobs list with
  total, search and status filter. Migration 0011. Results unchanged; no model calls.
  Decisions in §7w.
- **2026-11-23**: T27 (no issue; design §12, §15, §17) review HTTP API and roles by the
  automated build: `/v1/reviews` queue (severity then age, filters, pages), case with
  audit trail, decisions (approve / correct label and claim verdicts or stances / mark
  insufficient / reject / request re-analysis, reason required), severity override, and
  `/v1/me`. Roles (analyst/reviewer/admin) only from the JWT's `app_metadata`, enforced
  server-side. No migration. 1107 passed, 0 skipped locally with Postgres 16 + pgvector.
  Per-user ownership (videos.owner) still missing. Decisions in §7u.

- **2026-11-23**: T30 (no issue; D1 = B; design §7, §9, §11, §12) unproven-claim verdict
  by the automated build: UNSUPPORTED for efficacy claims after the full search budget
  finds nothing (code-gated; search errors rule it out); judge rule → MISINFO with
  `misinfo_basis` unproven, always reviewed; `results.misinfo_basis` (migration 0013) and
  `label_display` in the result API and jobs list; judge explanations in display wording.
  Review-reason text in analyst wording. Decisions in §7z.

- **2026-11-24**: T26 (no issue; design §12, §17) result API fields by the automated
  build: stance rationale and quoted segments, claim modality and source segments,
  transcript/OCR segments, evidence source kind/year/publisher/abstract snippet, critic
  notes, review case id/status (incl. resolved)/severity and structured reasons from one
  wording table; §17 `/v1` reads, all behind one access check that T27 fills in with its
  owner column. `review` stays set once resolved. No migration.
  Decisions in §7v.

- **2026-11-23**: T29 (no issue; design §12, §15, §17) signed playback URL by the automated
  build: `GET /v1/jobs/{job_id}/playback`, 10-minute signed Supabase read URL, owner check
  through the shared `ownership.py` hook (404 for others), no-store, URL never logged.
  Export not built (lead D7). 23 new tests; 1081 passed, 0 skipped locally (after rebase onto T26) with Postgres 16
  + pgvector. Real per-user enforcement waits for T28/T33's owner columns. Decisions in §7x.
- **2026-11-23**: T25 (no issue; design §6, §7, §14) extra-evidence-sources experiment
  by the automated build, report only. The 60 INSUFFICIENT_EVIDENCE claims in the 39 golden-set videos whose source says false but derive CANNOT_RECOGNIZE were searched in Cochrane (PubMed), Europe PMC, ClinicalTrials.gov v2 and the reference allow-list (`backend/scripts/t25_extra_sources.py`, no model calls, no fact-check databases). Judged under the unchanged §7: 0 claims and 0 videos become decidable; hits are Cochrane reviews that themselves find too little, related but different interventions, animal/cross-sectional work, or registry entries without results. Europe PMC and ClinicalTrials.gov were proxy-blocked at first but reachable for the full run. Near misses for a person: v159 (needs a jogging MET source), v85 (2026 PNAS null). Report: `evals/reports/T25_extra_sources.md`.
- **2026-11-23**: T23 (no issue; design §14, §16) backend CI by the automated build:
  GitHub Actions on PRs to `langgraph-build`/`main` with a pgvector Postgres service, Redis
  and OCR tools, failing on any skipped test; `backend/*.egg-info` untracked. Locally on a
  fresh Python 3.11 env with Postgres 16 + pgvector: 952 passed, 0 skipped (was 945 passed,
  7 skipped without the services). Decisions in §7t.

- **2026-11-23**: T24 (no issue; design §9, §14) judge cross-check by the automated
  build. Backend judge vs the golden set's independently written judge on all 82 golden
  videos (248 claims): labels 82/82 and deciding claims 66/66 agree; review reasons agree
  exactly on 48/66, the rest are four classified review-reason differences (three where
  the backend matches §9, one backend extension for a person to decide). No backend
  change, no model calls. Golden-set judge differences listed in the PR for the branch
  owner. Decisions in §7s.
- **2026-11-23**: T22 (no issue; design §11, §12) by the automated build: severity for
  review priority. Draft table in `config/severity.yaml` (categories seeded from T09's
  high-risk list + text topics), video severity = highest among MISINFO-relevant claims,
  queue by severity then age, reviewer overrides with reason logged to a new
  `audit_events` table (migration 0010). Labels and verdicts untouched. Table needs the
  project lead's, Dr. Brooks's and WHO's sign-off. Decisions in §7r.
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
