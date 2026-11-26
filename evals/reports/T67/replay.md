# T67 replay: critic-budget and thin-contradiction label rules

Code c9decd02cc2e (auto/T67). No model calls. Configurations: (a) T64 only; (b) T64 + change 1; (c) T64 + change 2; (d) T64 + changes 1 and 2; (e) T64 + change 3 (analysis_incomplete).

## A. T66 finished videos (stored states)

Pipeline states from T66 (PR #146, `origin/auto/T66`), run at 3372ef3 (pre-T64 upstream). The replay re-applies only the T64 guard, the judge and the review rule; extraction, retrieval, verification, the critic and validation are not re-run.
Excluded: v21 (status 'not_run:budget_mid_video') (not run, never scored).

### A. T66 stored states: 18 videos

**(a) T64 only**: accuracy 7/18 = 0.389; sent to review 17/18; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×0, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **2** | 2 | 0 | 3 | 7 |
| **NO_MISINFO** | 0 | **1** | 0 | 2 | 3 |
| **DEBUNKING** | 1 | 0 | **1** | 0 | 2 |
| **CANNOT_RECOGNIZE** | 2 | 0 | 1 | **3** | 6 |

**(b) T64 + change 1**: accuracy 11/18 = 0.611; sent to review 17/18; reasons added: `second_check_disagreed` ×43, `thin_contradiction` ×0, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **5** | 1 | 1 | 0 | 7 |
| **NO_MISINFO** | 0 | **2** | 0 | 1 | 3 |
| **DEBUNKING** | 1 | 0 | **1** | 0 | 2 |
| **CANNOT_RECOGNIZE** | 3 | 0 | 0 | **3** | 6 |

**(c) T64 + change 2**: accuracy 7/18 = 0.389; sent to review 17/18; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×2, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **1** | 2 | 0 | 4 | 7 |
| **NO_MISINFO** | 0 | **1** | 0 | 2 | 3 |
| **DEBUNKING** | 1 | 0 | **1** | 0 | 2 |
| **CANNOT_RECOGNIZE** | 1 | 0 | 1 | **4** | 6 |

**(d) T64 + changes 1 and 2**: accuracy 10/18 = 0.556; sent to review 17/18; reasons added: `second_check_disagreed` ×43, `thin_contradiction` ×3, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **4** | 1 | 1 | 1 | 7 |
| **NO_MISINFO** | 0 | **2** | 0 | 1 | 3 |
| **DEBUNKING** | 1 | 0 | **1** | 0 | 2 |
| **CANNOT_RECOGNIZE** | 2 | 0 | 1 | **3** | 6 |

**(e) T64 + change 3 (analysis_incomplete)**: accuracy 7/18 = 0.389; sent to review 17/18; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×0, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **2** | 2 | 0 | 3 | 7 |
| **NO_MISINFO** | 0 | **1** | 0 | 2 | 3 |
| **DEBUNKING** | 1 | 0 | **1** | 0 | 2 |
| **CANNOT_RECOGNIZE** | 2 | 0 | 1 | **3** | 6 |

Label changes (b) vs (a): 6; **worse: v114**

| video | gold | (a) | (b) | rule (b) | verdict |
| --- | --- | --- | --- | --- | --- |
| v11 | CANNOT_RECOGNIZE | DEBUNKING | MISINFO (contradicted) | `endorsed_contradicted` | neutral |
| v114 | MISINFO | CANNOT_RECOGNIZE | DEBUNKING | `refuted_contradicted` | worse |
| v122 | MISINFO | CANNOT_RECOGNIZE | MISINFO (contradicted) | `endorsed_contradicted` | fixed |
| v71 | NO_MISINFO | CANNOT_RECOGNIZE | NO_MISINFO | `judged_nothing_false_endorsed` | fixed |
| v78 | MISINFO | CANNOT_RECOGNIZE | MISINFO (contradicted) | `endorsed_contradicted` | fixed |
| v87 | MISINFO | NO_MISINFO | MISINFO (denies_supported) | `refuted_supported` | fixed |

Label changes (c) vs (a): 2; **worse: v88**

| video | gold | (a) | (c) | rule (c) | verdict |
| --- | --- | --- | --- | --- | --- |
| v65 | CANNOT_RECOGNIZE | MISINFO (contradicted) | CANNOT_RECOGNIZE | `refuted_unsettled` | fixed |
| v88 | MISINFO | MISINFO (contradicted) | CANNOT_RECOGNIZE | `nothing_judged` | worse |

Label changes (d) vs (a): 8; **worse: v114, v88**

| video | gold | (a) | (d) | rule (d) | verdict |
| --- | --- | --- | --- | --- | --- |
| v11 | CANNOT_RECOGNIZE | DEBUNKING | MISINFO (contradicted) | `endorsed_contradicted` | neutral |
| v114 | MISINFO | CANNOT_RECOGNIZE | DEBUNKING | `refuted_contradicted` | worse |
| v122 | MISINFO | CANNOT_RECOGNIZE | MISINFO (contradicted) | `endorsed_contradicted` | fixed |
| v65 | CANNOT_RECOGNIZE | MISINFO (contradicted) | DEBUNKING | `refuted_contradicted` | neutral |
| v71 | NO_MISINFO | CANNOT_RECOGNIZE | NO_MISINFO | `judged_nothing_false_endorsed` | fixed |
| v78 | MISINFO | CANNOT_RECOGNIZE | MISINFO (contradicted) | `endorsed_contradicted` | fixed |
| v87 | MISINFO | NO_MISINFO | MISINFO (denies_supported) | `refuted_supported` | fixed |
| v88 | MISINFO | MISINFO (contradicted) | CANNOT_RECOGNIZE | `nothing_judged` | worse |

Label changes (e) vs (a): 0; none worse

## B. Golden claims, all in-scope tune videos

Golden stances and verdicts; the T64 guard re-checks golden UNSUPPORTED claims on the T38 frozen evidence. Cited records come from the golden set's offline evidence cache. No critic, so change 1 cannot fire here: (b) = (a), (d) = (c). No verifier errors in the golden set, so change 3 cannot fire: (e) = (a).
Cited evidence IDs not in the offline cache (treated as empty records): 5 (v68:c2:https://wwwn.cdc.gov/tsp/PHS/PHS.aspx?phsid=336&toxid=59, v70:c2:https://api.nal.usda.gov/fdc/v1/food/174832?api_key=DEMO_KEY, v70:c2:https://api.nal.usda.gov/fdc/v1/food/2257045?api_key=DEMO_KEY, v70:c2:https://api.nal.usda.gov/fdc/v1/food/2257046?api_key=DEMO_KEY, v70:c2:https://api.nal.usda.gov/fdc/v1/food/171265?api_key=DEMO_KEY)

### B. golden claims, in-scope tune: 48 videos

**(a) T64 only**: accuracy 43/48 = 0.896; sent to review 24/48; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×0, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **13** | 2 | 0 | 3 | 18 |
| **NO_MISINFO** | 0 | **11** | 0 | 0 | 11 |
| **DEBUNKING** | 0 | 0 | **3** | 0 | 3 |
| **CANNOT_RECOGNIZE** | 0 | 0 | 0 | **16** | 16 |

**(b) T64 + change 1**: accuracy 43/48 = 0.896; sent to review 24/48; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×0, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **13** | 2 | 0 | 3 | 18 |
| **NO_MISINFO** | 0 | **11** | 0 | 0 | 11 |
| **DEBUNKING** | 0 | 0 | **3** | 0 | 3 |
| **CANNOT_RECOGNIZE** | 0 | 0 | 0 | **16** | 16 |

**(c) T64 + change 2**: accuracy 41/48 = 0.854; sent to review 31/48; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×10, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **11** | 3 | 0 | 4 | 18 |
| **NO_MISINFO** | 0 | **11** | 0 | 0 | 11 |
| **DEBUNKING** | 0 | 0 | **3** | 0 | 3 |
| **CANNOT_RECOGNIZE** | 0 | 0 | 0 | **16** | 16 |

**(d) T64 + changes 1 and 2**: accuracy 41/48 = 0.854; sent to review 31/48; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×10, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **11** | 3 | 0 | 4 | 18 |
| **NO_MISINFO** | 0 | **11** | 0 | 0 | 11 |
| **DEBUNKING** | 0 | 0 | **3** | 0 | 3 |
| **CANNOT_RECOGNIZE** | 0 | 0 | 0 | **16** | 16 |

**(e) T64 + change 3 (analysis_incomplete)**: accuracy 43/48 = 0.896; sent to review 24/48; reasons added: `second_check_disagreed` ×0, `thin_contradiction` ×0, `analysis_incomplete` ×0

| gold \ ours | MISINFO | NO_MISINFO | DEBUNKING | CANNOT_RECOGNIZE | n |
|---|---|---|---|---|---|
| **MISINFO** | **13** | 2 | 0 | 3 | 18 |
| **NO_MISINFO** | 0 | **11** | 0 | 0 | 11 |
| **DEBUNKING** | 0 | 0 | **3** | 0 | 3 |
| **CANNOT_RECOGNIZE** | 0 | 0 | 0 | **16** | 16 |

Label changes (b) vs (a): 0; none worse

Label changes (c) vs (a): 2; **worse: v119, v177**

| video | gold | (a) | (c) | rule (c) | verdict |
| --- | --- | --- | --- | --- | --- |
| v119 | MISINFO | MISINFO (contradicted) | CANNOT_RECOGNIZE | `nothing_judged` | worse |
| v177 | MISINFO | MISINFO (contradicted) | NO_MISINFO | `judged_nothing_false_endorsed` | worse |

Label changes (d) vs (a): 2; **worse: v119, v177**

| video | gold | (a) | (d) | rule (d) | verdict |
| --- | --- | --- | --- | --- | --- |
| v119 | MISINFO | MISINFO (contradicted) | CANNOT_RECOGNIZE | `nothing_judged` | worse |
| v177 | MISINFO | MISINFO (contradicted) | NO_MISINFO | `judged_nothing_false_endorsed` | worse |

Label changes (e) vs (a): 0; none worse

Thin contradictions on golden claims (config c):

- v23:c2 (REFUTES), contradicting PMID:40711778
- v27:c3 (ENDORSES), contradicting PMID:38282081
- v78:c2 (ENDORSES), contradicting PMID:34401872
- v86:c2 (ENDORSES), contradicting PMID:38169370, PMID:22229120
- v87:c1 (ENDORSES), contradicting PMID:29528501
- v88:c3 (ENDORSES), contradicting PMID:7477165
- v109:c7 (ENDORSES), contradicting PMID:42308439, PMID:39764175
- v111:c2 (ENDORSES), contradicting PMID:29771297
- v119:c4 (ENDORSES), contradicting PMID:34459009, PMID:21376230
- v177:c2 (ENDORSES), contradicting PMID:17987546, PMID:23459877, PMID:18652789

