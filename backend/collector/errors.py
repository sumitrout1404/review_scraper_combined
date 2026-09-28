"""Exception hierarchy used to drive retry, circuit-breaker and fallback decisions.

* ``TransientFetchError`` (a ``RetryableError``) – timeouts, 429, 5xx: retried with backoff.
* ``BlockedError`` – bot challenge / access denied: not retried on the same strategy,
  counts as a breaker failure and falls through to the next strategy.
* ``ResponseShapeError`` – the payload no longer looks like what the parser expects
  (markup / API drift). Falls through to the next strategy; the run is marked degraded.
* ``PageQualityError`` – parsed fine but failed the data-quality gate (too many rejects).
"""

from __future__ import annotations

from core.retry import RetryableError


class CollectorError(Exception):
    """Base class for collector failures."""


class TransientFetchError(RetryableError, CollectorError):
    """Temporary failure worth retrying (timeout, connection reset, 429, 5xx)."""


class FetchError(CollectorError):
    """Permanent (non-retryable) fetch failure for this strategy, e.g. an unexpected 4xx."""


class BlockedError(FetchError):
    """Booking served a bot challenge or denied access."""


class ResponseShapeError(FetchError):
    """The response parsed, but not into the structure we expect (page/API change)."""


class PageQualityError(CollectorError):
    """A page failed the data-quality gate and must not be written."""


class StrategyUnavailableError(CollectorError):
    """A strategy cannot run in this environment (e.g. Playwright not installed)."""
