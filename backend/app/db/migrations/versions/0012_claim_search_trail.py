"""claims.search_trail ("How we searched")

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-23

Target design §6, §8, §12 (T31). Additive only: one nullable JSON column on
``claims`` holding the claim's search trail (PubMed queries run, references and
library consulted, retrieved / screened / kept counts, budget used). Rows written
before this migration keep NULL and the result API returns ``search_trail: null``.
Numbered 0012 because T28's job_events migration (PR #81) is 0011 and merges first.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("claims") as batch:
        batch.add_column(sa.Column("search_trail", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("claims") as batch:
        batch.drop_column("search_trail")
