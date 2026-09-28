"""Scheduled collection + analysis, run by Vercel Cron through GET /api/cron/collect.

This is the only code path in the API that writes to the database (via the collector,
the analysis step, and a "skipped" audit row). It runs under the shared DB lease so
overlapping invocations (or a CLI run) are skipped. The collector and analysis
packages are imported lazily so the read API keeps working if they fail to import.
"""

from __future__ import annotations

import dataclasses
import importlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import PyMongoError

from db import SCRAPE_RUNS, LeaseHeldError, collection, db_lease

from ..config import Settings

logger = logging.getLogger(__name__)

LEASE_NAME = "collect"
PROPERTY_FIELDS = ("property_id", "status", "watermark_date", "reviews_new", "reviews_updated", "pages_fetched")


class JobUnavailable(RuntimeError):
    """The collector or analysis package could not be imported."""


def _load(module: str, attr: str) -> Callable[..., Any]:
    try:
        return getattr(importlib.import_module(module), attr)
    except (ImportError, AttributeError) as exc:
        raise JobUnavailable(f"{module}.{attr} is not available") from exc


def _as_dict(result: Any) -> dict[str, Any]:
    """Accept a dict, dataclass or pydantic model from the collector/analysis."""
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return dataclasses.asdict(result)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(vars(result))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_skip(run_id: str) -> None:
    """Best-effort audit row so skipped invocations are visible in /api/scrape-runs."""
    now = _utc_now()
    try:
        collection(SCRAPE_RUNS).insert_one(
            {"run_id": run_id, "property_id": None, "trigger": "cron", "started_at": now, "finished_at": now,
             "status": "skipped", "mode": "incremental", "errors": ["lease held by another run"]}
        )  # fmt: skip
    except PyMongoError as exc:
        logger.warning("Could not record skipped cron run: %s", type(exc).__name__)


def _summarise_collection(result: dict[str, Any], fallback_run_id: str) -> dict[str, Any]:
    properties = [{key: _as_dict(p).get(key) for key in PROPERTY_FIELDS} for p in result.get("properties") or []]
    return {
        "run_id": result.get("run_id") or fallback_run_id,
        "status": result.get("status") or "success",
        "properties": properties,
    }


def run_cron_job(settings: Settings, request_id: str, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Collect, then analyse within the remaining time budget. Returns the contract's JSON summary."""
    started = clock()
    run_id = f"cron-{uuid.uuid4().hex[:12]}"
    try:
        with db_lease(LEASE_NAME, ttl_s=settings.cron_lease_ttl_s):
            run_collection = _load("collector", "run_collection")
            collected = _as_dict(
                run_collection(mode="incremental", trigger="cron", time_budget_s=settings.cron_collect_budget_s)
            )
            summary = _summarise_collection(collected, run_id)
            remaining = int(settings.cron_total_budget_s - (clock() - started))
            summary["analysis"] = _run_analysis(remaining, settings)
    except LeaseHeldError:
        logger.info("Cron collect skipped: lease held request_id=%s", request_id)
        _record_skip(run_id)
        return {"run_id": run_id, "status": "skipped", "properties": [], "analysis": None}
    logger.info(
        "Cron collect finished request_id=%s run_id=%s status=%s elapsed_s=%.1f",
        request_id, summary["run_id"], summary["status"], clock() - started,
    )  # fmt: skip
    return summary


def _run_analysis(remaining_s: int, settings: Settings) -> dict[str, Any]:
    """Analyse new/changed reviews; failures here never undo a successful collection."""
    if remaining_s < settings.cron_min_analysis_s:
        return {"analysed": 0, "pending": None, "error": "no time left in this run; will continue next run"}
    try:
        run_analysis = _load("analysis", "run_analysis")
        result = _as_dict(run_analysis(method="auto", time_budget_s=remaining_s))
    except JobUnavailable as exc:
        logger.error("Analysis unavailable: %s", exc)
        return {"analysed": 0, "pending": None, "error": "analysis module unavailable"}
    except Exception:
        logger.exception("Analysis step failed")
        return {"analysed": 0, "pending": None, "error": "analysis failed; will retry next run"}
    return {"analysed": int(result.get("analysed") or 0), "pending": result.get("pending")}
