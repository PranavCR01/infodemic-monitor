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
