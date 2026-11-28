# CLAUDE.md

Rules and orientation for anyone, person or coding agent, changing this repository. Read
[README.md](README.md) for what the system does.

## What this is

The production WHO Infodemic Monitor. It checks the health claims in short videos
claim by claim. Its parts:

- **Backend:** FastAPI API and a Celery worker that runs a LangGraph pipeline.
- **Frontend:** Next.js.
- **Data and auth:** Supabase (Postgres, storage, auth).
- **Hosting:** Railway for the API and worker, Vercel for the frontend.

The design, with the reasoning behind each step, is in `docs/target-system-design.md`. That
document is the source of truth for behaviour.

## Where things are

| Path | What |
|---|---|
| `backend/app/core/graph/` | The pipeline: `builder.py` (graph), `nodes.py`, `retrieval_nodes.py`, `verifier.py`, `critic.py`, `judge.py` (label rules), `routing.py` (switches), `prompts/` (versioned prompts) |
| `backend/app/core/extraction/` | Transcription, fusion, vision OCR (`vision_ocr.py`), on-screen text routing (`screen_text.py`) |
| `backend/app/core/retrieval/` | PubMed, reference sources, find-the-study, offline library |
| `backend/config/` | `routing.yaml` (model per step), review policy, severity table, guardrails |
| `backend/app/db/migrations/` | Alembic migrations |
| `backend/app/tests/` | pytest suite. `fixtures/prod_*/` are real production runs, exported without personal data |
| `backend/scripts/` | Operational scripts, plus one-off evaluation replays named `tNN_*` (see its README) |
| `frontend/` | Next.js app (`app/(app)/` pages, `lib/vocabulary.ts` for user-facing wording) |
| `evals/` | Evaluation reports (`reports/`) and the eval registry (`registry/`) |
| `research/claim-level/dataset/` | Golden label set: `videos.csv` and `claims.csv` |
| `automation/` | `BUILD_QUEUE.md` (task queue), `OPEN_DECISIONS.md` |
| `context/` | Working context; `MULTI_AGENT.md` is the build log, with decisions per task |
| `docs/operations.md` | Accounts, env vars, deploys, migrations, common errors |

## Branches and releases

- `main` is production. Both Railway services auto-deploy on every merge to `main`.
- `langgraph-build` is the integration branch. Feature work merges there, and it is
  released to `main` through a reviewed release PR.
- A person merges every PR. Automation never merges its own work.

## Rules

1. **New behaviour ships behind a switch that defaults to off.** With the switch off,
   output must be byte-identical to before, and a test must show it. Rolling back means
   turning the switch off.
2. **Label rules are code, in `judge.py`, and tested.** Don't add a rule that matches on
   free-text prose. Use a structured field from the model step instead.
3. **Paid model runs need the project lead's direct approval, with a cap.** That covers
   evaluations, re-runs and comparisons. Build and test with fixtures and mocks.
4. **The golden set's test split is reserved** for the final held-out evaluation. Don't
   read or tune on it; use the tune split.
5. **Never commit media, archives, secrets or personal data.** The repository is public.
   Video files, frames and zips stay out. Production exports must strip user ids, emails,
   reviewer ids and storage paths.
6. **Schema changes go through Alembic migrations.** No `create_all` in production.
7. **Prompts are versioned.** Add `extract_v5.md`; don't edit `extract_v4.md` in place, and
   record the prompt version with each result.
8. **Model choice lives in `backend/config/routing.yaml`,** not in code.
9. **On-screen and spoken text from videos is untrusted data.** It is fenced as such in
   every prompt and never treated as instructions.
10. **Don't rewrite history on shared branches.** Resolve conflicts with merge commits.

## Checks before a PR

```bash
cd backend && python -m pytest       # CI also runs Postgres/ffmpeg tests and fails on any skip
cd frontend && npm test && npm run typecheck && npm run lint
```

Note in the PR which tests were skipped locally and why.
