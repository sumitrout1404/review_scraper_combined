"""Review feed search: filters, sorting, pagination and topic labelling."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from db import REVIEWS

from ..db import ro
from .catalog import label_for, list_properties
from .query import SCORE_RANGE_FOR_SENTIMENT, base_match, r2

SORTS: dict[str, list[tuple[str, int]]] = {
    "date_desc": [("review_date", -1), ("first_seen_at", -1), ("_id", 1)],
    "date_asc": [("review_date", 1), ("first_seen_at", 1), ("_id", 1)],
    "score_asc": [("score", 1), ("review_date", -1), ("_id", 1)],
    "score_desc": [("score", -1), ("review_date", -1), ("_id", 1)],
}
SEARCH_FIELDS = ("title", "positive_text", "negative_text", "analysis.summary", "room_type")
REVIEW_FIELDS = (
    "property_id", "score", "title", "positive_text", "negative_text", "language", "review_date", "stay_month",
    "nights", "room_type", "traveller_type", "reviewer_country", "hotel_response",
)  # fmt: skip
PROJECTION = {**{f: 1 for f in REVIEW_FIELDS}, "analysis": 1, "topics": 1}


@dataclass
class ReviewQuery:
    """Validated review-feed filters."""

    properties: list[str]
    date_from: date | None
    date_to: date | None
    sentiments: list[str]
    topics: list[str]
    polarity: str | None
    min_score: float | None
    max_score: float | None
    q: str | None
    sort: str = "date_desc"


def _sentiment_clause(sentiments: list[str]) -> dict[str, Any]:
    """Analysed sentiment, or the score rule for reviews that have not been analysed yet."""
    return {
        "$or": [{"analysis.sentiment": {"$in": sentiments}}]
        + [{"analysis.sentiment": None, "score": SCORE_RANGE_FOR_SENTIMENT[s]} for s in sentiments]
    }


def review_filter(rq: ReviewQuery) -> dict[str, Any]:
    """Mongo filter for the feed/CSV. Only validated values are used; ``q`` is regex-escaped."""
    clauses: list[dict[str, Any]] = []
    base = base_match(rq.properties, rq.date_from, rq.date_to)
    if base:
        clauses.append(base)
    if rq.sentiments:
        clauses.append(_sentiment_clause(rq.sentiments))
    if rq.topics or rq.polarity:
        elem: dict[str, Any] = {}
        if rq.topics:
            elem["topic"] = {"$in": rq.topics}
        if rq.polarity:
            elem["polarity"] = rq.polarity
        clauses.append({"topics": {"$elemMatch": elem}})
    score: dict[str, float] = {}
    if rq.min_score is not None:
        score["$gte"] = rq.min_score
    if rq.max_score is not None:
        score["$lte"] = rq.max_score
    if score:
        clauses.append({"score": score})
    if rq.q:
        pattern = re.escape(rq.q)
        clauses.append({"$or": [{f: {"$regex": pattern, "$options": "i"}} for f in SEARCH_FIELDS]})
    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def count_reviews(rq: ReviewQuery) -> int:
    return ro(REVIEWS).count_documents(review_filter(rq))


def iter_reviews(rq: ReviewQuery, skip: int = 0, limit: int = 0, batch_size: int = 500) -> Iterator[dict[str, Any]]:
    """Raw review documents in the requested order (``limit=0`` means all)."""
    cursor = ro(REVIEWS).find(review_filter(rq), PROJECTION).sort(SORTS[rq.sort]).skip(skip).batch_size(batch_size)
    if limit:
        cursor = cursor.limit(limit)
    return iter(cursor)


class ReviewFormatter:
    """Turns review documents into contract ``Review`` dicts (property names and topic labels resolved once)."""

    def __init__(self, labels: dict[str, str], topic_order: dict[str, int]) -> None:
        self.labels = labels
        self.topic_order = topic_order
        self.properties = {p["id"]: p for p in list_properties()}

    def __call__(self, doc: dict[str, Any]) -> dict[str, Any]:
        analysis = doc.get("analysis") or {}
        prop = self.properties.get(doc.get("property_id"), {})
        tags = sorted(
            (t for t in doc.get("topics") or [] if isinstance(t, dict) and t.get("topic")),
            key=lambda t: (t.get("polarity") != "positive", self.topic_order.get(t["topic"], 999), t["topic"]),
        )
        score = doc.get("score")
        return {
            "id": str(doc["_id"]),
            **{f: doc.get(f) for f in REVIEW_FIELDS},
            "score": r2(score),
            "property_name": prop.get("name"),
            "property_short_name": prop.get("short_name"),
            "sentiment": analysis.get("sentiment") or _score_sentiment(score),
            "sentiment_score": r2(analysis.get("sentiment_score")),
            "summary": analysis.get("summary"),
            "analysis_method": analysis.get("method"),
            "topics": [
                {
                    "topic": t["topic"],
                    "label": label_for(self.labels, t["topic"]),
                    "polarity": t.get("polarity"),
                    "evidence": t.get("evidence"),
                }
                for t in tags
            ],
        }


def _score_sentiment(score: float | None) -> str:
    if score is None:
        return "neutral"
    return "positive" if score >= 8 else "neutral" if score >= 6 else "negative"
