"""MongoDB access for analysis.

Analysis is embedded in each review document (``review.analysis`` + ``review.topics``), so
persisting one review is a single atomic ``update_one``. Writes are filtered on the
``content_hash`` that was analysed, so a review edited concurrently by the collector is
not overwritten with a stale classification (it stays pending for the next run).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pymongo import UpdateOne

from analysis.lexicon import TopicDef
from analysis.models import RULES_METHOD, AnalysisResult, ReviewInput
from db import REVIEWS, TOPICS, collection

_PROJECTION = {"_id": 1, "score": 1, "content_hash": 1, "title": 1, "positive_text": 1, "negative_text": 1,
               "language": 1, "review_date": 1}

# Never analysed, or analysed for an older version of the review.
_NEEDS_ANALYSIS: dict[str, Any] = {"$or": [
    {"analysis": {"$exists": False}},
    {"analysis": None},
    {"$expr": {"$ne": ["$analysis.content_hash", "$content_hash"]}},
]}


@dataclass(frozen=True)
class PendingReview:
    review: ReviewInput
    review_date: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_topics(topics: list[TopicDef]) -> None:
    """Idempotently sync the topic catalogue (``_id`` = topic key) from topics.yaml."""
    collection(TOPICS).bulk_write([
        UpdateOne({"_id": t.key},
                  {"$set": {"label": t.label, "description": t.description, "sort_order": t.sort_order}},
                  upsert=True)
        for t in topics
    ])


def count_reviews() -> int:
    return collection(REVIEWS).count_documents({})


def _to_pending(doc: dict[str, Any]) -> PendingReview:
    return PendingReview(
        ReviewInput(
            id=str(doc["_id"]), score=float(doc["score"]), content_hash=str(doc["content_hash"]),
            title=doc.get("title"), positive_text=doc.get("positive_text"),
            negative_text=doc.get("negative_text"), language=doc.get("language"),
        ),
        str(doc.get("review_date") or ""),
    )


def pending_reviews(reanalyse: bool) -> list[PendingReview]:
    """Reviews without an analysis for their current content_hash (all when ``reanalyse``), oldest first."""
    cursor = collection(REVIEWS).find({} if reanalyse else _NEEDS_ANALYSIS, _PROJECTION)
    return [_to_pending(doc) for doc in cursor.sort([("review_date", 1), ("_id", 1)])]


def upgradable_reviews(since: str) -> list[PendingReview]:
    """Up-to-date, rules-analysed reviews dated >= ``since`` (newest first) — candidates for the LLM."""
    query = {"analysis.method": RULES_METHOD, "review_date": {"$gte": since},
             "$expr": {"$eq": ["$analysis.content_hash", "$content_hash"]}}
    cursor = collection(REVIEWS).find(query, _PROJECTION)
    return [_to_pending(doc) for doc in cursor.sort([("review_date", -1), ("_id", 1)])]


def save_results(results: list[AnalysisResult], allowed_topics: frozenset[str]) -> tuple[int, int]:
    """Embed analyses + topics (one atomic update per review). Returns (reviews saved, topic rows written)."""
    if not results:
        return 0, 0
    analysed_at = utc_now_iso()
    ops = []
    topic_rows = 0
    for result in results:
        topics = [{"topic": m.topic, "polarity": m.polarity, "evidence": m.evidence}
                  for m in result.topics if m.topic in allowed_topics]
        topic_rows += len(topics)
        ops.append(UpdateOne(
            {"_id": result.review_id, "content_hash": result.content_hash},
            {"$set": {
                "analysis": {
                    "sentiment": result.sentiment,
                    "sentiment_score": result.sentiment_score,
                    "summary": result.summary,
                    "method": result.method,
                    "content_hash": result.content_hash,
                    "analysed_at": analysed_at,
                },
                "topics": topics,
            }},
        ))
    outcome = collection(REVIEWS).bulk_write(ops, ordered=False)
    return outcome.matched_count, topic_rows
