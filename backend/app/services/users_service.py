"""Who is who: display names and emails for review screens (target design §12 "every
action records who", §15, §17 ``users``; T34).

``remember(db, user)`` upserts the caller's row from their **verified** JWT (``sub``,
``email``, a display name from ``user_metadata``) and is called by the routes people
use to act: ``/v1/me``, the review routes, uploads and job creation. Nothing here calls
Supabase: names come only from tokens the API has already verified, so a user the API
has never seen since T34 shows no name (the id is still there).

``person(...)`` is the one place that decides what a viewer may learn about another
user (§15):

- reviewers and admins see the display name and the email;
- anyone else sees the display name only, never another user's email (they do see
  their own);
- ``name`` is the display name, else the email when the viewer may see it, else None.

``user_metadata`` is editable by its user, so a display name is only a label; the
email (verified by Supabase) is what a reviewer should trust.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy.orm import Session

from app.db.models.user import User

log = logging.getLogger(__name__)

_NAME_KEYS = ("display_name", "full_name", "name")
_NAME_MAX = 200
_EMAIL_MAX = 320


def _clean(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())  # no newlines or control whitespace in a label
    return value[:limit] or None


def profile_from_token(user: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """``(email, display_name)`` from a verified token's claims."""
    email = _clean(user.get("email"), _EMAIL_MAX)
    meta = user.get("user_metadata")
    name = None
    if isinstance(meta, Mapping):
        for key in _NAME_KEYS:
            name = _clean(meta.get(key), _NAME_MAX)
            if name:
                break
    return email, name


def remember(db: Session, user: Optional[Mapping[str, Any]]) -> None:
    """Upsert the caller's ``users`` row. Writes only when something changed. Never
    fails the request: on a database error it logs, rolls back its own change and
    returns (call it before the route's own writes)."""
    sub = (user or {}).get("sub")
    if not sub:
        return
    sub = str(sub)
    email, name = profile_from_token(user or {})
    try:
        row = db.get(User, sub)
        now = datetime.now(timezone.utc)
        if row is None:
            db.add(User(id=sub, email=email, display_name=name, created_at=now, updated_at=now))
        elif (email and row.email != email) or (name and row.display_name != name):
            # A token without the claim doesn't erase what we already know.
            row.email = email or row.email
            row.display_name = name or row.display_name
            row.updated_at = now
        else:
            return
        db.commit()
    except Exception as exc:  # a concurrent insert of the same user, a read-only replica, ...
        db.rollback()
        log.warning("could not record user %s: %s", sub, type(exc).__name__)


def load(db: Session, ids: Iterable[Optional[str]]) -> dict[str, User]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {u.id: u for u in db.query(User).filter(User.id.in_(sorted(wanted))).all()}


@dataclass(frozen=True)
class Person:
    name: Optional[str]
    email: Optional[str]


def person(
    users: Mapping[str, User],
    user_id: Optional[str],
    *,
    viewer: Optional[Mapping[str, Any]],
) -> Person:
    """What ``viewer`` may see about ``user_id`` (rules in the module docstring)."""
    from app.api.ownership import is_reviewer, owner_id

    if not user_id:
        return Person(None, None)
    row = users.get(user_id)
    if row is None:
        return Person(None, None)
    may_see_email = is_reviewer(viewer) or owner_id(viewer) == user_id
    email = row.email if may_see_email else None
    return Person(row.display_name or email, email)
