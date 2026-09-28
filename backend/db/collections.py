"""Collection names, document shapes and indexes – the single source of truth for the data model.

All collections are prefixed (default ``scraper_``), see ``db.client``.

Document shapes
---------------
properties        {_id: 'olympic-paddington', name, short_name, booking_pagename, booking_cc,
                   booking_url, booking_score, booking_review_count, updated_at}

reviews           {_id: <Booking review id | 'h_' + sha1>, property_id, source_review_id, content_hash,
                   score (1-10), title, positive_text, negative_text, language,
                   review_date 'YYYY-MM-DD' (Sydney), stay_month 'YYYY-MM', nights, room_type,
                   traveller_type, reviewer_country, hotel_response, helpful_votes,
                   first_seen_at, last_seen_at, updated_at,
                   analysis: {sentiment: positive|neutral|negative, sentiment_score (-1..1), summary,
                              method: 'rules' | 'llm:<model>', content_hash, analysed_at}   # absent until analysed
                   topics:   [{topic, polarity: positive|negative, evidence}]}              # [] until analysed

                  Analysis and topics are embedded, so a review and its classification are
                  always updated together in one atomic single-document write.

topics            {_id: 'cleanliness', label, description, sort_order}

scrape_runs       {_id: ObjectId, run_id, property_id, trigger: cron|cli|manual, started_at, finished_at,
                   status: running|success|partial|degraded|failed|skipped, method,
                   mode: incremental|full, watermark_date, pages_fetched, reviews_seen, reviews_new,
                   reviews_updated, reviews_rejected, errors: [str]}

job_locks         {_id: 'collect', holder, acquired_at, expires_at}

Conventions: dates are ISO strings ('YYYY-MM-DD'); timestamps are UTC ISO strings
('YYYY-MM-DDTHH:MM:SSZ'), which sort and range-compare correctly as strings.
"""

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.database import Database

from db.client import collection_prefix, get_database

PROPERTIES = "properties"
REVIEWS = "reviews"
TOPICS = "topics"
SCRAPE_RUNS = "scrape_runs"
JOB_LOCKS = "job_locks"

SENTIMENTS = ("positive", "neutral", "negative")
POLARITIES = ("positive", "negative")
RUN_STATUSES = ("running", "success", "partial", "degraded", "failed", "skipped")

_INDEXES: dict[str, list[IndexModel]] = {
    REVIEWS: [
        IndexModel([("property_id", ASCENDING), ("review_date", DESCENDING)], name="property_date"),
        IndexModel([("review_date", DESCENDING)], name="review_date"),
        IndexModel([("analysis.sentiment", ASCENDING), ("review_date", DESCENDING)], name="sentiment_date"),
        IndexModel([("topics.topic", ASCENDING), ("topics.polarity", ASCENDING)], name="topics"),
        IndexModel(
            [("property_id", ASCENDING), ("source_review_id", ASCENDING)],
            name="uniq_source_review",
            unique=True,
            partialFilterExpression={"source_review_id": {"$type": "string"}},
        ),
    ],
    SCRAPE_RUNS: [
        IndexModel([("started_at", DESCENDING)], name="started_at"),
        IndexModel([("run_id", ASCENDING)], name="run_id"),
    ],
    TOPICS: [IndexModel([("sort_order", ASCENDING)], name="sort_order")],
}


def ensure_indexes(db: Database | None = None) -> None:
    """Create collections' indexes (idempotent; safe to call on every run)."""
    db = db if db is not None else get_database()
    prefix = collection_prefix()
    for name, models in _INDEXES.items():
        db[prefix + name].create_indexes(models)
