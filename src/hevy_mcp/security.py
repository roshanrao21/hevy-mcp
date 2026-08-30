import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Settings
from .context import request_hevy_api_key

logger = logging.getLogger(__name__)


def require_confirmation(confirmation: str) -> None:
    if confirmation != "CONFIRM":
        raise ValueError(
            'This mutation requires confirmation="CONFIRM". Review the complete payload first.'
        )


@dataclass
class Bucket:
    timestamps: deque[float]


class InMemoryRateLimiter:
    def __init__(self, requests: int, window_seconds: int):
        self.requests = requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, Bucket] = defaultdict(lambda: Bucket(deque()))

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key].timestamps
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.requests:
            return False
        bucket.append(now)
        return True


class SecurityMiddleware:
    """Authenticate the MCP endpoint, inject a per-request Hevy key, and rate-limit callers."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings
        self.rate_limiter = InMemoryRateLimiter(
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in {"/health"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        supplied_gateway_token = (
            authorization.removeprefix("Bearer ").strip()
            if authorization.startswith("Bearer ")
            else ""
        )

        expected = self.settings.mcp_access_token
        if expected and not hmac.compare_digest(supplied_gateway_token, expected):
            await JSONResponse({"error": "unauthorized"}, status_code=401)(
                scope, receive, send
            )
            return

        hevy_key = self.settings.hevy_api_key
        if self.settings.allow_header_hevy_key:
            hevy_key = headers.get("x-hevy-api-key") or hevy_key

        if not hevy_key:
            await JSONResponse(
                {
                    "error": "missing_hevy_api_key",
                    "message": "Send X-Hevy-API-Key or configure HEVY_API_KEY.",
                },
                status_code=401,
            )(scope, receive, send)
            return

        caller = hashlib.sha256(
            f"{scope.get('client')}:{supplied_gateway_token}:{hevy_key}".encode()
        ).hexdigest()
        if not self.rate_limiter.allow(caller):
            await JSONResponse({"error": "rate_limited"}, status_code=429)(
                scope, receive, send
            )
            return

        token = request_hevy_api_key.set(hevy_key)
        try:
            await self.app(scope, receive, send)
        finally:
            request_hevy_api_key.reset(token)
