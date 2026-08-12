import asyncio
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.auth import require_bearer_token
from app.core.errors import ApiError
from app.core.rate_limit import RateLimitDep
from app.db.models import JobStatusValue, ReviewJob
from app.db.session import SessionDep
from app.schemas import ErrorDetail, JobResponse, JobStatus, SubmitResponse, Usage
from app.services.events import list_events_after
from app.services.jobs import create_or_reuse_job, parse_submission

router = APIRouter(
    prefix="/v1/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_bearer_token)],
)


def _job_response(job: ReviewJob) -> JobResponse:
    findings = job.findings if job.status == JobStatusValue.DONE else None
    error = None
    if job.status == JobStatusValue.FAILED:
        error = ErrorDetail(
            code=job.error_code or "internal",
            message=job.error_message or "Review processing failed.",
        )
    return JobResponse(
        jobId=job.id,
        status=JobStatus(job.status),
        findings=findings,
        usage=Usage(inputBytes=job.input_bytes, chunks=job.chunks, cacheHit=job.cache_hit),
        error=error,
    )


@router.post("", status_code=202)
async def submit_review(
    request: Request,
    session: SessionDep,
    _rate_limit: RateLimitDep,
    idempotency_key: Annotated[str | None, Header(max_length=255)] = None,
) -> SubmitResponse:
    raw_body = await request.body()
    submission = parse_submission(raw_body, request.app.state.settings)
    job = await create_or_reuse_job(
        session,
        submission,
        idempotency_key,
        request.app.state.submission_lock,
    )
    return SubmitResponse(jobId=job.id, status="queued")


@router.get("/{job_id}", response_model_exclude_none=True)
async def get_review(job_id: str, session: SessionDep) -> JobResponse:
    job = await session.get(ReviewJob, job_id)
    if job is None:
        raise ApiError(404, "not_found", "The requested review job was not found.")
    return _job_response(job)


@router.get("/{job_id}/stream", response_class=EventSourceResponse)
async def stream_review(
    job_id: str,
    request: Request,
    session: SessionDep,
    last_event_id: Annotated[str | None, Header()] = None,
) -> AsyncIterable[ServerSentEvent]:
    job = await session.get(ReviewJob, job_id)
    if job is None:
        raise ApiError(404, "not_found", "The requested review job was not found.")

    try:
        sequence = max(0, int(last_event_id or "0"))
    except ValueError:
        sequence = 0

    while True:
        events = await list_events_after(session, job_id, sequence)
        for event in events:
            sequence = event.sequence
            yield ServerSentEvent(
                data=event.payload,
                event=event.event_type,
                id=str(event.sequence),
            )
            if event.event_type == "done":
                return
            if event.event_type == "status" and event.payload.get("status") == "failed":
                return
        await session.rollback()
        await session.refresh(job)
        if job.status == JobStatusValue.FAILED and not events:
            return
        if await request.is_disconnected():
            return
        await asyncio.sleep(request.app.state.settings.worker_poll_seconds)
