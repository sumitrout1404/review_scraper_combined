"""Collection orchestration: per-property paging with watermark stop, backfill resume and time budget.

Public entrypoint: :func:`run_collection`. It does not take the DB lease – callers
(CLI ``run`` and the cron router) wrap it in ``db.db_lease("collect", ttl_s=900)``.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from collector.chain import AllStrategiesFailedError, StrategyChain
from collector.fetchers.base import ReviewSource, Throttle
from collector.fetchers.browser import BrowserSession
from collector.fetchers.registry import build_sources
from collector.models import PropertyMeta
from collector.normalise import utc_now_iso
from collector.properties import PROPERTIES, Property, select_properties
from collector.settings import Settings
from collector.store import ReviewStore
from core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

Mode = Literal["incremental", "full"]
Trigger = Literal["cron", "cli", "manual"]
_STATUS_RANK = {"success": 0, "partial": 1, "degraded": 2, "failed": 3}


@dataclass
class PropertyReport:
    """Outcome for one property in one run (mirrors a ``scrape_runs`` row)."""

    property_id: str
    status: str = "success"
    method: str | None = None
    watermark_date: str | None = None
    pages_fetched: int = 0
    reviews_seen: int = 0
    reviews_new: int = 0
    reviews_updated: int = 0
    reviews_rejected: int = 0
    stop_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    def downgrade(self, status: str) -> None:
        """Move to a worse status, never a better one."""
        if _STATUS_RANK[status] > _STATUS_RANK[self.status]:
            self.status = status


@dataclass
class RunReport:
    run_id: str
    mode: str
    trigger: str
    started_at: str
    finished_at: str | None = None
    status: str = "success"
    properties: list[PropertyReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return asdict(self)

    @property
    def any_collected(self) -> bool:
        return any(p.pages_fetched for p in self.properties)


@dataclass
class _Phase:
    start_offset: int
    max_pages: int
    stop_on_known: bool
    cutoff: date | None  # stop after a page containing a review older than this


class _Deadline:
    """Tracks the optional time budget; reserves one average page duration of headroom."""

    def __init__(self, budget_s: float | None, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._end = clock() + budget_s if budget_s is not None else None
        self._page_times: list[float] = []

    def record(self, seconds: float) -> None:
        self._page_times.append(seconds)

    def exhausted(self) -> bool:
        if self._end is None:
            return False
        headroom = sum(self._page_times[-5:]) / len(self._page_times[-5:]) if self._page_times else 0.0
        return self._clock() + headroom >= self._end


class PropertyCollector:
    """Collects one property through the strategy chain and writes accepted pages."""

    def __init__(self, store: ReviewStore, chain: StrategyChain, settings: Settings,
                 deadline: _Deadline, clock: Callable[[], float] = time.monotonic) -> None:
        self._store = store
        self._chain = chain
        self._settings = settings
        self._deadline = deadline
        self._clock = clock

    def collect(self, prop: Property, report: PropertyReport, mode: Mode, max_pages: int | None) -> None:
        watermark = report.watermark_date
        cap = max_pages or (self._settings.full_max_pages if mode == "full" else self._settings.backfill_max_pages)
        if mode == "full":
            self._page_through(prop, report, _Phase(0, cap, stop_on_known=False, cutoff=None))
            return
        cutoff = (date.fromisoformat(watermark) - timedelta(days=self._settings.watermark_overlap_days)
                  if watermark else None)
        total = self._page_through(prop, report, _Phase(0, cap, stop_on_known=watermark is not None, cutoff=cutoff))
        if report.stop_reason in {"known_page", "older_than_watermark"} and total and max_pages is None:
            self._resume_backfill(prop, report, total, cap)

    def _resume_backfill(self, prop: Property, report: PropertyReport, total: int, cap: int) -> None:
        """If an earlier backfill was cut short, continue from where the stored history ends."""
        stored = self._store.count_reviews(prop.id)
        if stored >= total - self._settings.backfill_tolerance:
            return
        page = self._settings.page_size
        start = max(0, (stored // page - 1) * page)  # one page of overlap for offset drift
        logger.info("%s: resuming backfill at offset %d (stored %d of %d)", prop.id, start, stored, total)
        self._page_through(prop, report, _Phase(start, cap, stop_on_known=False, cutoff=None))

    def _page_through(self, prop: Property, report: PropertyReport, phase: _Phase) -> int | None:
        """Fetch pages newest-first from ``phase.start_offset``; returns Booking's total if seen."""
        offset, pages, total = phase.start_offset, 0, None
        methods: list[str] = [m for m in (report.method or "").split("+") if m]
        while True:
            if pages >= phase.max_pages:
                report.stop_reason = "max_pages"
                return total
            if self._deadline.exhausted():
                report.stop_reason = "time_budget"
                report.downgrade("partial")
                report.errors.append("time budget exhausted; next run resumes")
                return total
            started = self._clock()
            try:
                fetched, errors = self._chain.fetch(prop, offset)
            except AllStrategiesFailedError as exc:
                report.errors.extend(exc.errors)
                report.stop_reason = "error"
                if exc.degraded:
                    report.downgrade("degraded")
                else:
                    report.downgrade("partial" if report.pages_fetched else "failed")
                return total
            report.errors.extend(errors)
            self._deadline.record(self._clock() - started)
            pages += 1
            report.pages_fetched += 1
            if fetched.source.name not in methods:
                methods.append(fetched.source.name)
                report.method = "+".join(methods)
            raw, validated = fetched.raw, fetched.validated
            total = raw.total_count if raw.total_count is not None else total
            self._store_meta(prop, raw.meta, raw.total_count)
            report.reviews_rejected += validated.rejected
            if validated.errors:
                logger.info("%s offset=%d: %d rejected (%s)", prop.id, offset, validated.rejected, validated.errors[0])
            if not validated.records:
                report.stop_reason = "end_of_list"
                return total
            result = self._store.upsert_page(validated.records, utc_now_iso())
            report.reviews_seen += len(validated.records)
            report.reviews_new += result.new
            report.reviews_updated += result.updated
            logger.info("%s offset=%d via %s: %d reviews (%d new, %d updated)", prop.id, offset,
                        fetched.source.name, len(validated.records), result.new, result.updated)
            if phase.stop_on_known and result.new == 0:
                report.stop_reason = "known_page"
                return total
            if phase.cutoff and any(r.review_date < phase.cutoff for r in validated.records):
                report.stop_reason = "older_than_watermark"
                return total
            offset += raw.found
            if raw.found < fetched.source.page_size or (total is not None and offset >= total):
                report.stop_reason = "end_of_list"
                return total

    def _store_meta(self, prop: Property, meta: PropertyMeta, total: int | None) -> None:
        merged = PropertyMeta(
            booking_score=meta.booking_score,
            booking_review_count=total if total is not None else meta.booking_review_count,
        )
        self._store.update_property_meta(prop.id, merged, utc_now_iso())


def _probe_headline(store: ReviewStore, session: BrowserSession | None, breaker: CircuitBreaker,
                    prop: Property, deadline: _Deadline) -> None:
    """Best effort: Booking's headline score lives only on the (WAF-protected) HTML page."""
    if session is None or deadline.exhausted() or not breaker.allow_request():
        return
    try:
        meta = session.headline(prop)
    except Exception as exc:  # noqa: BLE001 - optional enrichment must never fail a run
        breaker.record_failure()
        logger.warning("%s: headline score probe failed: %s", prop.id, exc)
        return
    breaker.record_success()
    # The GraphQL total is authoritative for the count; only the score comes from the page.
    store.update_property_meta(prop.id, PropertyMeta(booking_score=meta.booking_score), utc_now_iso())
    logger.info("%s: Booking headline score %s", prop.id, meta.booking_score)


def run_collection(
    *,
    mode: Mode = "incremental",
    trigger: Trigger = "cli",
    time_budget_s: float | None = None,
    properties: list[str] | None = None,
    max_pages: int | None = None,
    settings: Settings | None = None,
    sources: list[ReviewSource] | None = None,
) -> RunReport:
    """Collect reviews for the selected properties and record one ``scrape_runs`` row each.

    Never raises for a single property's failure; the returned report carries per-property
    status (``success`` / ``partial`` / ``degraded`` / ``failed``) and the overall worst status.
    ``settings`` and ``sources`` are injectable for tests; by default they come from the environment.
    """
    if mode not in ("incremental", "full"):
        raise ValueError(f"invalid mode {mode!r}")
    settings = settings or Settings.from_env()
    selected = select_properties(properties)
    store = ReviewStore()
    store.init(PROPERTIES, utc_now_iso())
    stale = store.fail_stale_runs(settings.stale_run_after_s, utc_now_iso())
    if stale:
        logger.warning("marked %d stale 'running' scrape_runs rows as failed", stale)

    report = RunReport(run_id=uuid.uuid4().hex, mode=mode, trigger=trigger, started_at=utc_now_iso())
    deadline = _Deadline(time_budget_s, time.monotonic)
    throttle = Throttle(settings.request_delay_s, settings.request_jitter_s)
    session: BrowserSession | None = None
    if sources is None:
        sources, session = build_sources(settings, throttle)
    chain = StrategyChain(sources, settings)
    collector = PropertyCollector(store, chain, settings, deadline)
    meta_breaker = CircuitBreaker("booking.com/headline_probe", failure_threshold=2,
                                  recovery_timeout=settings.breaker_recovery_s)
    logger.info("run %s: mode=%s trigger=%s strategies=%s", report.run_id, mode, trigger,
                [s.name for s in sources])
    try:
        for prop in selected:
            report.properties.append(_collect_one(store, collector, prop, report, mode, max_pages))
            if settings.probe_headline_score:
                _probe_headline(store, session, meta_breaker, prop, deadline)
    finally:
        chain.close()
    report.finished_at = utc_now_iso()
    report.status = max((p.status for p in report.properties), key=_STATUS_RANK.__getitem__, default="success")
    logger.info("run %s finished: %s", report.run_id, report.status)
    return report


def _collect_one(store: ReviewStore, collector: PropertyCollector, prop: Property, run: RunReport,
                 mode: Mode, max_pages: int | None) -> PropertyReport:
    """Collect one property in isolation: any exception is contained and recorded."""
    watermark = store.watermark(prop.id)
    report = PropertyReport(property_id=prop.id, watermark_date=watermark)
    row_id = store.start_run(run_id=run.run_id, property_id=prop.id, trigger=run.trigger, mode=mode,
                             watermark=watermark, now=utc_now_iso())
    try:
        collector.collect(prop, report, mode, max_pages)
    except Exception as exc:  # noqa: BLE001 - per-property isolation
        logger.exception("%s: unexpected failure", prop.id)
        report.errors.append(f"unexpected: {type(exc).__name__}: {exc}")
        report.downgrade("partial" if report.pages_fetched else "failed")
    report.errors = list(dict.fromkeys(report.errors))[:20]
    store.finish_run(
        row_id, status=report.status, method=report.method, pages_fetched=report.pages_fetched,
        reviews_seen=report.reviews_seen, reviews_new=report.reviews_new,
        reviews_updated=report.reviews_updated, reviews_rejected=report.reviews_rejected,
        errors=report.errors, now=utc_now_iso(),
    )
    logger.info("%s: %s (%d pages, %d new, %d updated, %d rejected, stop=%s)", prop.id, report.status,
                report.pages_fetched, report.reviews_new, report.reviews_updated, report.reviews_rejected,
                report.stop_reason)
    return report
