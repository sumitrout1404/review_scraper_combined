"""Pipeline behaviour with fake strategies: paging, stop rules, fallback, degraded detection."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta

from collector.errors import BlockedError, TransientFetchError
from collector.fetchers.base import ReviewSource
from collector.models import RawPage
from collector.pipeline import run_collection
from collector.properties import Property
from collector.settings import Settings
from db import REVIEWS, SCRAPE_RUNS, collection

SETTINGS = replace(Settings(), request_delay_s=0, request_jitter_s=0, retry_base_delay_s=0.001,
                   retry_max_delay_s=0.001, probe_headline_score=False, page_size=3)


def _candidate(i: int, day: date) -> dict:
    return {"source_review_id": f"rev{i:05d}", "score": 8.0, "title": None, "positive_text": f"good {i}",
            "negative_text": None, "language": "en", "review_date": day}


class FakeSource(ReviewSource):
    """Serves a newest-first list of candidates; optional per-call failure injection."""

    page_size = 3

    def __init__(self, name: str, items: list[dict], fail: list[Exception] | None = None, total: int | None = None):
        self.name = name
        self.items = items
        self.fail = list(fail or [])
        self.total = len(items) if total is None else total
        self.calls: list[int] = []

    def fetch_page(self, prop: Property, offset: int) -> RawPage:
        self.calls.append(offset)
        if self.fail:
            raise self.fail.pop(0)
        return RawPage(strategy=self.name, offset=offset, candidates=self.items[offset:offset + self.page_size],
                       total_count=self.total)


def _history(n: int, newest: date = date(2026, 9, 27)) -> list[dict]:
    return [_candidate(n - i, newest - timedelta(days=i)) for i in range(n)]


def _run(sources, **kw):
    return run_collection(properties=["potts-point"], settings=SETTINGS, sources=sources, **kw)


def _runs() -> list[dict]:
    return list(collection(SCRAPE_RUNS).find().sort("_id", 1))


def _count() -> int:
    return collection(REVIEWS).count_documents({})


def test_full_backfill_pages_to_end():
    src = FakeSource("http_graphql", _history(8))
    report = _run([src], mode="full")
    prop = report.properties[0]
    assert report.status == "success" and prop.reviews_new == 8
    assert src.calls == [0, 3, 6]
    assert prop.stop_reason == "end_of_list"
    row = _runs()[-1]
    assert row["status"] == "success" and row["method"] == "http_graphql" and row["mode"] == "full"


def test_incremental_stops_at_known_page_and_is_idempotent():
    items = _history(9)
    _run([FakeSource("http_graphql", items)], mode="full")
    new_items = [_candidate(100, date(2026, 9, 28))] + items
    src = FakeSource("http_graphql", new_items)
    report = _run([src])
    prop = report.properties[0]
    assert prop.reviews_new == 1
    assert src.calls == [0, 3]  # page 2 is fully known -> stop
    assert prop.stop_reason == "known_page"
    assert prop.watermark_date == "2026-09-27"
    assert _runs()[-1]["watermark_date"] == "2026-09-27"


def test_incremental_stops_when_page_older_than_watermark():
    # Watermark 2026-09-27; new items interleaved so no page is "fully known", but dates get old.
    _run([FakeSource("http_graphql", _history(1))], mode="full")
    fresh = [_candidate(200 + i, date(2026, 9, 27) - timedelta(days=i)) for i in range(12)]
    src = FakeSource("http_graphql", fresh)
    report = _run([src])
    assert report.properties[0].stop_reason == "older_than_watermark"
    assert src.calls == [0]  # first page already reaches 2026-09-25 < watermark - 1 day


def test_transient_errors_are_retried():
    src = FakeSource("http_graphql", _history(2), fail=[TransientFetchError("HTTP 503")])
    report = _run([src], mode="full")
    assert report.status == "success" and src.calls == [0, 0]


def test_blocked_primary_falls_back_to_next_strategy():
    blocked = FakeSource("http_graphql", [], fail=[BlockedError("challenge")] * 10)
    browser = FakeSource("browser_graphql", _history(12))
    report = _run([blocked, browser], mode="full")
    prop = report.properties[0]
    assert prop.status == "success" and prop.reviews_new == 12
    assert prop.method == "browser_graphql"
    assert any("BlockedError" in e for e in prop.errors)
    # breaker (threshold 3) opened, so the blocked strategy was not hammered on every page
    assert len(blocked.calls) == SETTINGS.breaker_failure_threshold


def test_zero_parse_first_page_is_degraded_and_writes_nothing():
    _run([FakeSource("http_graphql", _history(3))], mode="full")
    before = _count()
    report = _run([FakeSource("http_graphql", [], total=2459)])
    assert report.properties[0].status == "degraded"
    assert _count() == before
    assert "0 reviews" in _runs()[-1]["errors"][0]


def test_high_reject_ratio_is_degraded():
    junk = [{**c, "score": None} for c in _history(3)]
    report = _run([FakeSource("http_graphql", junk)], mode="full")
    prop = report.properties[0]
    assert prop.status == "degraded" and _count() == 0
    assert any("rejected" in e for e in prop.errors)


def test_outage_after_some_pages_is_partial():
    class Flaky(FakeSource):
        def fetch_page(self, prop, offset):
            if offset >= 3:
                raise TransientFetchError("timeout")
            return super().fetch_page(prop, offset)

    report = _run([Flaky("http_graphql", _history(9))], mode="full")
    prop = report.properties[0]
    assert prop.status == "partial" and prop.reviews_new == 3


def test_time_budget_stops_cleanly_as_partial():
    report = _run([FakeSource("http_graphql", _history(9))], mode="full", time_budget_s=0)
    prop = report.properties[0]
    assert prop.status == "partial" and prop.stop_reason == "time_budget" and prop.pages_fetched == 0


def test_one_failing_property_does_not_stop_others():
    class Boom(FakeSource):
        def fetch_page(self, prop, offset):
            if prop.id == "potts-point":
                raise RuntimeError("unexpected bug")
            return super().fetch_page(prop, offset)

    report = run_collection(properties=["potts-point", "darling-harbour"], mode="full",
                            settings=SETTINGS, sources=[Boom("http_graphql", _history(2))])
    statuses = {p.property_id: p.status for p in report.properties}
    assert statuses == {"potts-point": "failed", "darling-harbour": "success"}
    assert report.status == "failed"
    assert {r["property_id"] for r in _runs()} == {"potts-point", "darling-harbour"}
    assert len({r["run_id"] for r in _runs()}) == 1


def test_report_is_json_serialisable():
    report = _run([FakeSource("http_graphql", _history(2))])
    assert json.loads(json.dumps(report.to_dict()))["properties"][0]["property_id"] == "potts-point"
