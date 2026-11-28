# T72: why the video labels are wrong (offline error analysis)

> **Development numbers on 18 TUNE videos, not product accuracy.** No model or API calls ($0).
> The test split was not read: the script asserts `split == tune`.

**Inputs:**
- **System labels:** T67 replay config **b** (`evals/reports/T67/results.json`), 11/18 correct.
- **Claims, stances, verdicts and evidence:** T66's stored states (pipeline 3372ef3).
- **Golden set:** `research/claim-level/dataset/` (byte-identical to `data/golden-label-set` @ 92a731e).
- **Judge:** the repo's own `judge.judge`, run through `backend/scripts/t67_label_rules_replay.py`. It reproduces the b label, rule and deciding claims on all 18 videos.

**Files:**
- `analyze_t72.py`: the script (run from `backend/`).
- `analysis.json`: every number below.
- `material.md`: golden and system claims side by side, with the records each deciding claim cites.

## Primary cause of each wrong label (7 of 18)

| cause | videos | n |
|---|---|---|
| Central claim, wrong verdict | v11 (MIXED→CONTRADICTED), v92 (INSUFFICIENT→UNSUPPORTED), v109 (harms CONTRADICTED→INSUFFICIENT/MIXED) | 3 |
| Peripheral claim (not in gold) decided | v23 c5, v65 c11 | 2 |
| Evidence missing | v95 | 1 |
| Central claim, wrong stance | v114 | 1 |

## Counterfactuals (same judge, edited state)

| | correct / 18 |
|---|---|
| System (config b) | 11 |
| Only gold-matched (central) claims may decide | 10 (11 with hand-matched pairs) |
| Gold verdicts on matched claims | **14** |
| Both, plus gold stances | 17 |

## Aggregates

| measure | value |
|---|---|
| Extraction precision proxy (system claims matching a gold claim) | 84/162 = 0.52 |
| Extraction recall proxy | 74/76 = 0.97 |
| INSUFFICIENT_EVIDENCE share | system 0.67 (0.68 on central claims), gold 0.33 |
| Verdict agreement / stance agreement (matched claims) | 0.50 / 0.94 |
| Gold SUPPORTED/CONTRADICTED central claims that came out INSUFFICIENT | 26/42 |
| …of those, with none of gold's cited records retrieved (by ID, so an upper bound) | 23/26 |
| Gold MIXED central claims called CONTRADICTED | 4/8 |

## Findings

1. **Retrieval is the largest gap.** Key studies are not retrieved, so most decisive central claims end INSUFFICIENT. v95 c7 drifted to radiation as a treatment; v23 c2 and c6, v109 c7 are other examples.
2. **CONTRADICTED is given on contested evidence.** Gold MIXED came out CONTRADICTED in v11, v65 and v114, and was decisive or co-decisive in all three.
3. **A single thin, peripheral claim can decide the label.**
   - v65 c11 rests on one US-only record.
   - The verifier noted the mismatch only in free text, which the judge never reads.
   - T67's thin-contradiction rule (switched off) would have set it aside.
4. **Not supported as primary causes in this sample:**
   - Out-of-context verdicts (T70). In v109 c8 the verifier was *too* strict about context.
   - The rules. Fed gold inputs, they reproduce every gold label.
5. **Over-extraction is real but not sufficient on its own.** About half of the system's claims have no gold counterpart, yet removing them alone fixes none of the 7.

## Caveats

- **n = 18**: each video is about 6 points.
- **Replays, not fresh runs**: labels come from stored states, not a run of the shipped code.
- **Matching heuristic**: Jaccard ≥ 0.30 or containment ≥ 0.80. Spot-checked by eye, with 4 known false negatives and 1 consequential false positive (v109 g7).
- **Gold is mostly model-labelled.** 12 of the 18 videos are `pending` human review. v11, v65 and v109 have arguable gold labels.
- **The evidence check is by ID**, so the system's pool may contain other adequate records.
