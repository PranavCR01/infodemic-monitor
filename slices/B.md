# Slice B — Supabase Storage Backend

## Goal
Implement Supabase Storage as the cloud file backend.
Worker downloads video to a temp file before running the pipeline.
Local backend unchanged.

## Pre-implementation
1. Read CLAUDE.md + slices/A.md (must be complete)
2. Read existing `backend/app/core/storage/` — understand the
   StorageBackend protocol before writing anything
3. Check old repo for any S3/storage abstraction to reuse

## Tasks

### B1. backend/pyproject.toml
Add dependency: `supabase>=2.0.0`

### B2. backend/app/core/storage/supabase_backend.py
Implement `SupabaseBackend` satisfying the existing `StorageBackend` protocol:

```python
class SupabaseBackend:
    def __init__(self):
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is None:
            from supabase import create_client
            self._client = create_client(
                settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
            )
        return self._client

    def upload(self, local_path: str, destination_key: str) -> str:
        # read file bytes, upload to bucket, return destination_key
        # raises StorageError on failure

    def get_download_url(self, storage_key: str) -> str:
        # returns signed URL valid for 1 hour

    def delete(self, storage_key: str) -> None:
        # deletes object, best-effort (log error, don't raise)
```

Wrap all methods in try/except → raise `StorageError(storage_key, cause)`.
Import `StorageError` from `core/exceptions.py` (created in Slice D —
define it here temporarily if D isn't done yet).

### B3. backend/app/core/storage/__init__.py
Add to `get_storage_backend()` factory:
```python
elif settings.STORAGE_BACKEND == "supabase":
    from .supabase_backend import SupabaseBackend
    return SupabaseBackend()
```

### B4. backend/app/db/models/video.py
Add column:
```python
storage_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

### B5. New Alembic migration: 0002_add_storage_key.py
Adds `storage_key VARCHAR` (nullable) to `videos` table.

### B6. backend/app/services/video_service.py
After saving the file locally:
```python
if settings.STORAGE_BACKEND == "supabase":
    storage = get_storage_backend()
    key = f"videos/{video.id}/{filename}"
    storage.upload(local_path, key)
    video.storage_key = key
    # commit update
```

### B7. backend/app/worker/tasks.py
At the top of the task, resolve the file path:

```python
if settings.STORAGE_BACKEND == "supabase" and storage_key:
    storage = get_storage_backend()
    url = storage.get_download_url(storage_key)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    # download url → tmp.name using httpx (sync)
    file_path = tmp.name
    cleanup_temp = True
else:
    cleanup_temp = False

try:
    result = run_pipeline(file_path, ...)
finally:
    if cleanup_temp:
        os.unlink(file_path)
```

Task signature must include `storage_key: Optional[str] = None`.

Update the job creation call in `job_service.py` or wherever the task
is enqueued to pass `storage_key=video.storage_key`.

## Definition of Done
- [ ] `STORAGE_BACKEND=local` — behavior completely unchanged
- [ ] `STORAGE_BACKEND=supabase` — file uploads to bucket, worker
      downloads to temp file, temp file cleaned up after pipeline
- [ ] Migration 0002 runs cleanly against Supabase Postgres
- [ ] CLAUDE.md updated: Slice B → ✅
