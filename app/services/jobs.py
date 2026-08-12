import asyncio
import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.core.errors import ApiError
from app.db.models import CacheEntry, IdempotencyRecord, JobStatusValue, ReviewJob, utc_now
from app.diff.chunker import chunk_file_diffs
from app.diff.parser import DiffParseError, parse_unified_diff
from app.schemas import ReviewRequest
from app.services.events import append_event


@dataclass(slots=True)
class ParsedSubmission:
    request: ReviewRequest
    raw_body_hash: str
    request_hash: str
    input_bytes: int
    chunks: int


def parse_submission(raw_body: bytes, settings: Settings) -> ParsedSubmission:
    if len(raw_body) > settings.max_payload_bytes:
        raise ApiError(
            413,
            "payload_too_large",
            "The request payload exceeds the configured limit.",
        )
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApiError(400, "invalid_json", "The request body is not valid JSON.") from exc
    try:
        request = ReviewRequest.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(422, "invalid_diff", "The review request is not valid.") from exc
    try:
        files = parse_unified_diff(request.diff)
    except DiffParseError as exc:
        raise ApiError(
            422,
            "invalid_diff",
            "The supplied diff is not a valid unified diff.",
        ) from exc
    chunks = chunk_file_diffs(files, settings.chunk_bytes)
    canonical = json.dumps(
        {
            "diff": request.diff,
            "options": {
                "provider": request.options.provider.value,
                "maxFindings": request.options.max_findings,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return ParsedSubmission(
        request=request,
        raw_body_hash=hashlib.sha256(raw_body).hexdigest(),
        request_hash=hashlib.sha256(canonical).hexdigest(),
        input_bytes=len(request.diff.encode("utf-8")),
        chunks=len(chunks),
    )


async def create_or_reuse_job(
    session: AsyncSession,
    submission: ParsedSubmission,
    idempotency_key: str | None,
    submission_lock: asyncio.Lock,
) -> ReviewJob:
    async with submission_lock:
        if idempotency_key:
            existing = await session.get(IdempotencyRecord, idempotency_key)
            if existing:
                if existing.body_hash != submission.raw_body_hash:
                    raise ApiError(
                        409,
                        "idempotency_conflict",
                        "The idempotency key was already used with a different request body.",
                    )
                job = await session.get(ReviewJob, existing.job_id)
                if job is None:
                    raise ApiError(500, "internal", "The idempotency record is inconsistent.")
                return job

        cache = await session.get(CacheEntry, submission.request_hash)
        job = ReviewJob(
            diff=submission.request.diff,
            provider=submission.request.options.provider.value,
            max_findings=submission.request.options.max_findings,
            request_hash=submission.request_hash,
            input_bytes=submission.input_bytes,
            chunks=submission.chunks,
            cache_hit=cache is not None,
        )
        session.add(job)
        await session.flush()

        if cache is None:
            session.add(
                CacheEntry(
                    request_hash=submission.request_hash,
                    source_job_id=job.id,
                    state="running",
                )
            )
        if idempotency_key:
            session.add(
                IdempotencyRecord(
                    key=idempotency_key,
                    body_hash=submission.raw_body_hash,
                    job_id=job.id,
                )
            )
        await append_event(session, job.id, "status", {"status": "queued"})
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if idempotency_key:
                existing = await session.get(IdempotencyRecord, idempotency_key)
                if existing and existing.body_hash == submission.raw_body_hash:
                    existing_job = await session.get(ReviewJob, existing.job_id)
                    if existing_job:
                        return existing_job
            raise ApiError(500, "internal", "The review could not be queued.") from exc
        return job


async def recover_abandoned_jobs(session: AsyncSession) -> None:
    statement = select(ReviewJob).where(ReviewJob.status == JobStatusValue.RUNNING)
    jobs = list((await session.exec(statement)).all())
    for job in jobs:
        job.status = JobStatusValue.QUEUED
        job.updated_at = utc_now()
        await append_event(session, job.id, "status", {"status": "queued"})
    await session.commit()
