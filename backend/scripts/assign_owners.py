"""Assign owners to legacy jobs and videos (T33; design §15, §17). Admin only.

Jobs created before migration 0011 and videos uploaded before 0014 have no owner
(``user_id`` NULL). With ``REQUIRE_AUTH`` on only admins can see them; this script gives
them an owner (a Supabase user id, the JWT ``sub``) so their users see them again.

It is an operator tool, not an API route: it talks to the database directly
(``DATABASE_URL_SYNC``), so only someone with production database credentials, i.e. an
admin, can run it. Nothing changes without ``--apply`` (a dry run prints what would
change); an owner that is already set is never replaced without ``--force``. Every
change is written to ``audit_events`` (action ``owner_assigned``) with ``--actor``.

    # what has no owner
    python scripts/assign_owners.py list
    # fill owners that follow from the data: a video from its jobs' one owner, a job
    # from its video's owner
    python scripts/assign_owners.py infer --actor admin@example.org [--apply]
    # give jobs and/or videos to a user (--with-jobs also takes the videos' unowned jobs)
    python scripts/assign_owners.py set --user <sub> --job <id> [--job <id> ...] \\
        [--video <id> ...] [--with-jobs] --actor admin@example.org [--apply] [--force]
    # many at once: CSV with columns kind,id,user_id (kind = job or video)
    python scripts/assign_owners.py csv owners.csv --actor admin@example.org [--apply]
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models.job import Job  # noqa: E402
from app.db.models.review import AuditEvent  # noqa: E402
from app.db.models.video import Video  # noqa: E402

ACTION = "owner_assigned"
_MODELS = {"job": Job, "video": Video}


@dataclass
class Change:
    kind: str  # "job" | "video"
    id: str
    old: Optional[str]
    new: str
    applied: bool = False
    skipped: Optional[str] = None  # why nothing changed

    def line(self) -> str:
        if self.skipped:
            return f"skip {self.kind} {self.id}: {self.skipped}"
        verb = "set" if self.applied else "would set"
        return f"{verb} {self.kind} {self.id} owner {self.old!r} -> {self.new!r}"


def _audit(db: Session, change: Change, actor: str, reason: str) -> None:
    db.add(AuditEvent(
        actor_id=f"admin-script:{actor}", action=ACTION, entity_type=change.kind, entity_id=change.id,
        job_id=change.id if change.kind == "job" else None, reason=reason,
        details={"from": change.old, "to": change.new},
    ))


def _assign(db: Session, kind: str, obj_id: str, user_id: str, *, actor: str, reason: str,
            apply: bool, force: bool) -> Change:
    user_id = (user_id or "").strip()
    if not user_id:
        return Change(kind, obj_id, None, "", skipped="empty user id")
    obj = db.get(_MODELS[kind], obj_id)
    if obj is None:
        return Change(kind, obj_id, None, user_id, skipped="not found")
    change = Change(kind, obj_id, obj.user_id, user_id)
    if obj.user_id == user_id:
        change.skipped = "already owned by that user"
    elif obj.user_id is not None and not force:
        change.skipped = f"already owned by {obj.user_id!r} (use --force to replace)"
    elif apply:
        obj.user_id = user_id
        _audit(db, change, actor, reason)
        change.applied = True
    return change


def unowned(db: Session) -> dict[str, list]:
    return {
        "jobs": db.query(Job.id, Job.video_id, Job.created_at).filter(Job.user_id.is_(None))
                  .order_by(Job.created_at).all(),
        "videos": db.query(Video.id, Video.filename, Video.created_at).filter(Video.user_id.is_(None))
                    .order_by(Video.created_at).all(),
    }


def infer(db: Session, *, actor: str, apply: bool) -> list[Change]:
    """Owners that follow from the data, never overwriting one: a video takes the owner
    of its jobs when they all agree; a job takes its video's owner."""
    changes: list[Change] = []
    owners = (
        db.query(Job.video_id, func.min(Job.user_id), func.count(func.distinct(Job.user_id)))
        .filter(Job.user_id.isnot(None)).group_by(Job.video_id).all()
    )
    for video_id, owner, n in owners:
        video = db.get(Video, video_id)
        if video is None or video.user_id is not None:
            continue
        if n != 1:
            changes.append(Change("video", video_id, None, "", skipped=f"jobs from {n} users; assign by hand"))
            continue
        changes.append(_assign(db, "video", video_id, owner, actor=actor, apply=apply, force=False,
                               reason="inferred from the video's jobs"))
    if apply:
        db.flush()
    rows = (db.query(Job.id, Video.user_id).join(Video, Video.id == Job.video_id)
            .filter(Job.user_id.is_(None), Video.user_id.isnot(None)).all())
    for job_id, owner in rows:
        changes.append(_assign(db, "job", job_id, owner, actor=actor, apply=apply, force=False,
                               reason="inferred from the job's video"))
    return changes


def assign(db: Session, *, user_id: str, job_ids: Iterable[str] = (), video_ids: Iterable[str] = (),
           with_jobs: bool = False, actor: str, apply: bool, force: bool) -> list[Change]:
    changes = []
    video_ids = list(video_ids)
    for vid in video_ids:
        changes.append(_assign(db, "video", vid, user_id, actor=actor, reason="assigned by an admin",
                               apply=apply, force=force))
    job_ids = list(job_ids)
    if with_jobs and video_ids:
        q = db.query(Job.id).filter(Job.video_id.in_(video_ids))
        if not force:
            q = q.filter(Job.user_id.is_(None))
        job_ids += [j for (j,) in q.all() if j not in job_ids]
    for jid in job_ids:
        changes.append(_assign(db, "job", jid, user_id, actor=actor, reason="assigned by an admin",
                               apply=apply, force=force))
    return changes


def from_csv(db: Session, path: Path, *, actor: str, apply: bool, force: bool) -> list[Change]:
    changes = []
    with open(path, newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            kind = (row.get("kind") or "").strip().lower()
            if kind not in _MODELS:
                changes.append(Change(kind or "?", row.get("id") or "", None, "",
                                      skipped=f"line {n}: kind must be job or video"))
                continue
            changes.append(_assign(db, kind, (row.get("id") or "").strip(), row.get("user_id") or "",
                                   actor=actor, reason=f"assigned by an admin ({path.name})",
                                   apply=apply, force=force))
    return changes


def _session() -> Session:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    return sessionmaker(bind=create_engine(settings.DATABASE_URL_SYNC))()


def main(argv: list[str] | None = None, db: Optional[Session] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list jobs and videos with no owner")
    for name in ("infer", "set", "csv"):
        p = sub.add_parser(name)
        p.add_argument("--actor", required=True, help="who is running this (recorded in audit_events)")
        p.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
        if name != "infer":
            p.add_argument("--force", action="store_true", help="replace an owner that is already set")
        if name == "set":
            p.add_argument("--user", required=True, help="the Supabase user id (JWT sub)")
            p.add_argument("--job", action="append", default=[])
            p.add_argument("--video", action="append", default=[])
            p.add_argument("--with-jobs", action="store_true",
                           help="also give the videos' unowned jobs to the user")
        if name == "csv":
            p.add_argument("path", type=Path)
    args = ap.parse_args(argv)

    own = db is None
    db = db or _session()
    try:
        if args.cmd == "list":
            rows = unowned(db)
            for j in rows["jobs"]:
                print(f"job   {j.id}  video={j.video_id}  created={j.created_at}")
            for v in rows["videos"]:
                print(f"video {v.id}  {v.filename!r}  created={v.created_at}")
            print(f"{len(rows['jobs'])} jobs and {len(rows['videos'])} videos have no owner")
            return 0
        if args.cmd == "infer":
            changes = infer(db, actor=args.actor, apply=args.apply)
        elif args.cmd == "set":
            if not args.job and not args.video:
                ap.error("set needs --job and/or --video")
            changes = assign(db, user_id=args.user, job_ids=args.job, video_ids=args.video,
                             with_jobs=args.with_jobs, actor=args.actor, apply=args.apply, force=args.force)
        else:
            changes = from_csv(db, args.path, actor=args.actor, apply=args.apply, force=args.force)
        for c in changes:
            print(c.line())
        if args.apply:
            db.commit()
        done = sum(c.applied for c in changes)
        pending = sum(1 for c in changes if not c.skipped and not c.applied)
        print(f"{done} changed, {pending} would change (dry run; add --apply)" if not args.apply
              else f"{done} changed")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
