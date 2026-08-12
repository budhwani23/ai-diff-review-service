from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


JSON_COLUMN = JSON().with_variant(JSONB, "postgresql")


class JobStatusValue(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ReviewJob(SQLModel, table=True):
    __tablename__ = "xsolla_review_jobs"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, max_length=64)
    status: str = Field(default=JobStatusValue.QUEUED, index=True, max_length=16)
    diff: str = Field(sa_column=Column(Text, nullable=False))
    provider: str = Field(max_length=16)
    max_findings: int
    request_hash: str = Field(index=True, max_length=64)
    input_bytes: int
    chunks: int
    cache_hit: bool = False
    findings: list[dict[str, object]] | None = Field(
        default=None,
        sa_column=Column(JSON_COLUMN, nullable=True),
    )
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    __table_args__ = (Index("ix_review_jobs_status_created", "status", "created_at"),)


class IdempotencyRecord(SQLModel, table=True):
    __tablename__ = "xsolla_idempotency_records"

    key: str = Field(primary_key=True, max_length=255)
    body_hash: str = Field(max_length=64)
    job_id: str = Field(foreign_key="xsolla_review_jobs.id", index=True, max_length=64)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class CacheEntry(SQLModel, table=True):
    __tablename__ = "xsolla_cache_entries"

    request_hash: str = Field(primary_key=True, max_length=64)
    source_job_id: str = Field(foreign_key="xsolla_review_jobs.id", max_length=64)
    state: str = Field(default="running", max_length=16)
    findings: list[dict[str, object]] | None = Field(
        default=None,
        sa_column=Column(JSON_COLUMN, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class JobEvent(SQLModel, table=True):
    __tablename__ = "xsolla_job_events"

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="xsolla_review_jobs.id", index=True, max_length=64)
    sequence: int
    event_type: str = Field(max_length=16)
    payload: dict[str, object] = Field(sa_column=Column(JSON_COLUMN, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),
        Index("ix_job_events_job_sequence", "job_id", "sequence"),
    )
