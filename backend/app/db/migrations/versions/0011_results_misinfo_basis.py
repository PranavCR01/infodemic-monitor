"""results.misinfo_basis

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-23

Target design §9 (T30, decision D1 = B): a MISINFO result carries a ``misinfo_basis``,
``contradicted``, ``denies_supported`` or ``unproven``. The label column is unchanged
(still one of the four labels); the interface shows "MISINFO (unproven)" from the basis.
Additive only: one nullable column. NULL on rows written before this migration, on
non-MISINFO results and on the single-call path.

Numbering: T28 adds a migration in parallel. Whichever merges second renumbers itself
after the other.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.add_column(sa.Column("misinfo_basis", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.drop_column("misinfo_basis")
