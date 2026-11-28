# T70 gate: claim context (offline, no model calls, $0)

Code: `ca89eae29475218869bee5c49afcacfc782e2f68`. Tune split only. Baseline = as shipped (T64; T67 change 1 on, 2 off, 3 on; T69 off).
A excluded: v21 (status 'not_run:budget_mid_video'). B evidence IDs not in the offline cache: 5.

**Mocked:** the extract_v5 context items and topic, and the verify_v4 structured answers and the skin claim's verdict as meant are hand-written. **Recorded:** claims, stances, kept evidence, stored verdicts. **Real code:** extraction parsing and grounding, planner, verifier node, judge, review policy. PubMed is not called. None of this shows what a model would answer.

## 1. v135 production fixtures (golden NO_MISINFO)

| job | stored (prod) | off, re-run | on: as meant | on: contradicted, setting flagged | on: model ignores context (failure mode) |
|---|---|---|---|---|---|
| 008c97a3 | MISINFO (review) ← skin claim decides | MISINFO (review) ← skin claim decides | NO_MISINFO (review: softened_by_context) | NO_MISINFO (review: contradiction_context_mismatch) | MISINFO (review) ← skin claim decides |
| cf2ea579 | MISINFO (review) ← skin claim decides | MISINFO (review) ← skin claim decides | NO_MISINFO (review: softened_by_context) | NO_MISINFO (review: contradiction_context_mismatch) | MISINFO (review) ← skin claim decides |
| f85f2daa | MISINFO (review) ← skin claim decides | MISINFO (review) ← skin claim decides | NO_MISINFO (review: softened_by_context) | NO_MISINFO (review: contradiction_context_mismatch) | MISINFO (review) ← skin claim decides |

## 2. Vitamin K production fixtures

| job | prod | off, re-run | on (mocked context on the vague claim) | same? |
|---|---|---|---|---|
| 5cc07f48 | MISINFO (unproven) | NO_MISINFO | NO_MISINFO | yes |
| d2bf4179 | MISINFO (unproven) | NO_MISINFO | NO_MISINFO | yes |
| 3d48e75e (report rows, judge only) | NO_MISINFO | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | yes |

## 3. T66 recorded videos (A) and golden claims (B)

### A. T66 stored states (tune): 18 videos

**as shipped (T70 off)**: 11/18 correct; sent to review 17/18; label changed vs off: none; worse vs gold: none

**T70 on, stored verdicts**: 11/18 correct; sent to review 17/18; label changed vs off: none; worse vs gold: none

**T70 on, every endorsed/refuted CONTRADICTED claim softened as meant (upper bound)**: 8/18 correct; sent to review 17/18; label changed vs off: v11, v114, v122, v39, v65, v88; worse vs gold: v122, v39, v88

**T70 on, different setting flagged on every CONTRADICTED verdict (upper bound)**: 11/18 correct; sent to review 17/18; label changed vs off: none; worse vs gold: none

| video | gold | off | on | upper_soft | upper_mismatch |
|---|---|---|---|---|---|
| v109 | MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v11 | CANNOT_RECOGNIZE | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | NO_MISINFO (review) ✱ | MISINFO (contradicted) (review) |
| v114 | MISINFO | DEBUNKING (review) | DEBUNKING (review) | CANNOT_RECOGNIZE (review) ✱ | DEBUNKING (review) |
| v120 | MISINFO | MISINFO (unproven) (review) | MISINFO (unproven) (review) | MISINFO (unproven) (review) | MISINFO (unproven) (review) |
| v122 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) (review) |
| v150 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v176 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v23 | DEBUNKING | MISINFO (denies_supported) (review) | MISINFO (denies_supported) (review) | MISINFO (denies_supported) (review) | MISINFO (denies_supported) (review) |
| v39 | DEBUNKING | DEBUNKING (review) | DEBUNKING (review) | NO_MISINFO (review) ✱ ▼ | DEBUNKING (review) |
| v65 | CANNOT_RECOGNIZE | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | NO_MISINFO (review) ✱ | MISINFO (contradicted) (review) |
| v69 | NO_MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v71 | NO_MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v78 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | MISINFO (denies_supported) (review) ✱ | MISINFO (contradicted) (review) |
| v87 | MISINFO | MISINFO (denies_supported) (review) | MISINFO (denies_supported) (review) | MISINFO (denies_supported) (review) | MISINFO (denies_supported) (review) |
| v88 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | CANNOT_RECOGNIZE (review) ✱ ▼ | MISINFO (contradicted) (review) |
| v92 | CANNOT_RECOGNIZE | MISINFO (unproven) (review) | MISINFO (unproven) (review) | MISINFO (unproven) (review) | MISINFO (unproven) (review) |
| v94 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v95 | NO_MISINFO | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |

### B. Golden claims (tune, in scope): 48 videos

**as shipped (T70 off)**: 43/48 correct; sent to review 24/48; label changed vs off: none; worse vs gold: none

**T70 on, stored verdicts**: 43/48 correct; sent to review 24/48; label changed vs off: none; worse vs gold: none

**T70 on, every endorsed/refuted CONTRADICTED claim softened as meant (upper bound)**: 28/48 correct; sent to review 34/48; label changed vs off: v21, v23, v27, v39, v78, v79, v87, v88, v109, v111, v114, v119, v122, v131, v177; worse vs gold: v21, v23, v27, v39, v78, v79, v87, v88, v109, v111, v114, v119, v122, v131, v177

**T70 on, different setting flagged on every CONTRADICTED verdict (upper bound)**: 42/48 correct; sent to review 25/48; label changed vs off: v119; worse vs gold: v119

| video | gold | off | on | upper_soft | upper_mismatch |
|---|---|---|---|---|---|
| v11 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v21 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) |
| v22 | MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v23 | DEBUNKING | DEBUNKING (review) | DEBUNKING (review) | CANNOT_RECOGNIZE (review) ✱ ▼ | DEBUNKING (review) |
| v24 | NO_MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v27 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) (review) |
| v36 | MISINFO | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v39 | DEBUNKING | DEBUNKING (review) | DEBUNKING (review) | CANNOT_RECOGNIZE (review) ✱ ▼ | DEBUNKING (review) |
| v44 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v51 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v58 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v65 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v68 | NO_MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v69 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v70 | NO_MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v71 | NO_MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v78 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | CANNOT_RECOGNIZE (review) ✱ ▼ | MISINFO (contradicted) |
| v79 | DEBUNKING | DEBUNKING | DEBUNKING | NO_MISINFO (review) ✱ ▼ | DEBUNKING |
| v86 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | MISINFO (denies_supported) (review) ✱ | MISINFO (contradicted) (review) |
| v87 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | CANNOT_RECOGNIZE (review) ✱ ▼ | MISINFO (contradicted) |
| v88 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | CANNOT_RECOGNIZE (review) ✱ ▼ | MISINFO (contradicted) |
| v92 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v94 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v95 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v96 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v100 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v109 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) |
| v110 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v111 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | CANNOT_RECOGNIZE (review) ✱ ▼ | MISINFO (contradicted) |
| v114 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) (review) |
| v119 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | CANNOT_RECOGNIZE (review) ✱ ▼ | CANNOT_RECOGNIZE (review) ✱ ▼ |
| v120 | MISINFO | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v121 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v122 | MISINFO | MISINFO (contradicted) (review) | MISINFO (contradicted) (review) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) (review) |
| v123 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v131 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) |
| v135 | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO | NO_MISINFO |
| v141 | MISINFO | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) | NO_MISINFO (review) |
| v143 | MISINFO | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v144 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v146 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v150 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v152 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v160 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v167 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |
| v176 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE |
| v177 | MISINFO | MISINFO (contradicted) | MISINFO (contradicted) | NO_MISINFO (review) ✱ ▼ | MISINFO (contradicted) |
| v180 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) | CANNOT_RECOGNIZE (review) |

### MISINFO videos softened to a milder label, per video

**A**: every video whose label is MISINFO today (off) or in gold.

| video | gold | off | on (stored) | upper_soft | upper_mismatch |
|---|---|---|---|---|---|
| v109 | MISINFO | NO_MISINFO | NO_MISINFO (kept) | NO_MISINFO (kept) | NO_MISINFO (kept) |
| v11 | CANNOT_RECOGNIZE | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v114 | MISINFO | DEBUNKING | DEBUNKING (kept) | CANNOT_RECOGNIZE (kept) | DEBUNKING (kept) |
| v120 | MISINFO | MISINFO | MISINFO (kept) | MISINFO (kept) | MISINFO (kept) |
| v122 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v23 | DEBUNKING | MISINFO | MISINFO (kept) | MISINFO (kept) | MISINFO (kept) |
| v65 | CANNOT_RECOGNIZE | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v78 | MISINFO | MISINFO | MISINFO (kept) | MISINFO (kept) | MISINFO (kept) |
| v87 | MISINFO | MISINFO | MISINFO (kept) | MISINFO (kept) | MISINFO (kept) |
| v88 | MISINFO | MISINFO | MISINFO (kept) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v92 | CANNOT_RECOGNIZE | MISINFO | MISINFO (kept) | MISINFO (kept) | MISINFO (kept) |

**B**: every video whose label is MISINFO today (off) or in gold.

| video | gold | off | on (stored) | upper_soft | upper_mismatch |
|---|---|---|---|---|---|
| v21 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v22 | MISINFO | NO_MISINFO | NO_MISINFO (kept) | NO_MISINFO (kept) | NO_MISINFO (kept) |
| v27 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v36 | MISINFO | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (kept) | CANNOT_RECOGNIZE (kept) | CANNOT_RECOGNIZE (kept) |
| v78 | MISINFO | MISINFO | MISINFO (kept) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v86 | MISINFO | MISINFO | MISINFO (kept) | MISINFO (kept) | MISINFO (kept) |
| v87 | MISINFO | MISINFO | MISINFO (kept) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v88 | MISINFO | MISINFO | MISINFO (kept) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v109 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v111 | MISINFO | MISINFO | MISINFO (kept) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v114 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v119 | MISINFO | MISINFO | MISINFO (kept) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) | CANNOT_RECOGNIZE (SOFTENED, reviewed with T70/T69 reason) |
| v120 | MISINFO | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (kept) | CANNOT_RECOGNIZE (kept) | CANNOT_RECOGNIZE (kept) |
| v122 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v131 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |
| v141 | MISINFO | NO_MISINFO | NO_MISINFO (kept) | NO_MISINFO (kept) | NO_MISINFO (kept) |
| v143 | MISINFO | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE (kept) | CANNOT_RECOGNIZE (kept) | CANNOT_RECOGNIZE (kept) |
| v177 | MISINFO | MISINFO | MISINFO (kept) | NO_MISINFO (SOFTENED, reviewed with T70/T69 reason) | MISINFO (kept) |

## 4. Token increase per claim (estimate: characters / 4; no tokenizer offline)

| job | claims | extraction input +tok/claim | extraction output +tok/claim (mocked reply) | verifier input +tok/claim (in context / as stated) | verifier output +tok/claim |
|---|---|---|---|---|---|
| 008c97a3 | 19 | 65.1 | 7.8 | 483.2 / 325.0 | ≤ 20.5 |
| cf2ea579 | 13 | 95.2 | 8.9 | 462.8 / 325.0 | ≤ 20.5 |

- 008c97a3: extraction request 6067 → 7304 tokens per video (+20%); verifier request 4798.3 tokens on average per claim; the longer verify_v4 system prompt alone adds 203.2 to every call (+7% as stated, +10% in context).
- cf2ea579: extraction request 3993 → 5230 tokens per video (+31%); verifier request 5379.2 tokens on average per claim; the longer verify_v4 system prompt alone adds 203.2 to every call (+6% as stated, +9% in context).

