"""add error_code to jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-27

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("error_code", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "error_code")
