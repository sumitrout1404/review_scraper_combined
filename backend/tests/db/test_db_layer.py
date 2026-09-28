import pytest

import db
from db import LeaseHeldError, collection, db_lease, ensure_indexes


@pytest.fixture(autouse=True)
def mock_mongo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MONGODB_URI", "mongomock://localhost")
    monkeypatch.delenv("MONGODB_URI_READONLY", raising=False)
    monkeypatch.setenv("MONGODB_DB", "test_db")
    monkeypatch.delenv("MONGODB_COLLECTION_PREFIX", raising=False)
    db.reset_clients()
    yield
    db.reset_clients()


def test_collections_are_prefixed() -> None:
    assert collection("reviews").name == "scraper_reviews"
    assert collection("reviews").database.name == "test_db"


def test_prefix_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGODB_COLLECTION_PREFIX", "x_")
    assert collection("topics").name == "x_topics"


def test_ensure_indexes_is_idempotent() -> None:
    ensure_indexes()
    ensure_indexes()
    names = set(collection("reviews").index_information())
    assert {"property_date", "review_date", "topics", "uniq_source_review"} <= names


def test_lease_is_exclusive_and_released() -> None:
    with db_lease("collect"), pytest.raises(LeaseHeldError), db_lease("collect"):
        pass
    with db_lease("collect"):
        pass
    assert collection("job_locks").count_documents({}) == 0


def test_expired_lease_is_taken_over() -> None:
    collection("job_locks").insert_one(
        {"_id": "collect", "holder": "dead", "acquired_at": "2000-01-01T00:00:00Z",
         "expires_at": "2000-01-01T00:15:00Z"})
    with db_lease("collect") as holder:
        assert collection("job_locks").find_one({"_id": "collect"})["holder"] == holder


def test_missing_uri_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGODB_URI")
    monkeypatch.setattr("db.client._load_dotenv", lambda: None)
    db.reset_clients()
    with pytest.raises(db.DatabaseNotConfigured):
        collection("reviews")


def test_mock_read_only_and_write_clients_share_data() -> None:
    """With mongomock, read_only must not get its own empty in-memory store."""
    collection("reviews").insert_one({"_id": "r1", "score": 9.0})
    assert collection("reviews", read_only=True).find_one({"_id": "r1"}) is not None
