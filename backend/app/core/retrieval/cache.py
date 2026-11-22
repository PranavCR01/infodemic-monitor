"""Query cache for PubMed calls (§6 "Cache results by query").

Two kinds of entries, both JSON:

- ``esearch:<hash>`` → the PMIDs a query returned (keyed on the query, result cap and
  filters), so a retry, a repeated claim or a re-run doesn't search again;
- ``pmid:<pmid>`` → the parsed record for one paper, so a paper found by several
  queries or claims is fetched once.

The cache holds parsed records (title, abstract, IDs), never raw responses.
``InMemoryQueryCache`` serves one process (tests, a single worker).
``RedisQueryCache`` is for workers and, later, the shared MCP server (§6), which the
design says shares one query cache across teams.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Callable, Optional, Protocol

DEFAULT_TTL_SECONDS = 7 * 24 * 3600
EMPTY_RESULT_TTL_SECONDS = 24 * 3600  # an empty search is retried sooner


def search_key(query: str, max_results: int, filters_key: str) -> str:
    raw = json.dumps([query.strip(), max_results, filters_key], sort_keys=True)
    return "esearch:" + hashlib.sha256(raw.encode()).hexdigest()


def record_key(pmid: str) -> str:
    return f"pmid:{pmid}"


class QueryCache(Protocol):
    def get(self, key: str) -> Optional[Any]: ...

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL_SECONDS) -> None: ...


class InMemoryQueryCache:
    """Thread-safe in-process cache with per-entry expiry."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, payload = item
            if self._clock() >= expires:
                del self._data[key]
                return None
        return json.loads(payload)

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        payload = json.dumps(value)
        with self._lock:
            self._data[key] = (self._clock() + ttl, payload)

    def __len__(self) -> int:
        return len(self._data)


class RedisQueryCache:
    """Cache backed by a Redis client (``redis.Redis`` or anything with ``get`` and
    ``set(key, value, ex=)``). Cache errors are swallowed: a cache outage must not stop
    retrieval, it only costs extra NCBI calls."""

    def __init__(self, client: Any, prefix: str = "retrieval:") -> None:
        self._r = client
        self._prefix = prefix

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._r.get(self._prefix + key)
        except Exception:
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        try:
            self._r.set(self._prefix + key, json.dumps(value), ex=ttl)
        except Exception:
            pass
