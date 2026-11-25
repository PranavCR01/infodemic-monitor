"""results.routing_snapshot

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-24

Target design §12 and §14 (T36): graph results store a traceable version,
``graph_v1+<short git sha>+p<routing hash>``, in the existing ``pipeline_version``
column (String(64); the new form is ~26 chars), and the routing it names (prompt
version and model per LLM step, fallback policy) in this new JSON column.
Additive only: one nullable column. NULL on rows written before this migration and on
the single-call path; older rows keep their stored ``graph_v1``.

Numbering (automation/BUILD_QUEUE.md): 0014 = T33 (#94), 0015 = T36.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.add_column(sa.Column("routing_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.drop_column("routing_snapshot")
