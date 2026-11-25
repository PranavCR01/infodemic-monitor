"""Known users (target design §17 ``users``; T34).

One row per Supabase user the API has seen: the JWT ``sub`` as the id, plus the email
and display name from the verified token, refreshed whenever they change. It exists so
review screens can show *who* did something (audit trail, decisions, queue items)
without calling Supabase on every read.

Roles are **not** stored here: authorization always reads the verified token
(``app.auth.roles``), so a stale or edited row can never grant anything. The display
name comes from ``user_metadata``, which the user can edit, so it is a label only;
reviewer-facing views also carry the (Supabase-verified) email.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # JWT ``sub``
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
