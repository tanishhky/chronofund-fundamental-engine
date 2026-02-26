"""
client.py – Low-level HTTP client for SEC EDGAR.

Wraps requests with:
- User-Agent injection (required by SEC)
- Rate limiting
- Retry with exponential backoff
- Response caching via diskcache

Fix #5: Each EdgarClient instance owns its own requests.Session keyed to
its user_agent. This allows multiple concurrent engine instances with
different configurations in the same process without cross-contamination.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

from fundamental_engine.config import EngineConfig
from fundamental_engine.utils.hashing import request_cache_key
from fundamental_engine.utils.io import ResponseCache
from fundamental_engine.utils.rate_limit import SECRateLimiter
from fundamental_engine.utils.retry import check_response, with_retry

logger = logging.getLogger(__name__)

# Module-level cache keyed by user_agent so distinct configs reuse connections
# but never share a session with a different User-Agent.
_SESSION_POOL: dict[str, requests.Session] = {}


def _get_session(user_agent: str) -> requests.Session:
    """Return a per-user-agent requests.Session (cached at module level)."""
    if user_agent not in _SESSION_POOL:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        _SESSION_POOL[user_agent] = session
        logger.debug("Created new HTTP session for user_agent=%r", user_agent)
    return _SESSION_POOL[user_agent]


class EdgarClient:
    """
    SEC EDGAR HTTP client with rate limiting, caching, and retry logic.

    Each instance gets its own rate limiter and cache, but shares the HTTP
    session with other instances that use the same user_agent string.

    Parameters
    ----------
    config:
        Engine configuration.
    """

    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._rate_limiter = SECRateLimiter(rps=config.sec_rate_limit_rps)
        self._cache = ResponseCache(config.cache_dir / "edgar_http")
        self._session = _get_session(config.user_agent)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """
        Fetch a JSON endpoint from EDGAR, returning parsed dict.

        Results are cached indefinitely (EDGAR historical data is immutable).

        Parameters
        ----------
        url:
            Full URL to fetch.
        params:
            Optional query string parameters.

        Returns
        -------
        Parsed JSON object (dict or list).
        """
        cache_key = request_cache_key(url, params)

        if cache_key in self._cache:
            logger.debug("Cache hit: %s", url)
            return self._cache.get(cache_key)

        @with_retry(max_attempts=5, min_wait=2.0, max_wait=60.0)
        def _fetch() -> Any:
            self._rate_limiter.acquire()
            resp = self._session.get(url, params=params, timeout=30)
            check_response(resp)
            return resp.json()

        data = _fetch()
        self._cache.set(cache_key, data)
        logger.debug("Fetched and cached: %s", url)
        return data

    def get_raw(self, url: str) -> bytes:
        """
        Fetch raw bytes from EDGAR (e.g. for XBRL filing documents).

        Parameters
        ----------
        url:
            Full URL to fetch.

        Returns
        -------
        Raw bytes of response body.
        """
        cache_key = request_cache_key(url)

        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit (raw): %s", url)
            return cached  # type: ignore[return-value]

        @with_retry(max_attempts=5, min_wait=2.0, max_wait=60.0)
        def _fetch() -> bytes:
            self._rate_limiter.acquire()
            resp = self._session.get(url, timeout=60)
            check_response(resp)
            return resp.content

        data = _fetch()
        self._cache.set(cache_key, data)
        return data  # type: ignore[return-value]

    def close(self) -> None:
        """Close the underlying response cache (session is shared, not closed)."""
        self._cache.close()

    def __enter__(self) -> "EdgarClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
