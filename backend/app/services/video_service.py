from __future__ import annotations

import hashlib
import os
import uuid
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.video import Video


def _own_duplicate(db: Session, file_hash: str, user_id: Optional[str]) -> Optional[Video]:
    """The caller's earlier upload of the same file, if any. Duplicate detection is per
    user (T33): another user's identical upload is never returned, so its id and
    filename don't leak. With REQUIRE_AUTH off (one dev user) videos uploaded before
    owners existed still count."""
    q = db.query(Video).filter(Video.file_hash == file_hash)
    if user_id is None:
        return q.filter(Video.user_id.is_(None)).first()
    if not settings.REQUIRE_AUTH:
        return q.filter(or_(Video.user_id == user_id, Video.user_id.is_(None))).order_by(
            Video.user_id.is_(None)).first()
    return q.filter(Video.user_id == user_id).first()


def save_video(db: Session, content: bytes, filename: str, user_id: Optional[str] = None) -> Video:
    file_hash = hashlib.sha256(content).hexdigest()

    existing_video = _own_duplicate(db, file_hash, user_id)
    if existing_video:
        return existing_video

    video_id = str(uuid.uuid4())

    os.makedirs(settings.LOCAL_STORAGE_ROOT, exist_ok=True)
    ext = os.path.splitext(filename)[1] or ".mp4"
    local_path = os.path.join(settings.LOCAL_STORAGE_ROOT, f"{video_id}{ext}")

    with open(local_path, "wb") as f:
        f.write(content)

    storage_key: str | None = None

    if settings.STORAGE_BACKEND == "supabase":
        from app.core.storage import get_storage_backend
        storage = get_storage_backend()
        key = f"videos/{video_id}/{filename}"
        storage.upload(local_path, key)
        storage_key = key

    video = Video(
        id=video_id,
        filename=filename,
        file_path=local_path,
        file_size=len(content),
        file_hash=file_hash,
        storage_key=storage_key,
        user_id=user_id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def register_uploaded_video(
    db: Session,
    storage_key: str,
    filename: str,
    file_size: int,
    file_hash: str,
    user_id: Optional[str] = None,
) -> tuple[Video, bool]:
    """Register an object already in storage (signed upload, T20). Returns
    ``(video, duplicate)``; a SHA-256 the caller already uploaded reuses their earlier
    video (design §1; per user since T33)."""
    existing_video = _own_duplicate(db, file_hash, user_id)
    if existing_video:
        return existing_video, True
    video = Video(
        id=str(uuid.uuid4()),
        filename=filename,
        # The worker downloads by storage_key (STORAGE_BACKEND=supabase); there is
        # no local copy on the API server.
        file_path=storage_key,
        file_size=file_size,
        file_hash=file_hash,
        storage_key=storage_key,
        user_id=user_id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video, False
