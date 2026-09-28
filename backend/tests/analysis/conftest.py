"""Fixtures for analysis tests: an in-memory MongoDB (mongomock) and a fake LLM."""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest

import db
from analysis.llm_client import ChatResult
from analysis.settings import AnalysisSettings
from db import REVIEWS, collection

NO_KEY = AnalysisSettings(groq_api_key=None)
WITH_KEY = AnalysisSettings(groq_api_key="test-key-not-real", groq_model="fake-model", min_request_interval_s=0)


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """In-memory MongoDB (mongomock) per test; never touches Atlas."""
    monkeypatch.setenv("MONGODB_URI", "mongomock://localhost")
    monkeypatch.delenv("MONGODB_URI_READONLY", raising=False)
    monkeypatch.setenv("MONGODB_DB", "test_analysis")
    monkeypatch.delenv("MONGODB_COLLECTION_PREFIX", raising=False)
    db.reset_clients()
    yield
    db.reset_clients()


def add_review(rid: str, *, score: float = 7.0, positive: str | None = None, negative: str | None = None,
               review_date: str = "2026-09-20", content_hash: str | None = None, title: str | None = None) -> None:
    """Insert or update a review document (as the collector would)."""
    collection(REVIEWS).update_one(
        {"_id": rid},
        {"$set": {"property_id": "potts-point", "source_review_id": rid, "content_hash": content_hash or f"h-{rid}", "score": score,
                  "title": title, "positive_text": positive, "negative_text": negative, "review_date": review_date}},
        upsert=True,
    )


def review(rid: str) -> dict:
    return collection(REVIEWS).find_one({"_id": rid}) or {}


def topic_pairs(rid: str) -> set[tuple[str, str]]:
    return {(t["topic"], t["polarity"]) for t in review(rid).get("topics", [])}


@dataclass
class FakeChat:
    """A ChatClient answering from callable(reviews payload) -> response dict or raw string (or raising)."""

    respond: Callable[[list[dict]], dict | str]
    model: str = "fake-model"
    calls: list[list[dict]] = field(default_factory=list)

    def complete_json(self, system: str, user: str, max_tokens: int) -> ChatResult:
        reviews = json.loads(user)["reviews"]
        self.calls.append(reviews)
        answer = self.respond(reviews)
        content = answer if isinstance(answer, str) else json.dumps(answer)
        return ChatResult(content, prompt_tokens=100, completion_tokens=50)


def echo_topics(reviews: list[dict]) -> dict:
    """Fake LLM: marks every review negative with a grounded 'noise' complaint when 'noisy' appears."""
    out = []
    for r in reviews:
        topics = [{"topic": "noise", "polarity": "negative", "evidence": "noisy"}] if "noisy" in r["disliked"] else []
        out.append({"id": r["id"], "sentiment": "negative", "sentiment_score": -0.5, "summary": "s", "topics": topics})
    return {"reviews": out}
