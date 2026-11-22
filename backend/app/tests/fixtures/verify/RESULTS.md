# Verification test set: recorded results

Test set: `examples.jsonl`, 20 claims (issue #33, target design §7 and §14). Each has a
claim, its reranked evidence (title, abstract, publication type, study type), the gold
verdict and the gold supporting/contradicting evidence IDs.

**Read these numbers with care.** The abstracts are synthetic (written for this test,
marked "Synthetic.", fake PMIDs `97000001`–`97000030`), and the labels, the abstracts and
the heuristic floor were all written by the same build agent. The heuristic's score is
therefore inflated by construction: its cue words were chosen knowing the abstracts. It
checks the node and the harness; it says nothing about how a model will do on real
papers. A real measurement needs real PubMed abstracts labelled by two people (§14).

| Category | n | Gold |
|---|---|---|
| supported | 4 | SUPPORTED |
| contradicted (incl. "relieves symptoms but doesn't shorten illness") | 4 | CONTRADICTED |
| mixed | 3 | MIXED |
| insufficient: animal-only, off-topic, lab-only, wrong population, case report, symptoms-not-cure | 6 | INSUFFICIENT_EVIDENCE |
| not_verifiable (subjective claims with tangential papers) | 3 | NOT_VERIFIABLE |

Regenerate: `cd backend && python -m app.core.graph.verify_eval --caller heuristic --out app/tests/fixtures/verify/heuristic_baseline_results.json`.
A test fails if the recorded file drifts from a fresh run.

## Results (2026-11-22)

| Caller | Accuracy | Macro F1 | Insufficient called contradicted | Citation validity | Citations match gold |
|---|---|---|---|---|---|
| Heuristic cue words (floor; see caveat) | 0.85 | 0.87 | 0 | 1.00 | 0.85 |
| Oracle (harness check) | 1.00 | 1.00 | 0 | 1.00 | 1.00 |
| LLM (`verify_claims` route) | — | — | — | — | — |

Per verdict, heuristic floor:

| Verdict | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| SUPPORTED | 0.57 | 1.00 | 0.73 | 4 |
| CONTRADICTED | 1.00 | 1.00 | 1.00 | 4 |
| MIXED | 1.00 | 0.67 | 0.80 | 3 |
| INSUFFICIENT_EVIDENCE | 1.00 | 0.67 | 0.80 | 6 |
| NOT_VERIFIABLE | 1.00 | 1.00 | 1.00 | 3 |

The heuristic's three errors are the cases a model is there for: a wrong population
(adult melatonin trial read as supporting a toddler claim), symptom relief read as a cure
(honey and cough vs "cures sore throat infections"), and a mixed literature where one
paper's "lower risk" isn't recognised as a finding against "raises the risk".

The LLM row stays empty until API keys exist (T14):
`run_examples(ModelRouter(load_routing(), clients))`.
