# Slice G — Railway + Vercel Deployment Config

## Goal
All deployment configuration: Railway (api + worker), Vercel (frontend),
Next.js Supabase Auth, authenticated API client.

## Pre-implementation
1. Read CLAUDE.md
2. All slices A–F must be complete
3. Check old repo for any Next.js auth patterns to reuse

---

## G1. Railway — backend/Dockerfile review

Ensure:
```dockerfile
FROM python:3.11-slim
# OR nvidia/cuda:12.1.0-runtime-ubuntu22.04 if GPU needed

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY backend/ ./backend/
COPY .env.example .env.example

RUN pip install --no-cache-dir -e ./backend

# CMD is overridden by railway.toml — keep it as a fallback only
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

For Railway (no GPU): use `python:3.11-slim`.
For local GPU: keep `nvidia/cuda` base in a separate `Dockerfile.gpu`.

## G2. railway.toml (repo root)

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "backend/Dockerfile"

[[services]]
name = "api"
[services.deploy]
startCommand = "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30

[[services]]
name = "worker"
[services.deploy]
startCommand = "celery -A backend.app.worker.celery_app worker --concurrency=$CELERY_CONCURRENCY --loglevel=info"
```

## G3. .railway/ documentation (create directory)

Create `.railway/api.env.example` and `.railway/worker.env.example`
listing every env var needed per service. These are docs, not secrets.

api.env.example:
```
DATABASE_URL=postgresql+asyncpg://...pooler...:6543/postgres
DATABASE_URL_SYNC=postgresql://...direct...:5432/postgres
REDIS_URL=rediss://...upstash.io:6379
STORAGE_BACKEND=supabase
SUPABASE_URL=https://[ref].supabase.co
SUPABASE_SERVICE_KEY=...
SUPABASE_STORAGE_BUCKET=videos
SUPABASE_JWT_SECRET=...
INFERENCE_PROVIDER=openai
WHISPER_PROVIDER=openai
WHISPER_MODEL_SIZE=base
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
REQUIRE_AUTH=true
ALLOWED_ORIGINS=https://your-app.vercel.app
RUN_MIGRATIONS=true
CELERY_CONCURRENCY=4
```

worker.env.example: same as api but:
- `RUN_MIGRATIONS=false`
- `CELERY_CONCURRENCY=4`

---

## G4. frontend/package.json
Add dependencies:
```json
"@supabase/supabase-js": "^2.0.0",
"@supabase/ssr": "^0.5.0"
```

## G5. frontend/lib/supabase.ts

```typescript
import { createBrowserClient } from "@supabase/ssr";

export function getBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
```

For server components / middleware use `createServerClient` from `@supabase/ssr`
following the official Next.js SSR pattern with cookie handling.

## G6. frontend/lib/api.ts

```typescript
import { getBrowserClient } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const supabase = getBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (session?.access_token) {
    headers["Authorization"] = `Bearer ${session.access_token}`;
  }

  return fetch(`${API_URL}${path}`, { ...options, headers });
}
```

## G7. frontend/app/login/page.tsx
Clean login page matching WHO blue theme:
- Email + password fields
- `supabase.auth.signInWithPassword()`
- On success: `router.push("/")`
- On error: show inline error message
- No OAuth for now

## G8. frontend/middleware.ts

```typescript
import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  // Standard @supabase/ssr updateSession pattern
  // Redirect unauthenticated users to /login
  // Allow /login through without auth check
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

Follow the official Supabase Next.js SSR middleware docs exactly.

## G9. frontend/.env.example

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://[ref].supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

## G10. vercel.json (frontend/ directory)

```json
{
  "framework": "nextjs",
  "buildCommand": "next build",
  "outputDirectory": ".next"
}
```

## Definition of Done
- [ ] `railway.toml` defines both api and worker services
- [ ] `backend/Dockerfile` uses python:3.11-slim (no GPU assumption)
- [ ] `Dockerfile.gpu` preserved for local use
- [ ] Supabase client initializes without errors in Next.js
- [ ] Login page authenticates and redirects correctly
- [ ] `apiFetch` attaches Bearer token on every request
- [ ] Middleware redirects unauthenticated users to /login
- [ ] CLAUDE.md updated: Slice G → ✅
