import time
from typing import Any

import httpx

from fin_analyst.config import get_settings

_BASE_URL = "https://serpapi.com/search"


class SerpApiError(Exception):
    def __init__(self, message: str, params: dict[str, Any]):
        super().__init__(message)
        self.params = params


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: dict[str, Any], ttl_seconds: int):
        self.value = value
        self.expires_at = time.monotonic() + ttl_seconds


class SerpApiClient:
    """Thin async wrapper around SerpApi's /search endpoint with a TTL cache.

    Every engine (google_finance, google_finance_markets, google_news, google web
    search) is reached through this one client so caching, retries, and cost/latency
    accounting (see docs/07-cost-latency-strategy.md) live in exactly one place.
    """

    def __init__(self, api_key: str | None = None, ttl_seconds: int | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.serpapi_key
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.serpapi_cache_ttl_seconds
        self._cache: dict[tuple, _CacheEntry] = {}

    def _cache_key(self, params: dict[str, Any]) -> tuple:
        return tuple(sorted((k, v) for k, v in params.items() if k != "api_key"))

    async def search(self, engine: str, **params: Any) -> dict[str, Any]:
        query = {"engine": engine, "api_key": self._api_key, **params}
        key = self._cache_key(query)

        cached = self._cache.get(key)
        if cached is not None and cached.expires_at > time.monotonic():
            return cached.value

        async with httpx.AsyncClient(timeout=30.0) as client:
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    resp = await client.get(_BASE_URL, params=query)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
                    continue
            else:
                raise SerpApiError(f"SerpApi request failed after retries: {last_error}", query)

        if "error" in data:
            raise SerpApiError(str(data["error"]), query)

        self._cache[key] = _CacheEntry(data, self._ttl)
        return data


_client: SerpApiClient | None = None


def get_serpapi_client() -> SerpApiClient:
    global _client
    if _client is None:
        _client = SerpApiClient()
    return _client
