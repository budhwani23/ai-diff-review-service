from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("postgresql+psycopg"):
        connect_args["prepare_threshold"] = None
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=connect_args,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
