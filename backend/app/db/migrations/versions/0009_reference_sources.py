"""authoritative reference sources and claim_kind

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-22

Target design §4 and §6 "Trusted sources beyond PubMed" (T17). Additive only:

- ``reference_snapshots``: the text of each fetched reference page, keyed by its
  SHA-256 (pages change; a citation points at the text as it was).
- ``evidence_records``: nullable ``publisher``, ``retrieved_at``, ``snapshot_sha256``.
- ``claims``: nullable ``claim_kind`` (research_question / fact_of_record).

Nothing on the single-call path reads or writes these. Per-user job isolation
(context/PRODUCTION.md §6a), previously planned as 0009, moves to ``0010``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reference_snapshots",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.String(40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("evidence_records") as batch:
        batch.add_column(sa.Column("publisher", sa.String(255), nullable=True))
        batch.add_column(sa.Column("retrieved_at", sa.String(40), nullable=True))
        batch.add_column(sa.Column("snapshot_sha256", sa.String(64), nullable=True))
    with op.batch_alter_table("claims") as batch:
        batch.add_column(sa.Column("claim_kind", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("claims") as batch:
        batch.drop_column("claim_kind")
    with op.batch_alter_table("evidence_records") as batch:
        batch.drop_column("snapshot_sha256")
        batch.drop_column("retrieved_at")
        batch.drop_column("publisher")
    op.drop_table("reference_snapshots")
