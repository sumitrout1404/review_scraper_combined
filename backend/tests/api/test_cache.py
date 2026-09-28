"""The response cache must speed up repeat reads without ever serving the wrong body."""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi.testclient import TestClient

from app.cache import CachedResponse, ResponseCache, cache_key, is_cacheable_path


def test_repeat_read_is_served_from_cache(client: TestClient) -> None:
    first = client.get("/api/summary")
    second = client.get("/api/summary")
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json()
    assert second.headers["content-type"].startswith("application/json")


def test_different_filters_are_cached_separately(client: TestClient) -> None:
    a = client.get("/api/reviews?properties=potts-point")
    b = client.get("/api/reviews?properties=central-sydney")
    assert b.headers["X-Cache"] == "MISS"  # not served a's body
    assert a.json() != b.json() or a.json()["total"] == b.json()["total"] == 0


def test_query_parameter_order_does_not_matter(client: TestClient) -> None:
    client.get("/api/reviews?properties=potts-point&sentiment=negative")
    again = client.get("/api/reviews?sentiment=negative&properties=potts-point")
    assert again.headers["X-Cache"] == "HIT"


def test_cron_endpoint_is_never_cached() -> None:
    assert not is_cacheable_path("/api/cron/collect")
    assert not is_cacheable_path("/api/reviews/export.csv")
    assert is_cacheable_path("/api/summary")


def test_errors_are_not_cached(client: TestClient) -> None:
    bad = client.get("/api/reviews?date_from=not-a-date")
    assert bad.status_code == 422
    assert bad.headers.get("X-Cache") is None


def test_csv_export_still_streams(client: TestClient) -> None:
    r = client.get("/api/reviews/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert r.headers.get("X-Cache") is None


def test_caching_can_be_disabled(make_client: Callable[..., TestClient]) -> None:
    c = make_client(env={"CACHE_MAX_AGE": "0"})
    assert c.get("/api/summary").headers.get("X-Cache") is None


def test_entries_expire() -> None:
    cache = ResponseCache()
    cache.set("k", CachedResponse(200, b"{}", "application/json", time.monotonic() + 60))
    assert cache.get("k") is not None
    assert cache.get("k", now=time.monotonic() + 61) is None
    assert len(cache) == 0


def test_cache_evicts_least_recently_used() -> None:
    cache = ResponseCache(max_entries=2)
    expiry = time.monotonic() + 60
    for k in ("a", "b"):
        cache.set(k, CachedResponse(200, b"{}", "application/json", expiry))
    cache.get("a")  # 'a' is now the most recently used, so 'b' should go first
    cache.set("c", CachedResponse(200, b"{}", "application/json", expiry))
    assert cache.get("a") is not None
    assert cache.get("b") is None
    assert cache.get("c") is not None


def test_cache_key_is_stable() -> None:
    assert cache_key("/api/x", "b=2&a=1") == cache_key("/api/x", "a=1&b=2")
    assert cache_key("/api/x", "") != cache_key("/api/y", "")
