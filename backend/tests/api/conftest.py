"""Fixtures for API tests: an in-memory MongoDB (mongomock) seeded per test, and a TestClient."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import mongomock
import pytest
from fastapi.testclient import TestClient

import db
from app.config import get_settings
from app.main import create_app
from db import PROPERTIES as PROPERTIES_COLL
from db import REVIEWS, SCRAPE_RUNS, TOPICS, collection

NOW = "2026-01-20T00:00:00Z"

PROPERTIES = [
    ("olympic-paddington", "Olympic Hotel Paddington", "Paddington", "olympic-paddington"),
    ("potts-point", "Azzurro Potts Point", "Potts Point", "venus-potts-point-sydney"),
    ("central-sydney", "Azzurro Central Sydney", "Central Sydney", "venus-surry-hills"),
    ("darling-harbour", "Azzurro Darling Harbour", "Darling Harbour", "chateau-de-venus"),
]
TOPIC_ROWS = [
    ("cleanliness", "Cleanliness"),
    ("check_in", "Check-in & check-out"),
    ("staff", "Staff & reception"),
    ("noise", "Noise"),
    ("location", "Location"),
]


@dataclass
class R:
    """A review for test fixtures."""

    id: str
    property_id: str
    review_date: str
    score: float
    title: str | None = None
    positive_text: str | None = None
    negative_text: str | None = None
    hotel_response: str | None = None
    sentiment: str | None = None  # None -> no embedded analysis (score fallback)
    topics: list[tuple[str, str]] = field(default_factory=list)  # (topic, polarity)

    def document(self) -> dict:
        doc = {
            "_id": self.id, "property_id": self.property_id, "content_hash": "h" + self.id, "score": self.score,
            "title": self.title, "positive_text": self.positive_text, "negative_text": self.negative_text,
            "review_date": self.review_date, "hotel_response": self.hotel_response,
            "first_seen_at": NOW, "last_seen_at": NOW, "updated_at": NOW,
            "topics": [{"topic": t, "polarity": p, "evidence": f"{t} evidence"} for t, p in self.topics],
        }  # fmt: skip
        if self.sentiment:
            doc["analysis"] = {
                "sentiment": self.sentiment, "sentiment_score": 0.1, "summary": None, "method": "rules",
                "content_hash": "h" + self.id, "analysed_at": NOW,
            }  # fmt: skip
        return doc


def seed(reviews: list[R], with_topics: bool = True) -> None:
    """Insert properties, topics, reviews and two scrape_runs rows into the (mock) database."""
    collection(PROPERTIES_COLL).insert_many(
        [
            {"_id": pid, "name": name, "short_name": short, "booking_pagename": page,
             "booking_url": f"https://www.booking.com/hotel/au/{page}.html", "booking_score": 8.0}
            for pid, name, short, page in PROPERTIES
        ]
    )  # fmt: skip
    if with_topics:
        collection(TOPICS).insert_many(
            [
                {"_id": k, "label": label, "description": None, "sort_order": i}
                for i, (k, label) in enumerate(TOPIC_ROWS)
            ]
        )
    if reviews:
        collection(REVIEWS).insert_many([r.document() for r in reviews])
    base = {"run_id": "run-1", "trigger": "cron", "started_at": "2026-01-19T00:00:00Z", "mode": "incremental"}
    collection(SCRAPE_RUNS).insert_many(
        [
            {**base, "property_id": "olympic-paddington", "finished_at": "2026-01-19T00:05:00Z", "status": "success",
             "method": "html", "watermark_date": "2026-01-09", "errors": []},
            {**base, "property_id": "potts-point", "finished_at": None, "status": "failed", "method": "html",
             "watermark_date": None, "errors": ["timeout"]},
        ]
    )  # fmt: skip


# Current window: Mon 2026-01-05 .. Sun 2026-01-11. Previous: Mon 2025-12-29 .. Sun 2026-01-04.
CUR_FROM, CUR_TO = "2026-01-05", "2026-01-11"
PREV_FROM, PREV_TO = "2025-12-29", "2026-01-04"


def standard_reviews() -> list[R]:
    """Paddington drops sharply week over week; 4 of its 10 negative reviews mention cleanliness."""
    out: list[R] = []
    for i in range(10):  # current: 10 negative Paddington reviews, score 4
        topics = []
        if i < 4:
            topics.append(("cleanliness", "negative"))
        if 4 <= i < 7:
            topics.append(("noise", "negative"))
        out.append(
            R(f"cn{i}", "olympic-paddington", "2026-01-0" + str(5 + i % 5), 4.0, title=f"Bad stay {i}",
              negative_text="Dirty room" if i < 4 else "Loud", hotel_response="Sorry" if i == 0 else None,
              sentiment="negative" if i % 2 == 0 else None, topics=topics)
        )  # fmt: skip
    for i in range(2):  # current: 2 positive Paddington reviews praising location
        out.append(
            R(f"cp{i}", "olympic-paddington", "2026-01-10", 9.0, positive_text="Great location",
              sentiment="positive", topics=[("location", "positive")])
        )  # fmt: skip
    for i in range(5):  # current: Potts Point steady
        out.append(R(f"pp{i}", "potts-point", "2026-01-07", 9.0, positive_text="Lovely staff 100% recommend",
                     topics=[("staff", "positive"), ("location", "positive")]))  # fmt: skip
    for i in range(6):  # previous: Paddington good
        out.append(R(f"pn{i}", "olympic-paddington", "2025-12-30", 8.0, sentiment="positive",
                     topics=[("cleanliness", "negative")] if i == 0 else []))  # fmt: skip
    for i in range(5):  # previous: Potts Point
        out.append(R(f"pq{i}", "potts-point", "2026-01-02", 9.0))
    out.append(R("old1", "darling-harbour", "2025-11-15", 7.0, title='=HYPERLINK("http://x")'))  # older, for trends
    return out


def _shared_client(shared: mongomock.MongoClient) -> Callable[..., mongomock.MongoClient]:
    """Stand-in for ``db.client.get_client`` (keeps its ``cache_clear`` so ``reset_clients`` works)."""

    def get_client(read_only: bool = False) -> mongomock.MongoClient:
        return shared

    get_client.cache_clear = lambda: None  # type: ignore[attr-defined]
    return get_client


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., TestClient]]:
    """Factory: make_client(reviews=None, env=None, with_topics=True) -> TestClient over a fresh mock DB."""
    counter = {"n": 0}

    def factory(
        reviews: list[R] | None = None, env: dict[str, str] | None = None, with_topics: bool = True
    ) -> TestClient:
        counter["n"] += 1
        monkeypatch.setenv("MONGODB_URI", "mongomock://localhost")
        monkeypatch.delenv("MONGODB_URI_READONLY", raising=False)
        monkeypatch.setenv("MONGODB_DB", f"api_test_{counter['n']}")
        monkeypatch.delenv("MONGODB_COLLECTION_PREFIX", raising=False)
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
        for name in ("ENV", "CRON_SECRET", "CORS_ORIGINS"):
            monkeypatch.delenv(name, raising=False)
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        db.reset_clients()
        shared = mongomock.MongoClient()  # one in-memory server for both the read-only and the write client
        monkeypatch.setattr(db.client, "get_client", _shared_client(shared))
        get_settings.cache_clear()
        seed(standard_reviews() if reviews is None else reviews, with_topics)
        return TestClient(create_app(), raise_server_exceptions=False)

    yield factory
    db.reset_clients()
    get_settings.cache_clear()


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
