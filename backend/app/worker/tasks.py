from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _fail_job(db, job_id: str, error_code: str, detail: dict) -> None:
    """Set job status to FAILED with a named error_code and log structured context."""
    from app.db.models.job import Job, JobStatus
    logger.error(
        "Job %s failed — error_code=%s detail=%s",
        job_id, error_code, detail,
    )
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error_code = error_code
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as inner:
        logger.error("Failed to persist job failure for %s: %s", job_id, inner)
        db.rollback()


def _already_finished(db, job) -> bool:
    from app.db.models.job import JobStatus
    from app.db.models.result import Result

    if job.status not in (JobStatus.SUCCESS, JobStatus.REVIEW_REQUIRED):
        return False
    return db.query(Result).filter(Result.job_id == job.id).first() is not None


def _graph_checkpointer():
    """Postgres checkpoints when ``LANGGRAPH_CHECKPOINT_DSN`` is set (a retried task then
    resumes its own run), otherwise in-memory (a retried task starts over). The tables
    are created by a one-off deploy step, not here (context/MULTI_AGENT.md §7a)."""
    import contextlib

    from app.core.config import settings
    from app.core.graph.checkpoint import memory_checkpointer, postgres_checkpointer

    if settings.LANGGRAPH_CHECKPOINT_DSN:
        return postgres_checkpointer(settings.LANGGRAPH_CHECKPOINT_DSN, setup=False)
    return contextlib.nullcontext(memory_checkpointer())


def _run_graph_job(db, job, video, file_path: str) -> dict:
    """Graph path of ``process_video_task``: run, then persist result, claim-level rows,
    model runs and the job state in one transaction (``persist_outcome``)."""
    from app.core.inference.providers.graph_provider import build_graph_provider
    from app.core.pipeline import run_graph_pipeline
    from app.services.pipeline_result_service import persist_outcome

    with _graph_checkpointer() as checkpointer:
        provider = build_graph_provider(checkpointer=checkpointer)
        fusion, outcome = asyncio.run(
            run_graph_pipeline(file_path, job_id=job.id, video_id=video.id, provider=provider)
        )
    if outcome.fallback_used:
        logger.warning("Job %s: graph fell back to the single call (%s)", job.id, outcome.fallback_reason)
    persist_outcome(db, job.id, fusion, outcome)
    return {
        "job_id": job.id,
        "status": job.status.value,
        "label": outcome.classification.label.value,
        "pipeline": outcome.pipeline,
        "fallback_reason": outcome.fallback_reason,
    }


@celery_app.task(name="process_video_task", bind=True)
def process_video_task(self, job_id: str, storage_key: str | None = None):
    from app.core.config import settings
    from app.core.exceptions import (
        GroundingError,
        InferenceProviderError,
        StorageError,
        TranscriptionError,
    )
    from app.core.pipeline import run_pipeline
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.db.models.video import Video  # noqa: F401 — FK resolution
    from app.db.session import SessionLocal

    db = SessionLocal()
    file_path: str | None = None
    cleanup_temp = False

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {"error": "job not found"}

        if settings.USE_GRAPH_PIPELINE and _already_finished(db, job):
            # Celery delivers at least once (§1): a finished graph job is not re-run.
            return {"job_id": job_id, "status": job.status.value, "skipped": True}

        job.status = JobStatus.STARTED
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        video = db.query(Video).filter(Video.id == job.video_id).first()
        if not video:
            _fail_job(db, job_id, "UNKNOWN_ERROR", {"message": "video not found"})
            return {"error": "video not found"}

        # Resolve file — download from Supabase if needed
        if settings.STORAGE_BACKEND == "supabase" and storage_key:
            import httpx
            from app.core.storage import get_storage_backend

            storage = get_storage_backend()
            url = storage.get_download_url(storage_key)

            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp.close()

            with httpx.Client(timeout=300) as client:
                resp = client.get(url)
                resp.raise_for_status()
                with open(tmp.name, "wb") as f:
                    f.write(resp.content)

            file_path = tmp.name
            cleanup_temp = True
        else:
            file_path = video.file_path

        if settings.USE_GRAPH_PIPELINE:
            # T11: the LangGraph pipeline, with a single-call fallback. Off by default.
            return _run_graph_job(db, job, video, file_path)

        # Run async pipeline in a new event loop (Celery tasks are sync)
        fusion, classification = asyncio.run(run_pipeline(file_path))

        result = Result(
            job_id=job_id,
            label=classification.label.value,
            confidence=classification.confidence,
            explanation=classification.explanation,
            evidence_snippets=classification.evidence_snippets,
            citations=[c.model_dump() for c in classification.citations] if classification.citations else None,
            combined_content=fusion.combined_content,
            provider=classification.provider,
            model_used=classification.model_used,
            latency_ms=classification.latency_ms,
        )
        db.add(result)

        job.status = JobStatus.SUCCESS
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {"job_id": job_id, "status": "SUCCESS", "label": classification.label.value}

    except StorageError as exc:
        _fail_job(db, job_id, "STORAGE_ERROR", exc.to_dict())
        raise
    except TranscriptionError as exc:
        _fail_job(db, job_id, "TRANSCRIPTION_ERROR", exc.to_dict())
        raise
    except InferenceProviderError as exc:
        _fail_job(db, job_id, "INFERENCE_ERROR", exc.to_dict())
        raise
    except GroundingError as exc:
        _fail_job(db, job_id, "GROUNDING_ERROR", exc.to_dict())
        raise
    except Exception as exc:
        _fail_job(db, job_id, "UNKNOWN_ERROR", {"message": str(exc)})
        raise

    finally:
        db.close()
        if cleanup_temp and file_path:
            try:
                os.unlink(file_path)
            except OSError:
                pass
