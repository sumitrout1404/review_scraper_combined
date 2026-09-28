"""Typed runtime settings for the API, read once from environment variables.

Database selection (``DATABASE_URL`` / ``POSTGRES_URL`` for Postgres, else ``REVIEWS_DB_PATH``
for SQLite, default ``backend/data/reviews.db``) is handled by the shared ``db`` package.

Locally, ``backend/.env`` is loaded when python-dotenv is installed (it is a dev dependency,
not a runtime one); real environment variables always win. ``uvicorn --env-file .env`` works too.

Environment variables
---------------------
CORS_ORIGINS           Comma-separated allowlist, or "*" (default: the local Vite dev server).
ENV                    "production" disables OpenAPI docs and enables HSTS.
CACHE_MAX_AGE          Seconds for Cache-Control on successful public GETs (default 300).
RATE_LIMIT_PER_MINUTE  Per-IP token-bucket rate (default 120; 0 disables).
CRON_SECRET            Bearer token required by /api/cron/* (Vercel Cron sends it automatically).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173"
MIN_CRON_SECRET_LENGTH = 32

logger = logging.getLogger(__name__)


def load_dotenv_if_available(path: Path = BACKEND_DIR / ".env") -> bool:
    """Load ``backend/.env`` without overriding real env vars; no-op if python-dotenv is absent."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    return bool(path.is_file() and load_dotenv(path, override=False))


def _env(name: str, default: str) -> str:
    """Env var value, treating empty strings (common in .env templates) as unset."""
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    """All API configuration in one place."""

    cors_origins: tuple[str, ...]
    environment: str
    cache_max_age: int
    rate_limit_per_minute: int
    cron_secret: str | None
    config_problems: tuple[str, ...] = field(default=())
    max_url_length: int = 4096
    max_body_bytes: int = 1024
    # Cron time budget (the Vercel function has maxDuration 300 s).
    cron_collect_budget_s: int = 200
    cron_total_budget_s: int = 280
    cron_min_analysis_s: int = 5
    cron_lease_ttl_s: int = 900

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def config_ok(self) -> bool:
        return not self.config_problems


def validate(environment: str, cors_origins: tuple[str, ...], cron_secret: str | None) -> tuple[str, ...]:
    """Production safety checks. Messages name the setting, never its value."""
    if environment != "production":
        return ()
    problems = []
    if not cron_secret or len(cron_secret) < MIN_CRON_SECRET_LENGTH:
        problems.append(f"CRON_SECRET must be set and at least {MIN_CRON_SECRET_LENGTH} characters")
    if "*" in cors_origins:
        problems.append("CORS_ORIGINS must list explicit origins in production, not '*'")
    return tuple(problems)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings from the environment (cached; call ``get_settings.cache_clear()`` in tests)."""
    raw_origins = _env("CORS_ORIGINS", DEFAULT_CORS)
    origins = tuple(o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip())
    environment = _env("ENV", "development").lower()
    cron_secret = os.environ.get("CRON_SECRET", "").strip() or None
    problems = validate(environment, origins, cron_secret)
    for problem in problems:
        logger.error("Configuration problem: %s", problem)
    return Settings(
        cors_origins=origins,
        environment=environment,
        cache_max_age=int(_env("CACHE_MAX_AGE", "300")),
        rate_limit_per_minute=int(_env("RATE_LIMIT_PER_MINUTE", "120")),
        cron_secret=cron_secret,
        config_problems=problems,
    )
