from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.storage import get_storage_backend

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    checks: dict[str, str] = {}

    # 1. Database — async ping via asyncpg
    try:
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        async with AsyncSession(engine) as session:
            await session.execute(text("SELECT 1"))
        await engine.dispose()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # 2. Redis — async ping
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, ssl_cert_reqs=None)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # 3. Storage connectivity
    try:
        if settings.STORAGE_BACKEND == "supabase":
            storage = get_storage_backend()
            storage._get_client().storage.from_(settings.SUPABASE_STORAGE_BUCKET).list()
            checks["storage"] = "ok"
        else:
            import os
            path = settings.LOCAL_STORAGE_ROOT
            if os.path.isdir(path) and os.access(path, os.W_OK):
                checks["storage"] = "ok"
            else:
                checks["storage"] = f"error: path not writable: {path}"
    except Exception as exc:
        checks["storage"] = f"error: {exc}"

    # 4. Inference config — key presence only, no live API call
    try:
        provider = settings.INFERENCE_PROVIDER
        if provider == "openai" and not settings.OPENAI_API_KEY:
            checks["inference"] = "error: OPENAI_API_KEY not set"
        elif provider == "anthropic" and not settings.ANTHROPIC_API_KEY:
            checks["inference"] = "error: ANTHROPIC_API_KEY not set"
        else:
            checks["inference"] = "ok"
    except Exception as exc:
        checks["inference"] = f"error: {exc}"

    errors = [v for v in checks.values() if v.startswith("error")]
    if len(errors) == 0:
        overall = "healthy"
        http_status = 200
    elif len(errors) <= 2:
        overall = "degraded"
        http_status = 200
    else:
        overall = "unhealthy"
        http_status = 503

    return JSONResponse(
        status_code=http_status,
        content={"status": overall, "checks": checks, "version": "0.1.0"},
    )
