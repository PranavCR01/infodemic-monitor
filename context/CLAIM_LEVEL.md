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

- **New `Claim` schema:**
  ```
  Claim {
    text: str
    label: MisinfoLabel
    confidence: float
    evidence: list[str]
    citations: list[PubMedCitation]
  }
  ```
- `ClassificationResult.claims: list[Claim]` — added **alongside** the existing
  video-level `label`/`confidence`/`explanation` fields, for backward compatibility.
  Nothing that reads the video-level fields today should break.
- DB migration: a `claims` JSON column on the `results` table. Migration number is
  **0006 or 0007** depending on what the production track has already merged — check
  `backend/app/db/migrations/versions/` before naming your revision, and coordinate with
  the production student so you don't collide.
- Rewrite the classification tool schema (whatever structured-output/tool-call schema the
  Anthropic/OpenAI providers use) to return per-claim verdicts instead of one flat verdict.
- Unify claim extraction so `pubmed.py` grounds the **same** claims the classifier
  identified, instead of re-extracting its own set.

## 6. Objectives This Semester

1. **Define the `Claim` schema** — coordinate with the production student before
   finalizing, since it touches `ClassificationResult` and the DB schema they own.
2. **Build a prototype claim-level classifier** — can run standalone (a script, not wired
   into `run_pipeline`) for this semester.
3. **Create a labeled dataset** of at least 20 videos with **per-claim** ground truth
   (not just video-level labels — this is the ground-truth evaluation last semester
   skipped).
4. **Produce a written integration spec** detailed enough for the production student to
   implement without needing to re-derive design decisions.

## 7. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

-

## 8. PR Requirements

- Schema changes and prototype code go up as PRs, using
  `.github/ISSUE_TEMPLATE/claim-level.md` for the originating issue.
- **Coordinate with the production student on any change to core schemas** — this includes
  `ClassificationResult`, `PubMedCitation`, and any new Alembic migration. Don't land a
  migration number that collides with theirs.
- Reference the GitHub issue (`Closes #N`).
- Update this file with findings and decisions as they're made.
