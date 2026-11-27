from __future__ import annotations

from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver


@contextmanager
def postgres_checkpointer(database_url: str):
    with PostgresSaver.from_conn_string(database_url) as checkpointer:
        yield checkpointer