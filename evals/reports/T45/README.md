# T45: Unicode fix, meaning-based F1, extract_v3 and stance_v2 candidates (2026-11-25)

No model API calls were made. Everything here is code, prompts, tests and **dry-run**
estimates. Golden set `data/golden-label-set` @ `948b1c2`, **tune split only**. The paid
re-run below needs its own approval.

## (a) Unicode tokenisation (live guardrail behaviour changes; intended)

One shared tokeniser, `backend/app/core/text_tokens.py` (`word_tokens`), replaces
`re.compile(r"[a-z0-9]+")` in three places:

| where | what it does | before | after |
|---|---|---|---|
| `guardrails/outputs.py` `grounding_overlap` | drops ungrounded extracted claims (< 0.5) | a Devanagari claim scored **0.0 against itself**, so every Hindi claim was dropped as `claim_ungrounded` | 1.0 against its own source; an English translation of Hindi speech still scores 0.0 |
| `evaluation/metrics.py` `_tokens` (strict matcher, `text_similarity`) | T38's selection metric | two Devanagari strings had no tokens, so Jaccard **1.0**: any Hindi prediction matched any Hindi gold claim | real word overlap |
| `graph/claims.py` `_words` (dedup of overlapping windows) | merges repeated claims | Devanagari copies scored 0 and were never merged | merged like any other claim |

The third one is not in the queue row. It is included because, with the grounding fix
alone, a Hindi claim seen by two overlapping windows would now survive twice (the dedup
could not see its words) and cost precision.

A token is a maximal run of letters/digits in any script (`str.isalnum`) or combining
marks (Unicode `M*`; Devanagari vowel signs and virama, which `\w` rejects, would cut
every Hindi word apart). Text is NFC-normalised and lower-cased. Underscore still
separates words.

**Latin-script (ASCII) behaviour is unchanged**: a test compares `word_tokens` with the
old regex on 2,000 random ASCII strings plus fixed examples, and the existing English
grounding/dedup/matcher tests pass unchanged. What does change for Latin script:
accented words are now one token ("reprogramación", was "reprogramaci" + "n"). A claim
must therefore keep its source's accents to be grounded on that word, which is what
"quote, don't invent" asks for.

On the tune split (187 claims at 948b1c2): claims failing self-grounding drop from
**4 to 0** (all four are v167's Devanagari claims, 2.2% of tune recall); distinct
same-video gold pairs that the strict matcher calls a match drop from 19 to 13 (the 6
removed are the Devanagari 1.0 artefacts).

Not changed: scripts written without spaces (Chinese, Japanese, Thai) come out as one
token per run; the golden set has none. `error_analysis/matching.py`'s meaning-based
matcher keeps compare_blind.py's ASCII-only words so T43's ceiling numbers stay
comparable; it therefore still cannot match Devanagari claims (see (b)).

## (b) Meaning-based claim F1 next to strict

- **Routing experiment** (`routing_experiment/runners.py` `extract_extras`): every
  extraction candidate's `extras` now holds strict and meaning P/R/F1 with counts, and
  `report.md` shows them in one table. Selection still uses strict `claim_f1`
  (unchanged). Text-only: the experiment's gold items carry no time spans, so the
  meaning matcher's timed 0.34 relaxation is not used, which makes it slightly stricter
  than the T43 ceiling.
- **Eval harness** (`evaluation/scoring.py`): new metrics `claim_precision_meaning`,
  `claim_recall_meaning`, `claim_f1_meaning`, requestable in a run config like any
  other. `claim_f1` and the stance/verdict metrics keep the strict pairs.

## (c) `extract_v3` (from T43 §8, extract recommendations 1–6)

Changes against `extract_v2` (all examples are invented, none is a golden-set claim; the
tune claims were checked for verbatim overlap, and test-split labels were not read):

1. New rule 1: quote in the original language and script; never translate (a
   translation is ungrounded and dropped).
2. Rule 2 adopts the guide's conventions: `[brackets]` for a pronoun's referent (a
   word or two, and cite the referent's block too, so grounding holds), `…` for dropped
   words, an optional bracketed fix for a plainly misheard word; no lead-ins,
   wrappers, neighbouring sentences or paraphrase.
3. New granularity rule: split different predicates; one predicate with a list of
   objects/outcomes stays one claim; a question the video asks and answers is kept
   whole as the claim.
4. "State the myth, not the correction": a denied belief is written in its positive
   form; a negation stays only when the negative statement is itself the assertion.
   (v2's "keep negation" rule is narrowed to qualifiers accordingly.)
5. Expanded "What is NOT a claim": teasers and framing, unanswered rhetorical
   questions, audience/poll remarks, credentials or personal story without an
   assertion, sign-offs and "link in bio".
6. On-screen captions stated as fact: one claim per caption line, never merged;
   watermarks and headings are not claims.

`claim_category`, `claim_kind`, `requires_verification`, the output schema and the tool
are unchanged.

## (d) `stance_v2` (from T43 §8, stance recommendations 1–4)

1. Judge the embedded health proposition, not the reporting or correction frame ("we
   were told…", "this ad wrongly suggests that…"); "wrongly" inside a claim means
   REFUTES, not ENDORSES of the correction.
2. A debunk is REFUTES even when hedged, partial, joking or sarcastic. NEUTRAL only for
   an open research question with no correction or recommendation; UNCLEAR only for a
   real conflict (disagreeing speakers, self-contradiction, irony whose target can't be
   told, no position shown). NEUTRAL/UNCLEAR are not a safe middle.
3. A question-shaped claim takes the stance of the speaker's answer.
4. Arguing against advice is REFUTES.

v1's caption, reporting (QUOTES), hedge-plus-recommendation, citation and rationale
rules are kept. The labels and output schema are unchanged.

**Tension with the labelling guide, for the lead:** the guide says sarcasm and irony
are UNCLEAR ("prefer it to a guess"). T43 §8 stance 2 says a sarcastic debunk is
REFUTES, and the gold uses UNCLEAR only twice in 187 tune claims. stance_v2 resolves it
as: sarcasm whose target is clear is a debunk (REFUTES); irony whose target can't be
told stays UNCLEAR. If the paid run shows refutes recall rising but UNCLEAR recall
falling, this is the rule to revisit.

## Candidates (config/routing_experiment.yaml)

`claude-sonnet-5-5@extract_v3` and `claude-sonnet-5-5@stance_v2` are added next to the
existing candidates. `config/routing.yaml`, `extract_v2`/`stance_v1` as the live
defaults (`DEFAULT_PROMPT_VERSION`) and `config/pipeline.yaml` (`use_ocr: true`) are
unchanged; tests assert all of this.

## Dry-run estimates (no calls)

The proposed re-run uses `candidates_rerun.yaml` here (sonnet only: extract v2 vs v3,
stance v1 vs v2) and, for the ablation, `pipeline_no_ocr.yaml` (a copy of
`config/pipeline.yaml` with `use_ocr: false`). Full tables:
`dry_run_with_ocr/report.md`, `dry_run_no_ocr/report.md`.

| run | candidate | items | calls | input tokens | expected | upper bound |
|---|---|---|---|---|---|---|
| with OCR | sonnet @ extract_v2 | 48 videos | 50 | 235,832 | $0.77 | $3.23 |
| with OCR | sonnet @ extract_v3 | 48 videos | 50 | 274,360 | $0.85 | $3.42 |
| with OCR | sonnet @ stance_v1 | 187 claims | 187 | 430,614 | $1.14 | $2.03 |
| with OCR | sonnet @ stance_v2 | 187 claims | 187 | 522,354 | $1.33 | $2.26 |
| no OCR (ablation) | sonnet @ extract_v2 | 48 videos | 47 | 144,713 | $0.57 | $2.65 |
| no OCR (ablation) | sonnet @ extract_v3 | 48 videos | 47 | 180,932 | $0.64 | $2.83 |
| **total** | | | 568 | | **$5.31** | **$16.42** |

Upper bound = every call writes its full output cap and every repair fires (the
runner's standard bound). The ablation runs both extract prompts because T43 §8 rec 6
(caption claims) should be measured together with it; dropping the v2 ablation row
saves $0.57. A cap of **$7** covers the expected cost with margin; the runner refuses
to start if its own estimate exceeds the cap and stops at the cap.

Note: re-running `extract_v2`/`stance_v1` is needed even though T38 ran them, because
T38 kept no per-item outputs, the golden set moved to 948b1c2, and the strict matcher
changed for Devanagari in (a); the old numbers are not comparable.

## Commands for the paid run (NOT run; needs approval)

```
cd backend
python -m app.evaluation.routing_experiment run --golden-ref 948b1c2 \
    --candidates ../evals/reports/T45/candidates_rerun.yaml \
    --steps extract_claims analyze_stance \
    --out ../evals/reports/T45/run_with_ocr --live --max-usd <cap>
python -m app.evaluation.routing_experiment run --golden-ref 948b1c2 \
    --candidates ../evals/reports/T45/candidates_rerun.yaml \
    --steps extract_claims --pipeline-options ../evals/reports/T45/pipeline_no_ocr.yaml \
    --out ../evals/reports/T45/run_no_ocr --live --max-usd <cap>
```

The dry runs were produced by the same commands without `--live`/`--max-usd`.
