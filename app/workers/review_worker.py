import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.db.models import CacheEntry, JobStatusValue, ReviewJob, utc_now
from app.diff.chunker import chunk_file_diffs
from app.diff.parser import parse_unified_diff
from app.providers.base import ProviderError, ReviewProvider
from app.schemas import Finding, Usage
from app.services.events import append_event

LOGGER = logging.getLogger(__name__)


def _ordered_findings(findings: list[Finding], maximum: int) -> list[Finding]:
    deduplicated: dict[str, Finding] = {finding.id: finding for finding in findings}
    ordered = sorted(
        deduplicated.values(),
        key=lambda finding: (finding.path, finding.line, finding.rule_id),
    )
    return ordered[:maximum]


async def _claim_job(session: AsyncSession) -> ReviewJob | None:
    statement = (
        select(ReviewJob)
        .where(ReviewJob.status == JobStatusValue.QUEUED)
        .order_by(col(ReviewJob.created_at))
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = (await session.exec(statement)).first()
    if job is None:
        await session.rollback()
        return None
    job.status = JobStatusValue.RUNNING
    job.started_at = utc_now()
    job.updated_at = utc_now()
    await append_event(session, job.id, "status", {"status": "running"})
    await session.commit()
    return job


async def _finish_from_cache(session: AsyncSession, job: ReviewJob, cache: CacheEntry) -> bool:
    if cache.state != "done" or cache.findings is None:
        return False
    findings = [Finding.model_validate(item) for item in cache.findings]
    limited = _ordered_findings(findings, job.max_findings)
    job.findings = [finding.model_dump(by_alias=True) for finding in limited]
    job.status = JobStatusValue.DONE
    job.completed_at = utc_now()
    job.updated_at = utc_now()
    for finding in limited:
        await append_event(session, job.id, "finding", finding.model_dump(by_alias=True))
    await append_event(session, job.id, "status", {"status": "done"})
    usage = Usage(inputBytes=job.input_bytes, chunks=job.chunks, cacheHit=True)
    await append_event(
        session,
        job.id,
        "done",
        {"total": len(limited), "usage": usage.model_dump(by_alias=True)},
    )
    await session.commit()
    return True


async def _process_job(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    provider_factory: Callable[[str], ReviewProvider],
    job: ReviewJob,
) -> None:
    try:
        if job.cache_hit:
            while True:
                async with session_factory() as session:
                    current = await session.get(ReviewJob, job.id)
                    cache = await session.get(CacheEntry, job.request_hash)
                    if current is None or cache is None:
                        raise ProviderError("Cached review state is missing.")
                    if await _finish_from_cache(session, current, cache):
                        return
                    if cache.state == "failed":
                        raise ProviderError("The source review for this cache entry failed.")
                await asyncio.sleep(settings.worker_poll_seconds)

        files = parse_unified_diff(job.diff)
        chunks = chunk_file_diffs(files, settings.chunk_bytes)
        if settings.mock_processing_delay_ms and job.provider == "mock":
            await asyncio.sleep(settings.mock_processing_delay_ms / 1000)
        provider = provider_factory(job.provider)
        full_findings = await provider.review(chunks)
        ordered_full = _ordered_findings(full_findings, 10_000_000)
        limited = ordered_full[: job.max_findings]

        async with session_factory() as session:
            current = await session.get(ReviewJob, job.id)
            cache = await session.get(CacheEntry, job.request_hash)
            if current is None or cache is None:
                raise ProviderError("Review persistence state is missing.")
            current.findings = [finding.model_dump(by_alias=True) for finding in limited]
            current.status = JobStatusValue.DONE
            current.completed_at = utc_now()
            current.updated_at = utc_now()
            cache.findings = [finding.model_dump(by_alias=True) for finding in ordered_full]
            cache.state = "done"
            cache.updated_at = utc_now()
            for finding in limited:
                await append_event(
                    session,
                    current.id,
                    "finding",
                    finding.model_dump(by_alias=True),
                )
            await append_event(session, current.id, "status", {"status": "done"})
            usage = Usage(
                inputBytes=current.input_bytes,
                chunks=current.chunks,
                cacheHit=current.cache_hit,
            )
            await append_event(
                session,
                current.id,
                "done",
                {"total": len(limited), "usage": usage.model_dump(by_alias=True)},
            )
            await session.commit()
    except Exception as exc:
        LOGGER.exception("Review job %s failed", job.id)
        async with session_factory() as session:
            current = await session.get(ReviewJob, job.id)
            cache = await session.get(CacheEntry, job.request_hash)
            if current is not None:
                current.status = JobStatusValue.FAILED
                current.error_code = "internal"
                current.error_message = str(exc)[:1000] or "Review processing failed."
                current.completed_at = utc_now()
                current.updated_at = utc_now()
                await append_event(
                    session,
                    current.id,
                    "status",
                    {"status": "failed", "error": current.error_message},
                )
            if cache is not None and cache.source_job_id == job.id:
                cache.state = "failed"
                cache.updated_at = utc_now()
            await session.commit()


async def worker_loop(
    worker_number: int,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    provider_factory: Callable[[str], ReviewProvider],
    stop_event: asyncio.Event,
    claim_lock: asyncio.Lock,
) -> None:
    LOGGER.info("Review worker %s started", worker_number)
    while not stop_event.is_set():
        try:
            async with claim_lock:
                async with session_factory() as session:
                    job = await _claim_job(session)
            if job is None:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.worker_poll_seconds)
                except TimeoutError:
                    pass
                continue
            await _process_job(session_factory, settings, provider_factory, job)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Review worker %s encountered an error", worker_number)
            await asyncio.sleep(settings.worker_poll_seconds)
