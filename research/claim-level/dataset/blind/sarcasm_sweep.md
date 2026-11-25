# Sarcasm rule sweep (T47, 2026-11-25)

**Rule** (lead decision, 2026-11-25; README §5, REVIEW.md step 4): a sarcastic or
mocking debunk with a clear target is `REFUTES`, with the sarcasm explained in the
notes. `UNCLEAR` stays for genuinely ambiguous tone, several speakers who
disagree, a speaker who contradicts themselves, and jokes with no clear claim
being rejected.

**Method.** Every `UNCLEAR` `speaker_stance` in `claims.csv` (4 rows: 2 tune,
2 test) was re-read against the transcript and on-screen text and decided by the
rule alone. No model output was looked at. Changes are recorded in
`scripts/adjudication.py` (`SARCASM_CLAIMS`, `SARCASM_VIDEOS`) and applied by
`scripts/build_csvs.py`; video labels and review reasons are re-derived, not
hand-edited.

## Tune split (2 rows re-checked, 1 relabelled)

| Row | Decision | Why |
|---|---|---|
| v86 c3 | `UNCLEAR` → `REFUTES` | The speaker mocks the chimpanzee-origin account of HIV ("had to come from a monkey in Africa that one person slept with...") to reject it. The target is clear, so this is a sarcastic rejection, not ambiguous tone. The verdict stays `SUPPORTED`, so the row is a denial of a true claim (§9 rule 2) and adds `denies_supported:c3` to the video's review reasons. The label stays `MISINFO`/`contradicted` (decided by c2 and c4). |
| v121 c1 | stays `UNCLEAR` | A gynaecologist's joke list of "three advantages" of garlic ovules; the third is that the smell may work as "contraception" by keeping partners away. The joke ridicules garlic ovules in general, but the row's claim (garlic ovules as contraception) is the punchline itself, not a claim anyone makes that is being rejected. That is a joke with no clear claim being rejected, so `UNCLEAR` under the revised rule. The real debunk follows "now, joking aside" and is carried by c2 and c3 (`ENDORSES` + `SUPPORTED`); the video stays `NO_MISINFO`. The verdict stays `NOT_VERIFIABLE`. |

## Test split (2 rows re-checked, 0 relabelled)

Reported in aggregate only. One row is a light, ambiguous-tone relay of a
remedy where it cannot be told whether the speaker is mocking or entertaining
it (genuinely ambiguous tone); the other is one speaker's claim that the other
speaker never addresses (no position taken, not sarcasm). Neither qualifies, so
neither changed, and no test-split video label changed.

## Effect

- `speaker_stance`: REFUTES 58 → 59, UNCLEAR 4 → 3.
- Video labels: none changed (v86 stays MISINFO/contradicted).
- Review reasons: v86 gains `denies_supported:c3`.
