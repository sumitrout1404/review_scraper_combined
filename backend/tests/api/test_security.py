"""HTTP hardening: headers, methods, rate limiting, error masking, docs, CORS, DB path."""

from __future__ import annotations

import pathlib
import re

import pytest

from app.config import validate
from app.security import TokenBucketLimiter


def test_security_headers(client):
    r = client.get("/api/meta")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in r.headers["permissions-policy"]
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert "strict-transport-security" not in r.headers
    assert r.headers["cache-control"] == "public, max-age=300"
    assert len(r.headers["x-request-id"]) >= 16


def test_hsts_and_no_docs_in_production(make_client):
    c = make_client(env={"ENV": "production"})
    r = c.get("/api/meta")
    assert "max-age" in r.headers["strict-transport-security"]
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_docs_available_in_development(client):
    assert client.get("/openapi.json").status_code == 200


def test_request_id_echoed(client):
    assert client.get("/api/meta", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"
    assert client.get("/api/meta", headers={"X-Request-ID": "<script>"}).headers["x-request-id"] != "<script>"


def test_only_get_allowed(client):
    for method in ("post", "put", "delete", "patch"):
        r = getattr(client, method)("/api/reviews")
        assert r.status_code == 405
        assert r.json() == {"detail": "Method not allowed"}


def test_errors_not_cached(client):
    r = client.get("/api/reviews", params={"page_size": 500})
    assert r.status_code == 422 and r.headers["cache-control"] == "no-store"


def test_generic_500_hides_details(client):
    @client.app.get("/api/boom")
    def boom():
        raise RuntimeError("secret internals")

    r = client.get("/api/boom")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
    assert "secret" not in r.text and r.headers["x-request-id"]


def test_rate_limit_returns_429(make_client):
    c = make_client(env={"RATE_LIMIT_PER_MINUTE": "3"})
    codes = [c.get("/api/topics").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = c.get("/api/topics")
    assert int(r.headers["retry-after"]) >= 1


def test_token_bucket_refills():
    now = [0.0]
    lim = TokenBucketLimiter(60, clock=lambda: now[0])
    assert all(lim.acquire("ip") == 0 for _ in range(60))
    assert lim.acquire("ip") > 0
    now[0] += 1.0
    assert lim.acquire("ip") == 0
    assert lim.acquire("other") == 0


def test_cors_allowlist(make_client):
    c = make_client(env={"CORS_ORIGINS": "https://dash.example.com"})
    ok = c.get("/api/meta", headers={"Origin": "https://dash.example.com"})
    assert ok.headers["access-control-allow-origin"] == "https://dash.example.com"
    bad = c.get("/api/meta", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in bad.headers
    star = make_client(env={"CORS_ORIGINS": "*"}).get("/api/meta", headers={"Origin": "https://x.y"})
    assert star.headers["access-control-allow-origin"] == "*"


def test_cors_default_allows_vite(client):
    r = client.options(
        "/api/reviews", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


WRITE_METHODS = re.compile(
    r"\.(insert_one|insert_many|update_one|update_many|replace_one|delete_one|delete_many|bulk_write|find_one_and_\w+|drop|create_index\w*)\("
)


def test_public_api_never_writes():
    """Only the cron job may write; every other module goes through the read-only helpers."""
    app_dir = pathlib.Path(__file__).resolve().parents[2] / "app"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if path.name != "cron_job.py" and WRITE_METHODS.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_read_helpers_use_read_only_client(monkeypatch):
    import app.db as app_db

    seen = []
    monkeypatch.setattr(app_db, "collection", lambda name, read_only=False: seen.append(read_only) or [])
    app_db.ro("reviews")
    assert seen == [True]


@pytest.mark.parametrize("value", ["$where", "a.b", "$gt"])
def test_operator_like_values_rejected(client, value):
    for params in ({"properties": value}, {"topic": value}, {"sentiment": value}):
        r = client.get("/api/reviews", params=params)
        assert r.status_code == 422, params


def test_regex_search_is_escaped(client):
    assert client.get("/api/reviews", params={"q": ".*"}).json()["total"] == 0
    assert client.get("/api/reviews", params={"q": "(unclosed"}).status_code == 200


def test_production_config_validation():
    assert validate("development", ("*",), None) == ()
    problems = validate("production", ("*",), "short")
    assert len(problems) == 2 and all("short" not in p for p in problems)
    assert validate("production", ("https://dash.example.com",), "x" * 32) == ()


def test_health_reports_config_problems_without_values(make_client):
    c = make_client(env={"ENV": "production", "CORS_ORIGINS": "*", "CRON_SECRET": "tiny-secret"})
    body = c.get("/api/health").json()
    assert body["config_ok"] is False
    assert "tiny-secret" not in str(body)
