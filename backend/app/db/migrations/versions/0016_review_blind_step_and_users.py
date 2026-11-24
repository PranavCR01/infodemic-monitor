"""review reason codes, the blind pre-reveal step, and a users table

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-24

T34 (lead's decision D7; target design §12, §15, §17):

- ``human_reviews.reason_code``: nullable String(32), one of CLAIM_OVERGENERALISED,
  EVIDENCE_MISREAD, STANCE_MISREAD, MISSING_SOURCE, SYSTEM_CORRECT, OTHER. NULL on
  decisions made before this migration (no backfill: we don't know why they were made).
- ``review_pre_reveals``: a reviewer's own per-claim stance and verdict on a HIGH case,
  recorded before the system's view is shown; unique per (review, reviewer).
- ``users`` (§17): id = Supabase JWT ``sub``, email, display name, from the verified
  token. No role column: roles are only ever read from the token.

Numbering: 0015 is T36 (``results.routing_snapshot``); this one follows it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("human_reviews") as batch:
        batch.add_column(sa.Column("reason_code", sa.String(32), nullable=True))

    op.create_table(
        "review_pre_reveals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("review_id", sa.String(), sa.ForeignKey("human_reviews.id"), nullable=False),
        sa.Column("reviewer_id", sa.String(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("case_severity", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("review_id", "reviewer_id", name="uq_pre_reveal_review_reviewer"),
    )
    op.create_index("ix_review_pre_reveals_review_id", "review_pre_reveals", ["review_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_index("ix_review_pre_reveals_review_id", table_name="review_pre_reveals")
    op.drop_table("review_pre_reveals")
    with op.batch_alter_table("human_reviews") as batch:
        batch.drop_column("reason_code")
