"""Shared fixtures for collector tests: an in-memory MongoDB (mongomock) and fixture loaders."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import db
from collector.normalise import utc_now_iso
from collector.properties import PROPERTIES
from collector.store import ReviewStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every collector test runs against a fresh in-memory database."""
    monkeypatch.setenv("MONGODB_URI", "mongomock://localhost")
    monkeypatch.delenv("MONGODB_URI_READONLY", raising=False)
    monkeypatch.setenv("MONGODB_DB", "collector_test")
    monkeypatch.delenv("MONGODB_COLLECTION_PREFIX", raising=False)
    db.reset_clients()
    yield
    db.reset_clients()


@pytest.fixture()
def store() -> ReviewStore:
    s = ReviewStore()
    s.init(PROPERTIES, utc_now_iso())
    return s


@pytest.fixture()
def graphql_body() -> dict[str, Any]:
    return json.loads((FIXTURES / "graphql_reviewlist_potts_point.json").read_text(encoding="utf-8"))


@pytest.fixture()
def dom_html() -> str:
    return (FIXTURES / "dom_review_list_paddington.html").read_text(encoding="utf-8")
