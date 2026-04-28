# WHO Infodemic Monitor

**Production-grade multimodal health misinformation detection for short-form video.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?style=flat-square&logo=celery&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Upstash-DC382D?style=flat-square&logo=redis&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Auth_+_Storage-3ECF8E?style=flat-square&logo=supabase&logoColor=white)
![Railway](https://img.shields.io/badge/Railway-Deploy-0B0D0E?style=flat-square&logo=railway&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-Deploy-000000?style=flat-square&logo=vercel&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat-square&logo=openai&logoColor=white)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-D4A843?style=flat-square&logo=anthropic&logoColor=white)

---

## Overview

The WHO Infodemic Monitor analyses short-form videos (TikTok, Instagram Reels, YouTube Shorts) for health misinformation using a multimodal pipeline:

1. **Transcription** — audio extracted via OpenAI Whisper or faster-whisper
2. **OCR** — on-screen text captured via EasyOCR (optional, GPU)
3. **Multimodal fusion** — transcript and visual text combined into a single grounded context
4. **LLM classification** — GPT-4o or Claude reasons over the fused content and returns a structured verdict
5. **PubMed grounding** — health claims in the transcript are queried against PubMed in parallel; supporting literature is attached to the result

Results are stored in Supabase PostgreSQL, accessible through a Next.js dashboard with JWT-authenticated access.

Built for **WHO representatives and public health researchers** who need a rapid, evidence-backed triage tool for viral health content.

---

## Key Features

| Feature | Detail |
|---|---|
| **4-class label** | `MISINFO` · `NO_MISINFO` · `DEBUNKING` · `CANNOT_RECOGNIZE` |
| **Confidence score** | 0–100% numeric confidence from the LLM |
| **Natural language explanation** | Plain-English reasoning for every verdict |
| **Evidence snippets** | Verbatim quotes from the transcript that drove the classification |
| **PubMed citations** | Peer-reviewed papers linked to specific health claims, with direct PubMed URLs |
| **Provider-agnostic** | Toggle between OpenAI and Anthropic via a single env var |
| **JWT authentication** | Supabase Auth; all API routes require a valid Bearer token |
| **Async job queue** | Celery + Upstash Redis; upload returns immediately, analysis runs in background |
| **Polling dashboard** | Frontend polls every 5 s while a job is active, stops on terminal state |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User (Browser)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
                            ▼
┌───────────────────────────────────────┐
│             Vercel (Frontend)         │
│  Next.js 14 · App Router · Tailwind   │
│                                       │
│  /              Upload page           │
│  /jobs          Job history dashboard │
│  /jobs/[id]     Result detail         │
└───────────────────────┬───────────────┘
                        │ REST (Bearer JWT)
                        ▼
┌───────────────────────────────────────┐    ┌──────────────────────────┐
│          Railway — API service        │    │   Railway — Worker svc   │
│  FastAPI · Uvicorn · Alembic          │    │   Celery · faster-whisper│
│                                       │───▶│   EasyOCR · OpenAI API   │
│  POST /videos/upload                  │    │   Anthropic API          │
│  POST /jobs/create                    │    │   PubMed E-utilities     │
│  GET  /jobs                           │    └──────────┬───────────────┘
│  GET  /jobs/{id}/result               │               │
│  GET  /health                         │    ┌──────────▼───────────────┐
└───────────────┬───────────────────────┘    │   Upstash Redis (TLS)    │
                │                            │   Celery broker + backend│
                │                            └──────────────────────────┘
                │ asyncpg / psycopg2
                ▼
┌───────────────────────────────────────┐
│            Supabase                   │
│  PostgreSQL  — jobs, videos, results  │
│  Storage     — raw video files        │
│  Auth        — JWT issuer             │
└───────────────────────────────────────┘
```

### Service responsibilities

| Service | Platform | Role |
|---|---|---|
| **Frontend** | Vercel | Next.js SSR dashboard + Supabase Auth |
| **API** | Railway | FastAPI REST, DB migrations on startup |
| **Worker** | Railway | Celery consumer — runs the full pipeline |
| **Database + Storage + Auth** | Supabase | PostgreSQL, video blob storage, JWT |
| **Message broker** | Upstash | Redis (TLS) — job queue between API and Worker |

---

## Environment Variables

Copy `.env.example` and fill in your values:

```bash
cp .env.example .env          # backend
cp frontend/.env.example frontend/.env.local   # frontend
```

### Backend (`.env`)

| Variable | Description |
|---|---|
| `DATABASE_URL` | Supabase pooler URL (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | Supabase direct URL (`postgresql://...`) |
| `REDIS_URL` | Upstash Redis URL (`rediss://...`) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (Settings → API) |
| `SUPABASE_STORAGE_BUCKET` | Storage bucket name (default: `videos`) |
| `INFERENCE_PROVIDER` | `openai` or `anthropic` |
| `WHISPER_PROVIDER` | `openai` or `faster_whisper` |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `REQUIRE_AUTH` | `true` in production, `false` for local dev |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `RUN_MIGRATIONS` | `true` on API service, `false` on Worker |
| `CELERY_CONCURRENCY` | Worker concurrency (recommend `4` on Railway) |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `NEXT_PUBLIC_API_URL` | Railway API service URL |

Per-service env var templates are in `.railway/api.env.example` and `.railway/worker.env.example`.

---

## Deployment

### Prerequisites

- [Supabase](https://supabase.com) project with Auth enabled and a `videos` storage bucket
- [Upstash](https://upstash.com) Redis database (TLS enabled)
- [Railway](https://railway.app) account
- [Vercel](https://vercel.com) account

### 1 — Supabase

1. Create a new project
2. Enable **Email** auth provider (Auth → Providers)
3. Create a storage bucket named `videos` (Storage → New bucket, public: off)
4. Copy **Project URL**, **anon key**, **service role key**, and **JWT secret** from Settings → API

### 2 — Upstash

1. Create a Redis database, enable TLS
2. Copy the `rediss://` connection string

### 3 — Railway (API + Worker)

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

# Deploy from repo root
railway up
```

Railway reads `railway.toml` at the repo root and deploys two services:
- **api** — `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **worker** — `celery -A app.worker.celery_app worker --concurrency=$CELERY_CONCURRENCY`

Set env vars for each service using `.railway/api.env.example` and `.railway/worker.env.example` as reference. The Dockerfile is at `backend/Dockerfile` and installs only base deps (no PyTorch/EasyOCR) — set `WHISPER_PROVIDER=openai`.

### 4 — Vercel (Frontend)

```bash
cd frontend
vercel deploy --prod
```

Set the three `NEXT_PUBLIC_*` env vars in the Vercel dashboard. Point `NEXT_PUBLIC_API_URL` to the Railway API service URL and `ALLOWED_ORIGINS` on Railway to the Vercel deployment URL.

---

## Local Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[ml]"                               # includes faster-whisper + EasyOCR
cp ../.env.example ../.env && edit ../.env
uvicorn app.main:app --reload

# Worker (separate terminal)
celery -A app.worker.celery_app worker --concurrency=1 --loglevel=info

# Frontend
cd frontend
npm install
cp .env.example .env.local && edit .env.local
npm run dev
```

Set `REQUIRE_AUTH=false` and `WHISPER_PROVIDER=faster_whisper` in `.env` for local development without Supabase Auth.

---

## Pipeline Labels

| Label | Meaning |
|---|---|
| `MISINFO` | Content contains health misinformation |
| `NO_MISINFO` | Content is accurate or neutral |
| `DEBUNKING` | Content actively debunks misinformation |
| `CANNOT_RECOGNIZE` | Insufficient signal to classify |

---

*Built for WHO representatives and public health researchers as a rapid evidence-backed triage tool for viral health content.*
