# Slice D — Worker Hardening

## Goal
Pre-load Whisper model on worker startup. Define typed exceptions for all
cloud failure modes. Map exceptions to structured job failure states.

## Pre-implementation
1. Read CLAUDE.md
2. Read `backend/app/worker/tasks.py` and `celery_app.py` in full
3. Read `backend/app/core/extraction/transcription.py` — understand
   the current singleton pattern before refactoring

## Tasks

### D1. backend/app/core/exceptions.py (create)

```python
class InfodemicError(Exception):
    def __init__(self, message: str, cause: Exception = None):
        super().__init__(message)
        self.cause = cause

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "cause": str(self.cause) if self.cause else None,
        }

class StorageError(InfodemicError):
    def __init__(self, storage_key: str, cause: Exception = None):
        super().__init__(f"Storage operation failed for key: {storage_key}", cause)
        self.storage_key = storage_key

class TranscriptionError(InfodemicError):
    def __init__(self, provider: str, cause: Exception = None):
        super().__init__(f"Transcription failed (provider={provider})", cause)
        self.provider = provider

class InferenceProviderError(InfodemicError):
    def __init__(self, provider: str, cause: Exception = None):
        super().__init__(f"Inference failed (provider={provider})", cause)
        self.provider = provider

class GroundingError(InfodemicError):
    pass
```

### D2. backend/app/core/extraction/transcription.py
Refactor the module-level singleton into a cacheable function:

```python
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        device, compute_type = ("cuda", "float16") if _cuda_available() \
                                else ("cpu", "int8")
        _whisper_model = WhisperModel(
            settings.WHISPER_MODEL_SIZE, device=device,
            compute_type=compute_type
        )
    return _whisper_model
```

Update all internal callers to use `get_whisper_model()`.

Raise `TranscriptionError(provider="faster_whisper", cause=e)` on failure.
Do the same in the OpenAI path: `TranscriptionError(provider="openai", cause=e)`.

### D3. backend/app/worker/celery_app.py
Add worker_ready signal to pre-load Whisper:

```python
from celery.signals import worker_ready

@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    if settings.WHISPER_PROVIDER == "faster_whisper":
        from backend.app.core.extraction.transcription import get_whisper_model
        get_whisper_model()
        logger.info("faster-whisper model pre-loaded on worker startup")
```

### D4. backend/app/db/models/job.py
Add column:
```python
error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

### D5. New Alembic migration: 0003_add_job_error_code.py
Adds `error_code VARCHAR(64)` (nullable) to `jobs` table.

### D6. backend/app/worker/tasks.py
Replace the generic `except Exception` with typed catches:

```python
except StorageError as e:
    _fail_job(job_id, error_code="STORAGE_ERROR", detail=e.to_dict())
except TranscriptionError as e:
    _fail_job(job_id, error_code="TRANSCRIPTION_ERROR", detail=e.to_dict())
except InferenceProviderError as e:
    _fail_job(job_id, error_code="INFERENCE_ERROR", detail=e.to_dict())
except GroundingError as e:
    _fail_job(job_id, error_code="GROUNDING_ERROR", detail=e.to_dict())
except Exception as e:
    _fail_job(job_id, error_code="UNKNOWN_ERROR",
              detail={"message": str(e)})
```

Add `_fail_job(job_id, error_code, detail)` helper that:
- Sets job status → FAILED
- Sets job.error_code
- Logs with structured context (job_id, error_code, detail)

Also raise typed exceptions from inference providers and grounding
where bare `except Exception` currently swallows errors silently.

## Definition of Done
- [ ] `get_whisper_model()` initializes once, logs on first load
- [ ] Worker startup log shows "faster-whisper model pre-loaded"
      (when WHISPER_PROVIDER=faster_whisper)
- [ ] All pipeline failure modes produce a named error_code on the Job
- [ ] No silent `except Exception: pass` remains in the pipeline path
- [ ] Migration 0003 runs cleanly
- [ ] CLAUDE.md updated: Slice D → ✅
