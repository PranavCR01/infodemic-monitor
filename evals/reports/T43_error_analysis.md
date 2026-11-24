# T43: Error analysis of the T38 routing outputs (tune split), 2026-11-24

**No paid calls were made.** No Anthropic or OpenAI API was called, the T38 runner was
not run with `--live`, and no key was read. Everything below is from the T38 reports,
the golden set (`data/golden-label-set`, read with `git show`), and deterministic code
in `backend/app/evaluation/error_analysis/`. **Tune split only.** The test split was not
read: every golden-set read goes through `TuneSet`, which drops non-tune rows before use,
and that includes the blind re-label CSV.

## Headline

1. **T38 did not keep per-item outputs, so most of the analysis T43 asked for could not
   be done.** `evaluate_candidate` passes each item's answer to the scorer and keeps only
   the score. `claude/report.json` (Claude run) and `openai/full/report.json` (OpenAI run)
   hold per-step aggregates and per-call token/latency records, with no predicted claims
   or labels. The Claude report says so itself ("The runner keeps no per-item
   predictions"). As the task instructs, I stopped those parts:
   - the per-claim extraction error classification of Sonnet and Haiku output,
   - the stance confusion matrix and per-error review of the 15 refuted claims,
   - the per-error verify review, including *which* 4 insufficient→contradicted claims,
   - the bootstrap CIs,
   - the re-score of every step against dcf77b0.

   This PR fixes the cause: the runner now writes `per_item.json`, and
   `python -m app.evaluation.error_analysis analyze` produces all of the above from it.
   See §7 for what re-running would cost.
2. **The extraction ceiling is far below 1.0.** On the 26 tune videos in the blind
   sample, a second careful labelling pass scores only **strict F1 0.68** (95% CI
   0.59–0.76) against the first pass. With the meaning-based matcher it scores **0.79**
   (0.71–0.86). Sonnet's 0.42 (strict) is therefore about 62% of what a second labeller
   reaches under the same matcher, not 42% of perfect. The strict matcher alone costs
   that second labeller 0.11 F1 (paired CI 0.06–0.16).
3. **Gold changes since T38 are small but uneven.** Between 0fbc68a and dcf77b0, 11 tune
   claims changed: 4 were added, 2 were reworded, and 7 verdicts changed. **No stance
   label changed.** The stance winner (Sonnet, +0.12) cannot plausibly flip. The
   extraction winner (+0.059) and the verify winner (+0.069) could in principle flip;
   only a re-run on dcf77b0 settles them (§2).
4. **Found a deterministic bug that caps extraction recall regardless of model.** The
   grounding guardrail (`guardrails/outputs.py:grounding_overlap`) tokenises with
   `[a-z0-9]+`. A claim in a non-Latin script therefore has no words, scores grounding
   0.0, and is dropped as `claim_ungrounded`, even as a verbatim quote. The 4 Hindi gold
   claims in v167 are unreachable for every candidate. The strict matcher has the twin
   bug: `metrics.text_similarity` returns 1.0 for any two all-Devanagari strings.
5. **The extract prompt does not ask for the golden set's quoting conventions.** The
   golden set quotes claims in the original language (62 of 178 tune claims, 35%, are
   non-English), names referents in `[brackets]` (23 claims), and marks elisions with
   `…` (25 claims). `extract_v2` asks for none of these. A model that translates gets
   its claim dropped by the guardrail. A model that paraphrases fails the strict
   matcher. This is the top prompt recommendation (§8).

## 1. What was available

| source | per-item outputs? | what it has |
|---|---|---|
| `auto/T38-live`: `evals/reports/T38_routing/claude/report.json` | **no** | scores, costs, latency, step extras (debunk recall, insufficient→contradicted count) |
| `auto/T38-live`: `smoke_v11/report.json` | no (1 video) | per-call token records only |
| `auto/T38-openai`: `openai/full/report.json`, `combined/report.json` | **no** | as above, with `calls_summary` |
| `app.evaluation.selection.evaluate_candidate` | discards them | `outputs` goes to `scorer(...)` and is dropped |

The blind re-label's second pass (`blind/model_relabel_claims.csv` on
`data/golden-label-set`) is the only per-claim extraction output available. It is a
Claude labelling pass that followed the labelling guide, not a T38 candidate. §3 uses it
as a **proxy** to calibrate the matcher and the error categories, and it is labelled as
such wherever it appears.

## 2. Golden set: dcf77b0 vs the T38 run's 0fbc68a (tune split)

Data: `evals/reports/T43/gold_diff_0fbc68a_dcf77b0.json`
(`python -m app.evaluation.error_analysis gold-diff --old 0fbc68a --new dcf77b0`).
No video joined or left the tune split, no scope tag changed, and no tune transcript
changed.

| claim | change | stance | verdict (0fbc68a → dcf77b0) | T38 items touched |
|---|---|---|---|---|
| v11:c3 | verdict | ENDORSES | SUPPORTED → **MIXED** | verify |
| v21:c2 | text + verdict | ENDORSES | INSUFFICIENT_EVIDENCE → **CONTRADICTED** | extract, stance, verify |
| v21:c7 | added | ENDORSES | (new) INSUFFICIENT_EVIDENCE | extract, stance, verify |
| v22:c1 | verdict | ENDORSES | INSUFFICIENT_EVIDENCE → **SUPPORTED** | verify |
| v23:c1 | text + verdict | REFUTES | CONTRADICTED → **INSUFFICIENT_EVIDENCE** | extract, stance, verify |
| v36:c6 | added (screen infographic) | ENDORSES | (new) UNSUPPORTED | extract, stance, verify |
| v36:c7 | added (screen infographic) | ENDORSES | (new) UNSUPPORTED | extract, stance, verify |
| v36:c8 | added | ENDORSES | (new) INSUFFICIENT_EVIDENCE | extract, stance, verify |
| v71:c6 | verdict | ENDORSES | MIXED → **INSUFFICIENT_EVIDENCE** | verify |
| v109:c6 | verdict | ENDORSES | INSUFFICIENT_EVIDENCE → **CONTRADICTED** | verify |
| v120:c1 | verdict | ENDORSES | INSUFFICIENT_EVIDENCE → **UNSUPPORTED** | verify |

Items touched: extract 3 of 48 videos (gold claims 174 → 178); stance 6 claims (4 new,
2 reworded, **0 relabelled**); verify 11 claims. Gold UNSUPPORTED on tune goes from 5 to
8, and UNSUPPORTED is the class the verify macro-F1 is most sensitive to.

**Re-score of every T38 step metric against dcf77b0: not possible.** It needs the saved
outputs, and there are none. The side-by-side table below shows what is known. The
dcf77b0 column cannot be filled honestly.

| step | candidate | 0fbc68a (T38) | dcf77b0 |
|---|---|---|---|
| extract_claims (claim_f1, strict) | claude-sonnet-5-5 | **0.4193** | not computable (no outputs) |
| | claude-haiku-5-5 | 0.3601 | not computable |
| | gpt-5.6-luna | 0.3237 | not computable |
| analyze_stance (macro-F1) | claude-sonnet-5-5 | **0.6436** | not computable |
| | claude-haiku-5-5 | 0.5230 | not computable |
| | gpt-5.6-luna | 0.4977 | not computable |
| verify_claims (macro-F1) | claude-opus-5-5 | **0.6759** | not computable |
| | claude-sonnet-5-5 | 0.6073 | not computable |
| | gpt-5.6-terra | 0.4919 | not computable |

**Does the winner per step change?** These are bounds from the counts alone, not
measurements:

- **Stance: no, in any realistic case.** No stance label changed. The 4 added claims have
  no T38 output and would be scored only after a re-run. Only 2 items with outputs
  changed (their claim text was reworded: v21:c2 and v23:c1). Even if both went
  maximally against Sonnet, the shift (≲0.07 macro-F1) is below Sonnet's 0.12 margin.
- **Extraction: probably not, but a flip can't be excluded.** 6 gold claims changed (3
  videos). Under strict F1 each change moves a candidate's matched count by at most 1. In
  the worst case (every change against Sonnet and for Haiku) the margin moves by about
  0.06–0.07, the size of the margin itself.
- **Verify: unknown, and it could flip.** 5 relabelled items have outputs. 3 of them
  move into or out of the rare classes (MIXED, UNSUPPORTED, CONTRADICTED), where one
  item moves that class's F1 by 0.1–0.3 (about 0.02–0.05 macro over 6 classes). That is
  comparable to Opus's 0.069 margin. Re-running verify also needs **re-frozen evidence**:
  `FrozenEvidence.entry` refuses v21:c2 and v23:c1 ("text changed since the evidence was
  recorded"), and the 4 new claims have no evidence yet. `freeze-evidence --resume` is
  free (PubMed only).

## 3. Extraction

### 3a. The matchers (documented in `error_analysis/matching.py`)

- **Strict (what T38 scored with):** `metrics.match_claims`. Token Jaccard over all
  lower-case alphanumeric tokens, stop words included, threshold 0.5, greedy one-to-one.
  "Turmeric cures cancer" vs "the speaker says turmeric can cure cancer" scores
  2/8 = 0.25, a miss.
- **Meaning-based (new, deterministic, no model, no embeddings):** the rule the golden
  set's blind comparison used (`scripts/compare_blind.py`), without its hand-made
  matches:
  1. Content words: lower-case, accents stripped, 3+ characters, the same EN/ES/FR
     stop-word list, and a light suffix strip so cure/cures/cured/curing agree.
  2. Overlap coefficient |A∩B| / min(|A|,|B|), with at least 2 shared words.
  3. A pair matches at ≥ 0.6, or at ≥ 0.34 when both claims have time spans that overlap
     within ±3 s.
  4. Matching is greedy and one-to-one.

  It is lenient about a short claim inside a long compound one and strict about synonyms
  that share no words. I did not judge any match by reading; every number here is from
  this code.

### 3b. Ceiling from the blind re-label's two-pass agreement

The blind re-label's comparison file (`blind/model_relabel_comparison.md`) gives 124
matched of 141 first-pass and 153 second-pass claims over **all 41** blind videos. That
is F1 = 2·124/(141+153) = **0.84**, using its time-aware matcher plus 8 hand matches.
Those 41 videos include test-split videos. I used only that file's aggregate and
re-computed on the **tune** videos alone:

| tune blind videos (n = 26 in scope) | first-pass claims | second-pass claims | strict F1 (95% CI) | meaning F1 (95% CI) |
|---|---|---|---|---|
| second pass vs **0fbc68a** (true two-pass agreement) | 117 | 127 | **0.680** (0.586–0.761) | **0.787** (0.708–0.856) |
| second pass vs **dcf77b0** (adjudicated; biased upward, since adjudication used the second pass) | 121 | 127 | 0.702 | 0.806 |

CIs are bootstraps over videos (1000 resamples). Meaning minus strict on the same
resamples is +0.107 (paired CI 0.056–0.164). Both passes are Claude labelling passes,
so their errors may be correlated. A human ceiling could be lower.

**Reading T38 against this:** Sonnet's strict 0.419 is 62% of the two-pass strict
ceiling (0.68). Haiku's 0.360 is 53% of it. Extraction is still the weakest step, but
"F1 ≤ 0.42" overstates how far it is from labeller-level agreement. More than half of
Sonnet's gap to 1.0 (0.32 of 0.58) is disagreement that careful labellers also have.

### 3c. Error categories (proxy: blind second pass vs first pass, tune, 26 videos)

Rules: `error_analysis/extraction.py`. Each unmatched claim gets one category, first rule
that fires. **This is not a T38 candidate's output.** It shows what the categories look
like on real disagreements and where the categoriser is weak. The same code runs on a
T38 candidate once `per_item.json` exists.

| unmatched gold (first pass) | n | unmatched predicted (second pass) | n |
|---|---|---|---|
| missed | 17 | split_or_merged | 20 |
| reworded_same_meaning | 9 | non_health_or_not_a_claim | 11 |
| split_or_merged | 6 | reworded_same_meaning | 8 |
| screen_only_missed | 2 | translated | 3 |
| | | ocr_noise_derived | 2 |
| | | hallucinated | 0 |
| **total unmatched** | **34 of 117** | **total unmatched** | **44 of 127** |

Known weaknesses, visible in the examples below:
- `split_or_merged` is over-assigned when claims share a bracketed referent or topic
  words (v109's "[… puede darte] pancreatitis" pairs).
- `ocr_noise_derived` catches *correct* caption claims that the first pass missed. v36's
  infographic claims were added to the gold set in dcf77b0.
- `non_health_or_not_a_claim` mixes over-extraction with gold misses by design. The
  counts are indicative, and the examples matter more.

### 3d. Ten worked examples (proxy; short excerpts)

1. **reworded_same_meaning** (v21). Gold: "Almonds are naturally rich in tryptophan, an
   amino acid that plays a key role in the production of serotonin…". Second pass:
   "You'll sleep better. Almonds are naturally rich in tryptophan … serotonin, the sleep
   hormone". Same claim. Strict rejects it (the extra lead-in and `…` dilute the Jaccard
   score); meaning accepts it.
2. **reworded via brackets** (v120). Gold: "los beneficios son muchísimo primero elimina
   los metales pesados del cuerpo". Second pass: "[el agua de mar] elimina los metales
   pesados del cuerpo". The bracketed referent plus trimming changes enough tokens to
   fail strict.
3. **split_or_merged** (v100, screen-only, Spanish). Gold has 3 caption claims:
   "Logran revertir la diabetes tipo 1…", "…tipo 2…", "Científicos chinos logran que el
   páncreas…". The second pass merged all three into one caption string. One merge, so
   3 gold misses and 1 extra under strict.
4. **split_or_merged** (v68). Gold keeps one question-shaped claim, "does tap water lower
   testosterone … do endocrine disruptors lower testosterone". The second pass split it
   into "Tap water does not lower testosterone", "atrazine is commonly found in tap
   water", and "[Atrazine is] an endocrine disruptor".
5. **translated** (v167, Hindi). Gold quotes the Devanagari transcript. The second pass
   wrote English glosses in brackets ("[if you don't give cancer sugar, carbohydrates,
   roti, the cells die…]"). In the pipeline both forms are dropped: the gloss is
   ungrounded and the Devanagari quote is tokenised away (§3e).
6. **ocr-derived, actually a gold miss** (v36). Second pass: "Irish Sea Moss: Cures
   Thyroid Issues", "Burdock Root: Rids Kidney & Gallbladder Stones" (infographic
   captions). Absent from 0fbc68a; v36:c6–c7 were added in dcf77b0. These count against
   any extractor that reads captions correctly under the T38 gold.
7. **missed** (v122, Spanish). Gold has 6 statin and CoQ10 claims ("El tratamiento con
   estatinas se asoció con un 46% más de riesgo de la diabetes tipo 2", …). The second
   pass extracted only "[las estatinas] trae demencia". The comparison file attributes
   this to its transcript viewer truncating long lines, so it is a tooling miss, not a
   reading miss.
8. **non_health_or_not_a_claim** (v69). Second pass: "three things you could start doing
   today to make yourself cancer proof naturally" and "when you survey people, fewer
   than half the people actually knew that". Teasers and framing, not checkable claims.
9. **polarity** (v24). Gold (REFUTES): "[Cheerios carry harmful] glyphosate residues…".
   Second pass: "Cheerios do not have high amounts of glyphosate residues…". It stores
   the speaker's correction instead of the myth, so the same proposition has opposite
   polarity. It fails both matchers, and it would flip the stance if matched. This is
   rule 4 of the prompt, and the blind comparison found both of its stance
   disagreements were this artefact.
10. **missed, partial overlap** (v141, French). Gold: "Ce gamin de 15 ans a inventé un
    remède contre le cancer". Second pass: "[Heman Bekele] a fabriqué un savon qui …
    traite le cancer de la peau". Related claim, different assertion (skin cancer, soap).
    Correctly not matched.

### 3e. Deterministic findings (no outputs needed)

- **Devanagari claims are unreachable.** `grounding_overlap(t, t) == 0.0` for the v167
  claims, so `extract_window` drops any Devanagari claim as `claim_ungrounded`. An
  English translation is dropped too, because its words are not in the source. That is
  4 of 178 tune gold claims (2.2% of recall) lost for every candidate. Separately,
  `metrics.text_similarity` returns 1.0 for two token-less strings, so any Devanagari
  prediction would "match" any Devanagari gold claim. Both bugs share one fix:
  Unicode-aware tokenisation (`\w+` with `re.UNICODE`, or `str.isalnum`).
- **Accented words split.** "reprogramación" becomes "reprogramaci" + "n" in both the
  guardrail and the strict matcher. This is harmless for verbatim quotes, but it
  penalises a claim whose accents differ from its source text.
- **Language exposure.** 15 of 48 in-scope tune videos are `other_language`, with 62 of
  178 gold claims (35%).
- **Screen-only exposure** (for the no-OCR ablation). 7 tune gold claims are
  `source = screen`, 156 `both`, and 15 `speech`. Without OCR, at most the 7 screen-only
  claims become impossible to find. Precision may rise, because caption noise
  (watermarks, usernames) disappears.

## 4. Stance (analyze_stance)

The confusion matrix and the error-by-error review are **not possible** (no per-item
outputs). From the T38 aggregates (`extras`):

| candidate | macro-F1 | refutes recall (n = 15) | refutes missed | of which read as ENDORSES | of which read as QUOTES/NEUTRAL/UNCLEAR |
|---|---|---|---|---|---|
| claude-sonnet-5-5 | 0.6436 | 0.800 | 3 | 1 | **2** |
| claude-haiku-5-5 | 0.5230 | 0.667 | 5 | 1 | **4** |
| gpt-5.6-luna | 0.4977 | 0.600 | 6 | 1 | **5** |

So **most debunk misses are not read as endorsement. They land on a non-committal
label.** Gold uses NEUTRAL 0 times and UNCLEAR twice in 178 tune claims, while the
prompt offers both.

Gold-side patterns in the 15 refuted tune claims (from `claims.csv`; which claims the
models missed is unknown):

| pattern | claims | why it is a hazard |
|---|---|---|
| the claim text carries a reporting or debunk frame | v65:c1 "salt we were told is this devil white powder…", v70:c3 "this post wrongfully insinuate[s] that almond and oat milk cause cancer…", v39:c2 "that carbs make you fat", v39:c5 "that vegetables are bad for you" | The model must judge the embedded proposition, not the frame. "we were told" invites QUOTES. "wrongfully" inside the claim invites ENDORSES (of the correction). |
| question-shaped claim | v68:c1 "does tap water lower testosterone … do endocrine disruptors lower testosterone" | the stance is the speaker's answer |
| no correction cue in the claim text itself | v23:c1–c3, v24:c1, v39:c1, v39:c3–c4, v65:c2 | the correction must come from other segments in the stance context |
| the claim is advice the speaker argues against | v79:c1 "…five separate visits for vaccines rather than giving them all in the same day", v70:c1 | REFUTES of a recommendation |

## 5. Verify (opus winner)

Per-error review: **not possible** (no outputs). From aggregates: Opus and Sonnet each
called **4** claims CONTRADICTED where gold says INSUFFICIENT_EVIDENCE. UNSUPPORTED
recall was 1.0 for both (n = 5), so none of the 4 is an UNSUPPORTED claim. Which 4 they
are, and whether they overlap between the models, cannot be recovered. Under dcf77b0, 2
INSUFFICIENT claims became CONTRADICTED (v21:c2, v109:c6) and one CONTRADICTED became
INSUFFICIENT (v23:c1). So some of the 4 "errors" may now be correct, and this count
should be recomputed on dcf77b0 before acting on it.

## 6. Bootstrap 95% CIs

**Not computable for T38** (no per-item outputs). The code is ready
(`error_analysis/bootstrap.py`: 1000 resamples over items, seed 43, percentile CI;
the margin CI is paired on the same resamples and reports the share of resamples where
the winner is not ahead).

| step | candidate | score | 95% CI | winner's margin (paired 95% CI) |
|---|---|---|---|---|
| extract_claims | sonnet / haiku / luna | 0.419 / 0.360 / 0.324 | not computable | +0.059: not computable |
| analyze_stance | sonnet / haiku / luna | 0.644 / 0.523 / 0.498 | not computable | +0.121: not computable |
| verify_claims | opus / sonnet / terra | 0.676 / 0.607 / 0.492 | not computable | +0.069: not computable |

For scale, the only real per-video extraction data (the §3b proxy, 26 videos and 117
gold claims) gives a strict-F1 CI half-width of about **±0.09**. With 48 videos a
candidate's own CI is plausibly about ±0.06–0.07, comparable to the extraction margin
(0.059). A paired CI is narrower than that, so the margin may still be significant. Only
the outputs can tell.

## 7. Re-running to get the per-item outputs (needs approval; not done)

The runner now saves them (`per_item.json`: each item's id, gold and output; extraction
outputs keep text, time span, source pieces, category, and the node's errors such as
`claim_ungrounded`). Cost of a re-run is taken from T38's actual spend, not from an
estimate:

| scope | approx. cost (T38 actuals) |
|---|---|
| extract sonnet + haiku | $1.26 |
| stance sonnet + haiku | $1.47 |
| verify opus + sonnet | $9.08 |
| all Claude candidates | ≈ $11.8 |
| no-OCR extraction ablation (sonnet), separate approval | ≈ $1.20 |

Do it on **dcf77b0** after `freeze-evidence --resume` (free), then run
`python -m app.evaluation.error_analysis analyze --per-item <dir>/per_item.json
--golden-ref dcf77b0 --out …`. A cheaper first step is extraction plus stance only
(≈ $2.7), where the prompt recommendations below apply.

## 8. Recommendations, ranked

How to read the evidence labels: **[code]** = a deterministic fact verified in code or
data; **[gold]** = a mismatch between the prompt and the golden-set guide, or a pattern
in the gold labels; **[agg]** = from T38 aggregate numbers; **[proxy]** = from the blind
second pass. None of them is from observed T38 per-item errors, which don't exist.

### Before changing any prompt (prerequisites; no prompt or routing change)

0a. **Save per-item outputs and re-run on dcf77b0** (§7). Without them, a prompt change
    can't be attributed or bootstrapped. **[code]**
0b. **Fix Unicode tokenisation** in `grounding_overlap` and `metrics._tokens` (§3e).
    This recovers v167 (2.2% of tune recall) and stops the Devanagari 1.0-similarity
    artefact. It is a pipeline change, so it is listed here and not made. **[code]**
0c. **Report meaning-based F1 next to strict.** Strict costs a second labeller 0.11 F1.
    A prompt change that only rewords claims would look like a gain or a loss under
    strict with no change in meaning. **[proxy]**

### extract prompt (extract_v2 → v3), ranked by expected effect

1. **"Quote in the original language; never translate."** 35% of tune gold claims are
   non-English. A translated claim is always lost: the guardrail drops it as ungrounded
   (its words aren't in the source), and it can't match the gold quote. The prompt is
   silent on language. **[code][gold]**
2. **Adopt the guide's quoting conventions.** Name a pronoun's referent in `[square
   brackets]`, mark dropped words with `…`, and keep the claim to the assertion's own
   words (no lead-ins like "You'll sleep better." or "the speaker says"). 23 of 178
   gold claims use brackets and 25 use elisions, and strict Jaccard counts every extra
   word.
   **[gold][proxy]**
3. **Make the granularity rule match the gold.** Split different predicates ("prevents
   flu *and* cures pneumonia"). Keep one predicate with a list of objects as one claim
   ("seed oils are unhealthy, leads to inflammation, heart disease, obesity" is one gold
   claim). Keep a question-shaped claim whole. Add the counter-example to rule 1.
   split_or_merged is the largest unmatched-prediction category in the proxy. **[gold][proxy]**
4. **State the myth, not the correction** (strengthen rule 4 with a negation example:
   "Cheerios do not have harmful glyphosate levels" → claim "Cheerios carry harmful
   glyphosate residues"). A polarity flip fails both matchers and reverses the stance.
   **[proxy][gold]**
5. **Expand "What is NOT a claim"** with teasers and framing ("three things you can do
   to be cancer proof"), audience or survey remarks, and rhetorical set-ups. These are
   the bulk of the proxy's non_health_or_not_a_claim extras. **[proxy]**
6. **Captions stated as fact are claims, one per caption line** (v36 infographic lines;
   v100 merged three caption claims into one). Measure this together with the no-OCR
   ablation (§9). **[gold][proxy]**

### stance prompt (stance_v1 → v2), ranked

1. **Judge the embedded health proposition, not the frame.** If the claim text contains
   a reporting or correction frame ("we were told…", "this post wrongfully
   insinuates…", "that X"), the stance is the speaker's position on X. 4 of the 15
   refuted tune claims have this shape, and most T38 debunk misses went to a
   non-committal label, not to ENDORSES. **[gold][agg]**
2. **A debunk is REFUTES even when hedged or sarcastic.** Restrict UNCLEAR to real
   conflict, and NEUTRAL to open research questions with no correction. Gold uses
   NEUTRAL 0 times and UNCLEAR twice in 178 tune claims, while T38 lost 2–5 refutes per
   model to non-ENDORSES labels. **[gold][agg]**
3. **Question-shaped claims:** the stance is the speaker's answer ("does tap water lower
   testosterone? No…" → REFUTES). **[gold]**
4. **Arguing against advice is REFUTES** (v79:c1 "five separate visits for vaccines
   rather than…"). **[gold]**

## 9. The `use_ocr` switch (for the later paid ablation)

- **One place in config:** `backend/config/pipeline.yaml` → `extraction.use_ocr`
  (default `true`, unchanged live behaviour). It is loaded by
  `app/core/pipeline_options.py`.
- **Applied outside node code.** `graph_provider.build_nodes` wraps the extract node
  (`wrap_extract_node`), and the routing experiment's `build_plan` builds the extraction
  items through `items.extraction_view`. With `false`, extraction sees the transcript
  re-fused alone: no captions and no caption-only segments. Stance, the judge and
  validation still get OCR. `claims.py` does not reference the flag (a test asserts
  this).
- **Ablation run (separate approval, ~$1.20 for sonnet extraction):** copy the file
  with `use_ocr: false` and pass
  `run --steps extract_claims --pipeline-options <copy> --frozen-evidence … --out … --live --max-usd …`.
  The report records `use_ocr` and says "WITHOUT on-screen text".

## Reproduce

```
cd backend
python -m app.evaluation.error_analysis gold-diff --old 0fbc68a --new dcf77b0
python -m app.evaluation.error_analysis ceiling --first 0fbc68a --blind-ref dcf77b0
python -m app.evaluation.error_analysis ceiling --first dcf77b0 --blind-ref dcf77b0
# once a run has per_item.json:
python -m app.evaluation.error_analysis analyze --per-item <dir>/per_item.json \
    --golden-ref dcf77b0 --rescore-ref <other ref> --out <dir>/error_analysis.json
```

The §3c and §6 proxy numbers come from running `extraction.categorise` and `bootstrap`
over the second pass. The outputs are in `evals/reports/T43/blind_ceiling_*.json`
(per-video counts); the category counts and examples are quoted above.
