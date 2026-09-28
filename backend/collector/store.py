"""Persistence for the collector on MongoDB (via the shared ``db`` package).

* Properties are upserted from the fixed catalogue.
* Each review page is written with one ``bulk_write`` of per-document upserts:
  ``$set`` for content fields, ``$setOnInsert`` for ``first_seen_at`` / ``topics``.
  The embedded ``analysis`` / ``topics`` written by the analysis step are never touched here.
* ``content_hash`` + a full field comparison decide new / updated / unchanged, so
  re-running the same scrape changes nothing except ``last_seen_at``.
* ``scrape_runs`` documents follow the shape in ``db/collections.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo import DeleteOne, UpdateOne
from pymongo.collection import Collection

from collector.models import PropertyMeta, ReviewRecord
from collector.properties import Property
from db import PROPERTIES, REVIEWS, SCRAPE_RUNS, collection, ensure_indexes

logger = logging.getLogger(__name__)

#: fields compared to decide whether a stored review changed (timestamps excluded)
CONTENT_FIELDS = (
    "property_id", "source_review_id", "content_hash", "score", "title", "positive_text", "negative_text",
    "language", "review_date", "stay_month", "nights", "room_type", "traveller_type", "reviewer_country",
    "hotel_response", "helpful_votes",
)
_PROJECTION = {f: 1 for f in CONTENT_FIELDS}


@dataclass(frozen=True)
class UpsertResult:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0  # conflicting / lower-fidelity duplicates left untouched


def record_fields(record: ReviewRecord) -> dict[str, Any]:
    """Document fields (without ``_id`` and timestamps) for one validated record."""
    fields = record.model_dump()
    fields["review_date"] = record.review_date.isoformat()
    fields["content_hash"] = record.content_hash
    return fields


def upsert_op(review_id: str, fields: dict[str, Any], now: str) -> UpdateOne:
    """Idempotent upsert that preserves ``first_seen_at`` and the embedded analysis."""
    return UpdateOne(
        {"_id": review_id},
        {"$set": {**fields, "last_seen_at": now, "updated_at": now},
         "$setOnInsert": {"first_seen_at": now, "topics": []}},
        upsert=True,
    )


class ReviewStore:
    """Thin data-access layer used by the pipeline and CLI."""

    def __init__(self) -> None:
        self.reviews: Collection = collection(REVIEWS)
        self.properties: Collection = collection(PROPERTIES)
        self.runs: Collection = collection(SCRAPE_RUNS)

    # -- setup -----------------------------------------------------------------

    def init(self, props: Iterable[Property], now: str) -> None:
        """Ensure indexes and upsert the fixed property catalogue (idempotent)."""
        ensure_indexes()
        ops = [
            UpdateOne(
                {"_id": p.id},
                {"$set": {"name": p.name, "short_name": p.short_name, "booking_pagename": p.booking_pagename,
                          "booking_cc": p.booking_cc, "booking_url": p.booking_url},
                 "$setOnInsert": {"booking_score": None, "booking_review_count": None, "updated_at": now}},
                upsert=True,
            )
            for p in props
        ]
        if ops:
            self.properties.bulk_write(ops, ordered=False)

    def update_property_meta(self, property_id: str, meta: PropertyMeta, now: str) -> None:
        """Store Booking's headline score/count; never overwrite a known value with None."""
        values: dict[str, Any] = {}
        if meta.booking_score is not None:
            values["booking_score"] = meta.booking_score
        if meta.booking_review_count is not None:
            values["booking_review_count"] = meta.booking_review_count
        if values:
            self.properties.update_one({"_id": property_id}, {"$set": {**values, "updated_at": now}})

    # -- reads -----------------------------------------------------------------

    def watermark(self, property_id: str) -> str | None:
        """Newest stored ``review_date`` for the property, or None."""
        doc = next(iter(self.reviews.find({"property_id": property_id}, {"review_date": 1})
                        .sort("review_date", -1).limit(1)), None)
        return doc["review_date"] if doc else None

    def count_reviews(self, property_id: str | None = None) -> int:
        return self.reviews.count_documents({"property_id": property_id} if property_id else {})

    # -- writes ----------------------------------------------------------------

    def upsert_page(self, records: list[ReviewRecord], now: str) -> UpsertResult:
        """Write one page of validated records with a single ``bulk_write``."""
        if not records:
            return UpsertResult()
        existing = {d["_id"]: d for d in self.reviews.find({"_id": {"$in": [r.id for r in records]}}, _PROJECTION)}
        ops: list[UpdateOne | DeleteOne] = []
        new = updated = unchanged = skipped = 0
        for record in records:
            fields = record_fields(record)
            current = existing.get(record.id) or self._match_by_hash(record)
            if current is None:
                ops.append(upsert_op(record.id, fields, now))
                new += 1
            elif current["property_id"] != record.property_id:
                logger.warning("review id %s already stored for %s; skipping", record.id, current["property_id"])
                skipped += 1
            elif current["_id"] != record.id:
                if record.source_review_id is None:
                    # Lower-fidelity (DOM) copy of a review already held with full data: just mark it seen.
                    ops.append(UpdateOne({"_id": current["_id"]}, {"$set": {"last_seen_at": now}}))
                    skipped += 1
                else:
                    # Booking's id is now known for a review first captured without one: re-key it.
                    ops += [DeleteOne({"_id": current["_id"]}), upsert_op(record.id, fields, now)]
                    updated += 1
            elif all(current.get(f) == fields[f] for f in CONTENT_FIELDS):
                ops.append(UpdateOne({"_id": record.id}, {"$set": {"last_seen_at": now}}))
                unchanged += 1
            else:
                ops.append(upsert_op(record.id, fields, now))
                updated += 1
        if ops:
            self.reviews.bulk_write(ops, ordered=True)
        return UpsertResult(new=new, updated=updated, unchanged=unchanged, skipped=skipped)

    def _match_by_hash(self, record: ReviewRecord) -> dict[str, Any] | None:
        """Same review stored under a different key (hash-only copy, or id-keyed copy of a DOM record)."""
        query: dict[str, Any] = {"property_id": record.property_id, "content_hash": record.content_hash}
        if record.source_review_id:
            query["source_review_id"] = None
        return self.reviews.find_one(query, _PROJECTION)

    # -- run audit -------------------------------------------------------------

    def start_run(self, *, run_id: str, property_id: str, trigger: str, mode: str,
                  watermark: str | None, now: str) -> ObjectId:
        """Insert a 'running' audit document and return its id."""
        doc = {
            "run_id": run_id, "property_id": property_id, "trigger": trigger, "started_at": now,
            "finished_at": None, "status": "running", "method": None, "mode": mode, "watermark_date": watermark,
            "pages_fetched": 0, "reviews_seen": 0, "reviews_new": 0, "reviews_updated": 0,
            "reviews_rejected": 0, "errors": [],
        }
        return self.runs.insert_one(doc).inserted_id

    def finish_run(self, run_doc_id: ObjectId, *, status: str, method: str | None, pages_fetched: int,
                   reviews_seen: int, reviews_new: int, reviews_updated: int, reviews_rejected: int,
                   errors: list[str], now: str) -> None:
        self.runs.update_one({"_id": run_doc_id}, {"$set": {
            "finished_at": now, "status": status, "method": method, "pages_fetched": pages_fetched,
            "reviews_seen": reviews_seen, "reviews_new": reviews_new, "reviews_updated": reviews_updated,
            "reviews_rejected": reviews_rejected, "errors": errors,
        }})

    def fail_stale_runs(self, stale_after_s: int, now: str) -> int:
        """Mark 'running' documents left behind by a crashed run as failed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = self.runs.update_many(
            {"status": "running", "started_at": {"$lt": cutoff}},
            {"$set": {"status": "failed", "finished_at": now, "errors": ["interrupted: run did not finish"]}},
        )
        return result.modified_count
