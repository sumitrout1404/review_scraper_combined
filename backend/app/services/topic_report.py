"""Topic breakdown (GET /api/topics/breakdown)."""

from __future__ import annotations

from typing import Any

from ..deps import Filters
from .catalog import label_for, topic_catalog
from .query import pct
from .topic_stats import topic_counts


def build_breakdown(f: Filters) -> dict[str, Any]:
    """Complaints and praise per topic, sorted by complaints (then praise, then catalogue order).

    ``pct_of_negative_reviews`` = negative reviews with a complaint on the topic / negative reviews.
    ``pct_of_reviews`` = reviews mentioning the topic (either polarity) / all reviews.
    """
    tc = topic_counts(f.properties, f.date_from, f.date_to)
    catalog = topic_catalog()
    labels = {t["key"]: t["label"] for t in catalog}
    keys = [t["key"] for t in catalog]
    keys += sorted((set(tc.negative) | set(tc.positive)) - set(keys))  # tagged topics missing from the catalogue
    order = {k: i for i, k in enumerate(keys)}
    items = []
    for key in keys:
        neg, pos = tc.negative.get(key, 0), tc.positive.get(key, 0)
        items.append(
            {
                "topic": key,
                "label": label_for(labels, key),
                "negative_mentions": neg,
                "positive_mentions": pos,
                "pct_of_negative_reviews": pct(tc.neg_in_negative.get(key, 0), tc.negative_reviews),
                "pct_of_reviews": pct(tc.any_mention.get(key, 0), tc.total_reviews),
                "net": pos - neg,
            }
        )
    items.sort(key=lambda i: (-i["negative_mentions"], -i["positive_mentions"], order[i["topic"]]))
    return {"total_reviews": tc.total_reviews, "negative_reviews": tc.negative_reviews, "items": items}
