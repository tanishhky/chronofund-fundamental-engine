"""
rate_limit.py – SEC-compliant rate limiter (maximum 10 RPS per SEC policy).

Uses a token bucket algorithm to distribute requests evenly over time.
Thread-safe via threading.Lock.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

from fundamental_engine.utils.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., object])


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter.

    Parameters
    ----------
    rate:
        Maximum number of tokens (requests) per second.
    burst:
        Maximum burst size (tokens that can accumulate). Defaults to `rate`.
    """

    def __init__(self, rate: float, burst: float | None = None) -> None:
        if rate <= 0:
            raise ValueError(f"Rate must be positive, got {rate}")
        self._rate = rate
        self._burst = burst if burst is not None else rate
        self._tokens = self._burst
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, n: float = 1.0) -> None:
        """
        Block until ``n`` tokens are available, then consume them.

        Parameters
        ----------
        n:
            Number of tokens to consume (default 1).
        """
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return
                # Calculate sleep time to accumulate needed tokens
                sleep_for = (n - self._tokens) / self._rate

            time.sleep(sleep_for)
            logger.debug("Rate limiter sleeping %.3fs to respect %s RPS limit", sleep_for, self._rate)


class SECRateLimiter(TokenBucketRateLimiter):
    """
    Pre-configured rate limiter for SEC EDGAR.

    SEC requires a maximum of 10 requests per second. We default to 8
    to provide a safety margin and avoid 429 errors.

    Parameters
    ----------
    rps:
        Requests per second. Must be <= 10 (SEC hard limit).
    """

    def __init__(self, rps: float = 8.0) -> None:
        if rps > 10:
            raise ValueError(
                f"SEC EDGAR rate limit is 10 RPS maximum. Got {rps}. "
                "See: https://www.sec.gov/developer"
            )
        super().__init__(rate=rps, burst=rps)
        logger.info("SEC rate limiter configured at %.1f RPS", rps)
