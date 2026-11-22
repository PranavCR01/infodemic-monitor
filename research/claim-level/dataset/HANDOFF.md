# HANDOFF — extending the golden label set with fact-checked videos

Temporary file. Delete it when `candidates.csv` hits the targets.

## Where this got to

`candidates.csv` has **10 rows**, from **12 fact-check articles across 4
outlets**. Only **2 rows carry a usable video URL**. The targets were 25+ false,
10+ debunking, 10+ non-English — so this is roughly 8% of the way there, and the
reason is structural, not effort.

| Target | Have | Need |
|---|---|---|
| False/misleading on a health claim | 10 (2 with URL) | 25+ |
| Debunking confirmed by a fact-checker | **0** | 10+ |
| Non-English | 2 (Spanish, neither with URL) | 10+ |
| `speech_screen_disagree` | 2 leads | any |

## The blocker, with evidence

**Fact-checkers deliberately do not link live videos.** They archive instead —
`perma.cc`, `mvau.lt`, `web.archive.org` — precisely because the posts get
removed. Under the rule "use the video link the article itself gives, never
guess or construct a URL", most articles therefore yield nothing.

Checked, and what each gave:

| Outlet | Articles checked | Gave a platform URL |
|---|---|---|
| Health Feedback / Science Feedback | 9 | 1 (inside a `web.archive.org` wrapper) |
| Chequeado | 2 | 0 |
| Full Fact | 1 | 0 (video reported removed) |
| Lead Stories | 1 | 1, but a Facebook repost, not the TikTok |

The one win: Science Feedback's sugar/ADHD review links
`web.archive.org/web/20231023192146/https://www.tiktok.com/@drone721xxx/video/7284274028485938462`,
and the original TikTok URL is readable verbatim inside the wrapper. **That is
the pattern to hunt for** — `web.archive.org` wrappers expose the original URL;
`perma.cc` and `mvau.lt` do not.

**`factcheck.afp.com` is not fetchable** by the web tool (403 to the user
agent), which removes AFP Fact Check and AFP Factuel from the source list.

## How to resume

1. Open `scripts/add_candidates.py`, replace `ROWS` with the new batch, run it.
   It appends and de-duplicates on `video_url`, so it is safe to run repeatedly
   and across sessions. Rows with an empty `video_url` are appended once each.
2. Keep recording the verdict **word for word** (`Misleading`, `Unsupported`,
   `Not A Cure`, `Enganoso`, …). Do not map onto our labels.
3. Leave `video_url` **empty** when the article gives no playable link. Do not
   build one from a handle plus an ID. Two rows already do this and say so in
   `notes`.

### Outlets to try next, in priority order

- **Snopes** and **PolitiFact** — both often embed the original post rather than
  an archive. Untried. Highest expected yield.
- **Maldita** (es) and **Newtral** (es) — untried; Maldita's `malditobulo`
  articles frequently quote the handle.
- **BOOM** (hi/en) and **Alt News** (hi) — untried. BOOM searches returned
  mostly miscaptioned footage rather than creator health-claim videos, so
  search for `"health" "Instagram reel"` style queries instead of COVID terms.
- **Science Feedback**, remaining known health/TikTok reviews not yet fetched
  (verdicts already harvested from their TikTok outlet index):
  - `review/posts-exaggerate-negative-effects-birth-control-nutrition-mental-health/` — Misleading
  - `review/no-evidence-black-seed-oil-most-anti-inflammatory-food-eric-berg/` — Unsupported
  - `review/paul-saladino-incorrectly-attributes-acne-autoimmunity/` — Incorrect
  - `review/vitamin-d-fibroids-more-research-needed/` — Unsupported
  - `science.feedback.org/outlet/youtube/` and `/outlet/instagram/` — same index
    trick, not yet harvested
- Science Feedback also has an **AI-generated-doctor** investigation
  (`beware-ai-generated-doctors-health-advice-tiktok/`) and Chequeado has two
  Spanish equivalents. These are investigations rather than single-claim
  reviews, so they may name many accounts at once — good yield if they link
  posts.

### The debunking category needs a different search

Zero found so far, and ordinary fact-check searches will not surface them:
fact-checkers review *false* claims, so a creator's correct debunk rarely gets
its own article. Try instead:

- Science Feedback verdicts on the **positive** side of their scale
  (`Correct`, `Accurate`, `Mostly correct`) — filter their review index by
  rating rather than searching by topic.
- Fact-checks that **endorse** a creator's correction in passing ("as
  @creator correctly explained"), which means full-text search for phrases like
  `"correctly explains"` or `"accurately debunks"` on the fact-checker domains.
- Public-health bodies citing creators (WHO/CDC campaigns, NHS "myth-busting"
  partnerships) — the task allows "a fact-checker **or public-health body**
  confirms the correction".

## Rules that were followed and must stay followed

- Links and metadata only. **Nothing downloaded.**
- No URL constructed, guessed, or pattern-completed. Where none was given, the
  field is empty and `notes` records why.
- Verdicts quoted verbatim, untranslated.
- Health topics only; nothing from the existing 82-video set. The 15 creator
  handles already in `video_index.csv` are the dedup list — none recur so far.
