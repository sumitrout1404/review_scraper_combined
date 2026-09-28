from datetime import date

from collector.models import ReviewRecord
from db import REVIEWS, collection


def _rec(**kw) -> ReviewRecord:
    base = dict(property_id="potts-point", source_review_id="abc12345", score=8.0, title="Nice",
                positive_text="Great staff", negative_text=None, review_date=date(2026, 9, 1))
    base.update(kw)
    return ReviewRecord(**base)


def _docs() -> list[dict]:
    return list(collection(REVIEWS).find().sort("_id", 1))


def test_insert_then_idempotent_rerun(store):
    first = store.upsert_page([_rec(), _rec(source_review_id="def67890")], "2026-09-28T00:00:00Z")
    assert (first.new, first.updated, first.unchanged) == (2, 0, 0)
    before = _docs()
    assert before[0]["topics"] == [] and "analysis" not in before[0]
    again = store.upsert_page([_rec(), _rec(source_review_id="def67890")], "2026-09-29T00:00:00Z")
    assert (again.new, again.updated, again.unchanged) == (0, 0, 2)
    for b, a in zip(before, _docs(), strict=True):
        assert a["last_seen_at"] == "2026-09-29T00:00:00Z"
        assert {k: v for k, v in a.items() if k != "last_seen_at"} == {k: v for k, v in b.items() if k != "last_seen_at"}


def test_edit_detected_and_updated_in_place_keeping_analysis(store):
    store.upsert_page([_rec()], "2026-09-28T00:00:00Z")
    analysis = {"sentiment": "positive", "method": "rules", "content_hash": _rec().content_hash}
    collection(REVIEWS).update_one({"_id": "abc12345"}, {"$set": {"analysis": analysis,
                                                                 "topics": [{"topic": "staff", "polarity": "positive"}]}})
    result = store.upsert_page([_rec(negative_text="Noisy at night")], "2026-09-29T00:00:00Z")
    assert (result.new, result.updated) == (0, 1)
    (doc,) = _docs()
    assert doc["negative_text"] == "Noisy at night"
    assert doc["first_seen_at"] == "2026-09-28T00:00:00Z"
    assert doc["updated_at"] == "2026-09-29T00:00:00Z"
    assert doc["content_hash"] == _rec(negative_text="Noisy at night").content_hash
    # the collector never touches the embedded analysis; the stale hash tells analysis to redo it
    assert doc["analysis"] == analysis and doc["topics"] == [{"topic": "staff", "polarity": "positive"}]


def test_hash_only_dom_copy_does_not_duplicate_or_degrade(store):
    store.upsert_page([_rec(language="en", hotel_response="Thanks!")], "2026-09-28T00:00:00Z")
    dom_copy = _rec(source_review_id=None, hotel_response="Thanks! (truncated)")
    result = store.upsert_page([dom_copy], "2026-09-29T00:00:00Z")
    assert (result.new, result.skipped) == (0, 1)
    (doc,) = _docs()
    assert doc["_id"] == "abc12345" and doc["hotel_response"] == "Thanks!" and doc["language"] == "en"


def test_hash_row_is_rekeyed_when_booking_id_appears(store):
    store.upsert_page([_rec(source_review_id=None)], "2026-09-28T00:00:00Z")
    assert _docs()[0]["_id"].startswith("h_")
    result = store.upsert_page([_rec()], "2026-09-29T00:00:00Z")
    assert (result.new, result.updated) == (0, 1)
    (doc,) = _docs()
    assert doc["_id"] == "abc12345"


def test_watermark_and_counts(store):
    assert store.watermark("potts-point") is None
    store.upsert_page([_rec(), _rec(source_review_id="later999", review_date=date(2026, 9, 20))],
                      "2026-09-28T00:00:00Z")
    assert store.watermark("potts-point") == "2026-09-20"
    assert store.count_reviews("potts-point") == 2
    assert store.count_reviews("darling-harbour") == 0
