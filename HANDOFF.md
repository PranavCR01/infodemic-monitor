# WHO Infodemic Monitor — Team Handoff Guide

This document is the complete setup guide for an incoming team with no prior context.
Read it top to bottom before touching any code or creating any accounts.

---

## 1. Project Overview

**WHO Infodemic Monitor** is a production-grade web application that detects health
misinformation in short-form videos (TikTok, Instagram Reels, YouTube Shorts).

**Audience:** WHO representatives and public health researchers who need a rapid,
evidence-backed triage tool for viral health content.

**Pipeline:**
1. User uploads a video through the Next.js web interface
2. The backend API stores the video in Supabase Storage and queues a Celery job
3. The Celery worker downloads the video, transcribes it (Whisper), optionally runs
   OCR (EasyOCR), and fuses the content
4. An LLM (GPT-4o or Claude) classifies the content and returns a structured verdict
5. PubMed is queried in parallel for supporting literature; citations are attached
6. The result (label, confidence, explanation, evidence quotes, citations) is stored
   in Supabase PostgreSQL and displayed in the dashboard

**Classification labels:**

| Label | Meaning |
|---|---|
| `MISINFO` | Contains health misinformation |
| `NO_MISINFO` | Accurate or neutral content |
| `DEBUNKING` | Actively corrects misinformation |
| `CANNOT_RECOGNIZE` | Insufficient signal to classify |

---

## 2. Architecture Overview

```
Browser
  │ HTTPS
  ▼
Vercel (Frontend — Next.js 14)
  │ REST + Bearer JWT
  ▼
Railway — API service (FastAPI + Uvicorn)
  │                        │
  │ Celery task queue       │ asyncpg / psycopg2
  ▼                        ▼
Railway — Worker service    Supabase
  (Celery + Whisper)          PostgreSQL (jobs, videos, results)
                              Storage    (raw video files)
                              Auth       (JWT issuer)
  │
  ▼
Upstash Redis (TLS)   ← Celery broker + result backend
```

**What each platform does:**

| Platform | Role | Tier needed |
|---|---|---|
| **Supabase** | PostgreSQL DB, file storage, user auth (JWT) | Free tier is fine to start |
| **Upstash** | Managed Redis — Celery job queue over TLS | Free tier (10,000 req/day) |
| **Railway** | Hosts two Docker containers: API + Worker | Hobby plan ($5/mo) |
| **Vercel** | Hosts the Next.js frontend | Free tier |

---

## 3. Step-by-Step Account Setup

### 3a. Supabase

1. Go to [supabase.com](https://supabase.com) → New project
2. Choose any region, set a strong database password (no `@` characters — they must be
   percent-encoded in connection strings)
3. Wait for provisioning (~2 min)
4. Enable Email auth: **Authentication → Providers → Email** → toggle on
5. Create the storage bucket: **Storage → New bucket**
   - Name: `videos`
   - Public: **off**
6. Collect these four values from **Settings → API**:
   - Project URL
   - `anon` / public key
   - `service_role` key (keep secret — server-side only)
   - JWT Secret (under "JWT Settings")
7. Collect database connection strings from **Settings → Database**:
   - Transaction pooler URL (port 6543) → `DATABASE_URL`
   - Direct connection URL (port 5432) → `DATABASE_URL_SYNC`

> **Important:** if your DB password contains `@`, replace each `@` with `%40` in the
> connection strings. The password itself does not change — only the URL encoding.

### 3b. Upstash

1. Go to [upstash.com](https://upstash.com) → Create database
2. Choose **Redis**, pick a region close to your Railway region
3. Enable **TLS** (required — the app uses `rediss://` scheme)
4. Copy the `rediss://` connection string from the database page → `REDIS_URL`

### 3c. Railway (API + Worker)

1. Go to [railway.app](https://railway.app) → New project → Deploy from GitHub repo
2. Connect your GitHub account and select this repo
3. Railway will detect `railway.toml` and create two services: `api` and `worker`
4. For each service, go to **Settings → Variables** and add all env vars
   (see Section 4 below — api vars vs worker vars differ on `RUN_MIGRATIONS`)
5. The Dockerfile is at `backend/Dockerfile` — Railway builds and runs it automatically
6. After first deploy, the API service URL appears under **Settings → Domains**
   → Copy it as `YOUR_RAILWAY_API_URL`

### 3d. Vercel (Frontend)

1. Go to [vercel.com](https://vercel.com) → New project → Import from GitHub
2. Set **Root Directory** to `frontend`
3. Framework: Next.js (auto-detected)
4. Add three environment variables in the Vercel dashboard (Settings → Environment Variables):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_URL` → the Railway API URL from step 3c
5. Deploy — Vercel gives you a `.vercel.app` URL
6. Go back to Railway → API service → Variables → set `ALLOWED_ORIGINS` to that Vercel URL

---

## 4. Environment Variables Reference

### Backend (`backend/.env` / Railway service variables)

| Variable | What it is | Where to find it | Example format |
|---|---|---|---|
| `DATABASE_URL` | Supabase pooler connection (async) | Supabase → Settings → Database → Transaction pooler | `postgresql+asyncpg://postgres.xxxx:pw%40@aws-x.pooler.supabase.com:6543/postgres` |
| `DATABASE_URL_SYNC` | Supabase direct connection (sync, for Alembic) | Supabase → Settings → Database → Direct connection | `postgresql://postgres.xxxx:pw@db.xxxx.supabase.co:5432/postgres` |
| `REDIS_URL` | Upstash Redis TLS URL | Upstash Console → your DB | `rediss://default:TOKEN@host.upstash.io:6379` |
| `SUPABASE_URL` | Supabase project URL | Supabase → Settings → API → Project URL | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (server-side only) | Supabase → Settings → API → service_role | `sb_secret_...` |
| `SUPABASE_STORAGE_BUCKET` | Storage bucket name | You created it in step 3a | `videos` |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (for verifying auth tokens) | Supabase → Settings → API → JWT Secret | long base64 string |
| `INFERENCE_PROVIDER` | Which LLM to use | Set manually | `openai` or `anthropic` |
| `OPENAI_API_KEY` | OpenAI API key | platform.openai.com → API keys | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | console.anthropic.com → API keys | `sk-ant-api03-...` |
| `WHISPER_PROVIDER` | Transcription engine | Set manually | `openai` (Railway) or `faster_whisper` (local) |
| `WHISPER_MODEL_SIZE` | faster-whisper model size | Set manually | `base` (good default) |
| `STORAGE_BACKEND` | Where to store video files | Set manually | `supabase` (production) |
| `CELERY_CONCURRENCY` | Worker parallelism | Set manually | `4` (Railway), `1` (local) |
| `MAX_INPUT_CHARS` | Max text fed to LLM | Leave at default | `128000` |
| `PUBMED_RESULTS_PER_CLAIM` | PubMed results per health claim | Leave at default | `2` |
| `RUN_MIGRATIONS` | Run Alembic on startup | `true` on API only, `false` on Worker | `true` |
| `REQUIRE_AUTH` | Enforce JWT auth on all routes | `true` in production | `true` |
| `ALLOWED_ORIGINS` | CORS allowed origins | Your Vercel URL | `https://your-app.vercel.app` |

**API service gets all of the above.**
**Worker service gets all except:** `RUN_MIGRATIONS=false` and does not need `SUPABASE_JWT_SECRET` or `ALLOWED_ORIGINS`.

### Frontend (`frontend/.env.local` / Vercel environment variables)

| Variable | What it is | Where to find it |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Supabase → Settings → API → Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key | Supabase → Settings → API → anon key |
| `NEXT_PUBLIC_API_URL` | Railway API service URL | Railway → api service → Settings → Domains |

---

## 5. Running the Celery Worker Locally

The `start_worker.bat` file at the repo root is a convenience script for Windows.
Fill in your credentials (copy from `backend/.env`) and run it from a terminal:

```bat
start_worker.bat
```

On macOS/Linux, run equivalent shell commands:

```bash
export REDIS_URL=rediss://default:TOKEN@host.upstash.io:6379?ssl_cert_reqs=CERT_NONE
export DATABASE_URL=postgresql+asyncpg://...
export INFERENCE_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export WHISPER_PROVIDER=faster_whisper
export STORAGE_BACKEND=supabase
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_KEY=sb_secret_...
export RUN_MIGRATIONS=false
export REQUIRE_AUTH=false

celery -A backend.app.worker.celery_app worker --concurrency=1 --pool=solo --loglevel=info
```

> **Note on Redis SSL locally:** Upstash uses self-signed certs in some configurations.
> If you get `SSL: CERTIFICATE_VERIFY_FAILED`, append `?ssl_cert_reqs=CERT_NONE` to the
> `REDIS_URL`. This is already included in `start_worker.bat`.

---

## 6. Running Alembic Migrations Against a New Supabase Project

Migrations run automatically on API service startup (when `RUN_MIGRATIONS=true`).
To run them manually against a fresh Supabase project:

```bash
cd backend

# Activate your virtual environment
.venv\Scripts\activate        # Windows
# or
source .venv/bin/activate     # macOS/Linux

# Set the sync DB URL (Alembic uses psycopg2, not asyncpg)
export DATABASE_URL_SYNC=postgresql://postgres.xxxx:password@db.xxxx.supabase.co:5432/postgres

# Run all migrations
alembic upgrade head
```

`alembic.ini` reads `DATABASE_URL_SYNC` from the environment via `%(DATABASE_URL_SYNC)s`.

> **Migration race condition:** if both the API and Worker services start simultaneously,
> the worker may try to use the DB before migrations complete. Always set
> `RUN_MIGRATIONS=false` on the worker service — only the API service runs migrations.

---

## 7. Deploying to Railway

### First-time deploy

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

# From the repo root
railway link    # link to your Railway project
railway up      # build and deploy
```

Railway reads `railway.toml` at the repo root. It defines two services:
- **api**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **worker**: `celery -A app.worker.celery_app worker --concurrency=$CELERY_CONCURRENCY --loglevel=info`

Both services share the same Docker image built from `backend/Dockerfile`.

### Environment variables per service

Set variables in the Railway dashboard (not via CLI for secrets):
- **api service**: all backend env vars, `RUN_MIGRATIONS=true`
- **worker service**: all backend env vars except `SUPABASE_JWT_SECRET`, `ALLOWED_ORIGINS`,
  `RUN_MIGRATIONS=false`

### Re-deploys

Push to `main` branch — Railway auto-deploys if you have GitHub integration enabled.
Or trigger manually: `railway up`

### Docker build note

The `backend/Dockerfile` installs only base Python dependencies (no PyTorch, no EasyOCR).
Set `WHISPER_PROVIDER=openai` on Railway — `faster_whisper` requires PyTorch which bloats
the image and causes build timeouts on the free tier.

---

## 8. Deploying to Vercel (Frontend)

### First-time deploy

```bash
cd frontend
npm install -g vercel
vercel login
vercel deploy --prod
```

Or connect the GitHub repo in the Vercel dashboard and it deploys on every push to `main`.

**Root directory setting:** must be `frontend` (not the repo root).

### Environment variables

Set in Vercel Dashboard → Project → Settings → Environment Variables:

```
NEXT_PUBLIC_SUPABASE_URL      = https://YOUR_REF.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY = sb_publishable_...
NEXT_PUBLIC_API_URL           = https://YOUR_RAILWAY_API_URL.railway.app
```

After setting them, redeploy: **Deployments → the latest → Redeploy**.

### CORS wiring

After getting the Vercel URL, update the Railway **api** service:
```
ALLOWED_ORIGINS = https://your-app.vercel.app
```
Then redeploy the Railway api service. Without this, browser requests will be blocked.

---

## 9. Creating the First User in Supabase Auth

The login page uses Supabase email+password auth. To create the first user:

1. Supabase Dashboard → **Authentication → Users → Invite user**
2. Enter the team email address
3. The user receives an email with a magic link to set their password
4. Alternatively, use **Add user** to create with an explicit password (no email sent)

Only authenticated users can access the upload page and job history.
Set `REQUIRE_AUTH=false` in `backend/.env` for local development to bypass JWT checking.

---

## 10. Common Errors and Fixes

### `SSL: CERTIFICATE_VERIFY_FAILED` on Redis connection

**Symptom:** Celery worker fails to connect to Upstash Redis with an SSL error.

**Fix:** Append `?ssl_cert_reqs=CERT_NONE` to `REDIS_URL`:
```
REDIS_URL=rediss://default:TOKEN@host.upstash.io:6379?ssl_cert_reqs=CERT_NONE
```
This is safe for local dev. On Railway, Upstash certs are valid and this flag is not needed.

---

### `ValueError: invalid interpolation syntax` or `%` encoding error in DATABASE_URL

**Symptom:** Pydantic or SQLAlchemy raises an error about `%` in the database URL.

**Cause:** If your Supabase DB password contains `@`, it must be percent-encoded as `%40`
in the URL. However, some configuration parsers then double-encode it.

**Fix:** Use `%40` in the URL string. Do not use `urllib.parse.quote` on the full URL —
only encode the password portion. Verify the URL parses cleanly with:
```python
from urllib.parse import urlparse
urlparse("postgresql+asyncpg://user:password%40here@host:6543/postgres")
```

---

### Migration race condition on Railway startup

**Symptom:** Worker logs show table-not-found errors immediately after deploy.

**Cause:** Both API and Worker start simultaneously; the worker hits the DB before
Alembic finishes creating tables.

**Fix:** Ensure `RUN_MIGRATIONS=false` on the Worker service. Only the API service
should run migrations. Railway deploys services in parallel, so this separation is essential.

---

### Docker build timeout on Railway

**Symptom:** Railway build times out during `pip install`.

**Cause:** Installing PyTorch/EasyOCR (`faster_whisper` with GPU deps) takes too long
for Railway's build timeout.

**Fix:** Set `WHISPER_PROVIDER=openai` on Railway. The Dockerfile installs only base deps.
Reserve `faster_whisper` for local development where you have time to download the model.

---

### CORS errors in browser (`Access-Control-Allow-Origin` missing)

**Symptom:** Browser shows CORS error when the frontend tries to call the API.

**Cause:** `ALLOWED_ORIGINS` on the Railway API service does not include the Vercel URL.

**Fix:**
1. Get the full Vercel deployment URL (e.g., `https://your-app.vercel.app`)
2. Set `ALLOWED_ORIGINS=https://your-app.vercel.app` in the Railway api service vars
3. Redeploy the api service

If you have multiple preview URLs, separate them with commas:
```
ALLOWED_ORIGINS=https://your-app.vercel.app,https://your-app-git-main.vercel.app
```

---

### `401 Unauthorized` on all API calls

**Symptom:** All API requests return 401 even with a valid Supabase session.

**Cause:** `SUPABASE_JWT_SECRET` on Railway does not match the JWT secret in the Supabase project.

**Fix:** Copy the JWT secret from Supabase → Settings → API → JWT Secret and re-set
`SUPABASE_JWT_SECRET` in the Railway api service variables. Redeploy.

---

## 11. Slice Files Reference

The `slices/` directory contains detailed implementation specs for every feature:

| File | What it covers |
|---|---|
| `slices/A.md` | Config hardening — pydantic-settings, env var schema |
| `slices/B.md` | Supabase Storage backend — upload, signed URLs, delete |
| `slices/C.md` | Async PubMed grounding — claim extraction, parallel E-utilities |
| `slices/D.md` | Worker hardening — typed exceptions, error_code on Job, Celery task boundary |
| `slices/E.md` | Supabase Auth middleware — JWT verification, REQUIRE_AUTH toggle |
| `slices/F.md` | Health check expansion — /health endpoint, dependency probes |
| `slices/G.md` | Railway + Vercel deploy config — Dockerfile, railway.toml, vercel.json |
| `slices/H.md` | Job history dashboard — GET /jobs, citations column, polling UI |

Every implementation decision, edge case handled, and schema change is documented in these files.
Read the relevant slice before modifying any feature.

---

## 12. Repo Notes

- **Branch:** `main` is the production branch. All slices A–H are merged and complete.
- **No Docker for local dev** — Railway runs the container; local dev uses a Python venv.
- **No `create_all` in production** — schema changes go through Alembic migrations only.
- **Provider abstraction** — switch between OpenAI and Anthropic by changing one env var;
  no code changes needed.
- **Auth is on by default** — `REQUIRE_AUTH=true` in production. Set `false` only for local dev.
- **Supabase project** — the tables (`videos`, `jobs`, `results`) coexist with any other
  tables in the same Supabase project. To migrate to a fresh project: `pg_dump` the data,
  swap the env vars, run `alembic upgrade head`.
