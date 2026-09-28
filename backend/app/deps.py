"""FastAPI dependencies: common filter parsing and validation.

User input only ever becomes a *value* in a Mongo filter, never a key or operator:
ids are allowlisted, enums checked, dates parsed, and anything that looks like an
operator (``$...``) or a dotted path is rejected outright.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import HTTPException, Query

from .services.catalog import valid_property_ids
from .services.dates import sydney_today

MIN_DATE = date(2000, 1, 1)
MAX_FUTURE = timedelta(days=366)
MAX_LIST_PARAM = 500


def reject_operator_like(values: list[str], name: str) -> None:
    """422 for values that could be interpreted as a Mongo operator or field path."""
    bad = [v for v in values if v.startswith("$") or "." in v]
    if bad:
        raise HTTPException(status_code=422, detail=f"Invalid value for '{name}'")


def parse_csv(value: str | None, name: str = "value") -> list[str]:
    """Split a comma-separated query value into unique, non-empty, operator-free items (order kept)."""
    if not value:
        return []
    out: list[str] = []
    for part in value.split(","):
        item = part.strip()
        if item and item not in out:
            out.append(item)
    reject_operator_like(out, name)
    return out


@dataclass
class Filters:
    """Common filters shared by most endpoints."""

    properties: list[str]
    date_from: date | None
    date_to: date | None


def common_filters(
    properties: str | None = Query(None, max_length=MAX_LIST_PARAM, description="Comma-separated property ids"),
    date_from: date | None = Query(None, description="Inclusive start date YYYY-MM-DD"),
    date_to: date | None = Query(None, description="Inclusive end date YYYY-MM-DD"),
) -> Filters:
    """Parse and validate `properties`, `date_from`, `date_to`."""
    props = parse_csv(properties, "properties")
    if props:
        allowed = valid_property_ids()
        unknown = [p for p in props if p not in allowed]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown property id(s): {', '.join(unknown)}")
    latest = sydney_today() + MAX_FUTURE
    for name, value in (("date_from", date_from), ("date_to", date_to)):
        if value is not None and not (MIN_DATE <= value <= latest):
            raise HTTPException(status_code=422, detail=f"{name} must be between {MIN_DATE} and {latest}")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    return Filters(properties=props, date_from=date_from, date_to=date_to)
