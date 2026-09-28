"""scripts/seed_dev.py: refuses the production database and writes contract-shaped documents."""

from __future__ import annotations

import importlib.util
import pathlib

from db import REVIEWS, collection

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "seed_dev.py"


def load_seed():
    spec = importlib.util.spec_from_file_location("seed_dev", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_refuses_production_db(make_client, monkeypatch):
    make_client(reviews=[])
    monkeypatch.setenv("MONGODB_DB", "scraper")
    assert load_seed().main(["--n", "5"]) == 2


def test_seed_writes_dev_data_the_api_can_read(make_client, monkeypatch):
    c = make_client(reviews=[])
    seed = load_seed()
    assert seed.main(["--n", "50"]) == 0
    assert collection(REVIEWS).count_documents({}) == 50
    doc = collection(REVIEWS).find_one({"analysis": {"$exists": True}})
    assert {"sentiment", "method", "content_hash"} <= set(doc["analysis"])
    body = c.get("/api/reviews", params={"page_size": 5}).json()
    assert body["total"] == 50 and len(body["items"]) == 5
