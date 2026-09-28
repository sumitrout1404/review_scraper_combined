"""Strategy interface and shared politeness throttle."""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from collector.models import PropertyMeta, RawPage
from collector.properties import Property

logger = logging.getLogger(__name__)


class Throttle:
    """Enforces a minimum, jittered gap between consecutive requests to Booking.

    One instance is shared by every strategy so fallbacks never burst the site.
    """

    def __init__(
        self,
        min_interval_s: float,
        jitter_s: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = max(0.0, min_interval_s)
        self._jitter = max(0.0, jitter_s)
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        """Block until the next request is allowed, then mark it as sent."""
        if self._last is not None:
            gap = self._min_interval + random.uniform(0, self._jitter)  # noqa: S311 - not crypto
            remaining = gap - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


class ReviewSource(ABC):
    """A pluggable way of fetching one page of reviews (newest first) for a property."""

    #: stable identifier, stored in ``scrape_runs.method``
    name: str = "abstract"
    #: reviews per page this strategy returns when more are available
    page_size: int = 25

    @abstractmethod
    def fetch_page(self, prop: Property, offset: int) -> RawPage:
        """Fetch and parse the page starting at ``offset`` (0-based, newest first).

        Raises ``TransientFetchError`` (retryable), ``BlockedError``,
        ``ResponseShapeError`` or ``FetchError``.
        """

    def fetch_meta(self, prop: Property) -> PropertyMeta:
        """Booking's headline score / count for the property, if this strategy can see it."""
        return PropertyMeta()

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release network/browser resources."""
