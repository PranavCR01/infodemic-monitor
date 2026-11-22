"""Snapshots of fetched reference text (§6: "Pages change, so a snapshot of the fetched
text is stored with its hash").

The evidence record carries only the hash (``snapshot_sha256``) and the quoted passage;
the full text lives in a snapshot store, keyed by its SHA-256, so a reviewer can see the
page exactly as it was when it was cited. Graph state holds references, not payloads.

- ``InMemorySnapshotStore``: tests and local runs.
- ``SqlSnapshotStore``: the ``reference_snapshots`` table (migration 0009), written
  with its own short session so a failed run still keeps what it cited.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from app.core.retrieval.references.fetcher import FetchedPage, text_sha256


@dataclass(frozen=True)
class Snapshot:
    sha256: str
    url: str
    retrieved_at: str
    text: str


class SnapshotStore(Protocol):
    def save(self, page: FetchedPage) -> None: ...

    def get(self, sha256: str) -> Optional[Snapshot]: ...


class SnapshotMismatch(ValueError):
    pass


def _checked(page: FetchedPage) -> Snapshot:
    if text_sha256(page.text) != page.sha256:
        raise SnapshotMismatch(f"snapshot hash does not match the text of {page.url}")
    return Snapshot(page.sha256, page.url, page.retrieved_at, page.text)


class InMemorySnapshotStore:
    def __init__(self) -> None:
        self._data: dict[str, Snapshot] = {}
        self._lock = threading.Lock()

    def save(self, page: FetchedPage) -> None:
        snap = _checked(page)
        with self._lock:
            self._data.setdefault(snap.sha256, snap)  # first retrieval of identical text wins

    def get(self, sha256: str) -> Optional[Snapshot]:
        return self._data.get(sha256)

    def __len__(self) -> int:
        return len(self._data)


class SqlSnapshotStore:
    """``reference_snapshots`` rows, one per distinct text. ``session_factory`` returns a
    SQLAlchemy ``Session`` (e.g. ``app.db.session.SessionLocal``)."""

    def __init__(self, session_factory: Callable[[], object]) -> None:
        self._factory = session_factory

    def save(self, page: FetchedPage) -> None:
        from app.db.models.claim import ReferenceSnapshotRow

        snap = _checked(page)
        db = self._factory()
        try:
            if db.get(ReferenceSnapshotRow, snap.sha256) is None:
                db.add(ReferenceSnapshotRow(sha256=snap.sha256, url=snap.url,
                                            retrieved_at=snap.retrieved_at, text=snap.text))
                db.commit()
        except Exception as exc:
            db.rollback()
            from sqlalchemy.exc import IntegrityError

            if not isinstance(exc, IntegrityError):  # another worker saved the same text first
                raise
        finally:
            db.close()

    def get(self, sha256: str) -> Optional[Snapshot]:
        from app.db.models.claim import ReferenceSnapshotRow

        db = self._factory()
        try:
            row = db.get(ReferenceSnapshotRow, sha256)
            return None if row is None else Snapshot(row.sha256, row.url, row.retrieved_at, row.text)
        finally:
            db.close()
