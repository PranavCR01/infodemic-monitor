# T60: reranker relevance by measurement (BLOCKED, partial)

**Status: blocked.** The MedCPT cross-encoder weights could not be downloaded.
`huggingface.co` answers (model card, config, tokenizer files), but the weight file
`pytorch_model.bin` redirects (HTTP 302) to `us.aws.cdn.hf.co`, and the environment's proxy
refuses that host (CONNECT 403). The orchestrator's brief says to stop in that case and not
substitute another model or mock the weights, so **no comparison has been run and no
precision/recall numbers exist yet**. The default reranker is unchanged (lexical).

## What is done

| File | What |
| --- | --- |
| `candidates.json` | The relevance set's inputs: 30 claims × up to 20 records (599 records), abstracts and publication types re-fetched from PubMed (NCBI E-utilities, free) |
| `labels.json` | A relevance label (2 / 1 / 0) for every one of the 599 records, the labelling method, and `least_sure`: the calls to spot-check first |
| `../../backend/scripts/t60_rerank_measure.py` | `build` (made `candidates.json`), `score` (both scorers + threshold sweep), `latency` (CPU time and peak RSS, pinned cores) |
| `../../backend/app/core/retrieval/cross_encoder.py` | `CrossEncoderRelevance`, a `RelevanceModel` for `ncbi/MedCPT-Cross-Encoder` (lazy torch/transformers import, not wired into any default) |

**Claims.** Tune split only (`evals/reports/T50/tune_paid.json`; the test split was not read).
Claims with ≥ 20 retrieved records, sorted by id: 24 evenly spaced English and 5 evenly spaced
non-English (4 Spanish, 1 Hindi), plus the vitamin K job's c8 ("bleeding in the brain can
cause permanent neurological damage or death") with the records production retrieved for it
(query re-run live; production's 10 kept PMIDs added, including the deep-brain-stimulation and
acute-liver-failure papers). The pool per claim is the first 20 records in retrieval order; one
c8 PMID (28722976) no longer resolves in EFetch, so c8 has 19.

**Labels.** By an AI assistant (the Claude Code session that ran T60), not by people, and not
inter-annotator agreement: one labeller, no model API call, to be spot-checked by the lead
(`least_sure` first). Labelled before either scorer's output was looked at. Totals: 16 records
labelled 2, 87 labelled 1, 496 labelled 0. Only 9 of the 30 claims have any record labelled 2,
and 18 have one labelled ≥ 1, so the strict-label metrics will rest on few claims; report the
lenient (≥ 1) numbers alongside.

## To finish

1. Allow `us.aws.cdn.hf.co` (the weight CDN `huggingface.co` redirects to; `cas-bridge.xethub.hf.co`
   may also be used by newer `huggingface_hub` clients).
2. From `backend/`, with `torch` and `transformers` installed (not in `requirements.txt`):

       python scripts/t60_rerank_measure.py score --candidates ../evals/reports/T60/candidates.json \
           --labels ../evals/reports/T60/labels.json --out ../evals/reports/T60/results.json
       taskset -c 0   python scripts/t60_rerank_measure.py latency --threads 1 --candidates ../evals/reports/T60/candidates.json --out ../evals/reports/T60/latency_1cpu.json
       taskset -c 0,1 python scripts/t60_rerank_measure.py latency --threads 2 --candidates ../evals/reports/T60/candidates.json --out ../evals/reports/T60/latency_2cpu.json

3. Decide the default only on those numbers (switch only if MedCPT is clearly better and fits a
   1–2 vCPU Railway container), then re-run the judge cross-check and the backend suite.
