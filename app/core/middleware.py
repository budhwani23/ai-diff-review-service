import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings
from app.core.errors import error_response


class ContractMiddleware:
    """Enforce authentication and payload size even before route matching."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        headers = {key.lower(): value for key, value in scope.get("headers", [])}

        if path == "/v1" or path.startswith("/v1/"):
            raw_authorization = headers.get(b"authorization", b"").decode("latin-1")
            expected = f"Bearer {self.settings.bearer_token}"
            if not secrets.compare_digest(raw_authorization, expected):
                response = error_response(401, "unauthorized", "A valid bearer token is required.")
                await response(scope, receive, send)
                return

        if path == "/v1/reviews" and scope.get("method") == "POST":
            raw_length = headers.get(b"content-length")
            if raw_length is not None:
                try:
                    if int(raw_length) > self.settings.max_payload_bytes:
                        response = error_response(
                            413,
                            "payload_too_large",
                            "The request payload exceeds the configured limit.",
                        )
                        await response(scope, receive, send)
                        return
                except ValueError:
                    pass

        await self.app(scope, receive, send)
