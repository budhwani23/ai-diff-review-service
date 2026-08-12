import asyncio
import math
import time
from collections import deque
from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import ApiError


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.timestamps: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def consume(self) -> None:
        async with self.lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds

            # Remove requests that are outside the rolling window.
            while self.timestamps and self.timestamps[0] <= cutoff:
                self.timestamps.popleft()

            # Allow up to `limit` requests inside the window.
            if len(self.timestamps) < self.limit:
                self.timestamps.append(now)
                return

            # Oldest request determines when another request can be accepted.
            oldest = self.timestamps[0]

            retry_after = max(
                1,
                math.ceil(
                    self.window_seconds - (now - oldest)
                ),
            )

            raise ApiError(
                429,
                "rate_limited",
                "The submission rate limit has been exceeded.",
                {"Retry-After": str(retry_after)},
            )


async def enforce_rate_limit(request: Request) -> None:
    await request.app.state.rate_limiter.consume()


RateLimitDep = Annotated[
    None,
    Depends(enforce_rate_limit),
]