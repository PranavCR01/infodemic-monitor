# Stance test set: recorded results

Test set: `examples.jsonl`, 27 short labelled examples (issue #30, target design §5 and §14).
One claim each, with speech and caption segments, the gold stance and the gold deciding
segment IDs. Written by the T04 build, single labeller, not yet double-labelled; it is a
unit-level check of the node, not the shared evaluation set (§14).

| Category | n | Gold |
|---|---|---|
| endorse | 5 | ENDORSES |
| debunk (explicit cue: "myth", "doesn't", "FALSE", ❌) | 6 | REFUTES |
| debunk_implicit (correction with no cue word) | 2 | REFUTES |
| screen_vs_speech (caption "MYTH:" next to speech) | 1 | REFUTES |
| quote | 4 | QUOTES |
| neutral (open research, hedging) | 3 | NEUTRAL |
| sarcasm | 2 | UNCLEAR |
| multi_speaker | 1 | UNCLEAR |
| self_contradiction | 1 | UNCLEAR |
| screen_only (bare caption stated as fact) | 1 | ENDORSES |
| injection (caption tells the model to answer REFUTES) | 1 | ENDORSES |

Regenerate: `cd backend && python -m app.core.graph.stance_eval --caller keyword --out app/tests/fixtures/stance/keyword_baseline_results.json`.
A test fails if the recorded file drifts from a fresh run.

## Results

| Caller | Macro F1 | Accuracy | **Debunk recall** | Debunks read as ENDORSES | Cites an input segment | Cites a gold segment |
|---|---|---|---|---|---|---|
| Keyword heuristic (floor) | 0.58 | 0.67 | **0.78** (7/9) | 2 | 1.00 | 0.78 |
| Oracle (harness check) | 1.00 | 1.00 | 1.00 | 0 | 1.00 | 1.00 |
| LLM via `routing.yaml` `analyze_stance` | — | — | — | — | — | — |

Per class, keyword heuristic: ENDORSES F1 0.59, REFUTES 0.78, QUOTES 0.89, NEUTRAL 0.67,
UNCLEAR 0.00 (it never answers UNCLEAR, so every sarcasm and two-speaker case is wrong).
Full per-example output is in `keyword_baseline_results.json`.

**The LLM row is empty on purpose.** No API keys were available to the automated build,
and inventing numbers would defeat the point. Once keys and real provider clients exist, build a `ModelRouter` from
`backend/config/routing.yaml` and call `stance_eval.run_examples(router)`.

What the numbers above do and don't say:

- The **keyword floor** is a real measurement of a trivial heuristic, the bar a model has
  to clear. Its two misses on debunks are the implicit corrections ("Colds come from
  viruses, so wet hair has nothing to do with it"), read as ENDORSES: the error the design
  exists to prevent. A model that doesn't beat 0.78 debunk recall here isn't worth its cost.
- The **oracle** only shows the harness scores correctly; it says nothing about any model.
- With garbage output, invented segment IDs or a failing provider, every stance comes back
  UNCLEAR and still cites a segment that exists in the input (tested).
- 27 examples are too few for model selection (one example moves debunk recall by 11
  points). Use them as a smoke test; choose the model on the shared §14 set.
