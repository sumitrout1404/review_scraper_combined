"""MongoDB connection handling shared by the API, collector and analysis.

Configuration (environment):
    MONGODB_URI                Connection string (required). ``mongomock://`` uses an
                               in-memory fake – for tests only.
    MONGODB_URI_READONLY       Optional connection string for a read-only database user;
                               the public API uses it when set (least privilege).
    MONGODB_DB                 Database name (default ``scraper``).
    MONGODB_COLLECTION_PREFIX  Prefix for every collection (default ``scraper_``), so this
                               app can share a cluster without touching other data.

The client is created once per process and reused, which is what serverless
functions need to avoid opening a new connection pool on every request.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_NAME = "scraper"
DEFAULT_PREFIX = "scraper_"
MOCK_SCHEME = "mongomock://"


class DatabaseNotConfigured(RuntimeError):
    """MONGODB_URI is missing."""


def _load_dotenv() -> None:
    """Load backend/.env for local runs; Vercel injects env vars directly."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_file = BACKEND_DIR / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def database_name() -> str:
    return os.getenv("MONGODB_DB", "").strip() or DEFAULT_DB_NAME


def collection_prefix() -> str:
    value = os.getenv("MONGODB_COLLECTION_PREFIX")
    return DEFAULT_PREFIX if value is None else value.strip()


def _uri(read_only: bool) -> str:
    _load_dotenv()
    uri = (os.getenv("MONGODB_URI_READONLY") if read_only else None) or os.getenv("MONGODB_URI")
    if not uri:
        raise DatabaseNotConfigured("MONGODB_URI is not set")
    return uri.strip()


@lru_cache(maxsize=4)
def get_client(read_only: bool = False) -> MongoClient:
    """Process-wide cached client."""
    uri = _uri(read_only)
    if uri.startswith(MOCK_SCHEME):
        return _mock_client()
    return MongoClient(
        uri,
        appname="azzurro-review-insights",
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=30000,
        maxPoolSize=10,
        # Keep one socket open and authenticated. Establishing a connection to Atlas
        # costs a TLS handshake plus SCRAM auth (~hundreds of ms), which would
        # otherwise be paid again whenever the pool goes idle between requests.
        minPoolSize=1,
        maxIdleTimeMS=120_000,
        retryWrites=True,
        tz_aware=True,
    )


def get_database(read_only: bool = False) -> Database:
    return get_client(read_only)[database_name()]


def collection(name: str, read_only: bool = False) -> Collection:
    """Collection by logical name, e.g. ``collection("reviews")`` -> ``scraper_reviews``."""
    return get_database(read_only)[collection_prefix() + name]


@lru_cache(maxsize=1)
def _mock_client() -> MongoClient:
    """One shared in-memory store, so read-only and write clients see the same data."""
    import mongomock  # dev/test dependency only

    return mongomock.MongoClient()


def reset_clients() -> None:
    """Drop cached clients (tests / after changing env)."""
    get_client.cache_clear()
    _mock_client.cache_clear()
