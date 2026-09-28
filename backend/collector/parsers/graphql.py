"""Map a ReviewList GraphQL result to candidate review dicts (validated later)."""

from __future__ import annotations

from typing import Any

from collector.normalise import (
    clean_text,
    clean_title,
    normalise_language,
    parse_int,
    parse_review_date,
    parse_score,
    parse_stay_month,
)


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def parse_card(card: dict[str, Any]) -> dict[str, Any]:
    """Convert one ``reviewCard`` into the ReviewRecord field set (no reviewer name)."""
    text = card.get("textDetails") or {}
    booking = card.get("bookingDetails") or {}
    guest = card.get("guestDetails") or {}
    source_id = card.get("reviewUrl")
    return {
        "source_review_id": str(source_id).strip() if source_id else None,
        "score": parse_score(card.get("reviewScore")),
        "title": clean_title(text.get("title")),
        "positive_text": clean_text(text.get("positiveText")),
        "negative_text": clean_text(text.get("negativeText")),
        "language": normalise_language(text.get("lang")),
        "review_date": parse_review_date(card.get("reviewedDate")),
        "stay_month": parse_stay_month(booking.get("checkinDate")),
        "nights": parse_int(booking.get("numNights")),
        "room_type": clean_text(_get(booking, "roomType", "name")),
        "traveller_type": clean_text(guest.get("guestTypeTranslation")),
        "reviewer_country": clean_text(guest.get("countryName")),
        "hotel_response": clean_text(_get(card, "partnerReply", "reply")),
        "helpful_votes": parse_int(card.get("helpfulVotesCount")),
    }


def parse_review_list(result: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    """Return (candidate dicts, Booking's total review count) for one page."""
    cards = result.get("reviewCard") or []
    total = result.get("reviewsCount")
    candidates = [parse_card(c) for c in cards if isinstance(c, dict)]
    return candidates, int(total) if isinstance(total, (int, float)) else None
