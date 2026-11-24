"""results.misinfo_basis

Revision ID: 0013
Revises: 0012 (T31; 0011 is T28)
Create Date: 2026-11-23

Target design §9 (T30, decision D1 = B): a MISINFO result carries a ``misinfo_basis``,
``contradicted``, ``denies_supported`` or ``unproven``. The label column is unchanged
(still one of the four labels); the interface shows "MISINFO (unproven)" from the basis.
Additive only: one nullable column. NULL on rows written before this migration, on
non-MISINFO results and on the single-call path.

Numbering (automation/BUILD_QUEUE.md): 0011 = T28 (#81), 0012 = T31 (#84), 0013 = T30.
Neither 0011 nor 0012 is on ``langgraph-build`` yet, so this revision follows 0010 for
now and the branch has a single head. When #81 and #84 merge first, change
``down_revision`` to "0012" (one line) so ``alembic heads`` shows one head.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.add_column(sa.Column("misinfo_basis", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.drop_column("misinfo_basis")
