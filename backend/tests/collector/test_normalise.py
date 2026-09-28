from datetime import date

import pytest

from collector.normalise import (
    clean_text,
    clean_title,
    content_hash,
    epoch_to_sydney_date,
    normalise_language,
    parse_int,
    parse_review_date,
    parse_score,
    parse_stay_month,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Reviewed: 12 September 2026", date(2026, 9, 12)),
        ("Reviewed on 3 Sept 2026", date(2026, 9, 3)),
        ("Reviewed: September 12, 2026", date(2026, 9, 12)),
        ("1st March 2025", date(2025, 3, 1)),
        ("2026-01-31", date(2026, 1, 31)),
        ("Reviewed: 31 February 2026", None),
        ("yesterday", None),
        (None, None),
    ],
)
def test_parse_review_date_formats(raw, expected):
    assert parse_review_date(raw) == expected


def test_epoch_is_converted_to_sydney_calendar_date():
    # 2026-09-27T14:30:00Z is already 28 September in Sydney (UTC+10)
    epoch = 1790519400
    assert epoch_to_sydney_date(epoch) == date(2026, 9, 28)
    assert parse_review_date(epoch) == date(2026, 9, 28)
    assert parse_review_date(epoch * 1000) == date(2026, 9, 28)  # milliseconds


def test_clean_text_trims_and_nulls_placeholders():
    assert clean_text("  Great   staff \r\n\r\n\r\n  and bed  ") == "Great staff\n\nand bed"
    assert clean_text("   ") is None
    assert clean_text("") is None
    assert clean_text("There are no comments available for this review") is None
    assert clean_text("There are no comments available for this review.") is None
    assert clean_text("Nothing") == "Nothing"  # a real guest answer, kept


def test_clean_title_drops_dom_score_words_only_when_asked():
    assert clean_title("Good", drop_score_words=True) is None
    assert clean_title("Good") == "Good"
    assert clean_title("Good location", drop_score_words=True) == "Good location"


@pytest.mark.parametrize(("raw", "expected"), [("Scored 7.0 7.0", 7.0), ("8,5", 8.5), (10, 10.0), (None, None), ("n/a", None)])
def test_parse_score(raw, expected):
    assert parse_score(raw) == expected


def test_parse_int_and_stay_month():
    assert parse_int("3 nights") == 3
    assert parse_int(None) is None
    assert parse_stay_month("2026-09-23") == "2026-09"
    assert parse_stay_month("September 2026") == "2026-09"
    assert parse_stay_month("sometime") is None


@pytest.mark.parametrize(("raw", "expected"), [("en", "en"), ("en-gb", "en"), ("xt", "zh"), ("xu", None), ("", None), ("ZH_TW", "zh")])
def test_normalise_language(raw, expected):
    assert normalise_language(raw) == expected


def test_content_hash_is_whitespace_insensitive_and_content_sensitive():
    d = date(2026, 9, 1)
    a = content_hash("p", d, 8.0, "Nice", "Good  bed", None)
    assert a == content_hash("p", d, 8.0, "Nice", "Good bed", None)
    assert a != content_hash("p", d, 8.0, "Nice", "Good bed", "Noisy")
    assert a != content_hash("q", d, 8.0, "Nice", "Good bed", None)
