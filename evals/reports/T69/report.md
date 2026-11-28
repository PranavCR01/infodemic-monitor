# T69: a context-mismatched contradiction can't decide MISINFO alone (switch OFF)

Tune split only, offline, no model calls, $0. Development numbers, not product accuracy.
Full per-video tables: `replay.md`; raw: `results.json`; script:
`backend/scripts/t69_context_mismatch_replay.py`.

## Trigger

Production jobs cf2ea579 and f85f2daa (tune v135, labmuffin benzene; golden NO_MISINFO) came
out MISINFO, decided only by "Benzene doesn't get through skin easily", CONTRADICTED by two
narrative reviews of occupational solvent exposure. The verifier's own free-text
limitations noted the setting mismatch, but nothing structured carried it to the judge.

## What was built

| | |
| --- | --- |
| Switch (default) | `routing.CONTEXT_MISMATCH_RULE = False` |
| Verifier (§7), switch on only | The `record_verdict` tool gains an optional structured field `evidence_context`: `matches` / `different_population` / `different_exposure_setting`, plus one instruction line. A CONTRADICTED verdict with a mismatch value gets the limitation code `evidence_context_mismatch:<kind>`. With the switch off, the tool schema, prompt and results are byte-identical to before (tested). |
| Judge (§9) | An ENDORSES + CONTRADICTED claim is set aside (verdict kept, can't decide, label falls through) when **all** hold: (1) it is the only ENDORSES + CONTRADICTED claim; (2) every contradicting record it cites (≥1) has study type `narrative_review` or `in_vitro` (the reranker's bucket for lab, cell and in-silico/modelling studies), from the record's study type or PubMed publication type, so no primary human study, SR, RCT or guideline is among them; (3) the verdict carries the structured code from the verifier. Review reason `judge:contradiction_context_mismatch:<cid>` (always reviewed). |
| Reconciled with T67 (2) | One mechanism, not a parallel rule: `judge.set_aside_reason` returns T67's `thin_contradiction` (its own switch, still off, applied first) or T69's flag. Both share `judge.cited_contradicting`. They don't overlap: T67 catches contradictions with <2 on-topic records; T69 catches well-matched-on-topic but context-mismatched ones (v135's two reviews are on topic for "benzene", so T67's rule would not have fired). |
| Detection | No prose is read. Only the exact code `evidence_context_mismatch:<known kind>` counts; a free-text limitation saying "different exposure setting" does not (tested). |
| Wording | `REASON_TEXT`, judge `_FLAG_TEXT`, frontend `vocabulary.ts` (+ test). |

## Replay gate

Baseline = what ships today: T64 guard, T67 change 1 ON, change 2 OFF, change 3 ON.

- `off`: as shipped.
- `on`: switch on, stored verdicts.
- `upper`: switch on, **assuming the verifier flagged a mismatch on every CONTRADICTED verdict**.
  No stored verdict predates the new field, so `on` cannot fire on stored data. `upper` shows
  what the deterministic parts of the rule (sole deciding claim, evidence types) allow if
  the verifier's field were wrong in the worst way.

| Input | off | on | upper |
| --- | --- | --- | --- |
| A. T66 stored states (18 finished tune videos) | 11/18 | 11/18, 0 changes | 11/18, 0 changes, rule fired on 0 |
| B. Golden claims (48 in-scope tune videos) | 43/48 | 43/48, 0 changes | 42/48: **v119** (gold MISINFO) → CANNOT_RECOGNIZE |
| Sent to review, A / B | 17 / 24 | 17 / 24 | 17 / 25 |

**Videos T67 fixed (v71, v78, v87, v122 on A; 3d48e75e):** unchanged in all three configurations.
3d48e75e stays CANNOT_RECOGNIZE (`analysis_incomplete`) with the switch on, and T64's
d2bf4179 stays NO_MISINFO with identical review reasons (unit tests).

**v119 in `upper`.** Claim c4 "El Cancer es un hongo" (cancer is a fungus), ENDORSES +
CONTRADICTED by two reviews ("Cancer evolution: Darwin and beyond", narrative review;
"Hallmarks of cancer: the next generation", publication type Review but bucketed
`in_vitro` by the reranker's cue for "cancer cells"). It changes only if the verifier says
those reviews study a different population or exposure setting, which they don't: the
claim has no population or exposure. So on this data the structured field is what keeps
the rule safe, and it is the part the replay can't measure without re-running the
verifier.

**v135.** Golden claims (B): NO_MISINFO in all configurations (golden c4 is
INSUFFICIENT_EVIDENCE, so the production failure doesn't reproduce from golden claims).
The production failure is reproduced only by a **synthetic** stand-in in
`backend/app/tests/test_context_mismatch_t69.py` (two narrative reviews, verifier code
`different_exposure_setting`): MISINFO with the switch off, NO_MISINFO plus
`contradiction_context_mismatch:c4` with it on.

## Gaps, left for a person

1. **The v135 production fixture (cf2ea579 / f85f2daa) was not in the repo**, and this
   session's request to the coordinator was blocked by the environment's permission
   classifier. The gate was run on the T66 tune replay and golden claims as the lead's
   fallback instruction says. The real rows should be added and replayed before the
   switch goes on. They will still not fire the rule, because they predate the
   structured field: one verifier re-run of v135 with the switch on (a paid call, lead
   approval) is the real test.
2. **The verifier field is unmeasured.** Before turning the switch on, check the
   verifier's `evidence_context` on a labelled sample. v119 shows what a false
   "mismatch" would cost.
3. **`in_vitro` as "modelling".** The reranker has no separate modelling type. `in_vitro`
   ("lab, cell and in-silico (mechanistic)") is the closest bucket, so lab and cell
   studies also count as not primary human evidence. Its text cue also catches some
   narrative reviews (v119's "Hallmarks of cancer"). To restrict the rule to narrative
   reviews only, the lead can drop `in_vitro` from `judge.NARRATIVE_OR_MODELLING_TYPES`.
4. **"Only deciding claim"** is counted before T67's thin rule sets anything aside, so the
   rule never fires when two endorsed claims are contradicted, even if one of them is thin.
5. When the set-aside falls through to another MISINFO rule (e.g. a denied supported
   claim), the label stays MISINFO on that other basis, with the T69 reason still shown.
6. The limitation code is shown raw among the verdict's limitations, as T64's
   `outcome_unspecified` / `search_too_thin` codes are.
