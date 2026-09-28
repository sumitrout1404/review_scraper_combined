import copy

import pytest

from collector.booking.queries import build_payload, unwrap_review_list
from collector.errors import ResponseShapeError
from collector.models import validate_candidates
from collector.parsers.challenge import looks_like_challenge
from collector.parsers.dom import parse_headline, parse_hotel_ids, parse_review_cards
from collector.parsers.graphql import parse_review_list
from collector.properties import PROPERTIES_BY_ID


def test_graphql_fixture_parses_and_validates(graphql_body):
    candidates, total = parse_review_list(unwrap_review_list(graphql_body))
    assert total == 2459
    assert len(candidates) == 25
    page = validate_candidates("potts-point", candidates)
    assert page.rejected == 0
    assert len(page.records) == 25
    first = page.records[0]
    assert first.source_review_id and first.id == first.source_review_id
    assert 1 <= first.score <= 10
    assert first.review_date.isoformat() == "2026-09-28"
    assert any(r.hotel_response for r in page.records)
    assert all(r.language is None or len(r.language) == 2 for r in page.records)
    # no reviewer names anywhere in the parsed data
    assert all("username" not in c for c in candidates)


def test_graphql_error_payloads_raise_shape_error():
    with pytest.raises(ResponseShapeError, match="VALIDATION_INVALID_TYPE_VARIABLE"):
        unwrap_review_list({"errors": [{"message": "x", "extensions": {"code": "VALIDATION_INVALID_TYPE_VARIABLE"}}]})
    with pytest.raises(ResponseShapeError):
        unwrap_review_list({"data": {"reviewListFrontend": {"statusCode": 500, "message": "boom"}}})
    with pytest.raises(ResponseShapeError):
        unwrap_review_list({"data": {"somethingElse": {}}})
    with pytest.raises(ResponseShapeError):
        unwrap_review_list(["not", "an", "object"])


def test_renamed_fields_are_rejected_not_silently_stored(graphql_body):
    body = copy.deepcopy(graphql_body)
    for card in body["data"]["reviewListFrontend"]["reviewCard"]:
        card["score"] = card.pop("reviewScore")  # simulate API drift
    candidates, _ = parse_review_list(unwrap_review_list(body))
    page = validate_candidates("potts-point", candidates)
    assert page.records == [] and page.rejected == 25
    assert "score" in page.errors[0]


def test_payload_is_newest_first_and_capped():
    payload = build_payload(PROPERTIES_BY_ID["darling-harbour"], 50, 25)
    inp = payload["variables"]["input"]
    assert inp["sorter"] == "NEWEST_FIRST" and inp["skip"] == 50 and inp["limit"] == 25
    assert inp["hotelId"] == 10753881
    assert "username" not in payload["query"]


def test_dom_fixture_parses_cards(dom_html):
    cards = parse_review_cards(dom_html)
    assert len(cards) == 10
    page = validate_candidates("olympic-paddington", cards)
    assert page.rejected == 0
    first = page.records[0]
    assert first.source_review_id is None and first.id.startswith("h_")
    assert first.review_date.isoformat() == "2026-09-24"
    assert first.score == 7.0
    assert first.title is None  # DOM shows the score word "Good" when the guest left no title
    assert first.reviewer_country == "Australia"
    assert first.nights == 1 and first.stay_month == "2026-09"
    assert first.helpful_votes == 1
    assert "Guest" not in (first.positive_text or "")
    replies = [r.hotel_response for r in page.records if r.hotel_response]
    assert replies and not replies[0].lower().startswith("hotel response")


def test_dom_headline(dom_html):
    meta = parse_headline(dom_html)
    assert meta.booking_score == 7.1
    assert meta.booking_review_count == 63


def test_hotel_ids_from_inline_config():
    html = "<script>b_hotel_id: '16211291', b_ufi: '-1603135'</script>"
    assert parse_hotel_ids(html) == (16211291, -1603135)
    assert parse_hotel_ids("<html></html>") == (None, None)


def test_challenge_detection():
    challenge = "<html><script>window.awsWafCookieDomainList = ['booking.com'];</script>" \
                "<script src='/__challenge_x/challenge.js'></script></html>"
    assert looks_like_challenge(202, challenge)
    assert looks_like_challenge(200, challenge)
    assert looks_like_challenge(403, "")
    assert not looks_like_challenge(200, '{"data": {}}')
    big_real_page = "awsWafCookieDomainList" + "x" * 100_000
    assert not looks_like_challenge(200, big_real_page)
