from __future__ import annotations

import os
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.video import Video


def save_video(db: Session, content: bytes, filename: str) -> Video:
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
        storage_key=storage_key,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video
