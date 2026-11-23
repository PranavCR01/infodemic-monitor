"""Signed playback URL for the result page's video player (T29; design §15, §17).

``GET /v1/jobs/{job_id}/playback`` returns a short-lived signed read URL for the job's
video. The bucket stays private (§15 "private buckets, short-lived signed URLs"): the
URL is minted per request, only after the caller passes the same per-object check as
every other result read (``app.api.ownership``), and a job the caller may not see
answers 404, so its existence isn't revealed (§15, §17).

The route is keyed by job, not video, because the result page is a job page and a
video can be shared by several jobs (duplicate uploads resolve to one video row); the
access rule is the job's.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.ownership import owned_job_or_404
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.storage import SignedUrlUnsupported, StorageBackend, get_storage_backend
from app.db.models.video import Video
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/jobs", tags=["playback"])


def get_storage() -> StorageBackend:
    return get_storage_backend()


class PlaybackUrlResponse(BaseModel):
    job_id: str
    video_id: str
    url: str = Field(description="Signed read URL for the video; do not store or share it.")
    expires_in_seconds: int = Field(description="Lifetime of the URL when it was issued.")
    expires_at: datetime = Field(description="When the URL stops working (UTC); ask again after.")
    filename: str | None = None


@router.get("/{job_id}/playback", response_model=PlaybackUrlResponse)
def get_playback_url(
    job_id: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage),
) -> PlaybackUrlResponse:
    job = owned_job_or_404(db, job_id, current_user)
    video = db.get(Video, job.video_id)
    if video is None or not video.storage_key:
        # Legacy local uploads have no storage object to sign.
        raise HTTPException(status_code=404, detail="No playable video for this job")

    ttl = settings.PLAYBACK_URL_TTL_SECONDS
    issued_at = datetime.now(timezone.utc)
    try:
        url = storage.create_signed_download_url(video.storage_key, ttl)
    except SignedUrlUnsupported as exc:
        raise HTTPException(status_code=501, detail="playback needs STORAGE_BACKEND=supabase") from exc
    except StorageError as exc:
        # The key is logged, never the URL (it is a bearer credential).
        logger.warning("signed playback URL failed for job %s: %s", job_id, exc)
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    if not url:
        logger.warning("storage returned no signed playback URL for job %s", job_id)
        raise HTTPException(status_code=503, detail="storage unavailable")

    # A signed URL is a short-lived credential: no browser or proxy cache may keep it.
    response.headers["Cache-Control"] = "no-store"
    return PlaybackUrlResponse(
        job_id=job.id,
        video_id=video.id,
        url=url,
        expires_in_seconds=ttl,
        expires_at=issued_at + timedelta(seconds=ttl),
        filename=video.filename,
    )
