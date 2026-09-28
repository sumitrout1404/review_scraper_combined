"""Read-only MongoDB access for the public API, on top of the shared ``db`` package.

Only ``collection(name, read_only=True)`` is used here (``MONGODB_URI_READONLY`` when set).
Every filter is built by the services from validated parameters; user input only ever
appears as a *value* (allowlisted ids/enums, parsed dates, or an escaped regex).
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from db import REVIEWS, DatabaseNotConfigured, collection

logger = logging.getLogger(__name__)

# Errors that mean "the database is unavailable" -> HTTP 503 with a generic message.
DB_ERRORS: tuple[type[Exception], ...] = (PyMongoError, DatabaseNotConfigured)
UNAVAILABLE_MESSAGE = "Review database is temporarily unavailable"


class DatabaseUnavailable(Exception):
    """Raised when the review database cannot be reached."""


def ro(name: str) -> Collection:
    """Read-only handle for a logical collection name (e.g. ``REVIEWS``)."""
    return collection(name, read_only=True)


def aggregate(name: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run an aggregation pipeline on a read-only collection and materialise the result."""
    return list(ro(name).aggregate(pipeline))


def ping() -> None:
    """Round-trip to the server; raises ``DatabaseUnavailable`` on failure."""
    try:
        ro(REVIEWS).database.command("ping")
    except DB_ERRORS as exc:
        logger.warning("Database ping failed: %s", type(exc).__name__)
        raise DatabaseUnavailable(UNAVAILABLE_MESSAGE) from exc
