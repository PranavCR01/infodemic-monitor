import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

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
