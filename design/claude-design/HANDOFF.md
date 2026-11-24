# WHO Infodemic Monitor: design handoff

Everything needed to build the web frontend (Next.js 14 App Router, Tailwind CSS, Supabase Auth).
This document explains the design, then goes page by page with the layout, states, interactions and a code snippet to start from.

## Contents of this bundle

| Path | What it is |
|---|---|
| `CLAUDE.md` | Instructions for the Claude Code session (read automatically) |
| `HANDOFF.md` | This file |
| `design-reference/screens/*.dc.html` | Source of every designed screen. HTML plus a small logic class. **Reference only**: they need the design canvas runtime to render, so read them for structure, copy and states |
| `design-reference/im.css` | The shared stylesheet all screens use: tokens + component classes |
| `design-reference/icons/*.svg` | 42 stroke icons (24×24, 2px stroke) |
| `design-reference/canvas.json` | Canvas index: which screen is which, sizes, the dev notes as sticky text |
| `starter/styles/tokens.css` | Production CSS variables (light + dark) |
| `starter/tailwind.config.ts` | Tailwind theme wired to those variables |
| `starter/lib/vocabulary.ts` | Display names, icons, colours and the "what this means" table for every label, verdict, stance and status |

---

## 1. Design principles

1. **Evidence first, AI second.** Lead with the claim, the speaker's exact words and the sources. The video label comes last and small. Never write "the AI thinks"; write "the evidence shows" or "no study tests this claim".
2. **DEBUNKED must never look like MISINFO.** Both involve a false claim. They differ in colour (rust vs teal, opposite on the wheel), icon shape (warning triangle vs shield), and the fixed "what this means" line on the deciding claim: *"The speaker refutes a claim the evidence contradicts. This corrects misinformation."*
3. **Uncertainty is a result, not an error.** CANNOT RECOGNIZE, INSUFFICIENT EVIDENCE and UNCLEAR all use a dashed border and neutral grey. No red, no alert icon, no "something went wrong".
4. **Never colour alone.** Every label, verdict, stance and status = icon + text. Stance chips have no colour at all, because stance describes the speaker and colour is reserved for judgements.
5. **Machine vs human is always marked.** "System assessment" until an analyst confirms; "Verified/Corrected by [name], [date]" after.
6. **Calm and institutional.** Warm paper background, navy text, no neon, no gamification, no hero banners.

## 2. Which design direction to build

The canvas holds three iterations of the video result screen:

| Version | File | Status |
|---|---|---|
| Baseline | `Main.dc.html` (+ all other screens) | Complete set: every screen, state, tablet, export |
| Claim map exploration | `ResultV2.dc.html` | **Superseded.** The 2×2 stance × evidence map can't place QUOTES, NEUTRAL or untested claims honestly. Keep the 2×2 only as a teaching diagram in help |
| **Direction 3 (recommended)** | `ResultV3.dc.html`, `ReviewV3.dc.html` | Research-backed. Use for the video result and review workspace |

**Direction 3** combines:
- a **clinical evidence summary**: GRADE "Summary of findings" rows with footnoted reasons, a format WHO staff already know;
- an **annotated manuscript**: the transcript in serif as the spine of the page, with claims as margin notes;
- inside a **calm institutional shell** in the style of the GOV.UK and NHS design systems (tinted tags with dark text, sentence case).

Its weakest point is build cost. Keeping the video, timeline, transcript and margin notes in sync, and stopping margin notes from overlapping, is custom work. **Fallback:** two columns (transcript left, claim rows right) that scroll together.

All other screens (sign in, submit, jobs, progress, queue, evaluation, export, states) use the baseline designs. When building them, apply the Direction 3 wording ("Contradicted by evidence" etc. from `vocabulary.ts`).

## 3. Design tokens

### Colour (light / dark)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | #F7F6F2 | #0F1626 | page |
| `--surface` | #FFFFFF | #161F33 | cards |
| `--sunken` | #EFEDE7 | #0B1120 | tracks, counts |
| `--border` | #E6E4DD | #2A3550 | dividers |
| `--text` | #14213D (14.8:1) | #E8ECF3 (15.2:1) | body |
| `--text-2` | #4A5468 (7.0:1) | #A9B3C6 (7.8:1) | secondary |
| `--text-3` | #5E6677 (5.3:1) | #97A2B6 | captions |
| `--primary` | #1F5F99 (6.2:1) | #7FB2E5 (7.4:1) | links, primary buttons |
| MISINFO / Contradicted | fg #8A3A0C on #FBE4D3 (6.4:1) | #F5B58A on #3A2112 (8.4:1) | rust |
| NO-MISINFO / Supported | fg #1D4F80 on #DCE8F5 (6.8:1) | #9CC4EC on #142B45 (7.9:1) | blue |
| DEBUNKED | fg #0E6157 on #D5EEE9 (6.0:1) | #7FD3C4 on #0F302C (8.1:1) | teal |
| CANNOT RECOGNIZE / Insufficient / Not verifiable | fg #4A4F5C on #EEEDE8 (7.0:1), dashed | #C3C7D0 on #252B38 (8.4:1) | grey |
| Mixed | fg #6E5200 on #F6EBC4 (6.1:1) | #E6C766 on #33290C (8.7:1) | ochre |
| Review / warning | fg #6E5200 on #FBF3D9 | #E6C766 on #2B2410 | ochre tint |
| Error (system failures only) | fg #A3261E on #FCEBE9 (7.4:1) | #F2A39B on #3A1816 | never used for verdicts |

Ratios are WCAG contrast, computed. Known limit: the MISINFO and DEBUNKED tints have almost the same lightness, so in greyscale print they're told apart by icon and text only. That meets WCAG 1.4.1, and the export always prints the label name.

Dark mode: the research recommends deferring it. The tokens exist so it stays cheap later.

### Type

| Role | Spec |
|---|---|
| Display | Source Serif 4, 32/40, 600 |
| H1 | Source Serif 4, 24/32, 600 |
| H2 | IBM Plex Sans, 18/26, 600 |
| H3 | IBM Plex Sans, 15/22, 600 |
| Body | IBM Plex Sans, 14/22 |
| Small | 13/20 · Caption 12/16 · Overline 12/16 600 uppercase tracked |
| Transcript / explanation | Source Serif 4, 17/28 (explanation 18–20) |
| Mono | IBM Plex Mono 13, tabular numerals: timestamps, file names, IDs |

Serif is only for page titles, the one-sentence explanation and the transcript. All UI is Plex Sans.
For i18n, the fallback stacks are in `tailwind.config.ts` (Plex Sans Arabic / SC, Noto Naskh Arabic, Noto Serif SC). Have a native reader check the Chinese settings.

### Spacing, radius, shadow, breakpoints
- Spacing on a 4 px base: 4, 8, 12, 16, 20, 24, 32, 48, 64.
- Radius: sm 4 for label badges and stance chips; md 6 for inputs and buttons; lg 10 for cards; pill for verdict chips. Three shapes for three kinds of judgement.
- Shadows: sh-1 cards, sh-2 hover, sh-3 drawers and modals.
- Breakpoints: 640 · 834 (tablet) · 1024 · 1280 · 1440 (design width).
- Targets: at least 40 px on desktop and 44 px on tablet. Focus ring: 2 px primary, 2 px offset.

## 4. Components

| Component | Props | Notes |
|---|---|---|
| `LabelBadge` | `label`, `size: "sm" \| "lg"` | Square-ish (r-sm), tinted fill, icon + display name. CANNOT RECOGNIZE has a dashed border |
| `VerdictChip` | `verdict` | Pill, tinted. Insufficient = no fill + dashed |
| `StanceChip` | `stance` | Square, **no colour**, always next to the quoted words |
| `ReviewStatus`, `JobState` | `status` | Text + icon, no fill, so they don't compete with the label |
| `ReviewReasonChip` | `reasonCode` | Ochre tint; plain-language sentence from a reason table |
| `ClaimCard` | claim, `active`, `decided` | Timestamp, source tags (speech / on-screen), stance + quote, verdict + counts, "what this means" line |
| `EvidenceStrip` (Direction 3) | levels found, direction, official | Cells SR · RCT · OBS · LAB, ▲ supports / ▼ contradicts, dashed when empty; guidance badge outside the strip; text alternative below |
| `SourceCard` | `kind: pubmed \| official \| internal` | Kind + study-type tag + stance, title, year, quoted passage, link. Internal library documents are dashed, "Internal only", no external link |
| `ClaimTimeline` | claims, `currentTime` | Segments coloured by verdict, numbered; click to seek; plus next/previous buttons (WCAG 2.5.7) |
| `JobStepper` | steps, current, state | Steps: pending · done · now · warn (retrying) · fail |
| `DataTable` | | Sortable header with `aria-sort`, hover row, numbers right-aligned, scrolls in a box below 1024 px |
| `EmptyState`, `ErrorBanner`, `ReviewBanner` | | Pattern: what happened · what it means for the result · one action |

Starting snippet (Tailwind + `vocabulary.ts`):

```tsx
import { LABELS, VERDICTS, STANCES, type VideoLabel, type Verdict, type Stance } from "@/lib/vocabulary";

const tone = {
  misinfo: "text-misinfo-fg bg-misinfo-bg border-misinfo-bd",
  nomisinfo: "text-nomisinfo-fg bg-nomisinfo-bg border-nomisinfo-bd",
  debunked: "text-debunked-fg bg-debunked-bg border-debunked-bd",
  abstain: "text-abstain-fg bg-abstain-bg border-abstain-bd",
  mixed: "text-mixed-fg bg-mixed-bg border-mixed-bd",
} as const;

function Icon({ name, className = "" }: { name: string; className?: string }) {
  return <span aria-hidden className={`icon ${className}`} style={{ ["--m" as any]: `url(/icons/${name}.svg)` }} />;
}

export function LabelBadge({ label, size = "sm" }: { label: VideoLabel; size?: "sm" | "lg" }) {
  const m = LABELS[label];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-sm border font-bold tracking-wide
      ${size === "lg" ? "px-3 py-2 text-xl" : "px-2 py-0.5 text-cap"}
      ${tone[m.tone as keyof typeof tone]} ${m.dashed ? "border-dashed" : ""}`}>
      <Icon name={m.icon} className={size === "lg" ? "!w-6 !h-6" : ""} />{m.display}
    </span>
  );
}

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  const m = VERDICTS[verdict];
  const fill = verdict === "INSUFFICIENT_EVIDENCE" ? "!bg-transparent border-dashed" : "";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-cap font-semibold ${tone[m.tone as keyof typeof tone]} ${fill}`}>
      <Icon name={m.icon} className="!w-3.5 !h-3.5" />{m.display}
    </span>
  );
}

export function StanceChip({ stance }: { stance: Stance }) {
  const m = STANCES[stance];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-sm border border-line-strong bg-surface px-2 py-0.5 text-cap font-semibold text-ink
      ${m.dashed ? "border-dashed text-ink-2" : ""}`}>
      <Icon name={m.icon} className="!w-3.5 !h-3.5" />{m.display}
    </span>
  );
}
```

## 5. Routes and roles

| Route | Screen | Role |
|---|---|---|
| `/sign-in` | Sign in | public |
| `/` | Submit a video | analyst+ |
| `/videos` | Jobs list | analyst+ |
| `/videos/[id]` | Progress until terminal, then result | owner or reviewer |
| `/videos/[id]?claim=[cid]` | Claim detail drawer (linkable) | same |
| `/videos/[id]/export` | Print view | same |
| `/review`, `/review/[id]` | Queue, workspace | reviewer |
| `/evaluation` | Evaluation | admin (the only screen allowed to show model IDs) |

Roles come from a Supabase claim (analyst / reviewer / admin). Middleware checks the role claim; a missing role renders Permission denied, not a redirect.

---

## 6. Page by page

Each section gives the source file, purpose, layout, states, interactions and a starting snippet. Exact copy and markup are in the `.dc.html` file.

### 6.1 Sign in · `SignIn.dc.html`
- **Purpose:** Supabase email + password, or a magic link.
- **Layout:** split screen. Left: navy brand panel with a one-line purpose ("Check what health videos claim, against what the evidence shows."). Right: a 400 px form.
- **States:** form, link sent ("Check your email… works once, expires in 1 hour"), session expired (modal; see States).
- **Interactions:** "Email me a sign-in link" calls `signInWithOtp`. Allow paste and password managers (WCAG 3.3.8).

```tsx
<main className="min-h-screen flex flex-wrap">
  <section className="flex-[1_1_480px] bg-[#14213D] text-[#E8ECF3] p-14 flex flex-col justify-between">
    <Brand inverted />
    <h1 className="font-serif text-[40px] leading-[48px] font-semibold max-w-[520px]">
      Check what health videos claim, against what the evidence shows.
    </h1>
    <p className="text-small text-[#A9B3C6]">A research tool used with the World Health Organization. Access is by invitation.</p>
  </section>
  <section className="flex-[1_1_520px] grid place-items-center p-12">
    <SignInForm /> {/* email, password, Sign in, divider, Email me a sign-in link */}
  </section>
</main>
```

### 6.2 Submit a video · `Submit.dc.html`
- **Purpose:** drag-and-drop upload. MP4/MOV, up to 100 MB, up to 3 minutes. "Paste a link" is disabled and tagged "Coming soon".
- **Layout:** main column (tabs, drop zone, optional title and platform, Start analysis) plus a side column ("What gets checked", Recent).
- **States:** idle drop zone · uploading (file row, progress bar, MB and time left, Cancel) · error (e.g. "This video is too long to analyse… 4 min 12 s. The limit is 3 minutes").
- **Interactions:** validate type, size and duration on the client before uploading (read duration from a hidden `<video>` element's metadata). Use a resumable upload to Supabase Storage. On submit, go to `/videos/[id]`.

```tsx
<label htmlFor="file" className="flex flex-col items-center gap-3 py-14 border-2 border-dashed border-line-strong rounded-lg bg-surface text-center cursor-pointer">
  <span className="w-14 h-14 rounded-full bg-primary-subtle text-primary grid place-items-center"><Icon name="upload" className="!w-7 !h-7" /></span>
  <span className="text-h2">Drag a video here, or <span className="text-primary underline">choose a file</span></span>
  <span className="text-small text-ink-2">MP4 or MOV · up to 100 MB · up to 3 minutes</span>
  <input id="file" type="file" accept="video/mp4,video/quicktime" className="sr-only" onChange={onPick} />
</label>
<div role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} className="h-2 rounded-full bg-surface-sunken overflow-hidden">
  <span className="block h-full bg-primary" style={{ width: `${pct}%` }} />
</div>
```

### 6.3 Jobs list · `Jobs.dc.html`
- **Purpose:** the user's videos.
- **Columns:** video (thumbnail, title, file name), submitted, state (with a sub-line such as "Searching evidence · 1:12"), label, review, claims.
- **Controls:** search, label filter, state filter, "Needs review only", sort by Submitted (default newest), pagination.
- **States:** list · loading (skeleton rows) · empty ("No videos yet" + Submit your first video) · no matches (see States).
- **Polling:** every 10 s, but only while a visible row is Queued, Running or Retrying. Show "Updating N running jobs".
- **Interactions:** the whole row links to `/videos/[id]`. Keep filters in the URL search params.

```tsx
<td><span className={`inline-flex items-center gap-1.5 text-small font-medium ${stateTone[job.state]}`}>
  <Icon name={JOB_STATES[job.state].icon} className="!w-3.5 !h-3.5" />{JOB_STATES[job.state].display}
</span>{job.subline && <div className="text-cap text-ink-3">{job.subline}</div>}</td>
<td>{job.label ? <LabelBadge label={job.label} /> : <span className="text-ink-3">Not yet</span>}</td>
```

### 6.4 Job in progress · `JobProgress.dc.html`
- **Steps:** Uploaded → Transcribing speech → Reading on-screen text → Finding claims → Checking stance → Searching evidence → Verifying → Final checks.
- **Layout:** stepper card (state, headline, elapsed timer) plus a side card ("You can leave this page").
- **States:**
  - queued: "2 videos are ahead";
  - running: current step highlighted, step durations on completed steps;
  - retrying: ochre banner, "Temporary problem, retrying automatically… Attempt 2 of 3";
  - failed: plain-language reason, Retry analysis, Upload a different file, and a job reference. No partial result is ever shown.
- **Polling:** GET every 3 s for 3 min, then every 10 s. Pause while `document.hidden`, and poll immediately on focus. After 3 failed polls, show the "Lost connection" banner and back off 3 → 10 → 20 s. On Completed or Needs review, call `router.refresh()` to render the result.
- **Accessibility:** `aria-live="polite"` on the current step name only, not on the timer.

```tsx
const { data: job } = useSWR(`/api/jobs/${id}`, fetcher, {
  refreshInterval: (j) => (!j || ["QUEUED", "RUNNING", "RETRYING"].includes(j.state))
    ? (Date.now() - startedAt < 180_000 ? 3000 : 10000) : 0,
  revalidateOnFocus: true,
});
useEffect(() => { if (job && ["COMPLETED", "NEEDS_REVIEW"].includes(job.state)) router.refresh(); }, [job?.state]);
```

### 6.5 Video result: Direction 3 · `ResultV3.dc.html` (baseline: `Main.dc.html`)
The most important screen. Top to bottom:

1. **Assessment block** (compact, not a hero):
   - title and file name, with Request review and Export report buttons;
   - "Assessment": LabelBadge + "System assessment" tag + review status, then the one-sentence explanation in serif;
   - "How it was reached": the reasoning chain for the deciding claim: timestamp + quote → StanceChip → evidence (e.g. "1 randomised trial ▼ · WHO guidance ▼") → VerdictChip → label;
   - "Certainty": evidence found (not analyst-rated) and model confidence. Show "not yet calibrated" until calibration exists; after that, a band (High / Moderate / Low), never a raw number by default.
2. **Annotated transcript:**
   - left: video player, the claim timeline, and Previous / Next claim buttons;
   - centre: transcript rows (timestamp link, serif text, claim spans highlighted in the verdict tint); on-screen text appears as its own rows tagged "On screen";
   - right: a margin note on the row where each claim starts (claim number, Decided the label, claim text, stance, verdict).
3. **Summary of findings table:** one row per claim: claim (time, source, text) · what the speaker does (stance + quote) · evidence found (EvidenceStrip + text alternative) · verdict · notes with footnote number and "Sources →". Footnotes below give the reasons (e.g. "Indirect outcome: the trial measured symptom relief, not illness duration").
4. **Stance × evidence table:** empty rows and columns hidden. A solid outline marks MISINFO-driving cells and a double outline marks DEBUNKED-driving cells. "Show all 25 cells".
5. **How we searched:** PubMed query, official sites searched, run time, results screened and kept.

**Linked selection:** one `activeClaimId` shared by the timeline, transcript spans, margin notes and table rows. Playback sets it from `currentTime` (throttled to 4 Hz). A timeline click seeks to the claim and selects it. A note or table row click selects it; a "Sources →" click opens the claim detail drawer.

**Review banner** (baseline `Main.dc.html`, `needsReview`): an ochre banner reading "Waiting for a reviewer. Treat this label as provisional", plus reason chips.

```tsx
// One state shared by every view of the claims
const [active, setActive] = useState<string>(claims[0].id);
useEffect(() => {
  const v = videoRef.current!; let last = 0;
  const onTime = () => { const now = performance.now(); if (now - last < 250) return; last = now;
    const c = claims.find(c => v.currentTime >= c.start && v.currentTime <= c.end); if (c) setActive(c.id); };
  v.addEventListener("timeupdate", onTime); return () => v.removeEventListener("timeupdate", onTime);
}, [claims]);

// Transcript row with margin note
<div className="grid grid-cols-[56px_minmax(0,1fr)_minmax(260px,320px)] gap-x-6 px-6 py-2.5 items-start"
     style={{ background: row.claimId === active ? "var(--surface-2)" : undefined }}>
  <button className="font-mono text-small text-primary" onClick={() => seek(row.start)}>{fmt(row.start)}</button>
  <p className="font-serif text-transcript">{row.parts.map(p => p.claimId
      ? <mark key={p.i} className={highlightClass(p.claimId, active)}>{p.text}</mark> : p.text)}</p>
  {row.noteFor && <MarginNote claim={byId[row.noteFor]} active={row.noteFor === active} onSelect={setActive} />}
</div>
```

### 6.6 Claim detail drawer · `ClaimDetail.dc.html`
- **Container:** right drawer up to 640 px wide with a scrim; full page on phone. `role="dialog"`, focus trap; Esc closes and returns focus to the claim. Prev / next claim controls.
- **Content:**
  - claim text (serif), a "Play 0:03–0:08" button, source tags, Decided the label;
  - **What the speaker does:** stance + description, and the quoted words from speech and from on-screen text, each with a timestamp;
  - **What the evidence shows:** verdict, counts, a short explanation, and a Limitations box;
  - **Sources:** a Contradicts / Supports toggle; SourceCards ordered by study type, not by count.
- **Collapsed by default:** Critic's notes (`<details>`).
- **Footer:** Copy link to claim · Something looks wrong.

```tsx
<article className="border border-line rounded-lg p-4 flex flex-col gap-2">
  <div className="flex flex-wrap items-center gap-2">
    <SourceKind kind={s.kind} />                 {/* book / landmark / archive icon + label */}
    <Tag strong>{STUDY_TYPES[s.studyType]}</Tag>
    <VerdictChip verdict={s.direction === "supports" ? "SUPPORTED" : "CONTRADICTED"} />
  </div>
  <h4 className="text-h3">{s.title}</h4>
  <p className="text-small text-ink-2">{s.journal} · {s.year}</p>
  <blockquote className="text-small bg-surface-2 border border-line rounded-md px-3 py-2">“{s.passage}”</blockquote>
  {s.kind !== "internal" && <a href={s.url} target="_blank" rel="noreferrer">View on {s.kind === "pubmed" ? "PubMed" : s.host}</a>}
</article>
```

### 6.7 Review queue · `ReviewQueue.dc.html`
- **Columns:** priority (High / Normal), video, proposed label, why it needs review (reason chip), waiting time, submitted by, action.
- **Controls:** Needs decision / Decided by me toggle, reason filter buttons with counts, sort (Priority then oldest).
- **Rules:**
  - High priority means a MISINFO label or a possible debunk.
  - A reviewer's own submissions show "Your submission. Another reviewer decides." and have no Review button.
- **Polling:** every 30 s. If the item you have open is decided by someone else, show "Already decided by …" and disable the form.

### 6.8 Review workspace: Direction 3 · `ReviewV3.dc.html` (baseline: `ReviewWorkspace.dc.html`)
- **Evidence first:** "What the speaker said" (transcript lines with the claim highlighted) sits beside "What the sources say" (source cards, each with a "Your read of this source" override select).
- **High-priority items, step 1, "Your judgement first":** the reviewer picks a stance and an evidence verdict. The system assessment stays locked until they press Commit, which is disabled until both are picked.
- **Step 2, "You and the system":** a table compares stance, evidence and label (yours vs the system's), plus a disagreement warning. Then:
  - Decision, required;
  - Reason code, required;
  - Note, required, minimum 10 characters.
- **Normal-priority items:** show the system assessment inline, as in the baseline workspace, to keep throughput.
- **Decisions:**

  | Decision | Required | Resulting status |
  |---|---|---|
  | Approve | reason | Verified |
  | Correct | new label + reason; claim edits optional | Corrected |
  | Reject | reason | Rejected; label hidden from export |
  | Re-analyse | reason | new job; item leaves the queue until it returns |

  Correcting claims does **not** recompute the label. Warn on a mismatch, but don't block.
- **Audit trail:** append-only (DB trigger, no UPDATE or DELETE grants). Record: model version, evidence snapshot ID, whether the reviewer judged before the reveal, their pre-reveal judgement, the final decision, reason code and note, and timestamp. The server rejects self-review.

```tsx
const [mine, setMine] = useState<{ stance?: Stance; verdict?: Verdict }>({});
const [revealed, setRevealed] = useState(false);
<button className="btn-primary" disabled={!mine.stance || !mine.verdict}
  onClick={async () => { await logPreReveal(itemId, mine); setRevealed(true); }}>
  Commit and show system assessment
</button>
{revealed && <Comparison mine={mine} system={item.system} />}
```

### 6.9 Evaluation (admin) · `Evaluation.dc.html`
- **KPI tiles:**
  - **False MISINFO on debunking videos**: the safety metric, highlighted in teal;
  - sent to review %;
  - latency (median and 95th percentile);
  - cost per video.
- **Quality per step table:** transcription WER, claim F1, stance accuracy, verdict accuracy, label accuracy, plus the safety row. Below it, verdict accuracy per class as single-hue bars.
- **Reliability chart:** stated confidence vs observed accuracy, with a diagonal reference line and bin counts. A "Show as a table" link.
- **Model routing table:** step, model, fallback, share of cost, median time.
- All figures in the mock are placeholders in `[brackets]`. Use visx for the reliability chart and Recharts for the standard charts.

### 6.10 Export · `Export.dc.html`
- A print stylesheet on `/videos/[id]/export`, US Letter, flowing pages, 0.75 in margins, body 12 pt.
- **Order:**
  1. Header line;
  2. File title;
  3. Label + description;
  4. Explanation;
  5. Facts table (review status, confidence, date, submitter, online record link);
  6. Claims, each with stance and quote, verdict, explanation, limitations and a numbered source list (PMID / URL);
  7. "How to read this report" glossary;
  8. Footer.
- **Direction 3 additions:**
  - SoF-style claim table;
  - methods and limitations box (models, sources, date run);
  - audit trail annex;
  - "System assessment" vs "Analyst-confirmed by [role], [date]" marking.
- Never print the label without its one-sentence rationale. It must read correctly in greyscale.

### 6.11 System states · `States.dc.html`
Each state follows the pattern: what happened, what it means, one action.

| State | Copy / behaviour |
|---|---|
| Loading | Skeleton that keeps the real layout; no full-page spinner |
| Empty review queue | "Nothing to review" |
| No filter matches | "No videos match" + Clear filters |
| Failed upload | Red progress bar + "The upload stopped… Nothing was analysed" + Try again |
| Failed job | Step it failed at, reason, Retry, Upload a different file, job reference |
| Lost connection | Ochre banner + "Check now" |
| Permission denied | "You don't have access to this page" + role hint |
| Not found | "We can't find that video" |
| Session expired | Modal "Please sign in again", draft kept on this device |

The bottom of `States.dc.html` also defines the three label states that must never be confused: DEBUNKED, CANNOT RECOGNIZE, and confidence before and after calibration.

### 6.12 Tablet (834 px) · `ResultTablet.dc.html`, `ReviewTablet.dc.html`
- **Result:** the header stacks; the player (168 px) sits beside the timeline; claims go full width; the drawer takes 90% of the width.
- **Review:** claims with inline correction selects, then the decision form (decision as a segmented control, new label as a 2×2 radio grid). A sticky bottom bar summarises the decision, with Save.
- **Phone:** reading only, same order as tablet, review actions hidden.

---

## 7. Accessibility checklist (target WCAG 2.2 AA)
- Every label, verdict, stance and status is icon + text; icons are `aria-hidden`.
- Timeline segments are buttons with labels like "Claim 1, 0:03 to 0:08, contradicted by evidence". Next / previous buttons give a non-drag alternative (2.5.7). Targets are at least 24×24 (2.5.8).
- Sticky headers and video bars must not cover the focused element (2.4.11).
- Reviewers never retype a reason already given (3.3.7). Sign-in allows paste and password managers (3.3.8).
- Tables use `th scope` and `aria-sort`.
- Reduced motion: no spinner rotation, no smooth scroll.
- RTL readiness: use logical properties (`ms-`/`me-`, `ps-`/`pe-`) and mirror the margin-note layout. Don't mirror the video timeline until it has been tested with Arabic readers.

## 8. Open decisions (confirm before building)
1. **Build Direction 3, or the baseline,** for the result and review screens. The two-column fallback is listed above.
2. **CANNOT RECOGNIZE display text:** keep it, or use "Abstained: [reason]" as the research suggests.
3. **"Not required" review status:** a fifth value not in the original vocabulary. Needs backend agreement.
4. **Evidence snapshot versioning for the audit trail.** It has a real storage cost.
5. **Video retention and privacy:** ask WHO legal before building storage.
6. **WHO visual identity PDF:** check the fonts and colours against it before final styling.
7. **Placeholder content:** claim 2 and 3 quotes, source passages, Evaluation figures and model IDs are invented or bracketed.
