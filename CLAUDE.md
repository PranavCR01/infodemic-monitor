# CLAUDE.md — WHO Infodemic Monitor (Cloud)

> Single source of truth for all Claude sessions (chat + CLI).
> Read fully before doing anything. Update after every completed slice.

\---

## 1\. What This Is

**WHO Infodemic Monitor** — production-grade multimodal health misinformation
detection for short-form video (TikTok, Reels, Shorts). Audience: WHO
representatives and public health researchers.

Pipeline: video upload → transcription → OCR → LLM classification →
PubMed grounding → structured verdict with evidence.

### Labels

|Label|Meaning|
|-|-|
|`MISINFO`|Contains health misinformation|
|`NO\_MISINFO`|Accurate / neutral|
|`DEBUNKING`|Actively debunks misinformation|
|`CANNOT\_RECOGNIZE`|Insufficient signal|

\---

## 2\. Stack

|Layer|Technology|
|-|-|
|Frontend|Next.js 14 + TypeScript + Tailwind CSS|
|Backend API|FastAPI (Python 3.11)|
|Async workers|Celery|
|Message broker|Upstash Redis (`rediss://`)|
|Database|Supabase PostgreSQL (existing project)|
|ORM + migrations|SQLAlchemy + Alembic|
|File storage|Supabase Storage|
|Auth|Supabase Auth + JWT middleware|
|Transcription|faster-whisper (local/CPU) or OpenAI Whisper-1|
|OCR|EasyOCR (disabled by default, GPU optional)|
|LLM inference|OpenAI or Anthropic (env var toggled)|
|Grounding|PubMed E-utilities (async, parallel)|
|Deploy: frontend|Vercel|
|Deploy: backend|Railway (two services: api + worker)|

\---

## 3\. Repo Structure

```
who-infodemic-monitor-cloud/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint + startup
│   │   ├── auth/dependencies.py     # Supabase JWT verification
│   │   ├── api/routers/
│   │   │   ├── videos.py
│   │   │   ├── jobs.py
│   │   │   └── health.py
│   │   ├── core/
│   │   │   ├── config.py            # All env vars via pydantic-settings
│   │   │   ├── exceptions.py        # Typed exceptions
│   │   │   ├── extraction/
│   │   │   │   ├── transcription.py
│   │   │   │   ├── ocr/
│   │   │   │   └── multimodal.py
│   │   │   ├── inference/providers/
│   │   │   ├── grounding/pubmed.py  # Async + parallel
│   │   │   ├── pipeline/\_\_init\_\_.py
│   │   │   ├── schemas/pipeline.py
│   │   │   └── storage/             # Protocol + Local + Supabase backends
│   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── migrations/versions/
│   │   │   └── session.py
│   │   ├── services/
│   │   │   ├── video\_service.py
│   │   │   └── job\_service.py
│   │   └── worker/
│   │       ├── celery\_app.py
│   │       └── tasks.py
│   ├── Dockerfile
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/
│   ├── app/
│   │   ├── page.tsx                 # Upload page
│   │   ├── login/page.tsx
│   │   ├── jobs/page.tsx            # Job history dashboard
│   │   └── jobs/\[job\_id]/page.tsx   # Result detail
│   ├── lib/
│   │   ├── supabase.ts
│   │   └── api.ts
│   ├── middleware.ts
│   └── package.json
├── slices/                          # Implementation slice specs
│   ├── A.md  B.md  C.md  D.md
│   └── E.md  F.md  G.md  H.md
├── .env.example
├── railway.toml
├── vercel.json
└── CLAUDE.md
```

\---

## 4\. Key Design Decisions

* **No Docker for local dev** — Railway runs the container; dev uses venv
* **Provider abstraction** — `INFERENCE\_PROVIDER=openai|anthropic` env var;
never hardcode a vendor
* **WHISPER\_PROVIDER=openai|faster\_whisper** — toggleable; faster-whisper
falls back cpu/int8 automatically when no CUDA
* **CELERY\_CONCURRENCY** — env var; 1 for GPU/local, 4 for cloud API mode
* **Auth always on** — `REQUIRE\_AUTH=true` default; disable only in local dev
* **Single Supabase project** — tables coexist with existing project tables;
migrate to fresh project later via pg\_dump + env var swap
* **Alembic only** — no `create\_all` in production; `RUN\_MIGRATIONS=true`
only on api service, never worker
* **Async grounding** — PubMed claims queried in parallel via asyncio.gather
* **Typed exceptions** — all pipeline failures map to named exception classes,
caught at Celery task boundary, stored as error\_code on Job

\---

## 5\. Environment Variables

See `.env.example` for full list. Critical ones:

```
# Database
DATABASE\_URL=postgresql+asyncpg://...supabase...pooler...:6543/postgres
DATABASE\_URL\_SYNC=postgresql://...supabase...:5432/postgres

# Redis
REDIS\_URL=rediss://...upstash.io:6379

# Supabase
SUPABASE\_URL=https://\[ref].supabase.co
SUPABASE\_SERVICE\_KEY=...
SUPABASE\_STORAGE\_BUCKET=videos
SUPABASE\_JWT\_SECRET=...

# Inference
INFERENCE\_PROVIDER=openai          # or anthropic
WHISPER\_PROVIDER=openai            # or faster\_whisper
WHISPER\_MODEL\_SIZE=base
OPENAI\_API\_KEY=...
ANTHROPIC\_API\_KEY=...

# App
STORAGE\_BACKEND=supabase           # or local
CELERY\_CONCURRENCY=4
RUN\_MIGRATIONS=true                # false on worker service
REQUIRE\_AUTH=true
ALLOWED\_ORIGINS=https://your-app.vercel.app
```

\---

## 6\. Slice Progress

|Slice|Description|Status|
|-|-|-|
|A|Config hardening|✅|
|B|Supabase Storage backend|✅|
|C|Async PubMed grounding|✅|
|D|Worker hardening|✅|
|E|Supabase Auth middleware|✅|
|F|Health check expansion|✅|
|G|Railway + Vercel deploy config|✅|
|H|Job history dashboard|✅|

\---

## 7\. Old Code Reference

Old Docker-based repo may contain reusable pipeline logic. Before
implementing any slice, CLI should check the old repo for relevant files:

|Old module|Check for reuse|
|-|-|
|transcription.py|faster-whisper singleton pattern|
|ocr/text\_extractor.py|EasyOCR frame sampling|
|multimodal.py|Fusion layer logic|
|inference providers|JSON parsing + label extraction|
|grounding/pubmed.py|Claim extraction logic|

Audit rule: reuse if logic is sound + tests pass. Discard if it assumes
Docker networking, Streamlit, or local-only paths.

\---

## 8\. CLI Session Start Ritual

Every new Claude Code session must begin with:

```
Read CLAUDE.md fully. Then read slices/\[CURRENT\_SLICE].md.
Check old repo at "D:\\Python files\\who-infodemic-monitor" for reusable code before writing anything new.
Do not implement anything until you confirm understanding.
```

*Last updated: 2026-04-27 — All slices A–H complete. Slice H: GET /jobs endpoint, citations column on Result, job_service.py, jobs list page with polling, result detail page with PubMed citations, upload page, Next.js config (tsconfig, tailwind, postcss, layout, globals.css), server-side Supabase client + API fetch helpers.*

