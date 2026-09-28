"""GET /api/cron/collect: auth, lease, orchestration (collector/analysis are stubbed)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from db import db_lease

SECRET = "s" * 40
AUTH = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Install fake ``collector`` and ``analysis`` modules recording their calls."""
    calls: dict[str, list[dict[str, Any]]] = {"collect": [], "analyse": []}

    def run_collection(**kwargs: Any) -> dict[str, Any]:
        calls["collect"].append(kwargs)
        return {
            "run_id": "run-abc",
            "status": "success",
            "properties": [
                {"property_id": "potts-point", "status": "success", "watermark_date": "2026-01-09",
                 "reviews_new": 3, "reviews_updated": 1, "pages_fetched": 2, "internal": "not exposed"}
            ],
        }  # fmt: skip

    def run_analysis(**kwargs: Any) -> dict[str, Any]:
        calls["analyse"].append(kwargs)
        return {"analysed": 3, "pending": 0}

    monkeypatch.setitem(sys.modules, "collector", types.SimpleNamespace(run_collection=run_collection))
    monkeypatch.setitem(sys.modules, "analysis", types.SimpleNamespace(run_analysis=run_analysis))
    return calls


def test_cron_unconfigured_returns_503(client):
    r = client.get("/api/cron/collect", headers=AUTH)
    assert r.status_code == 503
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": SECRET}])
def test_cron_rejects_bad_auth(make_client, stubs, headers):
    c = make_client(env={"CRON_SECRET": SECRET})
    r = c.get("/api/cron/collect", headers=headers)
    assert r.status_code == 401
    assert r.headers["cache-control"] == "no-store"
    assert stubs["collect"] == []


def test_cron_runs_collection_then_analysis(make_client, stubs):
    c = make_client(env={"CRON_SECRET": SECRET})
    r = c.get("/api/cron/collect", headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["run_id"] == "run-abc" and body["status"] == "success"
    assert body["properties"] == [
        {"property_id": "potts-point", "status": "success", "watermark_date": "2026-01-09",
         "reviews_new": 3, "reviews_updated": 1, "pages_fetched": 2}
    ]  # fmt: skip
    assert body["analysis"] == {"analysed": 3, "pending": 0}
    assert stubs["collect"] == [{"mode": "incremental", "trigger": "cron", "time_budget_s": 200}]
    assert stubs["analyse"][0]["method"] == "auto" and 0 < stubs["analyse"][0]["time_budget_s"] <= 280


def test_cron_skips_when_lease_held(make_client, stubs):
    c = make_client(env={"CRON_SECRET": SECRET})
    with db_lease("collect", ttl_s=60):
        r = c.get("/api/cron/collect", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"
    assert stubs["collect"] == []
    runs = c.get("/api/scrape-runs", params={"limit": 1}).json()
    assert runs[0]["status"] == "skipped" and runs[0]["trigger"] == "cron"


def test_cron_lease_released_after_run(make_client, stubs):
    c = make_client(env={"CRON_SECRET": SECRET})
    assert c.get("/api/cron/collect", headers=AUTH).json()["status"] == "success"
    assert c.get("/api/cron/collect", headers=AUTH).json()["status"] == "success"
    assert len(stubs["collect"]) == 2


def test_cron_collector_missing_degrades(make_client, monkeypatch):
    monkeypatch.setitem(sys.modules, "collector", types.SimpleNamespace())  # no run_collection
    c = make_client(env={"CRON_SECRET": SECRET})
    r = c.get("/api/cron/collect", headers=AUTH)
    assert r.status_code == 503
    assert "not available" in r.json()["detail"]


def test_cron_analysis_failure_keeps_collection_result(make_client, stubs, monkeypatch):
    def broken(**kwargs: Any) -> None:
        raise RuntimeError("groq down")

    monkeypatch.setitem(sys.modules, "analysis", types.SimpleNamespace(run_analysis=broken))
    c = make_client(env={"CRON_SECRET": SECRET})
    body = c.get("/api/cron/collect", headers=AUTH).json()
    assert body["status"] == "success"
    assert body["analysis"]["analysed"] == 0 and "retry" in body["analysis"]["error"]
    assert "groq" not in str(body)
