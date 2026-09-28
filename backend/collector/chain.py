"""Strategy chain: retries, one circuit breaker per strategy, quality gate, automatic fallback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from collector.errors import (
    BlockedError,
    CollectorError,
    PageQualityError,
    ResponseShapeError,
    StrategyUnavailableError,
)
from collector.fetchers.base import ReviewSource
from collector.models import RawPage, ValidatedPage, validate_candidates
from collector.properties import Property
from collector.settings import Settings
from core.circuit_breaker import CircuitBreaker
from core.retry import retry_call

logger = logging.getLogger(__name__)


class AllStrategiesFailedError(CollectorError):
    """No strategy produced an acceptable page."""

    def __init__(self, errors: list[str], *, degraded: bool) -> None:
        super().__init__("; ".join(errors) or "no strategy available")
        self.errors = errors
        #: True when the failure points at blocking or page/API drift rather than a plain outage
        self.degraded = degraded


@dataclass
class FetchedPage:
    source: ReviewSource
    raw: RawPage
    validated: ValidatedPage


def check_page(prop: Property, raw: RawPage, max_reject_ratio: float) -> ValidatedPage:
    """Validate a raw page; raise if it looks like a page/API change rather than real data."""
    if raw.found == 0:
        if raw.offset == 0:
            raise ResponseShapeError(f"first page parsed to 0 reviews (Booking total={raw.total_count})")
        return ValidatedPage(records=[], rejected=0, errors=[])  # end of the list
    validated = validate_candidates(prop.id, raw.candidates)
    if validated.reject_ratio > max_reject_ratio:
        raise PageQualityError(
            f"{validated.rejected}/{raw.found} records rejected ({'; '.join(validated.errors[:2])})"
        )
    return validated


class StrategyChain:
    """Tries each strategy in order until one returns a page that passes the quality gate."""

    def __init__(self, sources: list[ReviewSource], settings: Settings,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.sources = sources
        self._settings = settings
        self._sleep = sleep
        self.breakers = {
            s.name: CircuitBreaker(
                f"booking.com/{s.name}",
                failure_threshold=settings.breaker_failure_threshold,
                recovery_timeout=settings.breaker_recovery_s,
            )
            for s in sources
        }
        self._unavailable: set[str] = set()

    def fetch(self, prop: Property, offset: int) -> tuple[FetchedPage, list[str]]:
        """Return the first acceptable page plus the errors of strategies that failed before it."""
        errors: list[str] = []
        degraded = True  # stays True if every strategy was open/blocked/drifted
        for source in self.sources:
            if source.name in self._unavailable:
                continue
            breaker = self.breakers[source.name]
            if not breaker.allow_request():
                errors.append(f"{source.name}: circuit open")
                continue
            try:
                raw = self._fetch_with_retry(source, prop, offset)
                validated = check_page(prop, raw, self._settings.max_reject_ratio)
            except StrategyUnavailableError as exc:
                self._unavailable.add(source.name)
                breaker.record_success()  # release a half-open slot; unavailability is not Booking's fault
                errors.append(f"{source.name}: unavailable ({exc})")
                continue
            except (BlockedError, ResponseShapeError, PageQualityError) as exc:
                breaker.record_failure()
                errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
                logger.warning("%s offset=%d %s failed: %s", prop.id, offset, source.name, exc)
                continue
            except Exception as exc:  # noqa: BLE001 - transient after retries, or unexpected
                breaker.record_failure()
                degraded = False
                errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
                logger.warning("%s offset=%d %s failed: %s", prop.id, offset, source.name, exc)
                continue
            breaker.record_success()
            return FetchedPage(source=source, raw=raw, validated=validated), errors
        raise AllStrategiesFailedError(errors, degraded=degraded)

    def _fetch_with_retry(self, source: ReviewSource, prop: Property, offset: int) -> RawPage:
        def on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            logger.info("%s %s offset=%d attempt %d failed (%s); retrying in %.1fs",
                        prop.id, source.name, offset, attempt, exc, delay)

        kwargs = {"sleep": self._sleep} if self._sleep else {}
        return retry_call(
            lambda: source.fetch_page(prop, offset),
            attempts=self._settings.retry_attempts,
            base_delay=self._settings.retry_base_delay_s,
            max_delay=self._settings.retry_max_delay_s,
            on_retry=on_retry,
            **kwargs,
        )

    def close(self) -> None:
        for source in self.sources:
            try:
                source.close()
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.debug("closing %s: %s", source.name, exc)
