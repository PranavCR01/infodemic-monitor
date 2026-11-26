"""deliberate re-analysis: jobs.previous_job_id and SUPERSEDED review cases

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-26

T55 (target design §1, §12, §17):

- ``jobs.previous_job_id``: nullable FK to ``jobs.id``, indexed. The job a re-run
  re-analyses (POST /v1/videos/{id}/reanalyse, or a reviewer's REQUEST_REANALYSIS).
  NULL on first runs; no backfill (older re-runs were never linked).
- ``reviewcasestatus`` gains ``SUPERSEDED``: an open case whose video was re-analysed
  leaves the queue without a decision.
- ``human_reviews.superseded_by_job_id``: nullable FK to ``jobs.id``, the new job.

Downgrade removes both columns and the enum value. Postgres can't drop one value from
an enum, so the type is rebuilt; SUPERSEDED cases become RESOLVED first (with no
action, which pre-0017 code shows as REANALYSIS_REQUESTED, the closest it has). That
step loses the link to the new job, which only 0017 can hold.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_JOB = "fk_jobs_previous_job_id"
_FK_CASE = "fk_human_reviews_superseded_by_job_id"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # ALTER TYPE ... ADD VALUE can't run inside a transaction block on older
        # Postgres; autocommit_block handles that (as in 0007).
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE reviewcasestatus ADD VALUE IF NOT EXISTS 'SUPERSEDED'")
    # Other dialects store the enum as VARCHAR without a CHECK constraint.

    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("previous_job_id", sa.String(), nullable=True))
        batch.create_foreign_key(_FK_JOB, "jobs", ["previous_job_id"], ["id"])
        batch.create_index("ix_jobs_previous_job_id", ["previous_job_id"])

    with op.batch_alter_table("human_reviews") as batch:
        batch.add_column(sa.Column("superseded_by_job_id", sa.String(), nullable=True))
        batch.create_foreign_key(_FK_CASE, "jobs", ["superseded_by_job_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("UPDATE human_reviews SET status = 'RESOLVED' WHERE status = 'SUPERSEDED'")

    with op.batch_alter_table("human_reviews") as batch:
        batch.drop_constraint(_FK_CASE, type_="foreignkey")
        batch.drop_column("superseded_by_job_id")

    with op.batch_alter_table("jobs") as batch:
        batch.drop_index("ix_jobs_previous_job_id")
        batch.drop_constraint(_FK_JOB, type_="foreignkey")
        batch.drop_column("previous_job_id")

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE reviewcasestatus RENAME TO reviewcasestatus_old")
        op.execute("CREATE TYPE reviewcasestatus AS ENUM ('OPEN', 'RESOLVED')")
        op.execute(
            "ALTER TABLE human_reviews ALTER COLUMN status TYPE reviewcasestatus "
            "USING status::text::reviewcasestatus"
        )
        op.execute("DROP TYPE reviewcasestatus_old")
