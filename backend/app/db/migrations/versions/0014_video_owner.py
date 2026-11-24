"""per-user video ownership (videos.user_id) and per-user duplicate detection

Revision ID: 0014
Revises: 0012
Create Date: 2026-11-24

Target design §15 ("a user sees only their own videos, jobs and results") and §17
(``videos``: owner). T33. Completes T28's job ownership (0011, ``jobs.user_id``); no
second owner column is added to ``jobs``.

- ``videos.user_id``: nullable text, the uploader's Supabase JWT ``sub``; indexed.
- Backfill: a video whose jobs all have the same (non-NULL) owner takes that owner.
  Videos with no owned job, or jobs from several users (one row shared through the old
  global duplicate check), stay NULL: only admins see them directly, and each job owner
  still reaches their own results through their job. ``scripts/assign_owners.py``
  assigns the rest.
- Duplicate detection becomes per user: the unique index on ``file_hash`` is replaced by
  a plain index plus a unique (``user_id``, ``file_hash``) constraint, so a second user
  uploading the same file gets their own video instead of learning of the first upload.

Numbering: 0012 is T31's (claims.search_trail). 0013 is reserved by T30 (PR #86, open);
if it lands a 0013 migration first, set ``down_revision`` here to "0013" so
``alembic heads`` shows one head.

Downgrade restores the global unique index, which fails if two users now have the same
file; remove the later duplicates first.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("videos") as batch:
        batch.add_column(sa.Column("user_id", sa.String(), nullable=True))
    op.create_index("ix_videos_user_id", "videos", ["user_id"])

    # A video takes its jobs' owner when they agree on exactly one.
    op.execute(
        """
        UPDATE videos SET user_id = (
            SELECT MIN(jobs.user_id) FROM jobs
            WHERE jobs.video_id = videos.id AND jobs.user_id IS NOT NULL
        )
        WHERE videos.user_id IS NULL
          AND (SELECT COUNT(DISTINCT jobs.user_id) FROM jobs
               WHERE jobs.video_id = videos.id AND jobs.user_id IS NOT NULL) = 1
        """
    )

    op.drop_index("ix_videos_file_hash", table_name="videos")
    op.create_index("ix_videos_file_hash", "videos", ["file_hash"], unique=False)
    with op.batch_alter_table("videos") as batch:
        batch.create_unique_constraint("uq_videos_user_file_hash", ["user_id", "file_hash"])


def downgrade() -> None:
    with op.batch_alter_table("videos") as batch:
        batch.drop_constraint("uq_videos_user_file_hash", type_="unique")
    op.drop_index("ix_videos_file_hash", table_name="videos")
    op.create_index("ix_videos_file_hash", "videos", ["file_hash"], unique=True)
    op.drop_index("ix_videos_user_id", table_name="videos")
    with op.batch_alter_table("videos") as batch:
        batch.drop_column("user_id")
