# T60: reranker relevance by measurement (lexical vs MedCPT)

**Decision: keep the lexical scorer as the default.** MedCPT (`ncbi/MedCPT-Cross-Encoder`, run
locally through the `RelevanceModel` hook) is **not clearly better** on this set, and it does
**not fit** a Railway-sized CPU container. It takes 6.7–12.9 s per claim and about 1.6 GB peak
memory. The lexical scorer takes about 11 ms and adds no memory. Either reason alone is enough
to keep lexical.
No paid or model-API calls were made. The test split was not read. The weights are not committed.

| File | What |
| --- | --- |
| `candidates.json` | 30 claims × first 20 retrieved records (599 PubMed records), abstracts and publication types re-fetched from NCBI |
| `labels.json` | 2 / 1 / 0 label for every record, the method, and `least_sure` (spot-check these first) |
| `results.json` | Both scorers' scores per record, MedCPT logits, threshold sweep (0–0.95) for both, strict and lenient |
| `compare.json` | English / non-English subsets, ranking quality on claims that have relevant records, paired bootstrap |
| `latency_1cpu.json`, `latency_2cpu.json` | CPU time per claim and peak RSS, pinned to 1 and 2 cores |
| `backend/scripts/t60_rerank_measure.py` | `build`, `score`, `compare`, `latency` (commands in its docstring) |
| `backend/app/core/retrieval/cross_encoder.py` | `CrossEncoderRelevance`: opt-in MedCPT `RelevanceModel` (lazy torch import, not wired into any default) |

## The relevance set and how it was labelled

- **Claims.** Tune split only (`evals/reports/T50/tune_paid.json`). The claims are those with
  ≥ 20 retrieved records, sorted by id: 24 evenly spaced English and 5 evenly spaced
  non-English (4 Spanish, 1 Hindi). The vitamin K job's **c8** ("bleeding in the brain can
  cause permanent neurological damage or death") is added with production's own query re-run
  live, plus production's 10 kept PMIDs, including the deep-brain-stimulation and
  acute-liver-failure papers. One c8 PMID no longer resolves, so c8 has 19 records.
- **Pool.** The first 20 records per claim in retrieval order. Both scorers rerank exactly these.
- **Labels.** By an AI assistant (the Claude Code session that ran T60). This is **one labeller,
  not people, and not inter-annotator agreement**, and the labels are to be spot-checked by the
  lead. Each record's title, publication types and the first ~450 characters of its abstract
  were read once. Labelling finished before either scorer's output was seen.
  - 2 = tests the claim (this exposure, this outcome, in humans).
  - 1 = partly relevant human evidence (close exposure or outcome, a narrower population, or a
    review addressing the question).
  - 0 = not evidence.
  - Totals: 16 × 2, 87 × 1, 496 × 0. Only **9 claims** have any record labelled 2, and 18 have
    one labelled ≥ 1. The strict numbers therefore rest on very few claims.
- **Least sure** (full list with reasons in `labels.json`):
  - v22:c2 34323086: egg antioxidants and the macula; 2 may be generous.
  - v71:c3 42096712: oral contraceptives and stroke, migraine-with-aura population only.
  - v87:c2 42690660: prenatal fluoride; 1, could be 2.
  - v92:c2 40507606: small earthing study; 2.
  - v100:c1 40544428: stem-cell islets, not "reprogramming"; 1, could be 2.
  - v86:c1 33586773: HIV remission review; 1.
  - vitk:c8: nothing got 2. Six records with outcomes after brain bleeds got 1. DBS and
    liver failure got 0.
  - The labelling of the claims whose pools are all 0 (v135:c1, v176:c1, v95:c4, v111:c4)
    rests on reading claims that lack video context.

## Precision and recall

The real `Reranker` is used: relevance blended 0.7 / 0.3 with study quality, a threshold, and a
cap of 10. Only the relevance score differs between the two runs. MedCPT's logit is squashed
with a sigmoid.

P@k is computed over the records a claim keeps. Claims that keep nothing are counted
separately, not as 0. Recall is relevant records kept divided by relevant records in the pool.
"Lenient" means label ≥ 1; "strict" means label = 2.

**Threshold sweep, all 30 claims** (selected rows; every row is in `results.json`):

| scorer | threshold | P@3 (lenient) | P@10 (lenient) | recall (lenient) | recall (strict, of 16) | claims with nothing kept | records kept | of which label 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lexical | 0.0 | 0.311 | 0.247 | 0.718 | 0.875 | 0 | 300 | 226 |
| lexical | 0.2 | 0.340 | 0.270 | 0.573 | 0.812 | 6 | 219 | 160 |
| **lexical** | **0.4 (default)** | **0.355** | **0.283** | **0.573** | **0.812** | **7** | **209** | **150** |
| lexical | 0.6 | 0.409 | 0.339 | 0.476 | 0.750 | 8 | 185 | 136 |
| lexical | 0.8 | 0.400 | 0.327 | 0.340 | 0.562 | 10 | 147 | 112 |
| medcpt | 0.0 | 0.356 | 0.267 | 0.777 | 0.688 | 0 | 300 | 220 |
| medcpt | 0.2 | 0.417 | 0.352 | 0.573 | 0.562 | 10 | 145 | 86 |
| **medcpt** | **0.5** | **0.417** | **0.350** | **0.544** | **0.562** | **10** | **132** | **76** |
| medcpt | 0.7 | 0.472 | 0.403 | 0.524 | 0.562 | 12 | 119 | 65 |
| medcpt | 0.9 | 0.451 | 0.382 | 0.417 | 0.500 | 13 | 99 | 56 |

**Ranking alone** (relevance score only, no threshold, claims with ≥ 1 relevant record):

| | MAP strict (9 claims) | MAP lenient (18 claims) | P@10 lenient |
| --- | --- | --- | --- |
| lexical | **0.488** | 0.558 | 0.400 |
| MedCPT | 0.336 | 0.556 | 0.428 |

**Paired bootstrap, MedCPT @ 0.5 minus lexical @ 0.4** (per-claim differences, 2000
resamples, 95% CI):

| metric | claims | mean diff | 95% CI |
| --- | --- | --- | --- |
| P@3 lenient | 18 | +0.028 | −0.083 … +0.148 |
| P@10 lenient | 18 | +0.025 | −0.035 … +0.097 |
| recall lenient | 18 | −0.034 | −0.189 … +0.123 |
| recall strict | 9 | **−0.385** | **−0.719 … −0.067** |

**English vs non-English** (`compare.json`):

- **English (25 claims).** MedCPT's lenient P@3 is 0.41 vs 0.33 and P@10 0.35 vs 0.27. Lenient
  recall is equal (0.608), and MedCPT keeps 73 off-topic records vs 131. Strict recall is
  9/14 vs 12/14. MedCPT drops 2 of them: the earthing trial (logit −15) and the
  contraceptives / hypertension SR. On v71:c3 it also ranks the migraine-with-aura cohort below
  the cap.
- **Non-English (5 claims).** MedCPT is given the claim in its original language, against
  English abstracts.
  - It keeps **nothing** for v100:c1 (es) or v122:c1 (es). Lexical keeps 7/10 and 4/5 relevant
    records there, including the statin meta-analysis that MedCPT scores at logit −10.9.
  - The Hindi claim (v167:c2) goes the other way: MedCPT keeps 8/9 relevant records and lexical
    keeps nothing.
  - Scoring the planner's translated text would be the fair next test. That is a design change,
    not done here.

**c8 (vitamin K, "bleeding in the brain").**

- Lexical at 0.4 keeps 10 records: 4 labelled 1, plus the deep-brain-stimulation review (0.53).
  The liver-failure paper scores 0 on today's code.
- MedCPT at 0.5 keeps 7 records, 3 labelled 1. It drops DBS (logit −4.2) and liver failure
  (−1.1), but it keeps a stereotactic-biopsy complications review (+6.1), a rabbit
  subarachnoid-haemorrhage model (+7.8) and a neonatal-ferroptosis review (+4.8). It also drops
  two labelled-1 records: the AVM treatment meta-analysis (−7.8) and the infratentorial-stroke
  cohort (−3.1).
- Neither scorer handles this claim well.

**Reading of the evidence.** MedCPT passes on about half as many off-topic papers. Its precision
gains are small and inside the noise. It loses strictly relevant papers, and that loss is
outside the noise. It fails on Spanish claims. This is not "clearly better".

## Latency, memory and image size (Railway-sized CPU container)

**Assumptions.**

- The reranker runs in the API/worker image on a **1–2 vCPU** container.
- The budget is **≤ 1 s added per claim** and **≤ 1 GB** extra RSS. Those are my assumptions,
  not a project spec.
- Measured with `taskset` pinned to 1 and then 2 cores, `torch.set_num_threads` matching, on
  this session's container CPU. A Railway vCPU may be slower.
- 20 records per claim. Production claims often have 40–59 candidates, which would scale MedCPT
  time roughly linearly.
- torch 2.15.0, transformers 5.24.1, max length 512, batch 16.

| | 1 vCPU | 2 vCPU |
| --- | --- | --- |
| MedCPT per claim, median / p95 | **12.9 s / 14.2 s** | **6.7 s / 7.4 s** |
| lexical per claim, median / p95 | 11 ms / 16 ms | 11 ms / 16 ms |
| model load | 3.1 s | 2.9 s |
| peak RSS: Python + model loaded / after runs | 1,149 MB / **1,609 MB** | 1,156 MB / **1,586 MB** |

**Image size.**

- The weights are 418 MB: `pytorch_model.bin` or `model.safetensors`. The Hugging Face cache
  fetched both, 836 MB in total, unless restricted.
- The PyPI torch wheel measured here pulls in CUDA. Installed, it is torch 1,150 MB + nvidia
  3,055 MB + triton 997 MB + transformers / tokenizers / hub ≈ 95 MB, so **about 5.3 GB**.
- A CPU-only torch wheel would be much smaller, but it could not be measured here because
  `download.pytorch.org` is blocked in this environment. Its `libtorch_cpu.so` alone is 428 MB
  in this install.
- Either way it is several hundred MB to GBs on an image that today has no ML dependencies
  (`backend/requirements.txt`).

**Verdict:** it does not fit the budget. That is 7–13× too slow per claim on 1–2 vCPU before
counting larger pools, and about 1.6 GB RSS.

## Other checks

- **Judge cross-check.** `python scripts/judge_crosscheck.py --fixture` output is
  **byte-identical** to `origin/langgraph-build`, with 181/181 golden reproductions. Nothing
  moved, which is expected: the default is unchanged and the judge does not read relevance scores.
- **Backend suite.** Results are in the PR description.
- **Download note.** The Hugging Face client's Xet transfer stalled behind the proxy.
  `HF_HUB_DISABLE_XET=1` (plain HTTPS via `us.aws.cdn.hf.co`) worked.
- **Eval registry.** T63's registry (#135) merged while this ran. 14 records are in
  `evals/registry/T60-rerank-*.json` (run group `T60-rerank-relevance`): P@3, P@10 and recall
  for both scorers, the two bootstrap differences with their CIs, and MedCPT CPU latency on 1
  and 2 vCPU. `test_eval_registry_t63.py`'s "no T60/T61 records" check now only requires that
  T60/T61 records belong to their own run group.

## If someone revisits this

1. Have the lead spot-check `least_sure`. Then add a second, independent human labeller and
   measure agreement.
2. Score MedCPT on the translated claim text (`plan.search_text`) for non-English claims.
3. Consider it only as a GPU or batch service, or as a second-stage scorer on the top few
   records. It cannot run inline on the CPU worker.
