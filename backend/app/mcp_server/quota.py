"""Token buckets for the shared NCBI quota and per-client call limits (design §6
"One NCBI quota for everyone").

NCBI allows about 10 requests a second per API key across every caller. One bucket,
``ncbi:global``, spaces all PubMed requests; each client also has its own bucket
(``ncbi:client:<id>``) refilled at its share of the global rate. A request takes a
token from *both* buckets atomically, so a client that has used its share waits for
its own bucket and never drains the tokens other clients (or our pipeline) rely on.

Two stores with the same algorithm:

- ``RedisBucketStore``: one Lua script, run atomically by Redis and timed by Redis's
  own clock, so every server replica and worker shares one view of the quota;
- ``InMemoryBucketStore``: one process (tests, local development).

``BucketLimiter`` adapts a store to the ``acquire()`` interface ``PubMedClient``
already uses for its rate limiter, so the retrieval package needs no change.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Sequence

from app.core.retrieval.pubmed import PubMedError


@dataclass(frozen=True)
class Bucket:
    key: str
    rate: float  # tokens per second
    capacity: float  # burst size

    def __post_init__(self) -> None:
        if self.rate <= 0 or self.capacity <= 0:
            raise ValueError(f"bucket {self.key}: rate and capacity must be positive")


class BucketStore(Protocol):
    def try_acquire(self, buckets: Sequence[Bucket], cost: float = 1.0) -> float:
        """Take ``cost`` tokens from every bucket, or from none. Returns 0.0 when taken,
        otherwise the seconds to wait before it could succeed."""
        ...


class QuotaExceeded(PubMedError):
    """A client's share of a limit is used up. Not retried by the PubMed client."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class InMemoryBucketStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._state: dict[str, tuple[float, float]] = {}  # key -> (tokens, last refill)

    def _level(self, b: Bucket, now: float) -> float:
        tokens, ts = self._state.get(b.key, (b.capacity, now))
        return min(b.capacity, tokens + max(0.0, now - ts) * b.rate)

    def try_acquire(self, buckets: Sequence[Bucket], cost: float = 1.0) -> float:
        with self._lock:
            now = self._clock()
            levels = [self._level(b, now) for b in buckets]
            waits = [(cost - lv) / b.rate for b, lv in zip(buckets, levels) if lv < cost]
            if waits:
                for b, lv in zip(buckets, levels):
                    self._state[b.key] = (lv, now)
                return max(waits)
            for b, lv in zip(buckets, levels):
                self._state[b.key] = (lv - cost, now)
            return 0.0


# KEYS: bucket keys. ARGV: cost, then (rate, capacity) per key.
# Returns {1, "0"} when taken, else {0, "<seconds to wait>"}.
_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local cost = tonumber(ARGV[1])
local n = #KEYS
local levels = {}
local wait = 0
for i = 1, n do
  local rate = tonumber(ARGV[2 * i])
  local cap = tonumber(ARGV[2 * i + 1])
  local data = redis.call('HMGET', KEYS[i], 'tokens', 'ts')
  local tokens = tonumber(data[1]) or cap
  local ts = tonumber(data[2]) or now
  local elapsed = now - ts
  if elapsed < 0 then elapsed = 0 end
  tokens = math.min(cap, tokens + elapsed * rate)
  levels[i] = tokens
  if tokens < cost then
    local w = (cost - tokens) / rate
    if w > wait then wait = w end
  end
end
local taken = 0
if wait == 0 then taken = 1 end
for i = 1, n do
  local rate = tonumber(ARGV[2 * i])
  local cap = tonumber(ARGV[2 * i + 1])
  local tokens = levels[i]
  if taken == 1 then tokens = tokens - cost end
  redis.call('HSET', KEYS[i], 'tokens', tostring(tokens), 'ts', tostring(now))
  redis.call('PEXPIRE', KEYS[i], math.ceil((cap / rate) * 1000) + 60000)
end
return {taken, tostring(wait)}
"""


class RedisBucketStore:
    """Buckets in Redis. Unlike the query cache, a Redis error is not swallowed: with
    no shared view of the quota the server can't promise NCBI's limit, so it fails
    closed and the caller sees an error."""

    def __init__(self, client: Any, prefix: str = "mcp:quota:") -> None:
        self._r = client
        self._prefix = prefix
        self._script = client.register_script(_LUA)

    def try_acquire(self, buckets: Sequence[Bucket], cost: float = 1.0) -> float:
        keys = [self._prefix + b.key for b in buckets]
        args: list[Any] = [cost]
        for b in buckets:
            args += [b.rate, b.capacity]
        taken, wait = self._script(keys=keys, args=args)
        if isinstance(wait, bytes):
            wait = wait.decode()
        return 0.0 if int(taken) == 1 else max(float(wait), 1e-3)


# ------------------------------------------------------------------ NCBI


def ncbi_global_bucket(rate: float, burst: int) -> Bucket:
    return Bucket("ncbi:global", rate, float(burst))


def ncbi_client_bucket(client_id: str, global_rate: float, share: float, burst: int) -> Optional[Bucket]:
    """The client's own NCBI bucket, or None when its share is 0 (cache hits only)."""
    if share <= 0:
        return None
    # Same burst as the global bucket: over time the client is held to its share,
    # and the global bucket bounds every burst.
    return Bucket(f"ncbi:client:{client_id}", global_rate * share, float(burst))


class BucketLimiter:
    """``acquire()`` for ``PubMedClient``: waits for a token from every bucket, at most
    ``max_wait`` seconds in total, then raises ``QuotaExceeded``."""

    def __init__(
        self,
        store: BucketStore,
        buckets: Sequence[Bucket],
        *,
        max_wait: float,
        label: str = "NCBI",
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.buckets = tuple(buckets)
        self.max_wait = max_wait
        self.label = label
        self._sleep = sleep
        self._clock = clock
        self.waited = 0.0

    def acquire(self) -> None:
        start = self._clock()
        waited = 0.0
        while True:
            wait = self.store.try_acquire(self.buckets)
            if wait <= 0:
                self.waited += waited
                return
            if waited + wait > self.max_wait:
                raise QuotaExceeded(
                    f"{self.label} quota used up; retry in {wait:.1f}s", retry_after=wait
                )
            self._sleep(wait)
            waited = max(waited + wait, self._clock() - start)


class DeniedLimiter:
    """For a client with no NCBI share: any request that would reach NCBI fails."""

    def acquire(self) -> None:
        raise QuotaExceeded("this client has no NCBI quota (cache hits only)", retry_after=0.0)


def pipeline_ncbi_limiter(store: BucketStore, *, has_api_key: bool, config=None, **kw) -> BucketLimiter:
    """A limiter for our own pipeline's in-process PubMed calls, drawing on the same
    global bucket with the pipeline's reserved share. Not wired into the graph yet:
    the integration task (T11) decides whether workers share the Redis bucket."""
    from app.mcp_server.config import load_config

    cfg = config or load_config()
    rate = cfg.ncbi.rate(has_api_key)
    buckets = [ncbi_global_bucket(rate, cfg.ncbi.burst)]
    own = ncbi_client_bucket("_pipeline", rate, cfg.ncbi.pipeline_share, cfg.ncbi.burst)
    if own:
        buckets.append(own)
    kw.setdefault("max_wait", 60.0)
    return BucketLimiter(store, buckets, **kw)
