"""Streaming CSV export of the review feed."""

from __future__ import annotations

import codecs
import csv
import io
from collections.abc import Iterator
from typing import Any

from .catalog import topic_labels, topic_order
from .review_search import ReviewFormatter, ReviewQuery, iter_reviews

CSV_COLUMNS = (
    "id", "property_id", "property_name", "review_date", "score", "sentiment", "title", "positive_text",
    "negative_text", "topics", "complaints", "praise", "summary", "language", "stay_month", "nights", "room_type",
    "traveller_type", "reviewer_country", "hotel_response", "sentiment_score", "analysis_method",
)  # fmt: skip
# Cells starting with these could be run as formulas by Excel/Sheets: = + - @ TAB CR.
FORMULA_PREFIXES = ("=", "+", "-", "@", chr(9), chr(13))
FLUSH_EVERY = 500
UTF8_BOM = codecs.BOM_UTF8.decode("utf-8")  # lets Excel detect UTF-8


def csv_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection by prefixing risky text cells with an apostrophe."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def flatten(item: dict[str, Any]) -> list[Any]:
    """Row values in CSV_COLUMNS order, with topics joined into single columns."""
    tags = item["topics"]
    item = {
        **item,
        "topics": "; ".join(f"{t['label']} ({'complaint' if t['polarity'] == 'negative' else 'praise'})" for t in tags),
        "complaints": "; ".join(t["label"] for t in tags if t["polarity"] == "negative"),
        "praise": "; ".join(t["label"] for t in tags if t["polarity"] == "positive"),
    }
    return [csv_safe(item.get(col)) for col in CSV_COLUMNS]


def export_filename(rq: ReviewQuery) -> str:
    parts = ["reviews"] + [d.isoformat() for d in (rq.date_from, rq.date_to) if d]
    return "_".join(parts) + ".csv"


def prepare_csv(rq: ReviewQuery) -> Iterator[str]:
    """Resolve lookups eagerly (so DB errors become a 503 before streaming starts), then return the row stream."""
    formatter = ReviewFormatter(topic_labels(), topic_order())
    return _stream(iter_reviews(rq), formatter)


def _stream(docs: Iterator[dict[str, Any]], formatter: ReviewFormatter) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    yield UTF8_BOM + _drain(buf)
    pending = 0
    for doc in docs:
        writer.writerow(flatten(formatter(doc)))
        pending += 1
        if pending >= FLUSH_EVERY:
            yield _drain(buf)
            pending = 0
    yield _drain(buf)


def _drain(buf: io.StringIO) -> str:
    out = buf.getvalue()
    buf.seek(0)
    buf.truncate(0)
    return out
