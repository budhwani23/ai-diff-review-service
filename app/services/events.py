from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import JobEvent


async def append_event(
    session: AsyncSession,
    job_id: str,
    event_type: str,
    payload: dict[str, object],
) -> JobEvent:
    statement = select(func.coalesce(func.max(JobEvent.sequence), 0)).where(
        JobEvent.job_id == job_id
    )
    sequence = int((await session.exec(statement)).one()) + 1
    event = JobEvent(
        job_id=job_id,
        sequence=sequence,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return event


async def list_events_after(
    session: AsyncSession,
    job_id: str,
    sequence: int,
) -> list[JobEvent]:
    statement = (
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.sequence > sequence)
        .order_by(col(JobEvent.sequence))
    )
    return list((await session.exec(statement)).all())
