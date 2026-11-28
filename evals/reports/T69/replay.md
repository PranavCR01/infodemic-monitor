# T69 replay: contradiction_context_mismatch (offline, no model calls)

Code: `6a72dab71992a08be4dd261fe9ead64bba174256` (T69 commit before this report was added; same code). Tune split only. Baseline = as shipped (T67 change 1 on, change 2 off, change 3 on; T64 guard).
A excluded: v21 (status 'not_run:budget_mid_video'). B evidence IDs not in the offline cache: 5.

The production v135 fixture (jobs cf2ea579 / f85f2daa) was not in the repo; see report.md.

T67-fixed videos (A): v122: {'off': 'MISINFO', 'on': 'MISINFO', 'upper': 'MISINFO'}, v71: {'off': 'NO_MISINFO', 'on': 'NO_MISINFO', 'upper': 'NO_MISINFO'}, v78: {'off': 'MISINFO', 'on': 'MISINFO', 'upper': 'MISINFO'}, v87: {'off': 'MISINFO', 'on': 'MISINFO', 'upper': 'MISINFO'}

Golden v135 (B): off NO_MISINFO, on NO_MISINFO, upper NO_MISINFO

### A. T66 stored states (tune): 18 videos

**as shipped (T69 switch off)**: accuracy 11/18; sent to review 17/18; `contradiction_context_mismatch` fired on 0 video(s)

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE |
|---|---|---|---|---|
| MISINFO | 5 | 1 | 1 | 0 |
| NO_MISINFO | 0 | 2 | 0 | 1 |
| DEBUNKING | 1 | 0 | 1 | 0 |
| CANNOT_RECOGNIZE | 3 | 0 | 0 | 3 |

**T69 switch on (stored verdicts)**: accuracy 11/18; sent to review 17/18; `contradiction_context_mismatch` fired on 0 video(s)

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE |
|---|---|---|---|---|
| MISINFO | 5 | 1 | 1 | 0 |
| NO_MISINFO | 0 | 2 | 0 | 1 |
| DEBUNKING | 1 | 0 | 1 | 0 |
| CANNOT_RECOGNIZE | 3 | 0 | 0 | 3 |

**T69 switch on, mismatch assumed on every CONTRADICTED verdict (upper bound)**: accuracy 11/18; sent to review 17/18; `contradiction_context_mismatch` fired on 0 video(s)

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE |
|---|---|---|---|---|
| MISINFO | 5 | 1 | 1 | 0 |
| NO_MISINFO | 0 | 2 | 0 | 1 |
| DEBUNKING | 1 | 0 | 1 | 0 |
| CANNOT_RECOGNIZE | 3 | 0 | 0 | 3 |

Per video (label, rule; ✱ = rule fired; ▼ = worse than `off` vs gold):

| video | gold | off | on | upper |
|---|---|---|---|---|
| v109 | MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v11 | CANNOT_RECOGNIZE | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v114 | MISINFO | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` |
| v120 | MISINFO | MISINFO (unproven) `unproven` | MISINFO (unproven) `unproven` | MISINFO (unproven) `unproven` |
| v122 (T67-fixed) | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v150 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` |
| v176 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v23 | DEBUNKING | MISINFO (denies_supported) `refuted_supported` | MISINFO (denies_supported) `refuted_supported` | MISINFO (denies_supported) `refuted_supported` |
| v39 | DEBUNKING | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` |
| v65 | CANNOT_RECOGNIZE | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v69 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v71 (T67-fixed) | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v78 (T67-fixed) | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v87 (T67-fixed) | MISINFO | MISINFO (denies_supported) `refuted_supported` | MISINFO (denies_supported) `refuted_supported` | MISINFO (denies_supported) `refuted_supported` |
| v88 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v92 | CANNOT_RECOGNIZE | MISINFO (unproven) `unproven` | MISINFO (unproven) `unproven` | MISINFO (unproven) `unproven` |
| v94 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v95 | NO_MISINFO | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |

### B. Golden claims (tune, in scope): 48 videos

**as shipped (T69 switch off)**: accuracy 43/48; sent to review 24/48; `contradiction_context_mismatch` fired on 0 video(s)

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE |
|---|---|---|---|---|
| MISINFO | 13 | 2 | 0 | 3 |
| NO_MISINFO | 0 | 11 | 0 | 0 |
| DEBUNKING | 0 | 0 | 3 | 0 |
| CANNOT_RECOGNIZE | 0 | 0 | 0 | 16 |

**T69 switch on (stored verdicts)**: accuracy 43/48; sent to review 24/48; `contradiction_context_mismatch` fired on 0 video(s)

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE |
|---|---|---|---|---|
| MISINFO | 13 | 2 | 0 | 3 |
| NO_MISINFO | 0 | 11 | 0 | 0 |
| DEBUNKING | 0 | 0 | 3 | 0 |
| CANNOT_RECOGNIZE | 0 | 0 | 0 | 16 |

**T69 switch on, mismatch assumed on every CONTRADICTED verdict (upper bound)**: accuracy 42/48; sent to review 25/48; `contradiction_context_mismatch` fired on 1 video(s)

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE |
|---|---|---|---|---|
| MISINFO | 12 | 2 | 0 | 4 |
| NO_MISINFO | 0 | 11 | 0 | 0 |
| DEBUNKING | 0 | 0 | 3 | 0 |
| CANNOT_RECOGNIZE | 0 | 0 | 0 | 16 |

Per video (label, rule; ✱ = rule fired; ▼ = worse than `off` vs gold):

| video | gold | off | on | upper |
|---|---|---|---|---|
| v11 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v21 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v22 | MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v23 | DEBUNKING | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` |
| v24 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v27 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v36 | MISINFO | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v39 | DEBUNKING | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` |
| v44 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v51 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v58 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v65 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `refuted_unsettled` | CANNOT_RECOGNIZE `refuted_unsettled` | CANNOT_RECOGNIZE `refuted_unsettled` |
| v68 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v69 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v70 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v71 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v78 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v79 | DEBUNKING | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` | DEBUNKING `refuted_contradicted` |
| v86 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v87 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v88 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v92 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v94 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v95 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v96 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v100 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v109 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v110 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v111 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v114 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v119 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | CANNOT_RECOGNIZE `nothing_judged`✱▼ |
| v120 | MISINFO | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v121 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v122 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v123 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v131 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v135 | NO_MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v141 | MISINFO | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` | NO_MISINFO `judged_nothing_false_endorsed` |
| v143 | MISINFO | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v144 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` |
| v146 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` |
| v150 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` |
| v152 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` |
| v160 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` | CANNOT_RECOGNIZE `no_claims` |
| v167 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v176 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |
| v177 | MISINFO | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` | MISINFO (contradicted) `endorsed_contradicted` |
| v180 | CANNOT_RECOGNIZE | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` | CANNOT_RECOGNIZE `nothing_judged` |

