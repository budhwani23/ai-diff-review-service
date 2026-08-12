"""Create xsolla review service tables.

Revision ID: 20260812_01
Revises:
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "xsolla_review_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("max_findings", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("input_bytes", sa.Integer(), nullable=False),
        sa.Column("chunks", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_xsolla_review_jobs_status", "xsolla_review_jobs", ["status"])
    op.create_index(
        "ix_review_jobs_status_created",
        "xsolla_review_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_xsolla_review_jobs_request_hash",
        "xsolla_review_jobs",
        ["request_hash"],
    )
    op.create_index(
        "ix_xsolla_review_jobs_created_at",
        "xsolla_review_jobs",
        ["created_at"],
    )

    op.create_table(
        "xsolla_idempotency_records",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["xsolla_review_jobs.id"]),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_xsolla_idempotency_records_job_id",
        "xsolla_idempotency_records",
        ["job_id"],
    )

    op.create_table(
        "xsolla_cache_entries",
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_job_id"], ["xsolla_review_jobs.id"]),
        sa.PrimaryKeyConstraint("request_hash"),
    )

    op.create_table(
        "xsolla_job_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["xsolla_review_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),
    )
    op.create_index(
        "ix_xsolla_job_events_job_id",
        "xsolla_job_events",
        ["job_id"],
    )
    op.create_index(
        "ix_job_events_job_sequence",
        "xsolla_job_events",
        ["job_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_table("xsolla_job_events")
    op.drop_table("xsolla_cache_entries")
    op.drop_table("xsolla_idempotency_records")
    op.drop_table("xsolla_review_jobs")
