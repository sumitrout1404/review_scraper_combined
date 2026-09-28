import csv
import json
import sqlite3
from datetime import date

from collector.export import export_samples
from collector.importer import import_reviews
from collector.models import ReviewRecord
from db import PROPERTIES, REVIEWS, SCRAPE_RUNS, collection


def _seed(store) -> None:
    store.upsert_page([
        ReviewRecord(property_id="potts-point", source_review_id="abc12345", score=8.0, positive_text="Great",
                     negative_text="=HYPERLINK('x')", review_date=date(2026, 9, 1)),
        ReviewRecord(property_id="darling-harbour", source_review_id="def67890", score=4.0,
                     negative_text="Dirty", review_date=date(2026, 9, 2)),
    ], "2026-09-28T00:00:00Z")


def test_export_writes_json_and_formula_safe_csv(store, tmp_path):
    _seed(store)
    json_path, csv_path, count = export_samples(tmp_path)
    assert count == 2
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert [r["id"] for r in payload["reviews"]] == ["def67890", "abc12345"]  # newest first
    assert payload["reviews"][0]["property_name"] == "Azzurro Darling Harbour"
    with csv_path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[1]["negative_text"].startswith("'=")


def test_json_export_round_trips_through_import(store, tmp_path):
    _seed(store)
    json_path, _, _ = export_samples(tmp_path)
    collection(REVIEWS).delete_many({})
    stats = import_reviews(json_path)
    assert (stats.reviews_read, stats.reviews_inserted, stats.reviews_rejected) == (2, 2, 0)
    assert collection(REVIEWS).find_one({"_id": "abc12345"})["first_seen_at"] == "2026-09-28T00:00:00Z"
    again = import_reviews(json_path)
    assert again.reviews_inserted == 0 and collection(REVIEWS).count_documents({}) == 2


def _legacy_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE properties (id TEXT PRIMARY KEY, booking_score REAL, booking_review_count INTEGER, updated_at TEXT);
        CREATE TABLE reviews (id TEXT PRIMARY KEY, property_id TEXT, source_review_id TEXT, content_hash TEXT,
            score REAL, title TEXT, positive_text TEXT, negative_text TEXT, language TEXT, review_date TEXT,
            stay_month TEXT, nights INTEGER, room_type TEXT, traveller_type TEXT, reviewer_country TEXT,
            hotel_response TEXT, helpful_votes INTEGER, first_seen_at TEXT, last_seen_at TEXT, updated_at TEXT);
        CREATE TABLE scrape_runs (id INTEGER PRIMARY KEY, run_id TEXT, property_id TEXT, trigger TEXT,
            started_at TEXT, finished_at TEXT, status TEXT, method TEXT, mode TEXT, watermark_date TEXT,
            pages_fetched INTEGER, reviews_seen INTEGER, reviews_new INTEGER, reviews_updated INTEGER,
            reviews_rejected INTEGER, error TEXT);
        INSERT INTO properties VALUES ('potts-point', 6.5, 2459, '2026-09-28T00:00:00Z');
        INSERT INTO reviews VALUES ('abc12345','potts-point','abc12345','x',8,NULL,'Great',NULL,'en','2026-09-01',
            '2026-08',2,'Double','Couple','Australia',NULL,0,'2026-09-02T00:00:00Z','2026-09-03T00:00:00Z',
            '2026-09-02T00:00:00Z');
        INSERT INTO reviews VALUES ('bad00001','potts-point','bad00001','x',42,NULL,'?',NULL,NULL,'2026-09-01',
            NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2026-09-02T00:00:00Z','2026-09-02T00:00:00Z','2026-09-02T00:00:00Z');
        INSERT INTO scrape_runs VALUES (1,'r1','potts-point','cli','2026-09-28T00:00:00Z',NULL,'running',NULL,'full',
            NULL,3,0,0,0,0,NULL);
    """)
    conn.commit()
    conn.close()


def test_legacy_sqlite_import_validates_and_is_idempotent(store, tmp_path):
    path = tmp_path / "legacy.db"
    _legacy_db(path)
    stats = import_reviews(path)
    assert (stats.reviews_read, stats.reviews_inserted, stats.reviews_rejected, stats.runs_imported) == (2, 1, 1, 1)
    doc = collection(REVIEWS).find_one({"_id": "abc12345"})
    assert doc["content_hash"] != "x"  # recomputed from the normalised content
    assert doc["topics"] == [] and doc["first_seen_at"] == "2026-09-02T00:00:00Z"
    assert collection(PROPERTIES).find_one({"_id": "potts-point"})["booking_score"] == 6.5
    run = collection(SCRAPE_RUNS).find_one({"run_id": "r1"})
    assert run["status"] == "failed" and run["errors"]
    again = import_reviews(path)
    assert (again.reviews_inserted, again.runs_imported) == (0, 0)
