"""add REVIEW_REQUIRED job state and human_reviews table

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22

Target design §11–§12 and §17 (``human_reviews``), issue #36 (T09). The job state is
additive: nothing on the single-call path sets it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CASE_STATUS = ("OPEN", "RESOLVED")
_ACTIONS = ("APPROVE", "CORRECT", "MARK_INSUFFICIENT", "REQUEST_REANALYSIS", "REJECT")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # ALTER TYPE ... ADD VALUE can't run inside a transaction block on older
        # Postgres; autocommit_block handles that.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'REVIEW_REQUIRED'")
    # Other dialects store the enum as VARCHAR without a CHECK constraint
    # (SQLAlchemy's default), so there is nothing to alter.

    op.create_table(
        "human_reviews",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("status", sa.Enum(*_CASE_STATUS, name="reviewcasestatus"), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("rules_fired", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("proposed_label", sa.String(32), nullable=True),
        sa.Column("proposed_result", sa.JSON(), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewer_id", sa.String(), nullable=True),
        sa.Column("action", sa.Enum(*_ACTIONS, name="reviewaction"), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("corrected_label", sa.String(32), nullable=True),
        sa.Column("corrections", sa.JSON(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_human_reviews_status", "human_reviews", ["status"])


def downgrade() -> None:
    op.drop_index("ix_human_reviews_status", table_name="human_reviews")
    op.drop_table("human_reviews")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS reviewaction")
        op.execute("DROP TYPE IF EXISTS reviewcasestatus")
        # Postgres can't drop one value from an enum. Move any REVIEW_REQUIRED jobs to
        # FAILED and rebuild the type without it.
        op.execute("UPDATE jobs SET status = 'FAILED' WHERE status = 'REVIEW_REQUIRED'")
        op.execute("ALTER TYPE jobstatus RENAME TO jobstatus_old")
        op.execute("CREATE TYPE jobstatus AS ENUM ('PENDING', 'STARTED', 'SUCCESS', 'FAILED')")
        op.execute(
            "ALTER TABLE jobs ALTER COLUMN status TYPE jobstatus USING status::text::jobstatus"
        )
        op.execute("DROP TYPE jobstatus_old")
