# T70: claim context (switch `CLAIM_CONTEXT`, OFF)

Tune split only, offline, no model calls, $0. These are development numbers, not product accuracy.

- Full tables: `gate.md`. Raw output: `results.json`.
- Scripts: `backend/scripts/t70_claim_context_gate.py` and `backend/scripts/t70_off_fingerprint.py`.
- Harness: `backend/app/evaluation/claim_context_gate.py`.
- Paid-run proposal: `run_t70.py` and `estimate.json`.

## Trigger

Tune video v135 (labmuffin benzene, golden NO_MISINFO) came out MISINFO in production jobs cf2ea579, f85f2daa and 008c97a3. Each time the label was decided by "Benzene doesn't get through skin easily". The video means one thin layer of a benzoyl-peroxide acne cream with 2-20 ppm benzene. The verifier judged that sentence against reviews of occupational solvent exposure.

## What was built (all behind `routing.CLAIM_CONTEXT = False`)

| Part | What it does |
| --- | --- |
| (a) extract_v5 | Each claim may carry a structured `context`: `subject`, `exposure`, `amount`, `population`, `outcome` and `scope` (`specific` or `universal`). Every item cites block IDs.<br>Code keeps an item only if all of its cited blocks exist and at least half of its content words appear in them. This is the same rule a claim's own text must pass. Dropped items are named in `ClaimContext.dropped`.<br>`claim_text` stays verbatim.<br>`outcome` is an addition to the row's list (see Deviations). |
| (b) video topic | The first window's tool asks for `video_topic`, a one-line topic with its block IDs, grounded like a context item. It is asked exactly once.<br>Later windows of a long video see the topic as a fenced block. It is stored as the state field `video_topic`. Claim context is read against it (extract_v5 rule 9, plus the verifier's context block). |
| (c) planner | A claim with grounded, specific context gets extra rungs, run first:<br>- the claim's intervention (or the context subject's) AND the exposure facets (`dermal`, `cosmetic`, `inhalation`, `oral`, `occupational`) from a small cue table;<br>- the context's population or condition, through the MeSH lexicon, when the claim names none.<br>For v135 008c97a3 the first rung is `benzene AND (Skin Absorption OR dermal OR percutaneous OR topical)`. The plan records which facets it used. |
| (d) verify_v4 | A claim judged in context gets its context fenced next to it, with the instruction to judge it as meant. T69's `evidence_context` field is reused, with one value added (see the mapping below). It is required on every verdict. Claims judged in context must also answer `contradicted_as_stated`.<br>Code derives three things:<br>- `setting_match` (`same`, `partial` or `different`), stored as the limitation code `setting_match:<v>`;<br>- T69's code `evidence_context_mismatch:<kind>`, on a CONTRADICTED verdict about another setting or population;<br>- `softened_by_context`, when the claim is contradicted as stated but not as meant. |
| (e) guardrail | A claim is `specific` only when the model said so AND at least one item survived grounding. Every other claim is `universal` and is judged as stated:<br>- the verifier sees no context, and the planner adds none;<br>- no mismatch code and no softening code is kept;<br>- an answer that sets `contradicted_as_stated` for a universal claim is rejected.<br>Ungrounded items never reach the verifier, the planner or the report. |
| judge | One set-aside mechanism, shared with T67 and T69. A softened claim keeps its verdict but cannot decide, and it raises `softened_by_context:<cid>`, which always goes to review. T69's context-mismatch rule also runs under `CLAIM_CONTEXT`. |
| (f) report/API | Each claim gains `context` (items, scope, video topic, `setting_match`, `softened`, search facets) and `context_text` ("In context: ..."). A screen-only claim gets `quote_source: "screen"` and a `screen_quote` from the OCR segments it cites, so it shows "On screen: ..." and never "The speaker says". These fields are omitted from the JSON when empty.<br>T69/T70 codes never appear in the limitations shown to readers.<br>The context is stored inside the claim's search-trail JSON, the way T65 (f) stored source_meta, so no migration is needed.<br>Frontend: the export and the claim card show the context line and use "On screen:". |
| (g) switch | `routing.CLAIM_CONTEXT = False`. Turning it on also needs routing.yaml to route `extract_claims` to `extract_v5` and `verify_claims` to `verify_v4`. The nodes refuse to build otherwise. |

### `setting_match` and T69's `evidence_context`: one field, mapped

The model answers one field. `setting_match` is derived from it and is never asked separately.

| `evidence_context` (the verifier's field) | asked when | `setting_match` | T69 code (CONTRADICTED only) |
| --- | --- | --- | --- |
| `matches` | T69 on, or T70 on | `same` | none |
| `partial` | T70 on only | `partial` | none |
| `different_population` | T69 on, or T70 on | `different` | `evidence_context_mismatch:different_population` |
| `different_exposure_setting` | T69 on, or T70 on | `different` | `evidence_context_mismatch:different_exposure_setting` |

When T70 is on, a universal claim keeps only `setting_match`. That code is informational and the judge never reads it. A universal claim keeps no T69 code, so the T69 set-aside cannot soften it.

## Gate (h): what is mocked

| Part | Status |
| --- | --- |
| Extraction parsing and grounding, planner, verifier node, judge, review policy | **Real code** |
| Claims, sources, stances, kept evidence, stored verdicts | **Recorded** (production rows) |
| extract_v5 context items and topic; verify_v4 structured answers; the skin claim's verdict as meant | **Mocked**: hand-written |

The mocked replies show what the code does with such answers. They **cannot show what a model would answer**: whether extract_v5 finds this context, and whether verify_v4 changes its verdict. PubMed is not called, so the new context rungs are planned and recorded but not searched. In this gate the verifier saw the evidence production kept, not what the new rungs would find.

### 1. v135 production fixtures (golden NO_MISINFO)

| job | off (stored replay = prod) | on: judged as meant (mock) | on: still contradicted, setting flagged (mock) | on: model ignores context (mock) |
| --- | --- | --- | --- | --- |
| cf2ea579 | MISINFO, skin claim decides | **NO_MISINFO + review** (`softened_by_context`) | **NO_MISINFO + review** (`contradiction_context_mismatch`) | MISINFO, skin claim decides |
| f85f2daa | MISINFO, skin claim decides | **NO_MISINFO + review** | **NO_MISINFO + review** | MISINFO |
| 008c97a3 | MISINFO, skin claim decides | **NO_MISINFO + review** | **NO_MISINFO + review** | MISINFO |

- **Fixed, with the switch on and a verifier that uses the context.** The skin claim never decides MISINFO. The video comes out NO_MISINFO and is always reviewed.
- **Not fixed if the model reads the context but ignores it** (last column). Only the paid run can say how often that happens.
- **Grounding on the real segments.** Every stored claim passes extract_v5 grounding verbatim (0 dropped). The deliberately ungrounded population item ("teenagers using prescription retinoids", citing t18) is dropped. The "known carcinogen" claim, marked universal, keeps no context code.

### 2. Vitamin K fixtures

| job | prod | off (current code) | on (mocked context on "a potentially devastating condition") |
| --- | --- | --- | --- |
| 5cc07f48 | MISINFO (unproven) | NO_MISINFO | NO_MISINFO (identical label and reasons) |
| d2bf4179 | MISINFO (unproven) | NO_MISINFO | NO_MISINFO (identical) |
| 3d48e75e | NO_MISINFO | CANNOT_RECOGNIZE (analysis_incomplete) | CANNOT_RECOGNIZE (identical) |

The vague claim's context (population "newborn babies", outcome "potentially life threatening bleeding") gives the planner a first rung: `vitamin K AND newborn AND bleeding`. T64 (c) still reads the claim's own words, so context does not reopen UNSUPPORTED.

### 3. T66 recorded videos (A, 18 finished) and golden claims (B, 48 in scope)

| config | A correct | B correct | labels changed vs off |
| --- | --- | --- | --- |
| off (as shipped) | 11/18 | 43/48 | none |
| on, stored verdicts | 11/18 | 43/48 | none (A and B) |
| upper_mismatch: a different setting flagged on every CONTRADICTED verdict | 11/18 | 42/48 | B: v119 |
| upper_soft: every endorsed or refuted CONTRADICTED claim softened as meant | 8/18 | 28/48 | A: 6 videos; B: 15 videos |

**Accuracy vs T66.** It is not below T66: 11/18, which is T66 plus T67 change 1, as shipped. No stored verdict carries a T70 code, so "on" can only show that turning the switch on changes nothing by itself. The real effect needs the paid run.

### MISINFO videos softened to a milder label, per video

**With the switch on and the stored verdicts: zero.** On A (v11, v120, v122, v23, v65, v78, v87, v88, v92) and on B, every video labelled MISINFO today stays MISINFO.

The two upper bounds are counterfactual. They show how far the code would let a wrong model go, and where a person still catches it.

| video (gold) | off | upper_soft | upper_mismatch |
| --- | --- | --- | --- |
| A v11 (CANNOT_RECOGNIZE) | MISINFO | NO_MISINFO, **softened, reviewed** | MISINFO, kept |
| A v122 (MISINFO) | MISINFO | NO_MISINFO, **softened, reviewed** | kept |
| A v65 (CANNOT_RECOGNIZE) | MISINFO | NO_MISINFO, **softened, reviewed** | kept |
| A v88 (MISINFO) | MISINFO | CANNOT_RECOGNIZE, **softened, reviewed** | kept |
| A v78, v87, v120, v23, v92 | MISINFO | kept | kept |
| B v21, v27, v109, v114, v122, v131, v177 (all gold MISINFO) | MISINFO | NO_MISINFO, **softened, reviewed** | kept |
| B v78, v87, v88, v111 (gold MISINFO) | MISINFO | CANNOT_RECOGNIZE, **softened, reviewed** | kept |
| B v119 (gold MISINFO) | MISINFO | CANNOT_RECOGNIZE, softened, reviewed | CANNOT_RECOGNIZE, **softened, reviewed** (= T69's upper bound) |
| B v86 (gold MISINFO) | MISINFO | MISINFO (denies_supported), kept | kept |

In every softened case the video is sent to review with `softened_by_context` or `contradiction_context_mismatch`. Context never changes a label silently. The upper_soft row is the residual risk: if extraction marks a sweeping claim "specific" and the verifier softens it, the label is milder until a person checks it.

The universal-scope guardrail is what stops this for claims like "vaccines cause autism" (tested end to end). How often the model marks a universal claim specific is unmeasured.

### Flag off = byte-identical (g)

`backend/scripts/t70_off_fingerprint.py` runs a full mocked graph run on two inputs: the test suite's two-claim sample, and the v135 008c97a3 transcript (30 claims, 62 model requests). It produces sha256 fingerprints of:

- every model request (step, prompt version, system prompt, input);
- the final state;
- the classification;
- the persisted rows (result, claims with search trails, verifications, evidence links);
- the API claim views.

It was run in this tree and in a worktree of `origin/langgraph-build` @ c5fdec5 (pre-T70; it imported the base code, which has no `claim_context`). **All 10 fingerprints are identical** (`off_fingerprint_base.json` = `off_fingerprint_t70.json`).

## Token increase per claim (estimate)

These are characters / 4. No tokenizer is available offline. They come from requests built by the real code on v135; extraction output uses the mocked reply.

| | 008c97a3 (19 claims) | cf2ea579 (13 claims) |
| --- | --- | --- |
| extraction input, per claim | +65 | +95 |
| extraction input, per video | 6,067 → 7,304 (+20%) | 3,993 → 5,230 (+31%) |
| extraction output, per claim | +8 | +9 |
| verifier input, per claim: universal (as stated) | +325 (+7%) | +325 (+6%) |
| verifier input, per claim: specific (in context) | +483 (+10%) | +463 (+9%) |
| verifier output, per claim | ≤ +21 | ≤ +21 |

Of the verifier increase, +203 comes from the longer verify_v4 system prompt, which is sent with every call. Prompt caching would make most of that cheap. The rest is the tool schema, the scope line and the context block.

## Paid tune-split run: PROPOSED ONLY, not run

- **Runner:** `run_t70.py`. It is the T66 runner (every provider client inside the SpendGuard) with `CLAIM_CONTEXT` on and the two context prompts. It refuses to run without `--live`, `--approved-by` and `--max-usd`; it refuses `--max-usd` above $35; and it never writes into T66's results.
- **Videos:** T66's 18 finished, plus v21 (partial in T66) and v135 (the trigger, not among T66's 18), in T66's declared order. That is 20 videos, for a paired comparison with T66.
- **Estimate** (`estimate.json`): T66's estimator with the T70 prompts, calibrated by T66's actual/expected ratio of 3.53, gives **$24.27**. The upper bound is $73.34. The same videos cost $22.91 in T66.
- **Cross-check:** adding the measured token increase (about +9% on verifier input, which is 63% of T66's spend, and +20-31% on extraction) to T66's $22.91, plus about $1.7 for v135, gives **about $26**.
- **Proposed cap: $30.** It needs the lead's direct approval.

## Decisions and deviations

1. **`outcome` was added to the context fields.** The row lists subject, exposure, amount, population and scope. `outcome` (the condition a vague claim refers to) is needed to supersede T64(d) ("a potentially devastating condition"). Code treats it like the others.
2. **`contradicted_as_stated` was added** (verify_v4, only for claims judged in context). It is not a second setting field: it asks about the verdict, not the evidence context. It is what lets code detect that context softened a verdict, and send that claim to review instead of letting it change the label silently.
3. **T69's rule runs under `CLAIM_CONTEXT` too** (`routing.context_mismatch_rule_on()`). Without it, the "still CONTRADICTED, setting flagged" answer would leave v135 MISINFO. The T69 switch itself stays off.
4. **Universal claims keep no T69 code under T70**, even though T69 alone would give them one. This is stricter than T69, by design (e).
5. **A set-aside claim no longer decides rule 2 (REFUTES + SUPPORTED) or rule 3 (unproven).** This is a no-op for T67 and T69, which only set aside CONTRADICTED claims. It is needed for softened claims, which can carry any verdict.
6. **"Routing flag" means a module switch** in `routing.py`, as for T67 and T69. The prompts are still chosen in routing.yaml, and the nodes refuse to build with the switch on and the wrong prompts.
7. **The context is stored inside the search-trail JSON**, because migrations are not allowed. `PlanningView` is unchanged, since adding a field would have changed every trail's JSON. The planner's facets are stored in the context payload instead.
8. **The screen-only "On screen:" fix is also behind the switch.** The backend sends `quote_source` only when the switch is on or the claim has context, so flag-off output is byte-identical.

## Left for a person

1. **The paid tune run** ($30 cap proposed). It is the only way to measure what extract_v5 and verify_v4 actually do. The gate's v135 fix rests on mocked replies.
2. **How often the extraction model marks a universal claim `specific`.** This is the residual softening risk (upper_soft), and it is caught only by review.
3. **The critic does not see the context.** In production the critic pushed back on the skin verdict ("the papers contradict the claim"). With T67 change 1 on, that adds `second_check_disagreed` (review) but keeps the verdict. Passing context to the critic is a follow-up.
4. **The reranker still scores against the bare claim text.** Records found by the new context rungs could be ranked below occupational ones.
5. **The exposure-facet cue table is small** and hand-made (5 facets). Grow it from the paid run's misses.
