"""Data freshness: when reviews were last collected and how the last runs went."""

from __future__ import annotations

import json
from typing import Any

from db import REVIEWS, SCRAPE_RUNS

from ..db import ro

DATA_STATUSES = ["success", "partial", "degraded"]  # runs that produced data
RUN_FIELDS = (
    "run_id", "property_id", "trigger", "started_at", "finished_at", "status", "method", "mode", "watermark_date",
    "pages_fetched", "reviews_seen", "reviews_new", "reviews_updated", "reviews_rejected",
)  # fmt: skip
NEWEST_FIRST = [("started_at", -1), ("_id", -1)]


def last_scraped_at() -> str | None:
    """Finish time of the latest run that produced data, else the latest review sighting."""
    run = ro(SCRAPE_RUNS).find_one(
        {"status": {"$in": DATA_STATUSES}, "finished_at": {"$type": "string"}}, sort=[("finished_at", -1)]
    )
    if run:
        return run["finished_at"]
    review = ro(REVIEWS).find_one(
        {"last_seen_at": {"$type": "string"}}, {"last_seen_at": 1}, sort=[("last_seen_at", -1)]
    )
    return review["last_seen_at"] if review else None


def summarise_statuses(statuses: set[str]) -> str:
    """One status for a run made of per-property rows ('partial' when mixed success/failure)."""
    if len(statuses) == 1:
        return next(iter(statuses))
    if "running" in statuses:
        return "running"
    if statuses <= {"success", "degraded"}:
        return "degraded"
    return "partial"


def last_run(trigger: str | None = None) -> dict[str, Any] | None:
    """Summary of the most recent run (optionally of one trigger type)."""
    latest = ro(SCRAPE_RUNS).find_one({"trigger": trigger} if trigger else {}, {"run_id": 1}, sort=NEWEST_FIRST)
    if not latest:
        return None
    rows = list(ro(SCRAPE_RUNS).find({"run_id": latest["run_id"]}, {"started_at": 1, "finished_at": 1, "status": 1}))
    finished = [r["finished_at"] for r in rows if r.get("finished_at")]
    return {
        "run_id": latest["run_id"],
        "started_at": min(r["started_at"] for r in rows),
        "finished_at": max(finished) if finished else None,
        "status": summarise_statuses({r["status"] for r in rows}),
    }


def _run_row(doc: dict[str, Any]) -> dict[str, Any]:
    row = {k: doc.get(k) for k in RUN_FIELDS}
    errors = doc.get("errors") or doc.get("error")
    row["error"] = json.dumps(errors) if isinstance(errors, list) else errors
    return row


def recent_runs(limit: int) -> list[dict[str, Any]]:
    """Latest scrape_runs rows, newest first; ``errors`` is exposed as the contract's JSON ``error`` string."""
    return [_run_row(d) for d in ro(SCRAPE_RUNS).find({}).sort(NEWEST_FIRST).limit(limit)]
