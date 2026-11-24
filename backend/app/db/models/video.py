import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Video(Base):
    __tablename__ = "videos"
    # Duplicate detection is per user (T33, migration 0014): the same file uploaded by
    # two users is two videos, so neither learns of the other's upload.
    __table_args__ = (UniqueConstraint("user_id", "file_hash", name="uq_videos_user_file_hash"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String)
    file_size: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        index=True,
        nullable=True,
        )
    storage_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # T33 (migration 0014). Owner = the JWT ``sub`` of the uploader; NULL on videos
    # uploaded before 0014 that no job owner could be inferred for (admin only).
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )