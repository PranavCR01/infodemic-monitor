# Slice F — Health Check Expansion

## Goal
Expand GET /health to verify all dependencies: DB, Redis, storage,
inference config. Railway uses this for automatic restarts.

## Pre-implementation
1. Read CLAUDE.md
2. Read current health endpoint (likely in main.py or a router)
3. Understand the async DB session pattern used in other routers

## Tasks

### F1. backend/app/api/routers/health.py
Create or replace with:

```python
from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()

@router.get("/health")
async def health_check():
    checks = {}

    # 1. Database
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # 2. Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, ssl_cert_reqs=None)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # 3. Storage
    try:
        if settings.STORAGE_BACKEND == "supabase":
            storage = get_storage_backend()
            # list bucket to verify connectivity (don't upload anything)
            storage._get_client().storage.from_(
                settings.SUPABASE_STORAGE_BUCKET
            ).list()
            checks["storage"] = "ok"
        elif settings.STORAGE_BACKEND == "local":
            import os
            path = settings.LOCAL_STORAGE_PATH
            if os.path.isdir(path) and os.access(path, os.W_OK):
                checks["storage"] = "ok"
            else:
                checks["storage"] = f"error: path not writable: {path}"
    except Exception as e:
        checks["storage"] = f"error: {e}"

    # 4. Inference config (no live API call — just presence check)
    try:
        provider = settings.INFERENCE_PROVIDER
        if provider == "openai" and not settings.OPENAI_API_KEY:
            checks["inference"] = "error: OPENAI_API_KEY not set"
        elif provider == "anthropic" and not settings.ANTHROPIC_API_KEY:
            checks["inference"] = "error: ANTHROPIC_API_KEY not set"
        elif provider == "ollama":
            checks["inference"] = "ok (ollama — no key required)"
        else:
            checks["inference"] = "ok"
    except Exception as e:
        checks["inference"] = f"error: {e}"

    # Determine overall status
    errors = [v for v in checks.values() if v.startswith("error")]
    if len(errors) == 0:
        status = "healthy"
        http_status = 200
    elif len(errors) <= 2:
        status = "degraded"
        http_status = 200
    else:
        status = "unhealthy"
        http_status = 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": status,
            "checks": checks,
            "version": "0.1.0",
        }
    )
```

### F2. backend/app/main.py
Ensure the health router is included and NOT protected by auth:
```python
app.include_router(health_router, tags=["health"])
# auth dependency must NOT be applied globally — only per-router
```

### F3. Add redis.asyncio support
`redis-py` already includes asyncio support. Confirm `redis>=4.0` is
in pyproject.toml. No new dependency needed.

## Railway health check config (noted here for Slice G)
Railway will be configured to call `GET /health` every 30s.
It expects HTTP 200 for healthy/degraded, restarts on 503.

## Definition of Done
- [ ] GET /health returns all 4 check keys
- [ ] DB down → database: "error: ..."
- [ ] Redis down → redis: "error: ..."
- [ ] status field is healthy / degraded / unhealthy correctly
- [ ] HTTP 503 returned when status=unhealthy
- [ ] Route is NOT protected by JWT (no auth dependency)
- [ ] CLAUDE.md updated: Slice F → ✅
