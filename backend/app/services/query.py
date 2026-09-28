"""Shared query building blocks and numeric helpers for MongoDB."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

# Sentiment from the analysis step, else derived from the score (>= 8 positive, >= 6 neutral, < 6 negative).
SENTIMENT_EXPR: dict[str, Any] = {
    "$ifNull": [
        "$analysis.sentiment",
        {"$cond": [{"$gte": ["$score", 8]}, "positive", {"$cond": [{"$gte": ["$score", 6]}, "neutral", "negative"]}]},
    ]
}
# Score ranges used when filtering unanalysed reviews by derived sentiment.
SCORE_RANGE_FOR_SENTIMENT: dict[str, dict[str, float]] = {
    "positive": {"$gte": 8},
    "neutral": {"$gte": 6, "$lt": 8},
    "negative": {"$lt": 6},
}


def base_match(properties: Sequence[str], date_from: date | None, date_to: date | None) -> dict[str, Any]:
    """Filter on validated property ids and an inclusive ISO date range."""
    match: dict[str, Any] = {}
    if properties:
        match["property_id"] = {"$in": list(properties)}
    dates: dict[str, str] = {}
    if date_from:
        dates["$gte"] = date_from.isoformat()
    if date_to:
        dates["$lte"] = date_to.isoformat()
    if dates:
        match["review_date"] = dates
    return match


def r2(value: float | None) -> float | None:
    """Round to 2 decimals, keeping None."""
    return None if value is None else round(float(value), 2)


def pct(num: int, den: int) -> float:
    """Percentage 0-100 rounded to 2 decimals; 0 when the denominator is 0."""
    return round(100.0 * num / den, 2) if den else 0.0
