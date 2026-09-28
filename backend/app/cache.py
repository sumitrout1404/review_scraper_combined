"""Short-lived in-process cache for the read-only API.

The dataset changes once a night (the cron collection run), so repeating the same
aggregation for every dashboard visit is wasted work. Each endpoint costs several
round-trips to Atlas -- mostly network latency -- and one dashboard page fires
half a dozen endpoints, so caching whole responses is the cheapest large win.

Scope and safety:
    * only successful ``GET`` responses to ``/api/*`` are cached, never ``/api/cron/*``
      (it writes) and never streaming responses such as the CSV export;
    * entries expire after ``CACHE_MAX_AGE`` seconds, the same value already sent in
      the ``Cache-Control`` header, so a cached body is never staler than the header
      promises;
    * the cache is per process. On serverless each instance keeps its own, which is
      fine: it is an optimisation, never a source of truth.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

MAX_ENTRIES = 256
MAX_BODY_BYTES = 2 * 1024 * 1024  # skip anything unusually large rather than hoard memory
CACHEABLE_PREFIX = "/api/"
# /api/cron writes; the CSV export streams and can be arbitrarily large.
UNCACHEABLE_PREFIXES = ("/api/cron", "/api/reviews/export")


@dataclass(frozen=True)
class CachedResponse:
    """A response body plus what is needed to replay it faithfully.

    ``content_type`` is taken from the response *header* rather than from
    ``media_type``: by the time middleware sees the response it is a streaming
    wrapper whose ``media_type`` is unset, so replaying that would drop the
    ``Content-Type`` and leave clients guessing at the format.
    """

    status_code: int
    body: bytes
    content_type: str | None
    expires_at: float


class ResponseCache:
    """Bounded TTL cache with least-recently-used eviction."""

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, CachedResponse] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str, now: float | None = None) -> CachedResponse | None:
        now = time.monotonic() if now is None else now
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry

    def set(self, key: str, entry: CachedResponse) -> None:
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


def is_cacheable_path(path: str) -> bool:
    """True for read endpoints; the cron endpoint writes and must always run."""
    return path.startswith(CACHEABLE_PREFIX) and not path.startswith(UNCACHEABLE_PREFIXES)


def cache_key(path: str, query: str) -> str:
    """Identity of a response: the path plus its query string, order-insensitive."""
    normalised = "&".join(sorted(query.split("&"))) if query else ""
    return f"{path}?{normalised}"
