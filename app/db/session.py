from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict[str, object] = {}

    is_postgres = settings.database_url.startswith(
        "postgresql+psycopg"
    )

    if is_postgres:
        # Required when using transaction-pooling proxies such as PgBouncer.
        connect_args["prepare_threshold"] = None

    engine_options: dict[str, object] = {
        "echo": False,
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }

    if is_postgres:
        engine_options.update(
            {
                "pool_size": 10,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 300,
            }
        )

    return create_async_engine(
        settings.database_url,
        **engine_options,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[
    AsyncSession,
    Depends(get_session),
]