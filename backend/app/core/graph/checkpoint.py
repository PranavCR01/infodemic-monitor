"""Checkpointers for the pipeline graph (§1 "Checkpointing").

- Tests and local runs use ``memory_checkpointer()`` (``InMemorySaver``).
- Workers use ``postgres_checkpointer(dsn)``. The DSN is read from the
  ``LANGGRAPH_CHECKPOINT_DSN`` environment variable by default and is never stored in
  code. Point it at a session-pooler (port 5432) URL: psycopg 3 prepared statements
  fail behind a transaction pooler (port 6543), so ``prepare_threshold=None`` is set as
  well.

Both use a serializer that allows exactly the state's model types, so checkpoints read
back cleanly with ``LANGGRAPH_STRICT_MSGPACK=true``.

The tables ``PostgresSaver.setup()`` creates (``checkpoints``, ``checkpoint_writes``,
``checkpoint_blobs``, ``checkpoint_migrations``) are not managed by Alembic; see
context/MULTI_AGENT.md for how production creates them.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.graph.state import CHECKPOINT_TYPES, STATE_SCHEMA_VERSION

DSN_ENV_VAR = "LANGGRAPH_CHECKPOINT_DSN"


class IncompatibleCheckpointError(RuntimeError):
    """A saved run was written with a different state schema version."""


def make_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=list(CHECKPOINT_TYPES))


def memory_checkpointer() -> InMemorySaver:
    return InMemorySaver(serde=make_serde())


@contextmanager
def postgres_checkpointer(dsn: str | None = None, *, setup: bool = True) -> Iterator["PostgresSaver"]:  # noqa: F821
    """Yield a ``PostgresSaver`` on its own connection; closes it on exit."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection
    from psycopg.rows import dict_row

    dsn = dsn or os.environ.get(DSN_ENV_VAR)
    if not dsn:
        raise RuntimeError(f"set {DSN_ENV_VAR} to a Postgres connection string")
    with Connection.connect(
        dsn, autocommit=True, prepare_threshold=None, row_factory=dict_row
    ) as conn:
        saver = PostgresSaver(conn, serde=make_serde())
        if setup:
            saver.setup()
        yield saver


def check_resumable(graph, config: dict) -> None:
    """Refuse to resume a run saved under another state schema version."""
    snapshot = graph.get_state(config)
    saved = snapshot.values.get("state_schema_version") if snapshot and snapshot.values else None
    if saved is not None and saved != STATE_SCHEMA_VERSION:
        raise IncompatibleCheckpointError(
            f"checkpoint has state schema {saved}, graph expects {STATE_SCHEMA_VERSION}"
        )
