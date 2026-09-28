"""Insights generator: statements, thresholds and ranking."""

from __future__ import annotations

from datetime import date

from app.services.dates import describe_window, previous_window

from .conftest import CUR_FROM, CUR_TO, R

WINDOW = {"date_from": CUR_FROM, "date_to": CUR_TO}
SEVERITY_ORDER = ["alert", "warning", "info", "positive"]


def by_id(items):
    return {i["id"]: i for i in items}


def test_insight_shape_and_ranking(client):
    items = client.get("/api/insights", params=WINDOW).json()
    assert items, "expected insights"
    for i in items:
        assert set(i) == {"id", "severity", "title", "text", "property_id", "topic", "sample_size"}
        assert i["severity"] in SEVERITY_ORDER
    ranks = [SEVERITY_ORDER.index(i["severity"]) for i in items]
    assert ranks == sorted(ranks)
    assert len({i["id"] for i in items}) == len(items)


def test_complaint_share_statement(client):
    items = by_id(client.get("/api/insights", params=WINDOW).json())
    clean = items["complaint-share:cleanliness"]
    assert "40% of negative reviews" in clean["text"] and "(4 of 10)" in clean["text"]
    assert clean["severity"] == "alert" and clean["sample_size"] == 10 and clean["topic"] == "cleanliness"
    assert clean["property_id"] == "olympic-paddington"  # all complaints from one property
    noise = items["complaint-share:noise"]
    assert "30% of negative reviews" in noise["text"] and noise["severity"] == "warning"


def test_property_drop_and_biggest_drop(client):
    items = by_id(client.get("/api/insights", params=WINDOW).json())
    pad = items["score:olympic-paddington"]
    assert pad["severity"] == "alert" and pad["title"].startswith("Biggest score drop")
    assert "down 3.2 from 8.0" in pad["text"]
    assert "score:potts-point" not in items  # unchanged


def test_unanswered_low_scores(client):
    item = by_id(client.get("/api/insights", params=WINDOW).json())["unanswered-low-scores"]
    assert item["text"].startswith("9 of 10 reviews scoring below 6")
    assert item["severity"] == "warning" and item["property_id"] == "olympic-paddington"


def test_praise_and_spike(client):
    items = by_id(client.get("/api/insights", params=WINDOW).json())
    praise = items["praise:location"]
    assert praise["severity"] == "positive" and "(7 of 17)" in praise["text"]
    spike = items["complaint-spike:cleanliness"]
    assert "rose to 4" in spike["text"] and "from 1" in spike["text"]
    assert "complaint-spike:noise" in items  # 0 -> 3


def test_small_sample_is_softened(make_client):
    reviews = [
        R(f"n{i}", "potts-point", "2026-01-06", 3.0, topics=[("noise", "negative")] if i < 2 else []) for i in range(3)
    ]
    items = make_client(reviews=reviews).get("/api/insights", params=WINDOW).json()
    texts = " ".join(i["text"] for i in items)
    assert "%" not in texts  # no percentages from n < 5
    by = by_id(items)
    assert by["volume:low"]["sample_size"] == 3
    assert by["complaint-share:noise"]["text"].startswith("2 of the 3 negative reviews")
    assert "score:overall" in by and "too few reviews" in by["score:overall"]["text"]


def test_single_mention_topics_dropped(make_client):
    reviews = [
        R(f"n{i}", "potts-point", "2026-01-06", 3.0, topics=[("noise", "negative")] if i == 0 else []) for i in range(6)
    ]
    items = by_id(make_client(reviews=reviews).get("/api/insights", params=WINDOW).json())
    assert "complaint-share:noise" not in items  # 1 mention is below the minimum


def test_no_score_comparison_below_min_sample(make_client):
    reviews = [R(f"c{i}", "potts-point", "2026-01-06", 4.0) for i in range(6)]
    reviews += [R(f"p{i}", "potts-point", "2026-01-01", 9.0) for i in range(4)]  # previous n=4 < 5
    items = by_id(make_client(reviews=reviews).get("/api/insights", params=WINDOW).json())
    assert "score:potts-point" not in items
    assert "too few reviews" in items["score:overall"]["text"]


def test_insights_empty_window(client):
    items = client.get("/api/insights", params={"date_from": "2020-01-01", "date_to": "2020-01-07"}).json()
    assert [i["id"] for i in items] == ["volume:none"]


def test_window_phrases():
    today = date(2026, 1, 14)  # Wednesday
    assert describe_window(date(2026, 1, 12), date(2026, 1, 14), today) == "this week"
    assert describe_window(date(2026, 1, 5), date(2026, 1, 11), today) == "last week"
    assert describe_window(date(2025, 12, 16), date(2026, 1, 14), today) == "in the last 30 days"
    assert previous_window(date(2026, 1, 12), date(2026, 1, 14)) == (date(2026, 1, 9), date(2026, 1, 11))
