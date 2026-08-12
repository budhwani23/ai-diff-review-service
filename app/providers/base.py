from typing import Protocol

from app.diff.chunker import ReviewChunk
from app.schemas import Finding


class ProviderError(RuntimeError):
    pass


class ReviewProvider(Protocol):
    async def review(self, chunks: list[ReviewChunk]) -> list[Finding]: ...
