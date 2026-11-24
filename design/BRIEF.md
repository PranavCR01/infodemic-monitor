# Frontend design brief (sent to Claude Design)

The designs in `design/claude-design/` were produced from this brief. When the designs and the brief disagree, ask the project lead; don't guess.

## What the product does
Public-health researchers working with WHO upload short health videos (TikTok, Reels, Shorts). The system transcribes speech and reads on-screen text, splits the video into health claims with timestamps, decides each claim's speaker stance, searches PubMed and official sources, decides what the evidence says per claim, combines that into one video label with an explanation, and sends uncertain or high-risk cases to a human reviewer. Core idea: the system shows its evidence; analysts check the evidence, not the AI.

## Users
Analyst (primary, non-technical): uploads, reads results, exports. Reviewer: works the review queue, approves or corrects with a required reason. Admin/researcher: evaluation metrics, routing, cost and latency.

## Vocabulary (display names; internal names never shown)
Video labels: MISINFO; NO-MISINFO (NO_MISINFO); DEBUNKED (DEBUNKING); CANNOT RECOGNIZE (CANNOT_RECOGNIZE).
Stance: ENDORSES, REFUTES, QUOTES, NEUTRAL, UNCLEAR. Verdict: SUPPORTED, CONTRADICTED, MIXED, INSUFFICIENT EVIDENCE, NOT VERIFIABLE.
Review status: Pending review, Verified, Corrected, Rejected. Job states: Queued, Running, Retrying, Needs review, Completed, Failed.
Severity (review priority only, never changes a label): HIGH, MEDIUM, LOW.
Must be obvious: DEBUNKED is a good video and never looks like MISINFO; INSUFFICIENT EVIDENCE is not "proven false"; CANNOT RECOGNIZE is an honest abstention, not an error.

## Screens
1 Sign in (Supabase). 2 Home/submit (upload MP4/MOV, limits, progress; "paste a link" disabled, coming soon). 3 Jobs list (filters, search, empty state). 4 Job in progress (pipeline stepper, polling, retrying/failed states). 5 Video result (label, explanation, review status, confidence "not yet calibrated", player with claim timeline, claim cards with stance + quoted words + verdict + source counts + speech/screen, transcript and on-screen text, review-reason banner in plain language, export). 6 Claim detail (stance basis, verdict + explanation + limitations, sources split Supports/Contradicts with study type, quote, link; source kind: PubMed / official reference / internal library; critic notes collapsed). 7 Review queue (reason chips, severity, age; sort by severity then age). 8 Review workspace (approve / correct label and claims / reject / re-analyse; reason required; audit trail; severity override with reason). 9 Evaluation (admin). 10 Export / print view. 11 System states.

## Principles
Evidence first; calm institutional look; uncertainty as a first-class state; never colour alone (icon + text), WCAG 2.1 AA, colour-blind safe; plain language; dense but readable; desktop first (1440), laptop and tablet usable.

## Tech
Next.js 14 App Router, Tailwind, Supabase Auth; API on Railway (FastAPI); polling, no websockets.
