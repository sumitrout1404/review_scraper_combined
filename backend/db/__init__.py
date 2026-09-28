"""Shared MongoDB data layer for the API, collector and analysis."""

from db.client import (
    DatabaseNotConfigured,
    collection,
    collection_prefix,
    database_name,
    get_client,
    get_database,
    reset_clients,
)
from db.collections import (
    JOB_LOCKS,
    POLARITIES,
    PROPERTIES,
    REVIEWS,
    RUN_STATUSES,
    SCRAPE_RUNS,
    SENTIMENTS,
    TOPICS,
    ensure_indexes,
)
from db.locks import LeaseHeldError, db_lease

__all__ = [
    "JOB_LOCKS",
    "POLARITIES",
    "PROPERTIES",
    "REVIEWS",
    "RUN_STATUSES",
    "SCRAPE_RUNS",
    "SENTIMENTS",
    "TOPICS",
    "DatabaseNotConfigured",
    "LeaseHeldError",
    "collection",
    "collection_prefix",
    "database_name",
    "db_lease",
    "ensure_indexes",
    "get_client",
    "get_database",
    "reset_clients",
]
