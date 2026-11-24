from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


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

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase JWTs carry audience="authenticated"
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
