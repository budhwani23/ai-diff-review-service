import time

from fastapi import APIRouter, Request

from app.schemas import HealthResponse, LimitsResponse, SpecResponse

router = APIRouter(tags=["service"])


@router.get("/health")
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        uptimeSeconds=max(0, time.monotonic() - request.app.state.started_at),
    )


@router.get("/spec")
async def spec(request: Request) -> SpecResponse:
    settings = request.app.state.settings
    return SpecResponse(
        specVersion="1.0",
        providers=["mock", "llm"],
        limits=LimitsResponse(
            maxPayloadBytes=settings.max_payload_bytes,
            chunkBytes=settings.chunk_bytes,
            maxConcurrentJobs=settings.max_concurrent_jobs,
            rateLimitPerMinute=settings.rate_limit_per_minute,
        ),
    )
