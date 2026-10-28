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

**Merged (#11):** the schema types in `backend/app/core/schemas/pipeline.py`. Nothing in
the pipeline uses them yet, so production behaviour is unchanged.

- **`Claim` schema:**
  ```
  Claim {
    claim_id: str        # stable ID per video, e.g. "c1"
    text: str
    label: MisinfoLabel
    confidence: float    # clamped to [0, 1]
    evidence: list[str]
    citations: list[PubMedCitation]
  }
  ```
  `claim_id` is new compared with the original spec. `PubMedCitation.claim` was free
  text (the search-query string `pubmed.py` generated), not a stable ID, so citations
  could not be reliably matched back to the classifier's claims without one.
- `PubMedCitation.claim_id: Optional[str] = None`, alongside the existing `claim: str`.
  Optional until grounding passes claim IDs through; required fields would break the
  current `pubmed.py`, which builds citations without an ID.
- `ClassificationResult.claims: Optional[list[Claim]] = None`: additive and backward
  compatible.

**Integration spec (draft; to be built and tested in the #12 prototype first):**

- DB migration: `claims` JSON column on `results`. Number TBD (0006 or 0007): check
  `backend/app/db/migrations/versions/` and coordinate with the production student
  before naming it. Not yet created.
- **Both providers' tool/prompt schemas** need a `claims` array (per-claim
  `claim_id`/`text`/`label`/`confidence`/`evidence`), plus a `_safe_claims()` parser
  in each.
- **`pubmed.py`**: `ground_transcript()` takes `claims: list[Claim]` instead of the raw
  transcript, removing its independent claim-extraction step. `claim_id` threads
  through to each returned `PubMedCitation`. `run_pipeline()` passes the classifier's
  claims into grounding and regroups citations onto each `Claim` by `claim_id`. This is
  the fix for the flat-citations problem in §3/§4.
- **Open questions for the prototype:**
  - Full claim sentences make poor PubMed search terms compared with the current 3–7
    word queries; claims probably need converting to a short search term first.
  - If grounding depends on the model returning `claims`, flagged videos must not lose
    all citations when the model omits them: either make `claims` required in the tool
    schema or keep the transcript-based search as a fallback.

## 6. Objectives This Semester

1. ~~**Define the `Claim` schema**~~: done, schema types merged (#11).
2. **Build a prototype claim-level classifier** (#12, Kiara): standalone script in
   `research/claim-level/`, not wired into `run_pipeline`. Starting point: the design
   in §5.
3. **Create a labeled dataset** of at least 20 videos with **per-claim** ground truth
   (#13, Delia). *In progress: scaffold and labeling guidelines created, no videos
   labeled yet.*
4. **Produce a written integration spec** detailed enough for the production student to
   implement without needing to re-derive design decisions. §5 is the draft.

## 7. Check-In Log

_(Add a dated entry each week with what was done, what was found, and what's next.)_

- **2026-10-10 (Kiara)** — PubMed grounding relevance fix.
  - **Found:** `_query_claim()` called ESearch without a `sort` parameter, so PubMed returned
    the most recently published papers matching the query terms, not the most relevant ones.
    With `PUBMED_RESULTS_PER_CLAIM=2`, citations were often off-topic. Example: the query
    "vaccines cause autism" returned a 2026 paper on GAD2 variants and one on antidepressant
    mortality in autism.
  - **Done:** added `sort=relevance` to the ESearch call. The same query now returns the 2014
    meta-analysis "Vaccines are not associated with autism" first.
  - **Next:** consider preferring systematic reviews / meta-analyses per claim, with a
    fallback to an unfiltered relevance search. Not done here — it belongs with the
    per-claim grounding design in the prototype (#12).
- **2026-10-19 (Delia)**: Finished a full design pass against current `backend/` code
  (schemas, both providers, `pubmed.py`, `run_pipeline`). `Claim` schema finalized with
  the `claim_id` addition. Full chain designed: classifier extracts claims with stable
  IDs → grounding uses those same claims → citations regrouped by `claim_id`. Next:
  build the prototype and start the dataset.
- **2026-10-26 (Delia)**: Created dataset scaffold under `research/claim-level/dataset/`
  (`videos.csv`, `claims.csv`, labeling guidelines in `README.md`). No videos labeled
  yet. Next: label first ~5 videos to test the process, then scale to 20+.
- **2026-10-28**: PR #40 trimmed to the schema types only, so the live pipeline is
  unchanged; the provider, `pubmed.py` and `run_pipeline` changes are carried forward as
  the §5 integration spec for the #12 prototype.

## 8. PR Requirements

- Schema changes and prototype code go up as PRs, using
  `.github/ISSUE_TEMPLATE/claim-level.md` for the originating issue.
- **Coordinate with the production student on any change to core schemas** — this includes
  `ClassificationResult`, `PubMedCitation`, and any new Alembic migration. Don't land a
  migration number that collides with theirs.
- Reference the GitHub issue (`Closes #N`).
- Update this file with findings and decisions as they're made.
