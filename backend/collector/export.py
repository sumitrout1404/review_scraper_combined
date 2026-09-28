"""Export collected reviews (with embedded analysis, when present) to JSON and CSV sample files.

``reviews.json`` is also a valid input for ``python -m collector import --from``.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from collector.normalise import utc_now_iso
from db import PROPERTIES, REVIEWS, collection

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = (
    "id", "property_id", "property_name", "review_date", "score", "title", "positive_text", "negative_text",
    "language", "stay_month", "nights", "room_type", "traveller_type", "reviewer_country", "hotel_response",
    "helpful_votes", "source_review_id", "content_hash", "sentiment", "sentiment_score", "topics",
    "first_seen_at", "last_seen_at", "updated_at",
)
_FORMULA_PREFIXES = ("=", "+", "-", "@", chr(9), chr(13))  # also tab and carriage return


def _csv_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in text cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def load_export_rows() -> list[dict[str, Any]]:
    """Reviews with property name, sentiment and topic tags, newest first."""
    names = {p["_id"]: p.get("name") for p in collection(PROPERTIES).find({}, {"name": 1})}
    rows: list[dict[str, Any]] = []
    for doc in collection(REVIEWS).find({}).sort([("review_date", -1), ("_id", 1)]):
        analysis = doc.get("analysis") or {}
        row = {
            **doc,
            "id": doc["_id"],
            "property_name": names.get(doc.get("property_id")),
            "sentiment": analysis.get("sentiment"),
            "sentiment_score": analysis.get("sentiment_score"),
            "topics": sorted(f"{t.get('topic')}:{t.get('polarity')}" for t in doc.get("topics") or []),
        }
        rows.append({c: row.get(c) for c in EXPORT_COLUMNS})
    return rows


def export_samples(out_dir: Path) -> tuple[Path, Path, int]:
    """Write ``reviews.json`` and ``reviews.csv`` to ``out_dir``; returns (json, csv, count)."""
    rows = load_export_rows()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = out_dir / "reviews.json", out_dir / "reviews.csv"
    payload = {"exported_at": utc_now_iso(), "source": "booking.com", "count": len(rows), "reviews": rows}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            flat = {**row, "topics": ";".join(row["topics"])}
            writer.writerow({k: _csv_safe(v) for k, v in flat.items()})
    logger.info("exported %d reviews to %s and %s", len(rows), json_path, csv_path)
    return json_path, csv_path, len(rows)
