import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.public import router as public_router
from app.api.reviews import router as reviews_router
from app.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import ContractMiddleware
from app.core.rate_limit import TokenBucket
from app.db.migrate import create_tables
from app.db.session import create_engine, create_session_factory
from app.providers.base import ReviewProvider
from app.providers.llm import CerebrasProvider
from app.providers.mock import MockProvider
from app.services.jobs import recover_abandoned_jobs
from app.workers.review_worker import worker_loop


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        app.state.started_at = time.monotonic()
        app.state.settings = app_settings
        app.state.engine = create_engine(app_settings)
        app.state.session_factory = create_session_factory(app.state.engine)
        app.state.rate_limiter = TokenBucket(
            capacity=app_settings.rate_limit_per_minute,
            refill_per_second=app_settings.rate_limit_per_minute / 60,
        )
        app.state.submission_lock = asyncio.Lock()
        app.state.claim_lock = asyncio.Lock()
        app.state.stop_event = asyncio.Event()

        await create_tables(app.state.engine)
        async with app.state.session_factory() as session:
            await recover_abandoned_jobs(session)

        mock_provider = MockProvider()
        cerebras_provider = CerebrasProvider(app_settings)

        def provider_factory(name: str) -> ReviewProvider:
            if name == "mock":
                return mock_provider
            if name == "llm":
                return cerebras_provider
            raise ValueError(f"Unsupported provider: {name}")

        workers = [
            asyncio.create_task(
                worker_loop(
                    number,
                    app.state.session_factory,
                    app_settings,
                    provider_factory,
                    app.state.stop_event,
                    app.state.claim_lock,
                ),
                name=f"review-worker-{number}",
            )
            for number in range(1, app_settings.max_concurrent_jobs + 1)
        ]
        try:
            yield
        finally:
            app.state.stop_event.set()
            await asyncio.gather(*workers, return_exceptions=True)
            await app.state.engine.dispose()

    app = FastAPI(
        title="AI Diff Review Service",
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.add_middleware(ContractMiddleware, settings=app_settings)
    install_error_handlers(app)
    app.include_router(public_router)
    app.include_router(reviews_router)
    return app


app = create_app()
