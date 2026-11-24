"""job progress events (job_events), §1 job state and per-user job ownership

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-23

Target design §1 (job states), §16 and §17 (``job_events``; every endpoint checks the
caller owns the object). T28. Additive only:

- ``jobs``: nullable ``user_id`` (owner, JWT ``sub``; indexed), nullable ``state`` (the
  §1 state, next to the legacy ``status`` the current frontend reads), nullable
  ``current_step`` (the stepper step) and ``attempts`` (default 0).
- ``job_events``: every state change and pipeline step, with time.

This is the per-user job isolation planned in context/PRODUCTION.md §6a (previously
"0011"). Jobs created before it have no owner: they are hidden from every signed-in
user until a person assigns ``jobs.user_id`` (see context/MULTI_AGENT.md §7w).
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
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("user_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("state", sa.String(32), nullable=True))
        batch.add_column(sa.Column("current_step", sa.String(32), nullable=True))
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_state", "jobs", ["state"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("step", sa.String(32), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_events_job_id", table_name="job_events")
    op.drop_table("job_events")
    op.drop_index("ix_jobs_state", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("attempts")
        batch.drop_column("current_step")
        batch.drop_column("state")
        batch.drop_column("user_id")
