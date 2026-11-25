"""User roles: analyst, reviewer, admin (target design §15 "Separate roles for
reviewers and admins", §17 ``users.role``; T27).

The role is decided on the server from the verified Supabase JWT, never from anything
the client sends in a request body, query or header of its own:

- It is read from ``app_metadata.role`` (a string) or ``app_metadata.roles`` (a list).
  Supabase only lets the service key write ``app_metadata``, so a user can't grant
  themselves a role. ``user_metadata`` is editable by the user and is **ignored**, as is
  the top-level ``role`` claim (Supabase puts the Postgres role there, e.g.
  ``authenticated``).
- Unknown values are ignored; with several known roles the highest wins.
- Anyone without a role claim is an analyst (least privilege).
- With ``REQUIRE_AUTH`` off (local development only) the dev user takes
  ``DEV_USER_ROLE`` (default ``analyst``).

Ranks: analyst < reviewer < admin. An admin can do everything a reviewer can.
"""
from __future__ import annotations

import enum
from typing import Any, Callable, Iterable, Mapping

from fastapi import Depends, HTTPException

from app.auth.dependencies import get_current_user


class Role(str, enum.Enum):
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Role.ANALYST: 0, Role.REVIEWER: 1, Role.ADMIN: 2}

# Where the role lives in the token. Only server-writable claims.
_CLAIM_CONTAINER = "app_metadata"


def _parse(value: Any) -> list[Role]:
    if isinstance(value, str):
        values: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return []
    out = []
    for v in values:
        if not isinstance(v, str):
            continue
        try:
            out.append(Role(v.strip().lower()))
        except ValueError:
            continue
    return out


def role_of(user: Mapping[str, Any]) -> Role:
    """The caller's role, from the verified token's ``app_metadata`` only."""
    meta = user.get(_CLAIM_CONTAINER)
    if not isinstance(meta, Mapping):
        return Role.ANALYST
    found = _parse(meta.get("role")) + _parse(meta.get("roles"))
    if not found:
        return Role.ANALYST
    return max(found, key=lambda r: r.rank)


def user_id_of(user: Mapping[str, Any]) -> str:
    sub = user.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token has no subject")
    return str(sub)


def has_role(user: Mapping[str, Any], minimum: Role) -> bool:
    return role_of(user).rank >= minimum.rank


def require_role(minimum: Role) -> Callable[..., dict]:
    """A dependency that lets through callers with at least ``minimum`` and answers
    403 otherwise. The check runs before any lookup, so a refusal says nothing about
    whether the requested object exists."""

    def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        user_id_of(current_user)
        if not has_role(current_user, minimum):
            raise HTTPException(status_code=403, detail=f"requires the {minimum.value} role")
        return current_user

    _dep.__name__ = f"require_{minimum.value}"
    return _dep


# What each role may do, for the frontend to show or hide controls. The server checks
# every action itself; this list is only a hint.
PERMISSIONS: dict[Role, list[str]] = {
    Role.ANALYST: ["videos:own", "jobs:own", "results:own"],
    Role.REVIEWER: ["videos:own", "jobs:own", "results:own",
                    "reviews:read", "reviews:decide", "reviews:override_severity"],
    Role.ADMIN: ["videos:own", "jobs:own", "results:own",
                 "reviews:read", "reviews:decide", "reviews:override_severity", "admin"],
}
