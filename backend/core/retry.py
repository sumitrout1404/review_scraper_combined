"""Retry with exponential backoff and full jitter.

Only errors the caller classifies as retryable are retried; ``RetryableError``
can carry a server-provided ``retry_after`` (e.g. from a 429 response), which
takes precedence over the computed backoff.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """A transient failure worth retrying (timeout, 429, 5xx, bot challenge...)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def default_is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (RetryableError, TimeoutError, ConnectionError))


def backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    retry_after: float | None = None,
) -> float:
    """Delay before retry number ``attempt`` (1-based)."""
    if retry_after is not None and retry_after >= 0:
        return min(retry_after, max_delay)
    ceiling = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)  # noqa: S311 - jitter, not security


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    is_retryable: Callable[[BaseException], bool] = default_is_retryable,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Call ``fn`` up to ``attempts`` times, sleeping between retryable failures."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == attempts or not is_retryable(exc):
                raise
            delay = backoff_delay(
                attempt, base_delay, max_delay, getattr(exc, "retry_after", None)
            )
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            else:
                logger.info("attempt %d/%d failed (%s); retrying in %.1fs",
                            attempt, attempts, type(exc).__name__, delay)
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
