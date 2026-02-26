"""
retry.py – Retry decorator with exponential backoff for HTTP requests.

Uses tenacity under the hood. Configured specifically for SEC EDGAR
429 (too many requests) and transient 5xx errors.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from fundamental_engine.exceptions import RateLimitError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class _RetryableHTTPError(Exception):
    """Wrapper used to signal tenacity that a retry should occur."""

    def __init__(self, response: requests.Response) -> None:
        self.response = response
        super().__init__(f"HTTP {response.status_code}: {response.url}")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _RetryableHTTPError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    return False


def with_retry(
    max_attempts: int = 5,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
) -> Callable[[F], F]:
    """
    Decorator factory that applies tenacity retry logic.

    Parameters
    ----------
    max_attempts:
        Maximum number of total attempts (including first).
    min_wait:
        Minimum wait between retries in seconds.
    max_wait:
        Maximum wait between retries in seconds.

    Usage
    -----
    >>> @with_retry(max_attempts=5)
    ... def fetch_something() -> dict:
    ...     ...
    """
    return retry(  # type: ignore[return-value]
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        stop=stop_after_attempt(max_attempts),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def check_response(response: requests.Response) -> requests.Response:
    """
    Raise ``_RetryableHTTPError`` for retryable status codes,
    raise ``RateLimitError`` if retries exhausted, or return response.

    Call this inside any function decorated with ``@with_retry``.

    Parameters
    ----------
    response:
        The ``requests.Response`` object to inspect.

    Returns
    -------
    requests.Response (same object, if status is OK)
    """
    if response.status_code == 429:
        raise _RetryableHTTPError(response)
    if response.status_code in {500, 502, 503, 504}:
        raise _RetryableHTTPError(response)
    response.raise_for_status()
    return response
