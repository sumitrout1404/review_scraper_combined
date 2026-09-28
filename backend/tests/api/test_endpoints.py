"""Endpoint shape and behaviour tests against docs/CONTRACT.md."""

from __future__ import annotations

import csv
import io
from datetime import date

from app.services.dates import sydney_today, week_start

from .conftest import CUR_FROM, CUR_TO, PREV_FROM, PREV_TO, R

PERIOD_STATS = {"count", "avg_score", "positive", "neutral", "negative", "pct_positive", "pct_negative"}
REVIEW_KEYS = {
    "id", "property_id", "property_name", "property_short_name", "score", "title", "positive_text", "negative_text",
    "language", "review_date", "stay_month", "nights", "room_type", "traveller_type", "reviewer_country",
    "hotel_response", "sentiment", "sentiment_score", "summary", "analysis_method", "topics",
}  # fmt: skip
WINDOW = {"date_from": CUR_FROM, "date_to": CUR_TO}


# ---------------------------------------------------------------- health / meta / catalogue
def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["config_ok"] is True
    assert body["db"]["dialect"] == "mongodb"
    assert body["db"]["last_cron_run"]["status"] == "partial"
    assert body["db"]["reviews"] == 29
    assert body["db"]["last_scraped_at"] == "2026-01-19T00:05:00Z"
    assert r.headers["cache-control"] == "no-store"


def test_database_errors_return_503(client, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    import app.db as app_db

    def down(*_args, **_kwargs):
        raise ServerSelectionTimeoutError("cluster0.example.net:27017 timed out")

    monkeypatch.setattr(app_db, "collection", down)
    health = client.get("/api/health")
    assert health.status_code == 503 and health.json()["status"] == "error"
    r = client.get("/api/summary")
    assert r.status_code == 503
    assert r.json() == {"detail": "Review database is temporarily unavailable"}
    assert "example.net" not in r.text


def test_database_not_configured_returns_503(client, monkeypatch):
    import app.db as app_db
    from db import DatabaseNotConfigured

    def missing(*_args, **_kwargs):
        raise DatabaseNotConfigured("MONGODB_URI is not set")

    monkeypatch.setattr(app_db, "collection", missing)
    assert client.get("/api/reviews").status_code == 503


def test_meta(client):
    body = client.get("/api/meta").json()
    today = sydney_today()
    assert body["today"] == today.isoformat()
    assert body["this_week_start"] == week_start(today).isoformat()
    assert date.fromisoformat(body["this_week_start"]).weekday() == 0
    assert body["min_review_date"] == "2025-11-15"
    assert body["max_review_date"] == "2026-01-10"
    assert body["total_reviews"] == 29
    assert body["last_run_status"] == "partial"  # one property succeeded, one failed


def test_properties(client):
    body = client.get("/api/properties").json()
    assert [p["id"] for p in body] == ["olympic-paddington", "potts-point", "central-sydney", "darling-harbour"]
    assert set(body[0]) == {"id", "name", "short_name", "booking_url", "booking_score", "total_reviews", "avg_score"}
    central = body[2]
    assert central["total_reviews"] == 0 and central["avg_score"] is None
    assert body[1]["avg_score"] == 9.0


def test_topics_ordered_and_fallback(client, make_client):
    body = client.get("/api/topics").json()
    assert [t["key"] for t in body][:2] == ["cleanliness", "check_in"]
    assert set(body[0]) == {"key", "label", "description"}
    empty_catalogue = make_client(with_topics=False).get("/api/topics").json()
    assert len(empty_catalogue) == 12  # contract topic keys


# ---------------------------------------------------------------- summary
def test_summary_shape_and_previous_window(client):
    body = client.get("/api/summary", params=WINDOW).json()
    assert set(body) == {"current", "previous", "delta_avg_score", "delta_count", "by_property"}
    cur, prev = body["current"], body["previous"]
    assert set(cur) == PERIOD_STATS | {"date_from", "date_to"}
    assert (cur["date_from"], cur["date_to"]) == (CUR_FROM, CUR_TO)
    assert (prev["date_from"], prev["date_to"]) == (PREV_FROM, PREV_TO)
    # current: 10x4.0 + 2x9.0 + 5x9.0 = 103 / 17
    assert cur["count"] == 17 and cur["avg_score"] == round(103 / 17, 2)
    assert cur["negative"] == 10 and cur["positive"] == 7 and cur["pct_negative"] == round(1000 / 17, 2)
    # previous: 6x8 + 5x9 = 93 / 11
    assert prev["count"] == 11 and prev["avg_score"] == round(93 / 11, 2)
    assert body["delta_count"] == 6
    assert body["delta_avg_score"] == round(round(103 / 17, 2) - round(93 / 11, 2), 2)

    pad = next(p for p in body["by_property"] if p["property_id"] == "olympic-paddington")
    assert set(pad["current"]) == PERIOD_STATS
    assert pad["current"]["avg_score"] == round((40 + 18) / 12, 2)
    assert pad["previous"]["avg_score"] == 8.0
    assert pad["top_complaint"] == {"topic": "cleanliness", "label": "Cleanliness", "count": 4}
    central = next(p for p in body["by_property"] if p["property_id"] == "central-sydney")
    assert central["current"]["avg_score"] is None and central["delta_avg_score"] is None
    assert central["top_complaint"] is None


def test_summary_previous_window_odd_length(client):
    body = client.get("/api/summary", params={"date_from": "2026-01-05", "date_to": "2026-01-07"}).json()
    assert body["previous"]["date_from"] == "2026-01-02"
    assert body["previous"]["date_to"] == "2026-01-04"


def test_summary_defaults_to_this_week(client):
    body = client.get("/api/summary").json()
    today = sydney_today()
    assert body["current"]["date_from"] == week_start(today).isoformat()
    assert body["current"]["date_to"] == today.isoformat()


def test_summary_empty_window(client):
    body = client.get("/api/summary", params={"date_from": "2020-01-01", "date_to": "2020-01-07"}).json()
    assert body["current"]["count"] == 0
    assert body["current"]["avg_score"] is None
    assert body["current"]["pct_negative"] == 0
    assert body["delta_avg_score"] is None
    assert all(p["top_complaint"] is None for p in body["by_property"])


def test_summary_property_filter(client):
    body = client.get("/api/summary", params={**WINDOW, "properties": "potts-point"}).json()
    assert body["current"]["count"] == 5
    assert [p["property_id"] for p in body["by_property"]] == ["potts-point"]


def test_empty_database(make_client):
    c = make_client(reviews=[])
    assert c.get("/api/summary").json()["current"]["avg_score"] is None
    assert c.get("/api/trends").status_code == 200
    assert c.get("/api/topics/breakdown").json()["total_reviews"] == 0
    assert c.get("/api/reviews").json()["total"] == 0
    assert c.get("/api/insights").json()[0]["id"] == "volume:none"


# ---------------------------------------------------------------- trends
def test_trends_week_fills_empty_periods(client):
    body = client.get(
        "/api/trends", params={"granularity": "week", "date_from": PREV_FROM, "date_to": "2026-01-25"}
    ).json()
    assert body["granularity"] == "week"
    starts = [p["period_start"] for p in body["series"]]
    assert starts == ["2025-12-29", "2026-01-05", "2026-01-12", "2026-01-19"]
    assert set(body["series"][0]) == PERIOD_STATS | {"period_start"}
    assert [p["count"] for p in body["series"]] == [11, 17, 0, 0]
    assert body["series"][2]["avg_score"] is None
    assert len(body["by_property"]) == 4
    pad = body["by_property"][0]
    assert pad["property_id"] == "olympic-paddington" and pad["short_name"] == "Paddington"
    assert pad["series"][1] == {"period_start": "2026-01-05", "count": 12, "avg_score": round(58 / 12, 2)}


def test_trends_month(client):
    body = client.get(
        "/api/trends", params={"granularity": "month", "date_from": "2025-11-01", "date_to": "2026-01-31"}
    ).json()
    assert [p["period_start"] for p in body["series"]] == ["2025-11-01", "2025-12-01", "2026-01-01"]
    assert [p["count"] for p in body["series"]] == [1, 6, 22]


def test_trends_bad_granularity(client):
    r = client.get("/api/trends", params={"granularity": "day"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


# ---------------------------------------------------------------- topics
def test_topic_breakdown(client):
    body = client.get("/api/topics/breakdown", params=WINDOW).json()
    assert body["total_reviews"] == 17 and body["negative_reviews"] == 10
    items = body["items"]
    assert set(items[0]) == {"topic", "label", "negative_mentions", "positive_mentions", "pct_of_negative_reviews",
                             "pct_of_reviews", "net"}  # fmt: skip
    assert items[0]["topic"] == "cleanliness"
    assert items[0]["negative_mentions"] == 4 and items[0]["pct_of_negative_reviews"] == 40.0
    negs = [i["negative_mentions"] for i in items]
    assert negs == sorted(negs, reverse=True)
    loc = next(i for i in items if i["topic"] == "location")
    assert loc["positive_mentions"] == 7 and loc["net"] == 7 and loc["pct_of_reviews"] == round(700 / 17, 2)


def test_topic_trends(client):
    body = client.get(
        "/api/topics/trends", params={"granularity": "week", "date_from": PREV_FROM, "date_to": CUR_TO}
    ).json()
    series = body["series"]
    assert set(series[0]) == {"period_start", "topic", "mentions"}
    clean = {(p["period_start"], p["mentions"]) for p in series if p["topic"] == "cleanliness"}
    assert clean == {("2025-12-29", 1), ("2026-01-05", 4)}
    pos = client.get("/api/topics/trends", params={"polarity": "positive", "date_from": CUR_FROM, "date_to": CUR_TO})
    assert {p["topic"] for p in pos.json()["series"]} == {"location", "staff"}


# ---------------------------------------------------------------- reviews
def test_reviews_shape_and_pagination(client):
    body = client.get("/api/reviews", params={"page_size": 5, "page": 2}).json()
    assert body["total"] == 29 and body["page"] == 2 and body["page_size"] == 5
    assert len(body["items"]) == 5
    item = body["items"][0]
    assert set(item) == REVIEW_KEYS
    assert item["property_name"] and item["property_short_name"]


def test_reviews_sentiment_fallback_from_score(client):
    body = client.get("/api/reviews", params={"q": "Bad stay 7"}).json()
    item = body["items"][0]
    assert item["id"] == "cn7" and item["sentiment"] == "negative" and item["analysis_method"] is None
    assert item["topics"] == []
    neutral = client.get("/api/reviews", params={"properties": "darling-harbour"}).json()["items"][0]
    assert neutral["sentiment"] == "neutral"  # score 7, no analysis


def test_reviews_filters(client):
    get = lambda **p: client.get("/api/reviews", params=p).json()  # noqa: E731
    assert get(sentiment="negative")["total"] == 10
    assert get(sentiment="positive,neutral")["total"] == 19
    assert get(topic="cleanliness", polarity="negative", **WINDOW)["total"] == 4
    assert get(topic="cleanliness")["total"] == 5
    assert get(topic="cleanliness,noise", polarity="negative", **WINDOW)["total"] == 7
    assert get(polarity="positive")["total"] == 7
    assert get(min_score=8.5)["total"] == 12
    assert get(max_score=4)["total"] == 10
    assert get(properties="potts-point,darling-harbour")["total"] == 11
    scores = [i["score"] for i in get(sort="score_asc", page_size=100)["items"]]
    assert scores == sorted(scores)
    dates = [i["review_date"] for i in get(sort="date_desc", page_size=100)["items"]]
    assert dates == sorted(dates, reverse=True)
    first = get(q="Dirty", topic="cleanliness")["items"][0]
    assert first["topics"][0] == {"topic": "cleanliness", "label": "Cleanliness", "polarity": "negative",
                                  "evidence": "cleanliness evidence"}  # fmt: skip


def test_reviews_search_escapes_like(client):
    assert client.get("/api/reviews", params={"q": "100%"}).json()["total"] == 5
    assert client.get("/api/reviews", params={"q": "%"}).json()["total"] == 5  # literal %, not wildcard
    assert client.get("/api/reviews", params={"q": "_"}).json()["total"] == 0


def test_reviews_validation(client):
    bad = [
        {"page_size": 101},
        {"page": 0},
        {"date_from": "2026-13-01"},
        {"date_from": "not-a-date"},
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
        {"date_from": "1990-01-01"},
        {"properties": "olympic-paddington,hilton"},
        {"sentiment": "angry"},
        {"topic": "parking"},
        {"polarity": "meh"},
        {"sort": "random"},
        {"min_score": 0},
        {"min_score": 9, "max_score": 5},
        {"q": "x" * 201},
    ]
    for params in bad:
        r = client.get("/api/reviews", params=params)
        assert r.status_code == 422, params
        assert isinstance(r.json()["detail"], str), params


def test_unknown_property_rejected_everywhere(client):
    for path in ("/api/summary", "/api/trends", "/api/topics/breakdown", "/api/insights", "/api/reviews/export.csv"):
        assert client.get(path, params={"properties": "nope"}).status_code == 422, path


def test_csv_export(client):
    r = client.get("/api/reviews/export.csv", params={**WINDOW, "sort": "date_asc"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="reviews_2026-01-05_2026-01-11.csv"'
    text = r.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 17
    clean = next(row for row in rows if row["id"] == "cn0")
    assert clean["topics"] == "Cleanliness (complaint)" and clean["complaints"] == "Cleanliness"
    pp = next(row for row in rows if row["id"] == "pp0")
    assert pp["praise"] == "Staff & reception; Location"


def test_csv_neutralises_formulas(client):
    r = client.get("/api/reviews/export.csv", params={"properties": "darling-harbour"})
    row = next(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert row["title"].startswith("'=HYPERLINK")


def test_csv_same_filters_as_feed(client):
    params = {"sentiment": "negative", "topic": "noise", "polarity": "negative"}
    feed_total = client.get("/api/reviews", params=params).json()["total"]
    rows = list(
        csv.DictReader(io.StringIO(client.get("/api/reviews/export.csv", params=params).content.decode("utf-8-sig")))
    )
    assert len(rows) == feed_total == 3


# ---------------------------------------------------------------- runs
def test_scrape_runs(client):
    body = client.get("/api/scrape-runs", params={"limit": 1}).json()
    assert len(body) == 1
    assert set(body[0]) == {"run_id", "property_id", "trigger", "watermark_date", "started_at", "finished_at", "status", "method", "mode",
                            "pages_fetched", "reviews_seen", "reviews_new", "reviews_updated", "reviews_rejected",
                            "error"}  # fmt: skip
    assert client.get("/api/scrape-runs", params={"limit": 0}).status_code == 422


def test_fixture_reviews_are_consistent():
    """Guard: fixture helper builds reviews with the expected defaults."""
    r = R("x", "potts-point", "2026-01-01", 5.0)
    assert r.sentiment is None and r.topics == []
