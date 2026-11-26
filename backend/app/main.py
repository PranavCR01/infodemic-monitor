from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import logging

from app.core.config import settings

_log = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.RUN_MIGRATIONS:
        from pathlib import Path

        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        # alembic.ini sits next to the `app` package (backend/alembic.ini); its
        # script_location is %(here)s-relative, so the working directory doesn't matter.
        ini = Path(__file__).resolve().parent.parent / "alembic.ini"
        try:
            alembic_command.upgrade(AlembicConfig(str(ini)), "head")
        except Exception:
            # Fail loudly: a silent create_all fallback leaves the database without
            # alembic_version or migration-only objects (pgvector tables, indexes),
            # and every later migration then breaks.
            _log.exception("database migrations failed; refusing to start")
            raise

    yield


app = FastAPI(title="WHO Infodemic Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check — no auth
from app.api.routers import health  # noqa: E402
app.include_router(health.router)

# Protected routes
from app.api.routers import videos, jobs  # noqa: E402
app.include_router(videos.router)
app.include_router(videos.v1_router)  # §1 signed uploads (T20)
app.include_router(jobs.router)
app.include_router(jobs.v1_router)  # §17 job state, events and list (T28)

# Review API and roles (T27, §12/§15/§17)
from app.api.routers import reviews  # noqa: E402
app.include_router(reviews.router)
from app.api.routers import results  # noqa: E402
app.include_router(results.router)  # §17 result reads (T26)
from app.api.routers import playback  # noqa: E402
app.include_router(playback.router)  # signed playback URL (T29)
from app.api.routers import admin  # noqa: E402
app.include_router(admin.router)  # admin-only eval registry (T63)
