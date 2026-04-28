# Slice A — Config Hardening

## Goal
Centralize all tunable values into `config.py` via env vars.
Parameterize Alembic. Fix migration race condition between api and worker.

## Pre-implementation
1. Read CLAUDE.md
2. Check old repo for existing `config.py` patterns — reuse if clean
3. Confirm understanding before writing any code

## Tasks

### A1. backend/app/core/config.py
Add these settings (with defaults shown):

```python
# Whisper
WHISPER_PROVIDER: str = "faster_whisper"   # or "openai"
WHISPER_MODEL_SIZE: str = "base"           # tiny | base | small | medium

# Celery
CELERY_CONCURRENCY: int = 1

# Pipeline limits
MAX_INPUT_CHARS: int = 128_000
PUBMED_RESULTS_PER_CLAIM: int = 2

# Migrations
RUN_MIGRATIONS: bool = True   # set False on Railway worker service

# Auth
REQUIRE_AUTH: bool = True
ALLOWED_ORIGINS: str = "http://localhost:3000"

# Supabase
SUPABASE_URL: str = ""
SUPABASE_SERVICE_KEY: str = ""
SUPABASE_STORAGE_BUCKET: str = "videos"
SUPABASE_JWT_SECRET: str = ""
```

Add a helper property:
```python
@property
def allowed_origins_list(self) -> list[str]:
    return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]
```

Replace every hardcoded occurrence of these values throughout the
codebase with `settings.<FIELD>`.

### A2. backend/alembic.ini
Replace hardcoded `sqlalchemy.url` line with:
```
sqlalchemy.url = %(DATABASE_URL_SYNC)s
```

### A3. backend/app/db/migrations/env.py
In both `run_migrations_offline()` and `run_migrations_online()`:
- Read `DATABASE_URL_SYNC` from `os.environ`
- Fall back: take `settings.DATABASE_URL` and replace
  `postgresql+asyncpg` with `postgresql`
- Pass as the effective URL

### A4. backend/app/main.py
Wrap the Alembic startup block:
```python
if settings.RUN_MIGRATIONS:
    # run alembic upgrade head
```
Keep the `create_all` fallback inside the same block.

### A5. infra/docker-compose.yml (if it exists in this repo)
Update worker command:
```
celery -A backend.app.worker.celery_app worker
  --concurrency=${CELERY_CONCURRENCY:-1} --loglevel=info
```
Pass `CELERY_CONCURRENCY` env var to worker service.

### A6. .env.example
Add all new vars:
```
WHISPER_MODEL_SIZE=base
CELERY_CONCURRENCY=1
DATABASE_URL_SYNC=postgresql://postgres:postgres@localhost:5432/infodemic
RUN_MIGRATIONS=true
REQUIRE_AUTH=false
ALLOWED_ORIGINS=http://localhost:3000
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_STORAGE_BUCKET=videos
SUPABASE_JWT_SECRET=
```

## Definition of Done
- [ ] No magic numbers remain in extraction/, grounding/, or inference/ 
- [ ] `alembic upgrade head` works with `DATABASE_URL_SYNC` env var set
- [ ] `RUN_MIGRATIONS=false` skips the migration block entirely
- [ ] All new settings have defaults so local dev needs no extra config
- [ ] CLAUDE.md updated: Slice A → ✅
