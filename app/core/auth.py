import secrets
from typing import Annotated

from fastapi import Header, Request

from app.core.errors import ApiError


async def require_bearer_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = f"Bearer {request.app.state.settings.bearer_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise ApiError(401, "unauthorized", "A valid bearer token is required.")
