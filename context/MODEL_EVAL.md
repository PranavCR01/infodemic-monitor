# Model Evaluation & Disagreement Track Context

## 1. What This Role Is

Two students (Student-ME1, Student-ME2) working as a pair on **research**, not production
code. You do not own or modify any backend/frontend code — your deliverables are datasets,
scripts, notebooks, and a written recommendation.

## 2. Last Semester Findings (Task 4)

Last semester compared three open-source models — **Llama 2, Mistral, Gemma** — on TikTok
health videos, all run under identical conditions (same transcript input, same prompt).

**Result:** 100% agreement between all three models across all test videos. The agreement
matrix was all `1.000`; the disagreement matrix was all `0.000`.

## 3. The Open Question

Is 100% agreement a real finding, or is the test dataset too easy or too homogeneous?
**5 videos is not statistically meaningful.** A perfect agreement score on a 5-video sample
could mean the models genuinely converge, or it could mean every video in the sample was an
unambiguous case that any reasonable classifier would get right.

**Your primary job this semester is to stress-test this finding.**

## 4. System Context

The production pipeline uses **Anthropic `claude-opus-4-6`** as the primary inference
provider and **OpenAI GPT-4** as fallback (see `context/PRODUCTION.md`). The research
models for this track — Llama 2, Mistral, Gemma — run via **Ollama locally** and are
**not** part of the production system; they exist purely for this comparison research.

Read `context/PROJECT_CONTEXT.md` for full system context. You will not be modifying
production code, but understanding the pipeline (transcription → fusion → classification)
matters because your comparison should feed the same fused transcript into each model, the
way the production classifier consumes `FusionResult`.

## 5. Objectives This Semester

1. **Expand the dataset** to a minimum of 50 videos across diverse content types: vaccine
   claims, nutrition, mental health, COVID, fitness.
2. **Re-run the three-model comparison** on the expanded dataset. Produce a proper
   confusion matrix and **Cohen's Kappa per model pair** (not just raw agreement
   percentage — Kappa corrects for chance agreement, which matters if one label dominates
   the dataset).
3. **Test the routing signal hypothesis:** does model agreement actually correlate with
   classification *accuracy*? Design an experiment to validate this — you need ground
   truth labels on at least a subset of the 50 videos to answer this, not just
   inter-model agreement.
4. **Produce a written recommendation:** at what agreement threshold should a video be
   flagged for human review vs. returned as an automated output? This recommendation feeds
   directly into any future ensemble/routing work in production.

## 6. Output Format

Results as CSV:

```
video_id, transcript_snippet, model_1_label, model_2_label, model_3_label, agreement, ground_truth
```

`ground_truth` may be empty where you don't have it, but include the column.

Labels must use the same four values as production's `MisinfoLabel` enum, so this format
is directly compatible with the `ClassificationResult` schema:

- `MISINFO`
- `NO_MISINFO`
- `DEBUNKING`
- `CANNOT_RECOGNIZE`

Do not invent new label strings or casing — a downstream reader (production student,
future routing logic) should be able to load your CSV and match labels 1:1 against the
production enum.

## 7. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

-

## 8. PR Requirements

- PRs for any scripts or notebooks, using `.github/ISSUE_TEMPLATE/model-eval.md` for the
  originating issue.
- Reference the GitHub issue (`Closes #N`).
- Update this file with findings **as they are confirmed** — not speculative results, but
  once an experiment is done and the numbers are in, record them here so the production
  and multi-agent tracks can build on them.
