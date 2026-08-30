import asyncio
import logging
from typing import Any

import httpx

from .errors import AuthenticationError, UpstreamError

logger = logging.getLogger(__name__)


class HevyClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float):
        if not api_key:
            raise AuthenticationError("A Hevy API key is required.")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "api-key": api_key,
                "Accept": "application/json",
                "User-Agent": "hevy-mcp/0.1.0",
            },
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retry_safe: bool = False,
    ) -> dict[str, Any]:
        attempts = 3 if retry_safe else 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = await self._client.request(method, path, params=params, json=json)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                raise UpstreamError(
                    "Hevy API could not be reached.",
                    retryable=retry_safe,
                ) from exc

            if response.status_code in {429, 502, 503, 504} and attempt + 1 < attempts:
                await asyncio.sleep(0.25 * (2**attempt))
                continue

            if response.status_code in {401, 403}:
                raise AuthenticationError(
                    "Hevy rejected the API key or the account lacks API access."
                )

            if response.is_error:
                detail = response.text[:500]
                logger.warning(
                    "Hevy API error status=%s path=%s response=%s",
                    response.status_code,
                    path,
                    detail,
                )
                raise UpstreamError(
                    f"Hevy API returned HTTP {response.status_code}.",
                    status_code=response.status_code,
                    retryable=response.status_code in {429, 502, 503, 504},
                )

            if response.status_code == 204 or not response.content:
                return {"success": True}

            data = response.json()
            return data if isinstance(data, dict) else {"items": data}

        raise UpstreamError("Hevy API request failed.", retryable=True) from last_error

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.request("GET", path, params=params, retry_safe=True)

    async def post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", path, json=json, retry_safe=False)

    async def put(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PUT", path, json=json, retry_safe=False)
