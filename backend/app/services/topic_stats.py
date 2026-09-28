"""Topic mention counts for a window (``$unwind`` over the embedded ``topics`` list)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from db import REVIEWS

from ..db import aggregate
from .query import SENTIMENT_EXPR, base_match


@dataclass
class TopicCounts:
    """Distinct-review counts per topic within a window."""

    total_reviews: int
    negative_reviews: int
    negative: dict[str, int]  # reviews with a complaint on the topic
    positive: dict[str, int]  # reviews with praise on the topic
    neg_in_negative: dict[str, int]  # negative-sentiment reviews with a complaint on the topic
    any_mention: dict[str, int]  # reviews mentioning the topic with either polarity
    negative_by_property: dict[str, dict[str, int]]  # topic -> property -> complaints


def _mentions(match: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per (review, topic, polarity) with the review's property and sentiment."""
    pipeline = [
        {"$match": match},
        {"$project": {"p": "$property_id", "s": SENTIMENT_EXPR, "topics": 1}},
        {"$unwind": "$topics"},
        {"$group": {"_id": {"r": "$_id", "t": "$topics.topic", "pol": "$topics.polarity", "p": "$p", "s": "$s"}}},
    ]
    return [row["_id"] for row in aggregate(REVIEWS, pipeline)]


def _totals(match: dict[str, Any]) -> tuple[int, int]:
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": None,
                "n": {"$sum": 1},
                "neg": {"$sum": {"$cond": [{"$eq": [SENTIMENT_EXPR, "negative"]}, 1, 0]}},
            }
        },
    ]
    rows = aggregate(REVIEWS, pipeline)
    return (int(rows[0]["n"]), int(rows[0]["neg"])) if rows else (0, 0)


def topic_counts(properties: Sequence[str], date_from: date | None, date_to: date | None) -> TopicCounts:
    """Count topic mentions for reviews matching the filters."""
    match = base_match(properties, date_from, date_to)
    total, negative_reviews = _totals(match)
    negative: dict[str, int] = defaultdict(int)
    positive: dict[str, int] = defaultdict(int)
    neg_in_negative: dict[str, int] = defaultdict(int)
    by_property: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mentioned: dict[str, set[str]] = defaultdict(set)
    for m in _mentions(match):
        mentioned[m["t"]].add(m["r"])
        if m["pol"] == "negative":
            negative[m["t"]] += 1
            by_property[m["t"]][m["p"]] += 1
            if m["s"] == "negative":
                neg_in_negative[m["t"]] += 1
        elif m["pol"] == "positive":
            positive[m["t"]] += 1
    return TopicCounts(
        total_reviews=total,
        negative_reviews=negative_reviews,
        negative=dict(negative),
        positive=dict(positive),
        neg_in_negative=dict(neg_in_negative),
        any_mention={t: len(ids) for t, ids in mentioned.items()},
        negative_by_property={t: dict(v) for t, v in by_property.items()},
    )


def top_complaints_by_property(
    properties: Sequence[str], date_from: date | None, date_to: date | None, order: dict[str, int]
) -> dict[str, tuple[str, int]]:
    """property_id -> (topic, complaints) for its most complained-about topic (ties by catalogue order)."""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for m in _mentions(base_match(properties, date_from, date_to)):
        if m["pol"] == "negative":
            counts[(m["p"], m["t"])] += 1
    out: dict[str, tuple[str, int]] = {}
    for (pid, topic), n in sorted(
        counts.items(), key=lambda kv: (kv[0][0], -kv[1], order.get(kv[0][1], 999), kv[0][1])
    ):
        out.setdefault(pid, (topic, n))
    return out
