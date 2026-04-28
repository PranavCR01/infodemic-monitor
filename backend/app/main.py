from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.RUN_MIGRATIONS:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        try:
            alembic_cfg = AlembicConfig("alembic.ini")
            alembic_command.upgrade(alembic_cfg, "head")
        except Exception:
            from app.db.base import Base
            from sqlalchemy import create_engine

            engine = create_engine(settings.DATABASE_URL_SYNC)
            Base.metadata.create_all(engine)
            engine.dispose()

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
app.include_router(jobs.router)
