"""Typed collector settings, read once from the environment (prefix ``COLLECTOR_``).

Every tunable lives here so the rest of the package has no magic numbers.
The database connection is owned by the shared ``db`` package (``MONGODB_URI``), not by the collector.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SAMPLES_DIR = BACKEND_DIR / "data" / "samples"
DEBUG_DIR = BACKEND_DIR / ".cache" / "collector"  # gitignored; raw captures only when enabled

BOOKING_BASE_URL = "https://www.booking.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HTTP_STRATEGY = "http_graphql"
BROWSER_STRATEGIES = ("browser_graphql", "browser_dom")
ALL_STRATEGIES = (HTTP_STRATEGY, *BROWSER_STRATEGIES)


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """All collector configuration. Build with :meth:`from_env`."""

    samples_dir: Path = SAMPLES_DIR
    debug_dir: Path = DEBUG_DIR
    save_raw: bool = False  # write raw response bodies to debug_dir (gitignored) for troubleshooting

    user_agent: str = DEFAULT_USER_AGENT
    accept_language: str = "en-GB,en;q=0.9"
    booking_lang: str = "en-gb"

    # Politeness / resilience
    request_delay_s: float = 1.5  # minimum pause between requests to Booking
    request_jitter_s: float = 1.5  # random extra pause in [0, jitter] -> 1.5-3.0 s gaps
    http_timeout_s: float = 30.0
    browser_timeout_s: float = 60.0
    challenge_timeout_s: float = 45.0  # how long to wait for the WAF JS challenge to resolve
    retry_attempts: int = 3
    retry_base_delay_s: float = 2.0
    retry_max_delay_s: float = 60.0
    breaker_failure_threshold: int = 3
    breaker_recovery_s: float = 300.0

    # Paging
    page_size: int = 25  # Booking's GraphQL caps `limit` at 25
    watermark_overlap_days: int = 1  # Booking dates are day-granular: re-read one extra day
    backfill_max_pages: int = 200  # pages per property when no watermark exists / resuming a backfill
    full_max_pages: int = 1000  # hard safety cap per property in --full mode
    backfill_tolerance: int = 25  # stored count this close to Booking's total counts as "complete"

    # Data-quality gates
    max_reject_ratio: float = 0.2  # a page with more rejected records than this is "degraded"
    stale_run_after_s: int = 3600  # 'running' rows older than this are marked failed (crashed run)

    strategies: tuple[str, ...] = field(default=ALL_STRATEGIES)
    headless: bool = True
    probe_headline_score: bool = True  # use the browser (if installed) to capture Booking's headline score

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables, falling back to defaults."""
        strategies = tuple(
            s.strip()
            for s in _env_str("COLLECTOR_STRATEGIES", ",".join(ALL_STRATEGIES)).split(",")
            if s.strip()
        )
        unknown = set(strategies) - set(ALL_STRATEGIES)
        if unknown or not strategies:
            raise ValueError(f"invalid COLLECTOR_STRATEGIES: {sorted(unknown) or 'empty'}")
        return cls(
            save_raw=_env_bool("COLLECTOR_SAVE_RAW", False),
            user_agent=_env_str("COLLECTOR_USER_AGENT", DEFAULT_USER_AGENT),
            request_delay_s=_env_float("COLLECTOR_REQUEST_DELAY_S", cls.request_delay_s),
            request_jitter_s=_env_float("COLLECTOR_REQUEST_JITTER_S", cls.request_jitter_s),
            http_timeout_s=_env_float("COLLECTOR_HTTP_TIMEOUT_S", cls.http_timeout_s),
            browser_timeout_s=_env_float("COLLECTOR_BROWSER_TIMEOUT_S", cls.browser_timeout_s),
            retry_attempts=_env_int("COLLECTOR_RETRY_ATTEMPTS", cls.retry_attempts),
            breaker_failure_threshold=_env_int("COLLECTOR_BREAKER_THRESHOLD", cls.breaker_failure_threshold),
            backfill_max_pages=_env_int("COLLECTOR_BACKFILL_MAX_PAGES", cls.backfill_max_pages),
            max_reject_ratio=_env_float("COLLECTOR_MAX_REJECT_RATIO", cls.max_reject_ratio),
            strategies=strategies,
            headless=_env_bool("COLLECTOR_HEADLESS", True),
            probe_headline_score=_env_bool("COLLECTOR_PROBE_HEADLINE_SCORE", True),
        )
