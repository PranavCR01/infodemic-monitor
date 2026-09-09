# Project Context — WHO Infodemic Monitor

Master overview. Read this first, then read your domain-specific file in `context/` before
touching any code.

---

## 1. What This System Is

The **WHO Infodemic Monitor** is a production web application that detects health
misinformation in short-form video (TikTok, Instagram Reels, YouTube Shorts). It's built
for WHO representatives and public health researchers who need a fast, evidence-backed way
to triage viral health content: upload a video, get a structured verdict with supporting
literature, in minutes instead of manual review.

This is not a class demo — it is a deployed system with real users, real infrastructure
cost, and a real production branch (`main`). Treat it accordingly: PRs get reviewed, schema
changes get coordinated, and the system must keep working for existing users while it grows.

## 2. Live Deployment

- **Live URL:** infodemic-monitor.vercel.app
- **Repo:** PranavCR01/infodemic-monitor
- **Production branch:** `main`

## 3. Tech Stack

**Backend**
- FastAPI (API framework)
- Celery (async task queue for video processing)
- Redis (Celery broker/result backend, hosted on Upstash)
- PostgreSQL (primary datastore, hosted on Supabase)
- SQLAlchemy (ORM, sync sessions)
- Alembic (schema migrations — the only sanctioned way to change schema)
- Anthropic SDK / OpenAI SDK (LLM inference, provider-abstracted)
- faster-whisper (local transcription) / OpenAI Whisper API (hosted transcription)
- EasyOCR (on-screen text extraction — implemented but currently disabled by omission)

**Frontend**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Supabase JS client (auth session handling)

**Infrastructure**
- Supabase (PostgreSQL + Storage + Auth/JWT issuer)
- Upstash (managed Redis, TLS)
- Railway (hosts the FastAPI API container; worker container defined but not fully cloud-deployed)
- Vercel (hosts the Next.js frontend)

## 4. Architecture Overview

```
Browser
  │ HTTPS
  ▼
Vercel — Next.js 14 frontend
  │ REST + Bearer JWT
  ▼
Railway — FastAPI (Uvicorn)
  │ Celery task enqueue (via Upstash Redis)
  ▼
Celery worker (transcription, fusion, classification, grounding)
  │
  ▼
Supabase PostgreSQL (jobs, videos, results) + Supabase Storage (raw video files)
```

The frontend never talks to the database or Celery directly — everything goes through the
FastAPI layer over REST with a Supabase-issued JWT in the `Authorization` header.

## 5. Classification Labels

Every video gets exactly one video-level label (claim-level labels are a research track,
see `context/CLAIM_LEVEL.md`):

| Label | Meaning |
|---|---|
| `MISINFO` | Contains health misinformation |
| `NO_MISINFO` | Accurate or neutral content |
| `DEBUNKING` | Actively corrects misinformation |
| `CANNOT_RECOGNIZE` | Insufficient signal to classify |

## 6. Pipeline, In Order

1. **Upload** — video file received by the API, stored in Supabase Storage
2. **SHA-256 dedup check** — *not yet implemented* (see `context/PRODUCTION.md`); every
   upload currently gets a fresh UUID even if the same file was analyzed before
3. **Transcription** — Whisper (faster-whisper locally, OpenAI Whisper API on Railway)
4. **Fusion** — `MultimodalFusion` combines transcript (and OCR text, when enabled) into
   one text payload for the classifier
5. **LLM Classification** — Anthropic is the primary inference provider, OpenAI is the
   fallback; both implement the same `InferenceProvider` Protocol
6. **PubMed grounding** — runs only when the label is `MISINFO` or `DEBUNKING`; extracts
   claims from the transcript and attaches supporting/refuting citations
7. **Persist to DB** — final `ClassificationResult` (label, confidence, explanation,
   evidence snippets, citations) is written to PostgreSQL and surfaced in the dashboard

## 7. Auth

- Supabase Auth issues JWTs; the backend verifies them with **PyJWT** against the
  Supabase JWT secret
- `REQUIRE_AUTH=true` in production — every API route is gated behind a valid JWT
- Locally, `REQUIRE_AUTH=false` bypasses JWT checking for faster iteration

## 8. Key Engineering Patterns

- **Provider abstraction** — `InferenceProvider` is a `typing.Protocol` in
  `backend/app/core/inference/classifier.py`. Switching LLM vendors is a config change
  (`INFERENCE_PROVIDER=openai|anthropic`), not a code change. Any new inference approach
  (ensemble, multi-agent) should implement this same Protocol to stay swappable.
- **tenacity retry** — external calls (LLM APIs, PubMed E-utilities) are wrapped in retry
  logic rather than failing on first transient error.
- **Alembic-only migrations** — schema changes never use `create_all()` in production.
  Every schema change is a numbered Alembic revision under
  `backend/app/db/migrations/versions/`.
- **Structured logging with job_id/video_id context** — log lines carry the job and video
  identifiers so a single pipeline run can be traced end-to-end across transcription,
  classification, and grounding.
- **Sync SQLAlchemy session throughout** — despite `DATABASE_URL` being configured for
  `asyncpg`, the entire app currently runs on synchronous SQLAlchemy sessions. This is a
  known gap, not a design choice (see below).

## 9. Known Technical Debt

- **No SHA-256 dedup** — planned, never implemented. Same video re-uploaded gets
  reprocessed from scratch under a new UUID.
- **No async DB session** — `DATABASE_URL` is asyncpg-formatted but unused; every router
  and service uses sync SQLAlchemy. Fixing this touches nearly every file that talks to
  the DB, so it's deliberately deferred.
- **No tests** — `pyproject.toml` points `pytest` at `backend/app/tests/`, which doesn't
  exist yet.
- **No docker-compose for local dev** — local development runs against a Python venv
  plus real Supabase/Upstash accounts, not containerized.
- **No per-user job isolation** — `GET /jobs` returns every job in the database regardless
  of who created it. Any authenticated user can see any other user's history.
- **Dead Ollama config** — `OLLAMA_BASE_URL` and `OLLAMA_MODEL` still exist in
  `backend/app/core/config.py` from an earlier provider that was removed. Nothing reads
  them.

## 10. Team Structure This Semester

| Track | Students | Focus |
|---|---|---|
| **Production** | 1 student (Student-P1) | System hardening (dedup, tests, dead config cleanup) + new features (per-user isolation, URL ingestion) |
| **Model Eval & Disagreement** | 2 students (Student-ME1, Student-ME2) | Expanding Task 4 — stress-testing last semester's 100% agreement finding at scale |
| **Modality Comparison** | 2 students (Student-MC1, Student-MC2) | Expanding Task 3 — validating whether OCR adds value at scale, and at what confidence threshold |
| **Claim-Level Classification** | 1 student (Student-CL1) | Continuing Task 5 — schema design and prototype for per-claim verdicts |
| **Multi-Agent** | 7 students in 2 pairs + 1 trio (Student-MA1–MA7) | Greenfield — deliberation/verification layer for low-confidence classifications |

Domain files: `context/PRODUCTION.md`, `context/MODEL_EVAL.md`, `context/MODALITY.md`,
`context/CLAIM_LEVEL.md`, `context/MULTI_AGENT.md`.

## 11. How Context Docs Are Organized

Each domain owns exactly one file under `context/`. **Read your domain file before touching
anything.** Domain files are living documents — they hold findings, open questions, and
decisions that aren't derivable from the code itself. **Update your domain file as part of
every PR** that changes anything it documents (a new finding, a schema change, a completed
objective). A PR that changes behavior without updating the relevant context doc is
incomplete.

## 12. GitHub Workflow

- **Issues = tasks.** Every unit of work gets an issue first, using the template for your
  track under `.github/ISSUE_TEMPLATE/`.
- **PRs reference issues** via `Closes #N` in the PR description.
- **Context docs are updated in the same PR as the code/analysis change** — not a
  follow-up, not a separate PR.
- **Pranav approves all PRs.** No self-merging.
