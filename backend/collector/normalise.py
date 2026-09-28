"""Pure normalisation helpers: text, dates, scores, languages, content hashing.

Everything here is deterministic and side-effect free so it can be unit tested
directly and shared by every parser (GraphQL JSON and DOM HTML).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

# Booking-generated placeholders that carry no guest content.
_PLACEHOLDER_TEXTS = frozenset(
    s.casefold().rstrip(".")
    for s in (
        "There are no comments available for this review",
        "This review has no comments",
        "No comments available",
        "The guest didn't leave a comment",
        "The guest did not leave a comment",
    )
)

# Default headings the DOM shows when a guest left no title (derived from the score).
SCORE_WORD_TITLES = frozenset(
    s.casefold()
    for s in (
        "Exceptional", "Superb", "Wonderful", "Fabulous", "Very good", "Good", "Pleasant",
        "Okay", "Passable", "Review score", "Disappointing", "Poor", "Very poor", "Bad",
    )
)

# Booking uses a few non-ISO pseudo codes; map to ISO 639-1 where the meaning is clear.
_LANGUAGE_ALIASES = {"xt": "zh", "xb": "pt", "zh-tw": "zh", "zh-cn": "zh", "pt-br": "pt", "pt-pt": "pt"}

_MONTHS = {
    name: idx
    for idx, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_DAY_MONTH_YEAR = re.compile(r"(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<m>[A-Za-z]{3,9})\.?,?\s+(?P<y>\d{4})")
_MONTH_DAY_YEAR = re.compile(r"(?P<m>[A-Za-z]{3,9})\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})")
_MONTH_YEAR = re.compile(r"(?P<m>[A-Za-z]{3,9})\.?\s+(?P<y>\d{4})")
_ISO_DATE = re.compile(r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_INLINE_WS = re.compile(r"[^\S\n]+")  # any whitespace except newline (incl. NBSP, thin spaces)
_MANY_NEWLINES = re.compile(r"\n{3,}")


def clean_text(value: object) -> str | None:
    """Normalise user text: NFC, unified newlines, trimmed; empty or placeholder -> None."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = (_INLINE_WS.sub(" ", line).strip() for line in text.split("\n"))
    text = _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()
    if not text or text.casefold().rstrip(".") in _PLACEHOLDER_TEXTS:
        return None
    return text


def clean_title(value: object, *, drop_score_words: bool = False) -> str | None:
    """Clean a review title; optionally drop DOM-generated score words like 'Good'."""
    title = clean_text(value)
    if title and drop_score_words and title.casefold() in SCORE_WORD_TITLES:
        return None
    return title


def parse_score(value: object) -> float | None:
    """Parse '7.0', '7,0', 'Scored 7.0', 8 -> float; None when absent/unparseable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 1)
    match = _NUMBER.search(str(value))
    return round(float(match.group(0).replace(",", ".")), 1) if match else None


def parse_int(value: object) -> int | None:
    """Extract the first integer from '3 nights' / 3 / '1 person found...'; None if absent."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def epoch_to_sydney_date(epoch_s: int | float) -> date:
    """Booking's ``reviewedDate`` is a UTC epoch; the calendar date shown is Sydney-local."""
    return datetime.fromtimestamp(float(epoch_s), tz=timezone.utc).astimezone(SYDNEY_TZ).date()


def _month_number(token: str) -> int | None:
    return _MONTHS.get(token.casefold().rstrip("."))


def parse_review_date(value: object) -> date | None:
    """Parse the many shapes Booking uses for a review date.

    Accepts epoch seconds/milliseconds, ISO dates, 'Reviewed: 12 September 2026',
    'Reviewed on 12 Sept 2026', 'September 12, 2026'. Returns None if unrecognised.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10**11 else value
        return epoch_to_sydney_date(seconds)
    text = str(value).strip()
    if text.isdigit():
        return parse_review_date(int(text))
    candidates = (
        (_ISO_DATE, True),
        (_DAY_MONTH_YEAR, False),
        (_MONTH_DAY_YEAR, False),
    )
    for pattern, numeric_month in candidates:
        match = pattern.search(text)
        if not match:
            continue
        month = int(match.group("m")) if numeric_month else _month_number(match.group("m"))
        if month is None:
            continue
        try:
            return date(int(match.group("y")), month, int(match.group("d")))
        except ValueError:
            return None
    return None


def parse_stay_month(value: object) -> str | None:
    """'2026-09-23' or 'September 2026' -> '2026-09'; None when unknown."""
    if value is None:
        return None
    text = str(value).strip()
    iso = _ISO_DATE.search(text)
    if iso:
        return f"{iso.group('y')}-{iso.group('m')}"
    match = _MONTH_YEAR.search(text)
    if match:
        month = _month_number(match.group("m"))
        if month:
            return f"{match.group('y')}-{month:02d}"
    return None


def normalise_language(value: object) -> str | None:
    """Map Booking language codes to ISO 639-1 ('en-gb' -> 'en', 'xt' -> 'zh'); unknown -> None."""
    if not value:
        return None
    code = str(value).strip().lower().replace("_", "-")
    code = _LANGUAGE_ALIASES.get(code, code)
    base = code.split("-", 1)[0]
    base = _LANGUAGE_ALIASES.get(base, base)
    if re.fullmatch(r"[a-z]{2}", base) and not base.startswith("x"):
        return base
    return None


def _hash_part(value: str | None) -> str:
    return " ".join(value.split()) if value else ""


def content_hash(
    property_id: str,
    review_date: date,
    score: float,
    title: str | None,
    positive_text: str | None,
    negative_text: str | None,
) -> str:
    """sha1 over the normalised review content (schema: property, date, score, title, texts)."""
    parts = [
        property_id,
        review_date.isoformat(),
        f"{score:.1f}",
        _hash_part(title),
        _hash_part(positive_text),
        _hash_part(negative_text),
    ]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()


def utc_now_iso() -> str:
    """Current UTC time as '2026-09-28T06:21:00Z'."""
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
