"""Booking's public ``ReviewList`` GraphQL operation (the one the hotel page's reviews panel uses).

The query is a *data-minimised* subset of what the site requests: reviewer names,
avatars and photos are deliberately not requested (privacy; not needed).
"""

from __future__ import annotations

from typing import Any

from collector.errors import ResponseShapeError
from collector.properties import Property

GRAPHQL_PATH = "/dml/graphql"
OPERATION_NAME = "ReviewList"
SORT_NEWEST_FIRST = "NEWEST_FIRST"

REVIEW_LIST_QUERY = """
query ReviewList($input: ReviewListFrontendInput!) {
  reviewListFrontend(input: $input) {
    ... on ReviewListFrontendResult {
      reviewsCount
      reviewCard {
        reviewUrl
        reviewedDate
        reviewScore
        helpfulVotesCount
        guestDetails { countryCode countryName guestTypeTranslation }
        bookingDetails { customerType roomType { id name } checkinDate checkoutDate numNights stayStatus }
        textDetails { title positiveText negativeText textTrivialFlag lang }
        partnerReply { reply }
      }
    }
    ... on ReviewsFrontendError { statusCode message }
  }
}
""".strip()

# Headers the site's own client sends; Booking's gateway uses them for routing.
CLIENT_HEADERS = {
    "content-type": "application/json",
    "accept": "*/*",
    "apollographql-client-name": "b-property-web-property-page",
    "x-booking-topic": "capla_browser_b-property-web-property-page",
    "x-booking-context-action-name": "hotel",
    "x-booking-site-type-id": "1",
}


def build_payload(prop: Property, offset: int, limit: int, *, hotel_id: int | None = None,
                  ufi: int | None = None) -> dict[str, Any]:
    """GraphQL request body for one page of reviews, newest first."""
    return {
        "operationName": OPERATION_NAME,
        "variables": {
            "input": {
                "hotelId": hotel_id or prop.hotel_id,
                "ufi": ufi or prop.ufi,
                "hotelCountryCode": prop.booking_cc,
                "sorter": SORT_NEWEST_FIRST,
                "filters": {"text": ""},
                "skip": offset,
                "limit": limit,
                "upsortReviewUrl": "",
            }
        },
        "extensions": {},
        "query": REVIEW_LIST_QUERY,
    }


def unwrap_review_list(body: Any) -> dict[str, Any]:
    """Return the ``reviewListFrontend`` result object or raise ``ResponseShapeError``."""
    if not isinstance(body, dict):
        raise ResponseShapeError("GraphQL response is not a JSON object")
    errors = body.get("errors")
    data = body.get("data") or {}
    result = data.get("reviewListFrontend") if isinstance(data, dict) else None
    if errors and not result:
        first = errors[0] if isinstance(errors, list) and errors else {}
        code = (first.get("extensions") or {}).get("code", "?") if isinstance(first, dict) else "?"
        raise ResponseShapeError(f"GraphQL error {code}: {first.get('message', '?') if isinstance(first, dict) else first}")
    if not isinstance(result, dict):
        raise ResponseShapeError("GraphQL response has no data.reviewListFrontend")
    if result.get("__typename") == "ReviewsFrontendError" or "statusCode" in result:
        raise ResponseShapeError(f"ReviewList error {result.get('statusCode')}: {result.get('message')}")
    if "reviewCard" not in result or not isinstance(result.get("reviewCard") or [], list):
        raise ResponseShapeError("ReviewList result has no reviewCard list")
    return result
