# Claim-Level Classification Track Context

## 1. What This Role Is

One student (Student-CL1) working solo on **research + implementation**. Unlike the other
research tracks, this one is expected to produce a schema and a prototype, not just a
written recommendation — but the prototype stays standalone this semester (not integrated
into production).

## 2. Last Semester Findings (Task 5)

Feasibility was confirmed: an LLM can reliably extract discrete claims from a transcript
and produce per-claim JSON with a label and confidence for each. What's **missing**:

- No ground-truth evaluation was completed — nobody checked the per-claim outputs against
  labeled reality.
- No formal schema was defined — last semester's output was ad hoc JSON, not a typed
  contract.
- No UI was built.

## 3. Current System

Today, `ClassificationResult` carries exactly **one** label, **one** confidence, **one**
explanation for the whole video, plus a flat `evidence_snippets` list and a flat
`citations` list.

`PubMedCitation` already has a `claim` field — individual citations *are* tagged with
which claim they came from internally — but by the time they reach the final result, that
structure is thrown away: `ground_transcript()` extends all citations into one flat list
with no claim grouping.

There are also **two uncoordinated LLM calls** that each independently think about
"claims":
- The classifier extracts evidence snippets as part of producing the video-level verdict.
- `pubmed.py` independently re-extracts claims from the transcript, purely to generate
  PubMed search queries.

These two calls don't share claim IDs — they're solving overlapping problems with no
shared vocabulary.

## 4. The Coordination Problem

To build a claim-level UI properly, these two claim-extraction steps need to agree on a
shared set of claim IDs. Otherwise the UI ends up with two different claim sets that don't
line up — the classifier's claim #2 might not be the same real-world claim as pubmed.py's
claim #2. This is the central design problem for this track, not an afterthought.

## 5. Schema Change Needed
- **`Claim` schema** (designed and validated, pending production-student sign-off):
  ```
  Claim {
    claim_id: str 
# NEW — not in original spec. PubMedCitation.claim was free
# text (the search-query string pubmed.py generated), not a
# stable ID, so citations couldn’t be reliably matched back
# to the classifier’s claims without one.
    text: str
    label: MisinfoLabel
    confidence: float
    evidence: list[str]
    citations: list[PubMedCitation]
  }
  ```
- `PubMedCitation` also gets `claim_id: str` added, alongside existing `claim: str`.
- `ClassificationResult.claims: list[Claim]` — additive, backward compatible.
- DB migration: `claims` JSON column on `results`. Number TBD (0006 or 0007) —
  check `backend/app/db/migrations/versions/` and coordinate with the production
  student before naming it. Not yet created.
- **Both providers' tool/prompt schemas** need a `claims` array (per-claim
  `claim_id`/`text`/`label`/`confidence`/`evidence`), plus a `_safe_claims()`
  parser in each. Fully designed against current code.
- **`pubmed.py`**: `ground_transcript()` now takes `claims: list[Claim]` instead
  of raw transcript — removes its old independent claim-extraction step
  entirely. `claim_id` threads through to each returned `PubMedCitation`.
  `run_pipeline()` passes the classifier's claims into grounding and regroups
  citations back onto each `Claim` by `claim_id`. This is the actual fix for
  the flat-citations problem in §3/§4.
- Open question: claim text may need converting to a shorter PubMed search
  term — current design searches on the full claim text as-is.

## 6. Objectives This Semester

1. ~~**Define the `Claim` schema**~~ — design complete, pending
   production-student coordination.
2. **Build a prototype claim-level classifier** — design validated, not yet
   built. Next: standalone script in `research/claim-level/`.
3. **Create a labeled dataset** of ≥20 videos with per-claim ground truth —
   not started.
4. **Produce a written integration spec** - Section 5 is the draft 

## 7. Check-In Log

- **2026-10-19**: Finished full design pass against current `backend/` code
  (schemas, both providers, `pubmed.py`, `run_pipeline`). `Claim` schema
  finalized with `claim_id` addition. Full chain validated: classifier
  extracts claims with stable IDs → grounding uses those same claims →
  citations regrouped by `claim_id`. Closes the coordination problem in §4.
  Nothing implemented in `backend/` yet — prototyping standalone next. Next:
  build prototype, open issue + PR, start dataset.

## 8. PR Requirements

- Schema changes and prototype code go up as PRs, using
  `.github/ISSUE_TEMPLATE/claim-level.md` for the originating issue.
- **Coordinate with the production student on any change to core schemas** — this includes
  `ClassificationResult`, `PubMedCitation`, and any new Alembic migration. Don't land a
  migration number that collides with theirs.
- Reference the GitHub issue (`Closes #N`).
- Update this file with findings and decisions as they're made.
