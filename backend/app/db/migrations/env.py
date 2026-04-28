import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.db.base import Base  # noqa: E402
import app.db.models  # noqa: F401 — registers all ORM models with Base.metadata

target_metadata = Base.metadata


def _get_url() -> str:
    """Read DATABASE_URL_SYNC directly from the environment.

    Bypasses configparser entirely — config.set_main_option() runs the value
    through Python's configparser interpolation, which treats % as a special
    character and breaks URLs containing percent-encoded passwords (e.g. %40).
    """
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        # Fall back: strip the asyncpg driver from the async URL
        from app.core.config import settings
        url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
