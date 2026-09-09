# Production Track Context

## 1. What This Role Is

You are inheriting and extending a **live production system**. One student, working alone,
owns this track. There is no pair to split work with — scope your sprints accordingly, and
open an issue for every discrete piece of work so progress is visible.

Unlike the research tracks, changes here ship to real users on `infodemic-monitor.vercel.app`.
Treat schema changes, config changes, and deploy changes with the caution that implies.

## 2. Read These First

1. `HANDOFF.md`
2. `context/PROJECT_CONTEXT.md`
3. This file, in full
4. The key files listed in Section 3, in order

## 3. Key Files To Read In Order

1. `backend/app/core/pipeline/__init__.py` — the pipeline entry point (`run_pipeline`).
   Shows the full flow: fusion → classify → conditional grounding.
2. `backend/app/core/inference/__init__.py` — provider selection (`get_provider()`), reads
   `INFERENCE_PROVIDER` from settings.
3. `backend/app/core/inference/providers/anthropic_provider.py` — primary inference
   provider implementation.
4. `backend/app/core/inference/providers/openai_provider.py` — fallback inference provider.
5. `backend/app/worker/tasks.py` — the Celery task boundary; where the pipeline actually
   gets invoked from a queued job, and where typed exceptions surface as `Job.error_code`.
6. `backend/app/db/session.py` — sync SQLAlchemy session setup (this is what you'll touch
   if async DB sessions are ever tackled — not this sprint).
7. `backend/app/api/routers/jobs.py` — job creation/listing/detail endpoints; this is where
   per-user job isolation gets added.
8. `backend/app/services/video_service.py` — video upload handling; this is where SHA-256
   dedup gets added.
9. `backend/app/auth/dependencies.py` — JWT verification dependency, `REQUIRE_AUTH` gate,
   and where `current_user["sub"]` comes from.
10. `backend/app/core/config.py` — `Settings` (pydantic-settings). This is where the dead
    Ollama fields live and where new env vars get declared.

## 4. What's Actually Deployed

- **FastAPI** — Railway, container built from `backend/Dockerfile`
- **Celery worker** — currently runs on a local machine via `start_worker.bat`, **not**
  fully cloud-deployed. The Railway `worker` service is defined in `railway.toml` but not
  running continuously. This means the pipeline only processes jobs while someone's local
  worker is up.
- **Database + Storage** — Supabase PostgreSQL + Supabase Storage
- **Redis** — Upstash (TLS, `rediss://`)
- **Frontend** — Next.js on Vercel
- **Inference provider** — Anthropic `claude-opus-4-6`
- **Transcription** — OpenAI `whisper-1` (Railway deploys use the OpenAI Whisper API, not
  `faster_whisper`, because bundling PyTorch bloats the Docker image past Railway's build
  timeout — see `HANDOFF.md` §10)

## 5. Known Gaps To Fix — Hardening Sprint First

Do these in order, opening a GitHub issue (using `.github/ISSUE_TEMPLATE/production.md`)
before starting each one.

### 5a. SHA-256 dedup

Never implemented. Every upload gets a fresh UUID and is reprocessed from scratch, even if
the exact same file was already analyzed.

**Implementation:**
- In `video_service.py`, compute `hashlib.sha256` over the uploaded content bytes at
  upload time.
- Check the `Video` table for an existing row with that `file_hash`.
- If a match exists, return the existing `video_id` instead of creating a new video/job.
- Needs a new column: `Video.file_hash`. Write it as **Migration 0005**
  (`alembic revision --autogenerate -m "add file_hash to videos"`), following the existing
  numbering in `backend/app/db/migrations/versions/` (0001–0004 are taken).

### 5b. No tests

`pyproject.toml` points `pytest` at `backend/app/tests/`, which does not exist yet.

**Implementation:**
- Create `backend/app/tests/`.
- Write unit tests for, at minimum:
  - the transcription singleton (whatever caches/reuses the Whisper model instance)
  - provider label normalization (both Anthropic and OpenAI providers must produce one of
    the four `MisinfoLabel` values, regardless of how the raw LLM output is formatted)
  - pipeline error propagation (a failure partway through `run_pipeline` surfaces as a
    typed exception / `Job.error_code`, not a silent failure)
  - dedup logic, once 5a is implemented

### 5c. Async DB session — leave it alone this sprint

`DATABASE_URL` (asyncpg) is configured but nothing reads it — the entire app runs on sync
SQLAlchemy sessions via `DATABASE_URL_SYNC`. Fixing this means rewriting every router and
service that touches the DB. **Do not attempt this sprint.** Flag it as tech debt in this
file if you touch anything adjacent to it, but the hardening sprint is scoped to 5a/5b/5d.

### 5d. Dead Ollama config

`OLLAMA_BASE_URL` and `OLLAMA_MODEL` still exist in `backend/app/core/config.py` — a
leftover from a provider that was removed when the Anthropic/OpenAI provider abstraction
was built. Nothing reads them anymore. Delete both fields.

## 6. New Features — After Hardening

Only start these once 5a–5d are done and merged.

### 6a. Per-user job isolation

- Add `user_id` (populated from the JWT `sub` claim) to the `Job` model.
- In `create_job`, read `current_user["sub"]` and store it on the new job.
- In `list_jobs`, filter by the current user's `sub` — no more global job list.
- Add an ownership check in `get_job` / `get_result` — a user requesting another user's
  job/result should get a 404, not a 403 (don't leak existence).
- Migration number follows whatever the dedup migration landed as — **0005 if dedup
  hasn't shipped yet, 0006 if it has.** Check `backend/app/db/migrations/versions/` before
  naming your revision.

### 6b. URL ingestion

- New endpoint: `POST /videos/from-url` accepting `{url: str}`.
- Download happens in the Celery worker via `yt-dlp`, reusing the existing Supabase
  temp-file download pattern already present in `tasks.py` (don't invent a new download
  path — follow the pattern used for Supabase Storage downloads).
- Add a new `DownloadError` exception type so failures here surface through the same
  typed-exception → `Job.error_code` path as the rest of the pipeline.

## 7. PR Requirements

- Every PR must update **this file** if anything it documents changes (a gap gets fixed,
  a new gap is discovered, deployment topology changes).
- Every PR that adds backend logic must include tests for that code.
- Every PR references the GitHub issue it closes (`Closes #N`).

## 8. Current Sprint

**Hardening first, in this order:**
1. SHA-256 dedup (§5a)
2. Tests (§5b)
3. Dead Ollama config cleanup (§5d)

Open a GitHub issue for each before starting. Do not start §6 (new features) until all
three are merged.
