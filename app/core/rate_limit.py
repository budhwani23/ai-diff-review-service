import asyncio
import math
import time
from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import ApiError


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self.capacity = float(capacity)
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()

    async def consume(self) -> None:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
            self.updated_at = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            retry_after = max(1, math.ceil((1 - self.tokens) / self.refill_per_second))
            raise ApiError(
                429,
                "rate_limited",
                "The submission rate limit has been exceeded.",
                {"Retry-After": str(retry_after)},
            )


async def enforce_rate_limit(request: Request) -> None:
    await request.app.state.rate_limiter.consume()


RateLimitDep = Annotated[None, Depends(enforce_rate_limit)]
