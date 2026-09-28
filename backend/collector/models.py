"""Validated domain models.

Parsers produce plain dicts of *candidate* fields; :class:`ReviewRecord` is the
gate every record must pass before it can touch the database. Validation
failures are counted as rejects and feed the page-change detector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from collector.normalise import SYDNEY_TZ, clean_text, content_hash

MAX_TEXT_LEN = 20_000
EARLIEST_REVIEW_DATE = date(2005, 1, 1)
_OptionalText = str | None


class ReviewRecord(BaseModel):
    """One normalised Booking.com review, ready to upsert."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    property_id: str = Field(min_length=1)
    source_review_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{4,64}$")
    score: float = Field(ge=1, le=10)
    title: _OptionalText = Field(default=None, max_length=MAX_TEXT_LEN)
    positive_text: _OptionalText = Field(default=None, max_length=MAX_TEXT_LEN)
    negative_text: _OptionalText = Field(default=None, max_length=MAX_TEXT_LEN)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    review_date: date
    stay_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    nights: int | None = Field(default=None, ge=0, le=365)
    room_type: _OptionalText = Field(default=None, max_length=500)
    traveller_type: _OptionalText = Field(default=None, max_length=100)
    reviewer_country: _OptionalText = Field(default=None, max_length=100)
    hotel_response: _OptionalText = Field(default=None, max_length=MAX_TEXT_LEN)
    helpful_votes: int | None = Field(default=None, ge=0)

    @field_validator(
        "title", "positive_text", "negative_text", "room_type", "traveller_type",
        "reviewer_country", "hotel_response", mode="before",
    )
    @classmethod
    def _clean(cls, value: Any) -> str | None:
        return clean_text(value)

    @field_validator("review_date")
    @classmethod
    def _plausible_date(cls, value: date) -> date:
        today_sydney = datetime.now(SYDNEY_TZ).date()
        if value < EARLIEST_REVIEW_DATE or value > today_sydney + timedelta(days=1):
            raise ValueError(f"implausible review_date {value.isoformat()}")
        return value

    @model_validator(mode="after")
    def _stay_not_after_review(self) -> ReviewRecord:
        if self.stay_month and self.stay_month > self.review_date.strftime("%Y-%m"):
            raise ValueError("stay_month is after review_date")
        return self

    @property
    def content_hash(self) -> str:
        return content_hash(
            self.property_id, self.review_date, self.score, self.title, self.positive_text, self.negative_text
        )

    @property
    def id(self) -> str:
        """Primary key: Booking's own review id, else a content-hash surrogate."""
        return self.source_review_id or f"h_{self.content_hash}"


@dataclass(frozen=True)
class PropertyMeta:
    """Booking's own headline numbers for a property, when captured."""

    booking_score: float | None = None
    booking_review_count: int | None = None


@dataclass
class RawPage:
    """What a strategy returns for one page, before validation."""

    strategy: str
    offset: int
    candidates: list[dict[str, Any]]  # parser output; one dict per review card found
    total_count: int | None  # Booking's reported total for the property, if known
    meta: PropertyMeta = field(default_factory=PropertyMeta)

    @property
    def found(self) -> int:
        return len(self.candidates)


@dataclass
class ValidatedPage:
    records: list[ReviewRecord]
    rejected: int
    errors: list[str]

    @property
    def reject_ratio(self) -> float:
        total = len(self.records) + self.rejected
        return self.rejected / total if total else 0.0


def validate_candidates(property_id: str, candidates: list[dict[str, Any]], max_errors: int = 5) -> ValidatedPage:
    """Validate parser output, de-duplicating ids within the page and collecting reject reasons."""
    records: list[ReviewRecord] = []
    errors: list[str] = []
    rejected = 0
    seen: set[str] = set()
    for candidate in candidates:
        try:
            record = ReviewRecord(property_id=property_id, **candidate)
        except (ValidationError, TypeError) as exc:
            rejected += 1
            if len(errors) < max_errors:
                errors.append(_summarise_validation_error(exc))
            continue
        if record.id in seen:
            continue
        seen.add(record.id)
        records.append(record)
    return ValidatedPage(records=records, rejected=rejected, errors=errors)


def _summarise_validation_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return f"validation: {loc}: {first.get('msg')}"
    return f"validation: {exc}"
