# Infodemic Monitor frontend: instructions for Claude Code

You are building the web frontend for the WHO Infodemic Monitor from the design in this folder.

## Read first
1. `HANDOFF.md`: design principles, tokens, components, routes and a page-by-page spec with snippets.
2. `design-reference/screens/*.dc.html`: the source of each designed screen. These are **reference only**: they need a design-canvas runtime and won't render in a browser. Read them for structure, exact copy, states and interactions. Each file has an HTML template (`{{holes}}`, `<sc-if>`, `<sc-for>`) and a `class Component` whose `renderVals()` holds the example data and state logic.
3. `design-reference/im.css`: class names used by the screens (`.lb`, `.vd`, `.st`, `.claim`, `.tbl`…). Translate them to Tailwind; don't ship this file as-is.

## Stack
Next.js 14 App Router, TypeScript, Tailwind CSS, Supabase Auth (email/password + magic link). Suggested: shadcn/ui on Radix for dialogs, popovers and tabs (**restyle it to these tokens; its default look is what this design avoids**), SWR or TanStack Query for polling, visx for the reliability chart and Recharts for the other charts, next-intl for strings.

## Setup
- Copy `starter/styles/tokens.css` into `app/` and import it from `globals.css`.
- Use `starter/tailwind.config.ts` as the Tailwind config.
- Copy `starter/lib/vocabulary.ts` to `lib/`.
- Copy `design-reference/icons/*.svg` to `public/icons/`.
- Load fonts with `next/font/google`: Source Serif 4 (`--font-serif`), IBM Plex Sans (`--font-sans`), IBM Plex Mono (`--font-mono`).

## Which screens to build from which file
| Screen | Build from |
|---|---|
| Video result | `ResultV3.dc.html` (Direction 3). Fallback if time is short: two columns, transcript plus claim rows, scrolling together |
| Review workspace | `ReviewV3.dc.html` for high-priority items, `ReviewWorkspace.dc.html` for normal ones |
| Everything else | Baseline files: `SignIn`, `Submit`, `Jobs`, `JobProgress`, `ClaimDetail`, `ReviewQueue`, `Evaluation`, `Export`, `States`, `ResultTablet`, `ReviewTablet` |
| Ignore | `ResultV2.dc.html` (superseded exploration), `Tokens`, `Components`, `DevNotes` (documentation boards; their content is in HANDOFF.md) |

## Rules that must not be broken
- Never show an internal enum (`NO_MISINFO`, `DEBUNKING`…) or a model ID outside `/evaluation`. All display text comes from `lib/vocabulary.ts`.
- Every label, verdict, stance and status = icon + text. Stance chips have no colour.
- DEBUNKED never styled like MISINFO. INSUFFICIENT EVIDENCE never styled like CONTRADICTED. CANNOT RECOGNIZE never styled like an error.
- The "what this means" line comes from `claimMeaning()`, never from model output.
- Every review decision requires a reason; the audit trail is append-only; reviewers can't decide their own submissions.
- No websockets: poll as described in HANDOFF.md §6.4.
- WCAG 2.2 AA.

## Suggested build order
1. Tokens, fonts, icons, `vocabulary.ts`, and the base components (LabelBadge, VerdictChip, StanceChip, statuses).
2. Auth and role middleware, plus the Sign in screen.
3. Submit → Jobs list → Job progress (with polling).
4. Video result (Direction 3), then the claim detail drawer.
5. Review queue → review workspace → audit trail.
6. Export (print CSS), System states, Evaluation.
7. Tablet passes, then an accessibility pass.

Before step 4, ask the user to confirm the open decisions in HANDOFF.md §8.
