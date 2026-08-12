from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

from app.db import models  # noqa: F401


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
