"""add file hash to videos

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("file_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_videos_file_hash",
        "videos",
        ["file_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_videos_file_hash", table_name="videos")
    op.drop_column("videos", "file_hash")

