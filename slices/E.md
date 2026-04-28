# Slice E — Supabase Auth Middleware

## Goal
Protect FastAPI routes with Supabase JWT verification.
REQUIRE_AUTH flag allows disabling in local dev.

## Pre-implementation
1. Read CLAUDE.md
2. Read all routers in `backend/app/api/routers/`
3. Confirm Slice A is done (REQUIRE_AUTH + ALLOWED_ORIGINS in config)

## Tasks

### E1. backend/pyproject.toml
Add dependency: `PyJWT>=2.8.0`

### E2. backend/app/auth/__init__.py
Empty init file to make it a package.

### E3. backend/app/auth/dependencies.py

```python
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    if not settings.REQUIRE_AUTH:
        # Local dev: return a mock user so route signatures stay identical
        return {"sub": "local-dev-user", "email": "dev@local"}

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase JWTs have audience = "authenticated"
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
```

### E4. backend/app/api/routers/videos.py
Add to every endpoint except health:
```python
from backend.app.auth.dependencies import get_current_user

@router.post("/upload")
async def upload_video(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
    ...
):
```

### E5. backend/app/api/routers/jobs.py
Same pattern — add `current_user: dict = Depends(get_current_user)`
to all endpoints.

For GET /jobs (job history list — added in Slice H):
Use `current_user["sub"]` as the user_id filter if you want per-user
job isolation. For now, return all jobs (single-tenant WHO tool).

### E6. backend/app/main.py — CORS update
Replace hardcoded allow_origins with:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### E7. .env.example additions (if not done in Slice A)
```
SUPABASE_JWT_SECRET=your-jwt-secret-from-supabase-dashboard
REQUIRE_AUTH=false
ALLOWED_ORIGINS=http://localhost:3000
```

## Where to Find the JWT Secret
Supabase dashboard → Project Settings → API → JWT Secret.
This is NOT the anon key or service key. It's the raw signing secret.

## Definition of Done
- [ ] `REQUIRE_AUTH=false` → all routes accessible without token (local dev)
- [ ] `REQUIRE_AUTH=true` → missing/invalid JWT returns 401
- [ ] Valid Supabase JWT → route proceeds, payload available as current_user
- [ ] CORS allows only origins in ALLOWED_ORIGINS
- [ ] CLAUDE.md updated: Slice E → ✅
