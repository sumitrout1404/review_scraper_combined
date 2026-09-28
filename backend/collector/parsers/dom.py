"""Parse review cards and headline numbers from Booking hotel-page HTML (last-resort path).

Selectors rely on Booking's ``data-testid`` attributes, which are far more stable
than its hashed CSS class names. Reviewer names are never read.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from collector.models import PropertyMeta
from collector.normalise import (
    clean_text,
    clean_title,
    parse_int,
    parse_review_date,
    parse_score,
    parse_stay_month,
)

CARD_SELECTOR = '[data-testid="review-card"]'
_REPLY_PREFIX = re.compile(r"^\s*hotel response\s*:?\s*", re.IGNORECASE)
_REPLY_SUFFIX = re.compile(r"\s*(continue reading|read more|show less)\s*$", re.IGNORECASE)
_REVIEW_COUNT = re.compile(r"([\d,.\s]+)\s+reviews?", re.IGNORECASE)


def _text(card: Tag, testid: str) -> str | None:
    el = card.select_one(f'[data-testid="{testid}"]')
    return clean_text(el.get_text(" ", strip=True)) if el else None


def _country(card: Tag) -> str | None:
    avatar = card.select_one('[data-testid="review-avatar"]')
    if not avatar:
        return None
    flag = avatar.find("img", alt=True, src=re.compile(r"flags", re.IGNORECASE))
    if flag and flag.get("alt"):
        return clean_text(flag["alt"])
    # Fallback: the country is rendered in a span next to the flag, after the name heading.
    spans = [s for s in avatar.find_all("span") if s.get_text(strip=True)]
    return clean_text(spans[-1].get_text(" ", strip=True)) if spans else None


def _hotel_response(card: Tag) -> str | None:
    raw = _text(card, "review-partner-reply")
    if not raw:
        return None
    return clean_text(_REPLY_SUFFIX.sub("", _REPLY_PREFIX.sub("", raw)))


def _helpful_votes(card: Tag) -> int | None:
    raw = _text(card, "review-vote")
    if raw and "found this review helpful" in raw.casefold():
        return parse_int(raw)
    return 0 if raw else None


def parse_card(card: Tag) -> dict[str, Any]:
    """Convert one DOM review card into ReviewRecord candidate fields."""
    return {
        "source_review_id": None,  # the DOM exposes no stable review id
        "score": parse_score(_text(card, "review-score")),
        "title": clean_title(_text(card, "review-title"), drop_score_words=True),
        "positive_text": _text(card, "review-positive-text"),
        "negative_text": _text(card, "review-negative-text"),
        "language": None,
        "review_date": parse_review_date(_text(card, "review-date")),
        "stay_month": parse_stay_month(_text(card, "review-stay-date")),
        "nights": parse_int(_text(card, "review-num-nights")),
        "room_type": _text(card, "review-room-name"),
        "traveller_type": _text(card, "review-traveler-type"),
        "reviewer_country": _country(card),
        "hotel_response": _hotel_response(card),
        "helpful_votes": _helpful_votes(card),
    }


def parse_review_cards(html: str) -> list[dict[str, Any]]:
    """All review cards currently rendered in ``html``."""
    soup = BeautifulSoup(html, "html.parser")
    return [parse_card(card) for card in soup.select(CARD_SELECTOR)]


def parse_headline(html: str) -> PropertyMeta:
    """Booking's headline score and total review count from a hotel page, if present."""
    soup = BeautifulSoup(html, "html.parser")
    score: float | None = None
    count: int | None = None
    scored = soup.select_one("[data-review-score]")
    if scored:
        score = parse_score(scored.get("data-review-score"))
    component = soup.select_one('[data-testid="review-score-component"]')
    if component:
        text = component.get_text(" ", strip=True)
        if score is None:
            score = parse_score(text)
        match = _REVIEW_COUNT.search(text)
        if match:
            count = parse_int(re.sub(r"[,.\s]", "", match.group(1)))
    if score is not None and not 1 <= score <= 10:
        score = None
    return PropertyMeta(booking_score=score, booking_review_count=count)


_HOTEL_ID = re.compile(r"b_hotel_id\s*[:=]\s*'(\d+)'")
_UFI = re.compile(r"b_ufi\s*[:=]\s*'?(-?\d+)")


def parse_hotel_ids(html: str) -> tuple[int | None, int | None]:
    """Extract (hotel_id, ufi) from the hotel page's inline JS config."""
    hotel = _HOTEL_ID.search(html)
    ufi = _UFI.search(html)
    return (int(hotel.group(1)) if hotel else None, int(ufi.group(1)) if ufi else None)
