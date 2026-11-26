import logging
from typing import Optional

from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import ownership
from app.api.ownership import owner_id
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.guardrails.limits import InputRejected
from app.core.storage import SignedUploadUnsupported, StorageBackend, get_storage_backend
from app.db.session import get_db
from app.services.upload_service import (
    UploadGuard,
    get_upload_guard,
    new_upload_id,
    owns_key,
    rejection_to_http,
    storage_key_for,
)
from app.services.video_service import register_uploaded_video, save_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("/upload")
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    guard: UploadGuard = Depends(get_upload_guard),
):
    content = file.file.read()
    filename = file.filename or "upload.mp4"
    if settings.UPLOAD_SAFEGUARDS:
        # T20: T10's input limits on the legacy route, behind a flag (default off).
        try:
            guard.hit_rate(current_user)
            guard.check_media(content, filename)
            guard.consume_quota(current_user)
        except InputRejected as exc:
            raise rejection_to_http(exc) from exc
    video = save_video(db, content, filename, user_id=owner_id(current_user))
    return {
        "video_id": video.id,
        "filename": video.filename,
        "file_size": video.file_size,
    }


# ------------------------------------------------------------------ §1 / §17 API

v1_router = APIRouter(prefix="/v1/videos", tags=["videos"])


def get_storage() -> StorageBackend:
    return get_storage_backend()


class SignedUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None


class RegisterVideoRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=512)
    filename: Optional[str] = Field(default=None, max_length=255)


@v1_router.post("/uploads", status_code=201)
def create_signed_upload(
    payload: SignedUploadRequest,
    current_user: dict = Depends(get_current_user),
    guard: UploadGuard = Depends(get_upload_guard),
    storage: StorageBackend = Depends(get_storage),
):
    """A short-lived signed URL for uploading one video straight to storage."""
    if payload.content_type and not payload.content_type.lower().startswith("video/"):
        raise rejection_to_http(InputRejected("unsupported_media", f"{payload.content_type} is not a video"))
    try:
        guard.check_declared(payload.filename, payload.size_bytes)
        guard.hit_rate(current_user)
        # Quota is spent here: each URL lets the caller write one object to storage.
        guard.consume_quota(current_user)
    except InputRejected as exc:
        raise rejection_to_http(exc) from exc

    upload_id = new_upload_id()
    key = storage_key_for(current_user, upload_id, payload.filename)
    try:
        signed = storage.create_signed_upload_url(key)
    except SignedUploadUnsupported as exc:
        raise HTTPException(status_code=501, detail="signed uploads need STORAGE_BACKEND=supabase") from exc
    except StorageError as exc:
        logger.warning("signed upload URL failed: %s", exc)
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return {
        "upload_id": upload_id,
        "storage_key": key,
        "signed_url": signed["signed_url"],
        "token": signed.get("token"),
        "max_bytes": guard.limits.max_file_bytes,
    }


@v1_router.post("", status_code=201)
def register_video(
    payload: RegisterVideoRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    guard: UploadGuard = Depends(get_upload_guard),
    storage: StorageBackend = Depends(get_storage),
):
    """Register an uploaded object: it must exist, be the caller's, and pass the limits."""
    if not owns_key(current_user, payload.storage_key):
        # Someone else's key (or a malformed one) looks the same as a missing one (§15).
        raise HTTPException(status_code=404, detail="upload not found")
    try:
        guard.hit_rate(current_user)
    except InputRejected as exc:
        raise rejection_to_http(exc) from exc
    try:
        content = storage.download(payload.storage_key)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="upload not found") from exc
    filename = payload.filename or payload.storage_key.rsplit("/", 1)[-1]
    try:
        checked = guard.check_media(content, filename)
    except InputRejected as exc:
        # A rejected file is not kept in storage.
        storage.delete(payload.storage_key)
        raise rejection_to_http(exc) from exc

    video, duplicate = register_uploaded_video(
        db, payload.storage_key, filename, checked.media.size_bytes, checked.media.sha256,
        user_id=owner_id(current_user),
    )
    if duplicate and video.storage_key != payload.storage_key:
        storage.delete(payload.storage_key)
    return {
        "video_id": video.id,
        "filename": video.filename,
        "file_size": video.file_size,
        "duration_seconds": checked.duration_seconds,
        "container": checked.media.container,
        "duplicate": duplicate,
    }


# ------------------------------------------------------------------ re-analysis (T55)


class ReanalyseRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class ReanalyseResponse(BaseModel):
    job_id: str
    video_id: str
    status: str            # PENDING; FAILED (error_code DISPATCH_FAILED) if queuing failed
    state: str             # §1 state: QUEUED; FAILED if queuing failed
    error_code: Optional[str] = None
    celery_task_id: Optional[str] = None
    previous_job_id: Optional[str] = None
    superseded_review_ids: list[str] = Field(default_factory=list)
    reanalyses_remaining: int  # the smaller of the per-video and per-user allowances left
    created_at: Optional[datetime] = None


def get_reanalysis_dispatcher() -> Callable[[str, Optional[str]], Optional[str]]:
    """Queues the new job exactly as POST /jobs/create does; returns the task id.
    Overridden in tests."""

    def _dispatch(job_id: str, storage_key: Optional[str]) -> Optional[str]:
        from app.api.routers.jobs import process_video_task

        return process_video_task.delay(job_id, storage_key=storage_key).id

    return _dispatch


@v1_router.post("/{video_id}/reanalyse", response_model=ReanalyseResponse, status_code=202)
def reanalyse_video(
    video_id: str,
    response: Response,
    payload: Optional[ReanalyseRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    dispatch: Callable = Depends(get_reanalysis_dispatcher),
):
    """Analyse a video again on purpose (T55), e.g. to check a pipeline change on it.

    Only the video's owner or an admin; the reviewer role is not enough. Always creates
    a new job linked to the video's previous one (``previous_job_id``); the reuse rules
    of POST /jobs/create don't apply. An open review case on the video is SUPERSEDED.
    At most ``REANALYSIS_MAX_PER_VIDEO`` per caller per video per
    ``REANALYSIS_WINDOW_HOURS``, and ``REANALYSIS_MAX_PER_USER`` per caller across all
    videos in the same window (admins included): over either, 429 with Retry-After and
    ``limit_kind``."""
    from app.auth.roles import role_of
    from app.db.models.video import Video
    from app.services import reanalysis_service as rs
    from app.services import users_service

    uid = ownership.owner_id(current_user)
    video = db.get(Video, video_id)
    if uid is None or video is None or not ownership.can_view_video(db, video, current_user):
        raise HTTPException(status_code=404, detail="Video not found")
    is_owner = video.user_id == uid or (video.user_id is None and not settings.REQUIRE_AUTH)
    if not (is_owner or ownership.is_admin(current_user)):
        # The caller may see the video (a reviewer) but not re-run it.
        raise HTTPException(status_code=403, detail={
            "code": "REANALYSIS_FORBIDDEN",
            "message": "only the video's owner or an admin can re-analyse it",
        })
    users_service.remember(db, current_user)
    try:
        out = rs.reanalyse_video(
            db, video, actor_id=uid, actor_role=role_of(current_user).value,
            reason=payload.reason if payload else None, dispatch=dispatch,
        )
    except rs.ReanalysisRateLimited as exc:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail={"code": "REANALYSIS_RATE_LIMITED", "message": str(exc),
                    "limit_kind": exc.limit_kind,  # "per_video" or "per_user"
                    "retry_after_seconds": exc.retry_after, "limit": exc.limit,
                    "window_hours": exc.window_hours},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except rs.ReanalysisDisabled as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail={"code": "REANALYSIS_DISABLED", "message": str(exc)}) from exc

    from app.services.job_events import effective_state

    job = out.job
    response.headers["X-Reanalyses-Remaining"] = str(out.remaining)
    return ReanalyseResponse(
        job_id=job.id, video_id=job.video_id, status=job.status.value, state=effective_state(job),
        error_code=job.error_code, celery_task_id=job.celery_task_id, previous_job_id=out.previous_job_id,
        superseded_review_ids=out.superseded_review_ids, reanalyses_remaining=out.remaining,
        created_at=job.created_at,
    )
