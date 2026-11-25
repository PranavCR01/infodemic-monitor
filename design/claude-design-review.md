# Claude Design export: review against BRIEF.md, API gaps, build plan

Phase 1 of the frontend work. The export is in `design/claude-design/`. Its own `HANDOFF.md` and `CLAUDE.md` describe it. Status: waiting for the project lead's go-ahead and answers to §4.

## 1. Review against the brief

### What holds up
- **The four labels are distinct.** MISINFO is rust with a warning triangle. DEBUNKED is teal with a shield. NO-MISINFO is blue with a check. CANNOT RECOGNIZE is grey with a help icon and a dashed border. Every label, verdict, stance and status is icon + text, and stance chips have no colour at all.
- **DEBUNKED vs MISINFO.** The deciding claim also carries a fixed "what this means" sentence (`claimMeaning()` in `starter/lib/vocabulary.ts`). It is written in code, never taken from model output. For REFUTES + CONTRADICTED it reads "The speaker refutes a claim the evidence contradicts. This corrects misinformation."
- **INSUFFICIENT EVIDENCE** is a pill with no fill and a dashed border, with the copy "Untested is not the same as false". It never uses the rust of CONTRADICTED.
- **CANNOT RECOGNIZE** is styled as an abstention, never as an error. The red error tokens are kept for system failures only.
- **No internal names in the screens.** No raw enum or model ID appears in the product screens. Model IDs appear only on `/evaluation`, as the brief allows for the admin screen.
- **A reason is required for every review decision**, in all three review screens. The note has a 10-character minimum in Direction 3. The audit trail is append-only.
- **Contrast** (I recomputed every pair):
  - every text/background pair passes AA in both themes;
  - the lowest is `--text-3` on `--sunken` at 4.92:1;
  - each label and verdict colour on its own tint is 6.0–7.0:1.

### Deviations from the brief and other gaps (ranked by risk)
1. **The design ties severity to more than queue order.**
   - The brief says severity (HIGH / MEDIUM / LOW) only orders the queue.
   - The design instead uses two levels, "High / Normal priority", defined as "a MISINFO label or a possible debunk". That is a different rule from the backend's claim-based severity (§12, T22).
   - High priority also changes the reviewer's workflow. Direction 3 asks for the reviewer's own judgement before revealing the system's.
   - The label is not affected, but this goes past "orders the queue". **Needs a decision (Q1).**
2. **No severity override in the design.** Brief screen 8 asks for "severity override with reason", and the backend has `override_claim_severity`. No screen shows it. I would add a small "Change priority" control with a required reason to the workspace, built from existing components.
3. **The decision list differs from the backend.**
   - The design has Approve, Correct, Reject and Re-analyse.
   - The backend's `ReviewAction` also has `MARK_INSUFFICIENT`.
   - The baseline workspace takes one free-text reason; Direction 3 takes a reason code plus a note.
   - I'd use reason code + note everywhere and hide MARK_INSUFFICIENT, which is the same as Correct with the label set to CANNOT RECOGNIZE. **Q2.**
4. **"Not required" review status.** The design adds a fifth review status, "Not required", which the brief doesn't have. I'd keep it; it is what a finished result with no review shows. It needs T26 to return it. **Q3** (the design's own open decision 3).
5. **The upload limit is wrong.** The design says "up to 3 minutes"; the backend allows 600 s (`config/guardrails.yaml`). The UI must show the server's limit. **Q4: which one is right?**
6. **Fields the backend doesn't store.**
   - Submit has optional "Title" and "Platform" fields. Jobs and the result show a title and thumbnail.
   - None of these are stored. I'd drop them for v1 and show the file name.
7. **Resumable upload.** The handoff asks for resumable upload; T20 gives a single signed URL. I'll do one PUT with a progress bar and cancel. Resumable (TUS) is out of scope.
8. **Routes.**
   - The design uses `/sign-in`, `/videos`, `/videos/[id]`, `/review` and `/evaluation`. Today the app has `/login` and `/jobs`.
   - I'd adopt the design's routes and redirect the old ones.
9. **Border tokens are below 3:1.** `--border-strong` on white is 1.6:1, so input outlines fail WCAG 1.4.11 (non-text contrast) and the dashed outlines are faint.
   - Labels still pass 1.4.1 because icon + text carry the meaning.
   - I'll add an `--input-border` token of at least 3:1 for form controls and leave the decorative borders alone.
10. **MISINFO and DEBUNKED tints match in greyscale.** They have almost the same lightness, so on paper they are told apart by icon and text only. The design says so itself. The export always prints the label name, so I accept this.
11. **Suggested dependencies.** The handoff suggests shadcn/Radix, SWR, visx + Recharts and next-intl. I'd add only:
    - `@radix-ui/react-dialog`, for the drawer's focus trap;
    - vitest + Testing Library, for tests;
    - a small in-house polling hook, because the handoff's back-off and pause-when-hidden rules are specific and easier to test that way.

    I'd use one chart library, later, for evaluation, and keep strings in `vocabulary.ts` until i18n is actually scheduled.
12. **Direction 3 is the expensive option.** The result screen syncs the video, the timeline, the transcript and margin notes. The design itself calls this its weakest point. I'd build the two-column fallback first (transcript beside the claim rows) behind the same data and components, then the margin notes if there is time before the WHO demo. **Q5.**

## 2. Screen → API map: what's missing
T26–T29 refer to the backend tasks the coordinating session has queued: T26 exposes stored fields, T27 review endpoints and roles, T28 job progress and list filters, T29 playback and export.

| Screen | Needs that the API doesn't return | Covered by |
|---|---|---|
| All | Role claim (analyst/reviewer/admin) for middleware and nav | T27 |
| All, review, jobs | **Video/job owner.** The `videos` table has no owner column. Without one there is no "Submitted by", no block on reviewing your own submission, no "Decided by me" and no per-user jobs list | **Not in T26–T29 as described. Needs adding (T27?)** |
| Submit | Server limits (`max_bytes` is returned per upload; `max_duration_seconds` is not), to show before upload | T26 or small add |
| Jobs list | total, search, state filter, "needs review" filter, review status, claim count, current step sub-line | T28 (+ T26 for review status) |
| Job progress | current step out of 8, per-step durations, Queued/Retrying, attempt n of m, failed step + plain reason, **queue position ("2 videos are ahead")** | T28; queue position not mentioned |
| Video result | stance rationale + quoted segment ids, claim source (speech/screen), transcript + OCR segments with times, evidence source kind / year / publisher / passage, review status after a decision + reviewer + date, deciding-claim chain, signed playback URL | T26, T29 |
| Video result | **"How we searched"**: PubMed query, sites searched, results screened/kept. Not persisted anywhere today | **New** |
| Video result | "Request review" on a result that wasn't sent to review | **New** (T27?) |
| Claim detail | critic notes; a quoted passage per source (only the abstract is stored); evidence-strip level mapping (backend has 12 study types, the strip has 4 levels + a guidance badge). Mapping lives in the frontend | T26; mapping in the frontend |
| Claim detail | "Something looks wrong" feedback | **New, or drop for v1** |
| Review queue | case id, severity, reasons as plain text, waiting time, submitter, proposed label, decided-by | T27 + owner |
| Review workspace | decision POST (reason required, self-review rejected), severity override POST, audit trail GET, **pre-reveal judgement log** (Direction 3), per-source "your read" override, "already decided by …" | T27; pre-reveal and per-source overrides are **new fields** |
| Export | print view of the result + audit annex + methods box (models and sources used, date run) | T29 (or client-side from the result payload, which I'd prefer: no export endpoint needed) |
| Evaluation | `/v1/admin/evaluations` | not queued |

## 3. Build plan (one PR per chunk, each into `design/frontend-v1`)
Each chunk ships with typed mocks behind `lib/adapters/*`. A switch shows which adapter is live, so moving to the real API is one file per endpoint.

1. **`frontend/foundation`**: tokens.css, Tailwind config, fonts, icons, `vocabulary.ts`. Components: LabelBadge, VerdictChip, StanceChip, ReviewStatus, JobState, ReviewReasonChip, EmptyState/ErrorBanner/ReviewBanner. Also vitest with tests for the label/verdict/stance mapping and `claimMeaning`, a contrast check script, the `--input-border` fix, and a `/dev/components` page.
2. **`frontend/shell-auth`**: app shell + nav, `/sign-in` (password + magic link), role-aware middleware with a Permission denied page, redirects from the old routes.
3. **`frontend/result`**: the video result (two-column version first), ClaimCard, ClaimTimeline, EvidenceStrip, review banner, adapter over `/jobs/{id}/result` + mocks for the T26 fields.
4. **`frontend/claim-detail`**: the drawer (Radix dialog, linkable `?claim=`), SourceCard, critic notes.
5. **`frontend/review`**: queue, workspace (baseline + Direction 3 blind step for high priority), decision form validation with tests, audit trail, severity override.
6. **`frontend/jobs`**: jobs list with URL filters, the job progress stepper with the polling hook (with tests), system states.
7. **`frontend/upload`**: the signed upload flow (T20) with client-side checks, progress and cancel.
8. **`frontend/export`**: print view.
9. **`frontend/evaluation`**: the admin screen on mocks.
10. Direction 3 margin notes and tablet passes, if time allows.

`npm run build` and `npm run lint` must pass on every PR.

## 4. Questions for the project lead
- **Q1.** Severity/priority: keep the brief's rule (HIGH / MEDIUM / LOW from the backend, ordering only)? Or adopt the design's High/Normal, including the blind "your judgement first" step for high? My suggestion: show the backend's three levels, sort by them, and use the blind step for HIGH only.
- **Q2.** Use reason code + note on every decision, and hide MARK_INSUFFICIENT?
- **Q3.** Keep "Not required" as a fifth review status?
- **Q4.** Duration limit: 3 min (design) or 10 min (backend)?
- **Q5.** For the result screen: the two-column fallback first, then Direction 3 margin notes? Or Direction 3 straight away?
- **Q6.** The design's own open decisions:
  - CANNOT RECOGNIZE display text, or "Abstained: [reason]"? I'd keep CANNOT RECOGNIZE, as in the brief.
  - The WHO visual identity check.
