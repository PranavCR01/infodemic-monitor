"""Bearer-token authentication against Supabase Auth (T48; design §15, §17).

Which key verifies a token is decided by the server, per algorithm, never by the
token alone:

- ``ES256`` / ``RS256``: the public key with the token's ``kid`` from the project's
  JWKS (``SUPABASE_URL + /auth/v1/.well-known/jwks.json``), and only if that key's
  type matches the algorithm (an EC key never verifies RS256 and vice versa).
- ``HS256``: only the legacy shared secret ``SUPABASE_JWT_SECRET``, and only when it
  is configured. A public key is never used as an HMAC secret (algorithm confusion).
- Anything else, ``none`` included, is refused.

Every token must carry ``aud == "authenticated"`` and an ``exp`` in the future
(``nbf``/``iat`` are checked when present). The issuer must be
``SUPABASE_URL + /auth/v1``; for HS256 tokens this is checked whenever
``SUPABASE_URL`` is set. Roles are read later from ``app_metadata`` only
(``app.auth.roles``). With ``REQUIRE_AUTH`` off a fixed local dev user is returned.
"""
from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.auth.jwks import ASYMMETRIC_ALGORITHMS, JWKSCache
from app.core.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

AUDIENCE = "authenticated"
_REQUIRED_CLAIMS = ["exp", "aud"]

_jwks_cache: JWKSCache | None = None


def supabase_issuer() -> str:
    base = settings.SUPABASE_URL.strip().rstrip("/")
    return f"{base}/auth/v1" if base else ""


def get_jwks_cache() -> JWKSCache | None:
    """The process-wide JWKS cache for the configured project (None without SUPABASE_URL)."""
    global _jwks_cache
    issuer = supabase_issuer()
    if not issuer:
        return None
    url = f"{issuer}/.well-known/jwks.json"
    c = _jwks_cache
    if (c is None or c.url != url or c.ttl != settings.SUPABASE_JWKS_CACHE_SECONDS
            or c.min_refetch != settings.SUPABASE_JWKS_MIN_REFETCH_SECONDS):
        c = _jwks_cache = JWKSCache(
            url,
            ttl=float(settings.SUPABASE_JWKS_CACHE_SECONDS),
            min_refetch=float(settings.SUPABASE_JWKS_MIN_REFETCH_SECONDS),
        )
    return c


def reset_jwks_cache() -> None:
    global _jwks_cache
    _jwks_cache = None


def _unauthorized(detail: str, reason: str) -> HTTPException:
    # Log the reason only; never the token, a key or the secret.
    logger.info("Rejected bearer token: %s", reason)
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def _decode(token: str, key, algorithm: str, issuer: str) -> dict:
    options = {"require": list(_REQUIRED_CLAIMS) + (["iss"] if issuer else [])}
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],  # exactly one, chosen by the server for this key
            audience=AUDIENCE,
            issuer=issuer or None,
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired", "expired")
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token", type(exc).__name__)


async def verify_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token", "malformed header")
    alg = header.get("alg")
    issuer = supabase_issuer()

    if alg in ASYMMETRIC_ALGORITHMS:
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise _unauthorized("Invalid token", "asymmetric token without kid")
        cache = get_jwks_cache()
        if cache is None:
            raise _unauthorized("Invalid token", "SUPABASE_URL not configured; cannot verify asymmetric token")
        key = cache.cached_key(kid)
        if key is None:
            key = await run_in_threadpool(cache.get_key, kid)  # may fetch the JWKS
        if key is None:
            raise _unauthorized("Invalid token", "unknown signing key id")
        if key.algorithm != alg:
            raise _unauthorized("Invalid token", "algorithm does not match the signing key")
        return _decode(token, key.key, key.algorithm, issuer)

    if alg == "HS256":
        secret = settings.SUPABASE_JWT_SECRET
        if not secret:
            raise _unauthorized("Invalid token", "HS256 token but no shared secret configured")
        return _decode(token, secret, "HS256", issuer)

    raise _unauthorized("Invalid token", "unsupported algorithm")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if not settings.REQUIRE_AUTH:
        # Local development only. The role comes from server config, never the client
        # (T27); app.auth.roles reads it from app_metadata like a real token.
        return {
            "sub": "local-dev-user",
            "email": "dev@local",
            "app_metadata": {"role": settings.DEV_USER_ROLE},
        }

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    return await verify_token(credentials.credentials)
