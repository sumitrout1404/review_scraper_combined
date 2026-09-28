"""Lease lock stored in MongoDB, safe across serverless instances.

Acquire = one atomic upsert that only matches when the lease is free or expired.
If another holder's lease is still valid, the filter matches nothing and the
upsert collides on ``_id`` (DuplicateKeyError) -> the lease is held. A crashed
holder never blocks forever: its lease simply expires.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from db.client import collection
from db.collections import JOB_LOCKS


class LeaseHeldError(RuntimeError):
    """Another run currently holds the lease."""


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def db_lease(name: str, ttl_s: int = 900) -> Iterator[str]:
    """Hold lease ``name`` for up to ``ttl_s`` seconds; yields the holder id."""
    locks = collection(JOB_LOCKS)
    holder = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    try:
        locks.update_one(
            {"_id": name, "expires_at": {"$lt": _iso(now)}},
            {"$set": {"holder": holder, "acquired_at": _iso(now),
                      "expires_at": _iso(now + timedelta(seconds=ttl_s))}},
            upsert=True,
        )
    except DuplicateKeyError as exc:
        raise LeaseHeldError(f"job '{name}' is already running") from exc
    try:
        yield holder
    finally:
        locks.delete_one({"_id": name, "holder": holder})
