"""Cached JSON Web Key Set for verifying Supabase asymmetric access tokens (T48).

Supabase signs access tokens with the project's signing keys (ES256, or RS256) and
publishes the public keys at ``SUPABASE_URL + /auth/v1/.well-known/jwks.json``.

- Only asymmetric signing keys are kept: EC P-256 -> ES256, RSA -> RS256. Symmetric
  (``oct``) keys and anything else are dropped, so a JWKS can never introduce a shared
  secret, and each key is bound to exactly one algorithm.
- The set is cached for ``ttl`` seconds. An unknown ``kid`` triggers a refetch, but
  fetches (successful or not) happen at most once per ``min_refetch`` seconds, so a
  flood of tokens with made-up kids can't hammer Supabase.
- If a fetch fails, keys from the last good fetch stay usable for ``max_stale``
  seconds after they went stale; after that, or with nothing cached, lookups return
  None and the caller answers 401 (fail closed).
- Nothing here logs key material or tokens.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import jwt

logger = logging.getLogger(__name__)

# kty (+ crv) -> the one algorithm a key of that type may verify.
_ALG_FOR_KEY = {("EC", "P-256"): "ES256", ("RSA", None): "RS256"}
ASYMMETRIC_ALGORITHMS = frozenset(_ALG_FOR_KEY.values())

_MAX_JWKS_BYTES = 64 * 1024


@dataclass(frozen=True)
class SigningKey:
    kid: str
    algorithm: str  # "ES256" or "RS256"
    key: Any        # cryptography public key object


def _parse_jwks(doc: Any) -> dict[str, SigningKey]:
    if not isinstance(doc, dict) or not isinstance(doc.get("keys"), list):
        raise ValueError("JWKS document has no 'keys' list")
    out: dict[str, SigningKey] = {}
    for jwk in doc["keys"]:
        if not isinstance(jwk, dict):
            continue
        kid = jwk.get("kid")
        kty = jwk.get("kty")
        if not isinstance(kid, str) or not kid:
            continue
        if jwk.get("use") not in (None, "sig"):
            continue
        if kty == "EC":
            alg = _ALG_FOR_KEY.get(("EC", jwk.get("crv")))
        elif kty == "RSA":
            alg = _ALG_FOR_KEY[("RSA", None)]
        else:
            alg = None  # oct (shared secrets), OKP, unknown: never accepted
        if alg is None:
            continue
        if "alg" in jwk and jwk["alg"] != alg:
            continue
        if "d" in jwk:
            continue  # a private key has no business in a public JWKS
        try:
            parsed = jwt.PyJWK(jwk, algorithm=alg)
        except Exception:  # malformed key: skip it, don't fail the whole set
            logger.warning("Skipping unusable JWKS key (kid=%s, kty=%s)", kid, kty)
            continue
        out[kid] = SigningKey(kid=kid, algorithm=alg, key=parsed.key)
    return out


def _http_fetch(url: str) -> Any:
    with httpx.Client(timeout=5.0, follow_redirects=False) as client:
        resp = client.get(url, headers={"Accept": "application/json"})
        resp.raise_for_status()
        if len(resp.content) > _MAX_JWKS_BYTES:
            raise ValueError("JWKS document too large")
        return resp.json()


class JWKSCache:
    def __init__(
        self,
        url: str,
        *,
        ttl: float = 600.0,
        min_refetch: float = 30.0,
        max_stale: float = 3600.0,
        fetch: Callable[[str], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.ttl = ttl
        self.min_refetch = min_refetch
        self.max_stale = max_stale
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, SigningKey] = {}
        self._fetched_at: float | None = None   # last successful fetch
        self._attempted_at: float | None = None  # last fetch attempt, ok or not
        self.fetch_count = 0

    # -- state helpers (call with the lock held) --------------------------------
    def _fresh(self, now: float) -> bool:
        return self._fetched_at is not None and now - self._fetched_at < self.ttl

    def _usable(self, now: float) -> bool:
        return self._fetched_at is not None and now - self._fetched_at < self.ttl + self.max_stale

    def _may_fetch(self, now: float) -> bool:
        return self._attempted_at is None or now - self._attempted_at >= self.min_refetch

    def _refresh(self, now: float) -> None:
        self._attempted_at = now
        self.fetch_count += 1
        try:
            fetch = self._fetch or _http_fetch  # looked up at call time (tests patch it)
            keys = _parse_jwks(fetch(self.url))
        except Exception as exc:
            # Exception type only: messages from HTTP clients can carry URLs/headers.
            logger.warning("JWKS fetch failed (%s); keeping %d cached key(s)",
                           type(exc).__name__, len(self._keys))
            return
        self._keys = keys
        self._fetched_at = now

    # -- public ------------------------------------------------------------------
    def cached_key(self, kid: str) -> SigningKey | None:
        """The key for ``kid`` if the cache is fresh and has it; never does I/O."""
        with self._lock:
            if self._fresh(self._clock()):
                return self._keys.get(kid)
            return None

    def get_key(self, kid: str) -> SigningKey | None:
        """The key for ``kid``, fetching the JWKS when stale or when ``kid`` is unknown
        (rate-limited). Blocking: call from a worker thread in async code."""
        with self._lock:
            now = self._clock()
            if self._fresh(now) and kid in self._keys:
                return self._keys[kid]
            if self._may_fetch(now):
                self._refresh(now)
            if self._usable(now):
                return self._keys.get(kid)
            return None
