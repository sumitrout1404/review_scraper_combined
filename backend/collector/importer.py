"""Idempotent import of previously collected reviews into MongoDB.

Sources:
* the legacy SQLite database (``data/reviews.db``, contract v1-v3): reviews, embedded
  analysis/topics when present, properties' headline numbers and scrape_runs;
* an export file (``data/samples/reviews.json``): reviews only (analysis is re-run).

Every review is re-validated through :class:`ReviewRecord`, so the import passes the
same data-quality gate as live collection. Upserts are keyed by review id;
``first_seen_at`` keeps the earliest and ``last_seen_at`` the latest value, so
importing the same file twice changes nothing. stdlib ``sqlite3`` is used only here.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pymongo import UpdateOne
from pymongo.collection import Collection

from collector.models import ReviewRecord
from collector.normalise import utc_now_iso
from collector.properties import PROPERTIES, PROPERTIES_BY_ID
from collector.store import ReviewStore, record_fields
from db import PROPERTIES as PROPERTIES_COLL
from db import REVIEWS, SCRAPE_RUNS, collection

logger = logging.getLogger(__name__)

_BATCH = 500
_RECORD_FIELDS = tuple(ReviewRecord.model_fields)
_ANALYSIS_FIELDS = ("sentiment", "sentiment_score", "summary", "method", "content_hash", "analysed_at")


@dataclass
class ImportStats:
    source: str
    reviews_read: int = 0
    reviews_inserted: int = 0
    reviews_rejected: int = 0
    with_analysis: int = 0
    runs_imported: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _Row:
    fields: dict[str, Any]
    analysis: dict[str, Any] | None = None
    topics: list[dict[str, Any]] | None = None


def import_reviews(path: Path) -> ImportStats:
    """Import ``path`` (SQLite ``.db`` or export ``.json``) into the configured MongoDB."""
    if not path.is_file():
        raise FileNotFoundError(path)
    ReviewStore().init(PROPERTIES, utc_now_iso())
    stats = ImportStats(source=path.name)
    if path.suffix.lower() == ".json":
        _write_reviews(_rows_from_json(path), stats)
    else:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            _write_reviews(_rows_from_sqlite(conn), stats)
            _import_property_meta(conn)
            stats.runs_imported = _import_runs(conn)
        finally:
            conn.close()
    logger.info("import finished: %s", stats)
    return stats


def _write_reviews(rows: Iterator[_Row], stats: ImportStats) -> None:
    reviews = collection(REVIEWS)
    batch: list[UpdateOne] = []
    now = utc_now_iso()
    for row in rows:
        stats.reviews_read += 1
        op = _to_op(row, now, stats)
        if op is not None:
            batch.append(op)
        if len(batch) >= _BATCH:
            _flush(reviews, batch, stats)
    _flush(reviews, batch, stats)


def _to_op(row: _Row, now: str, stats: ImportStats) -> UpdateOne | None:
    candidate = {k: row.fields.get(k) for k in _RECORD_FIELDS}
    if candidate.get("property_id") not in PROPERTIES_BY_ID:
        stats.reviews_rejected += 1
        return None
    try:
        record = ReviewRecord(**candidate)
    except ValidationError as exc:
        stats.reviews_rejected += 1
        if len(stats.errors) < 5:
            stats.errors.append(f"{row.fields.get('id')}: {exc.errors()[0].get('msg')}")
        return None
    fields = record_fields(record)
    update: dict[str, Any] = {
        "$set": {**fields, "updated_at": row.fields.get("updated_at") or now},
        "$min": {"first_seen_at": row.fields.get("first_seen_at") or now},
        "$max": {"last_seen_at": row.fields.get("last_seen_at") or now},
    }
    if row.analysis and row.analysis.get("content_hash") == fields["content_hash"]:
        update["$set"]["analysis"] = row.analysis
        update["$set"]["topics"] = row.topics or []
        stats.with_analysis += 1
    else:
        update["$setOnInsert"] = {"topics": []}
    return UpdateOne({"_id": record.id}, update, upsert=True)


def _flush(reviews: Collection, batch: list[UpdateOne], stats: ImportStats) -> None:
    if batch:
        stats.reviews_inserted += reviews.bulk_write(batch, ordered=False).upserted_count
        batch.clear()


def _rows_from_json(path: Path) -> Iterator[_Row]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["reviews"] if isinstance(payload, dict) else payload
    for item in items:
        yield _Row(fields=item)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?"
    return conn.execute(query, ("table", name)).fetchone() is not None


def _rows_from_sqlite(conn: sqlite3.Connection) -> Iterator[_Row]:
    analysis: dict[str, dict[str, Any]] = {}
    topics: dict[str, list[dict[str, Any]]] = {}
    if _has_table(conn, "review_analysis"):
        for a in conn.execute("SELECT * FROM review_analysis"):
            analysis[a["review_id"]] = {k: a[k] for k in _ANALYSIS_FIELDS}
    if _has_table(conn, "review_topics"):
        for t in conn.execute("SELECT review_id, topic, polarity, evidence FROM review_topics"):
            topics.setdefault(t["review_id"], []).append(
                {"topic": t["topic"], "polarity": t["polarity"], "evidence": t["evidence"]}
            )
    for r in conn.execute("SELECT * FROM reviews"):
        row = dict(r)
        yield _Row(fields=row, analysis=analysis.get(row["id"]), topics=topics.get(row["id"]))


def _import_property_meta(conn: sqlite3.Connection) -> None:
    props = collection(PROPERTIES_COLL)
    for p in conn.execute("SELECT id, booking_score, booking_review_count, updated_at FROM properties"):
        values = {k: p[k] for k in ("booking_score", "booking_review_count") if p[k] is not None}
        if values and p["id"] in PROPERTIES_BY_ID:
            props.update_one({"_id": p["id"]}, {"$set": {**values, "updated_at": p["updated_at"]}})


def _import_runs(conn: sqlite3.Connection) -> int:
    """Copy audit rows once; matched on (run_id, property_id) so re-imports add nothing."""
    runs = collection(SCRAPE_RUNS)
    existing = {(d["run_id"], d.get("property_id")) for d in runs.find({}, {"run_id": 1, "property_id": 1})}
    docs = []
    for r in conn.execute("SELECT * FROM scrape_runs"):
        row = dict(r)
        if (row["run_id"], row["property_id"]) in existing:
            continue
        error = row.pop("error", None)
        row.pop("id", None)
        row["errors"] = json.loads(error) if error else []
        if row.get("status") == "running":  # a legacy run that was interrupted
            row["status"] = "failed"
            row["errors"].append("interrupted: run did not finish")
        docs.append(row)
    if docs:
        runs.insert_many(docs)
    return len(docs)
