"""review severity (priority) and audit_events

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-23

Target design §12 "Severity: which reviews come first" and §17 ``audit_events`` (T22).
Additive only:

- ``human_reviews``: nullable ``severity`` (indexed, for the queue order),
  ``claim_severities`` and ``severity_table_version``;
- ``audit_events``: who did what to which record, and when. Reviewer severity
  overrides are logged here.

Nothing on the single-call path reads or writes these. Per-user job isolation
(context/PRODUCTION.md §6a), previously planned as 0010, moves to ``0011``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("human_reviews") as batch:
        batch.add_column(sa.Column("severity", sa.String(8), nullable=True))
        batch.add_column(sa.Column("claim_severities", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("severity_table_version", sa.String(64), nullable=True))
    op.create_index("ix_human_reviews_severity", "human_reviews", ["severity"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_job_id", "audit_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_job_id", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_human_reviews_severity", table_name="human_reviews")
    with op.batch_alter_table("human_reviews") as batch:
        batch.drop_column("severity_table_version")
        batch.drop_column("claim_severities")
        batch.drop_column("severity")
