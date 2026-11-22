"""claim-level results of the graph pipeline

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22

Target design §17, issue #38 (T11). Additive: new tables plus nullable columns on
``results``; nothing on the single-call path writes them. Per-user job isolation
(context/PRODUCTION.md §6a) moves to ``0009``.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pk() -> sa.Column:
    return sa.Column("id", sa.String(), primary_key=True)


def _job_fk() -> sa.Column:
    return sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False)


def _claim_fk(unique: bool) -> sa.Column:
    return sa.Column("claim_pk", sa.String(), sa.ForeignKey("claims.id", ondelete="CASCADE"),
                     nullable=False, unique=unique)


def upgrade() -> None:
    with op.batch_alter_table("results") as batch:
        batch.add_column(sa.Column("pipeline", sa.String(32), nullable=True))
        batch.add_column(sa.Column("pipeline_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column("fallback_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("decision_rule", sa.String(64), nullable=True))
        batch.add_column(sa.Column("deciding_claim_ids", sa.JSON(), nullable=True))

    for name in ("transcript_segments", "ocr_segments"):
        cols = [
            _pk(), _job_fk(),
            sa.Column("segment_id", sa.String(64), nullable=False),
            sa.Column("start_seconds", sa.Float(), nullable=False),
            sa.Column("end_seconds", sa.Float(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
        ]
        if name == "ocr_segments":
            cols.append(sa.Column("confidence", sa.Float(), nullable=False))
        op.create_table(name, *cols, sa.UniqueConstraint("job_id", "segment_id", name=f"uq_{name}_job_segment"))
        op.create_index(f"ix_{name}_job_id", name, ["job_id"])

    op.create_table(
        "claims", _pk(), _job_fk(),
        sa.Column("claim_id", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("source_segment_ids", sa.JSON(), nullable=False),
        sa.Column("requires_verification", sa.Boolean(), nullable=False),
        sa.Column("label", sa.String(32), nullable=True),
        sa.Column("deciding", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", "claim_id", name="uq_claims_job_claim"),
    )
    op.create_index("ix_claims_job_id", "claims", ["job_id"])

    op.create_table(
        "claim_stances", _pk(), _claim_fk(unique=True),
        sa.Column("stance", sa.String(16), nullable=False),
        sa.Column("segment_ids", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
    )

    op.create_table(
        "evidence_records", _pk(), _job_fk(),
        sa.Column("evidence_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("pmid", sa.String(32), nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("publication_type", sa.JSON(), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("study_type", sa.String(64), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.UniqueConstraint("job_id", "evidence_id", name="uq_evidence_records_job_evidence"),
    )
    op.create_index("ix_evidence_records_job_id", "evidence_records", ["job_id"])

    op.create_table(
        "claim_evidence", _pk(), _claim_fk(unique=False),
        sa.Column("evidence_pk", sa.String(), sa.ForeignKey("evidence_records.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.UniqueConstraint("claim_pk", "evidence_pk", name="uq_claim_evidence_pair"),
    )

    op.create_table(
        "verification_results", _pk(), _claim_fk(unique=True),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("raw_confidence", sa.Float(), nullable=True),
        sa.Column("revisions", sa.Integer(), nullable=False),
        sa.Column("retrieval_attempts", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
    )

    op.create_table(
        "critic_reviews", _pk(), _claim_fk(unique=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
    )

    op.create_table(
        "model_runs", _pk(), _job_fk(),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_model_runs_job_id", "model_runs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_model_runs_job_id", table_name="model_runs")
    op.drop_table("model_runs")
    op.drop_table("critic_reviews")
    op.drop_table("verification_results")
    op.drop_table("claim_evidence")
    op.drop_index("ix_evidence_records_job_id", table_name="evidence_records")
    op.drop_table("evidence_records")
    op.drop_table("claim_stances")
    op.drop_index("ix_claims_job_id", table_name="claims")
    op.drop_table("claims")
    for name in ("ocr_segments", "transcript_segments"):
        op.drop_index(f"ix_{name}_job_id", table_name=name)
        op.drop_table(name)
    with op.batch_alter_table("results") as batch:
        batch.drop_column("deciding_claim_ids")
        batch.drop_column("decision_rule")
        batch.drop_column("fallback_reason")
        batch.drop_column("pipeline_version")
        batch.drop_column("pipeline")
