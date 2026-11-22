# HANDOFF — extending the golden label set with fact-checked videos

Temporary file. Delete it when `candidates.csv` hits the targets and the rows
have been triaged.

## Where this got to (session 2, 2026-11-22)

`candidates.csv` has **321 rows; 133 carry a platform video URL** that was
checked to appear verbatim on its source page. The other 188 are leads
(180 of them dataset rows that give only a platform video ID).

| Target | Rows | With a URL | URL + TikTok/Reel/Short | Goal |
|---|---|---|---|---|
| False / misleading health claim (not debunks) | 286 | 98 | 85 | 25+ |
| Debunking (creator corrects a myth) | 34 | 34 | 34 | 10+ |
| — of which independent creators confirmed by a fact-checker | 20 | 20 | 20 | |
| — of which Maldita's own @malditobulo videos (self-confirmed) | 14 | 14 | 14 | |
| Non-English (es 66, fr 8, hi 6) | 80 | 78 | 65 | 10+ |
| `speech_screen_disagree` | 2 | 1 (Facebook) | 1 | any |

How to recompute: the snippet at the end of this file.

### Liveness is UNKNOWN for every TikTok row

TikTok's public oEmbed endpoint, from this network and from the web-fetch tool
alike, returns HTTP 200 and a bare player iframe for **any** numeric ID,
including a made-up control ID, with no `title` / `author_name`. So it cannot
distinguish live from removed. `scripts/check_tiktok_live.py` queries a control
ID first and records `[oEmbed DATE: inconclusive ...]` in notes rather than
claiming "live". **No row is confirmed live.** Rerun it from another network —
if the control comes back without an embed or with an error, the real rows will
get live/removed verdicts.

## Sources and what they yielded

| Source | Rows added | Notes |
|---|---|---|
| **Maldita.es** (es) | 69 with URL | Best source by far: its "Lo que circula" ClaimReview box lists the circulating TikTok/Reels URLs directly. 839 Maldita Ciencia articles link-scanned. Includes 14 of Maldita's own @malditobulo debunk TikToks (self-confirmed: flag) and Spanish doctors' debunks Maldita cites. |
| **Science Feedback** (en) | 24 | Video URLs mostly read verbatim out of `web.archive.org/web/<ts>/<original>` wrapper paths; ~80 reviews checked. Outlet indexes (`/outlet/tiktok/`, `/youtube/`, `/instagram/`) fully read: only 3 positive ratings across 218 reviews, so this is not a debunk source. |
| **Lead Stories** (en) | 23 | `/health/YYYY/MM/` monthly archives; links are direct after "The claim appeared in…". Short verdict labels ("Not A Cure", "Lacks Roots"). |
| **Science Feedback French site** (fr) | 8 | Original URL often only in the page's ClaimReview JSON, not a visible link (noted per row). Several are Facebook / long-form YouTube. |
| **Alt News / BOOM** (hi) | 6 | Mostly Facebook / X / long-form YouTube from 2020–24; TikTok is banned in India. Spoken language often assumed — flagged "verify" in notes. |
| **Snopes** (en) | 3 | Embeds live links, but its tag pagination stops at page 2 and the sitemap host is blocked; WebSearch surfaced few health+video items. |
| **M4Health** dataset | 97 ID-only leads | Shang (LMU), Zenodo doi:10.5281/zenodo.19616866, CC-BY-4.0, expert-annotated subset of 3,000 (TikTok / YouTube Shorts / Reddit). Only `Credibility == FALSE` rows from TikTok (57) and YouTube Shorts (40) added; label recorded verbatim (`FALSE`). |
| **MHMisinfo-Gold** dataset | 83 ID-only leads | Nguyen et al., ICWSM 2025 (arXiv 2407.02662), Zenodo doi:10.5281/zenodo.13191247, CC-BY-4.0, expert labels. Only YouTube rows with `label == -1` (mental-health misinformation) added; label recorded verbatim (`-1`). |
| Chequeado, Newtral, Full Fact | 0 new | Link only archive.li / perma.cc, or never link the video. |

Datasets ruled out (no IDs, no health, no release, or gated): FakeTT
(application form only — the user could apply:
github.com/ICTMCG/FakingRecipe), Zenodo 7545488 (#coronavirus TikTok, no IDs),
ShortCheck, ViClaim (no health), RELIANCE (no IDs), arXiv 2310.04237 (no
release), MultiTec (no release), MSD/BOL4Y (Brazilian, mostly long-form, licence
inconsistent across hosts), Visual Authority (no truth labels).

## Open decisions for the user

1. **Dataset IDs → URLs.** M4Health and MHMisinfo give a bare platform video ID.
   The rule "never construct a URL" was applied strictly, so `video_url` is
   empty and the ID is in notes as `dataset_video_id=...`. If a canonical URL
   built from a dataset's own ID is acceptable (`youtube.com/shorts/<id>`;
   TikTok needs a handle, so `tiktok.com/@/video/<id>` is less clean), 180 more
   rows become usable. Not done without approval.
2. **Self-made debunks.** 14 debunk rows are videos made by the fact-checker
   (Maldita) itself. Keep them as debunks, or require independent creators?
3. **Network allowlist.** Blocked by the proxy and therefore not covered:
   politifact.com, web.archive.org, archive.ph, media.snopes.com (sitemaps),
   all Portuguese fact-checkers (aosfatos.org, lupa.uol.com.br,
   projetocomprova.com.br, poligrafo.sapo.pt, observador.pt), colombiacheck.com,
   verifica.efe.com, animalpolitico.com, factchequeado.com, factly.in,
   newschecker.in, hindi.boomlive.in, vishvasnews.com, thequint.com,
   indiatoday.in, liberation.fr, 20minutes.fr, francetvinfo.fr, rtbf.be,
   ici.radio-canada.ca, observers.france24.com, and all public-health bodies
   and big news sites (who.int, cdc.gov, nhs.uk, mayoclinic.org, nytimes,
   washingtonpost, npr, statnews, huffpost). lemonde.fr returns HTTP 402
   (paywall), so Les Décodeurs was not reached. Allowing these hosts in the
   environment is the single biggest lever for Portuguese, Hindi, French and
   public-health-confirmed debunks.

## What's left

- **Portuguese: 0** — every pt fact-checker is blocked (see above).
- **Hindi: only 6, none TikTok/Reel/Short.** Hindi BOOM deepfake-doctor
  articles (Devi Shetty diabetes remedy, Naresh Trehan BP pill) were found by
  search but could not be opened.
- **French: 8, half not short-form.** Les Décodeurs unreached.
- **`speech_screen_disagree`: still only the 2 first-pass leads.** No fact-check
  in this pass described on-screen text contradicting the audio. Better found
  by watching the videos (e.g. tag `on_screen_only` rows, and the Lead Stories
  Rife-machine reel).
- **Public-health-body-confirmed debunks: 0** (all those sites blocked). Leads
  seen in search: HuffPost piece embedding a dermatologist's "sunscreen causes
  cancer" debunk TikTok; NHS trust myth-buster TikToks (CNWL, Imperial,
  Kent & Medway).
- **Triage.** Rows flagged "verify" in notes (assumed language, Instagram `/p/`
  posts whose format is unstated, possible on-screen-only claims,
  @dra.moltoni.gineco stance unclear) need a human pass.

## How to resume

1. Put new rows in a new `candidate_batches/<date>_<source>.jsonl` (one JSON
   object per line, keys = the CSV columns) and run
   `python research/claim-level/dataset/scripts/add_candidates.py`. It
   de-duplicates (URL ignoring query string; URL-less leads on
   fact_check_url + dataset id / claim) and rejects anything in the 82-video
   set. Earlier batches stay in place as provenance; re-running is safe.
2. Run `scripts/check_tiktok_live.py` afterwards (one oEmbed request per second).
3. Before adding, confirm each URL is on its source page. The session used a
   scratchpad helper that fetched the fact-check page and checked the URL's
   path or numeric ID appears in the HTML (including inside web.archive.org
   wrapper paths and ClaimReview JSON); every URL in this session's batch files (137, a few duplicated across batches) passed.

## Rules that were followed and must stay followed

- Links and metadata only. **Nothing downloaded** (no media; only small
  dataset label CSVs, outside the repo).
- No URL constructed, guessed, or pattern-completed. Tracking query strings
  were kept as given, or stripped with the full original kept in notes.
- Verdicts quoted verbatim, untranslated. Where an outlet has no one-word
  rating, the shortest verbatim verdict phrase is quoted and notes say so.
- Health topics only; nothing from the existing 82-video set.
- At most one request per second per site.

```python
# recompute the target table
import csv
R = list(csv.DictReader(open("research/claim-level/dataset/candidates.csv", encoding="utf-8")))
t = lambda r: set(r["candidate_tags"].split(";"))
url = lambda r: bool(r["video_url"].strip())
groups = {
    "false": [r for r in R if "debunking" not in t(r) and t(r) & {"clearly_false", "mixed"}],
    "debunk": [r for r in R if "debunking" in t(r)],
    "non-en": [r for r in R if r["language"] not in ("en", "und")],
    "ssd": [r for r in R if "speech_screen_disagree" in t(r)],
}
for k, L in groups.items():
    print(k, len(L), sum(map(url, L)))
```
