"""The four Azzurro properties (ids fixed by docs/CONTRACT.md).

``hotel_id`` is Booking's numeric property id (the ``dest_id`` of ``dest_type=hotel``
in the task URLs, confirmed via ``b_hotel_id`` on each hotel page); ``ufi`` is the
Booking city id for Sydney. Both are required by Booking's ReviewList GraphQL
query. The browser strategy re-discovers them from the live page, so a change on
Booking's side is picked up automatically when the browser path is used.
"""

from __future__ import annotations

from dataclasses import dataclass

from collector.settings import BOOKING_BASE_URL

SYDNEY_UFI = -1603135


@dataclass(frozen=True)
class Property:
    id: str
    name: str
    short_name: str
    booking_pagename: str
    hotel_id: int
    ufi: int = SYDNEY_UFI
    booking_cc: str = "au"

    @property
    def booking_url(self) -> str:
        """Clean public hotel URL without tracking parameters."""
        return f"{BOOKING_BASE_URL}/hotel/{self.booking_cc}/{self.booking_pagename}.html"

    def localized_url(self, lang: str) -> str:
        return f"{BOOKING_BASE_URL}/hotel/{self.booking_cc}/{self.booking_pagename}.{lang}.html"


PROPERTIES: tuple[Property, ...] = (
    Property("olympic-paddington", "Olympic Hotel Paddington", "Paddington", "olympic-paddington", 16211291),
    Property("potts-point", "Azzurro Potts Point", "Potts Point", "venus-potts-point-sydney", 9491412),
    Property("central-sydney", "Azzurro Central Sydney", "Central Sydney", "venus-surry-hills", 9888182),
    Property("darling-harbour", "Azzurro Darling Harbour", "Darling Harbour", "chateau-de-venus", 10753881),
)
PROPERTIES_BY_ID: dict[str, Property] = {p.id: p for p in PROPERTIES}


def select_properties(ids: list[str] | None) -> list[Property]:
    """Return the requested properties (all when ``ids`` is empty); unknown ids raise ValueError."""
    if not ids:
        return list(PROPERTIES)
    unknown = [i for i in ids if i not in PROPERTIES_BY_ID]
    if unknown:
        raise ValueError(f"unknown property id(s): {', '.join(unknown)}; valid: {', '.join(PROPERTIES_BY_ID)}")
    return [PROPERTIES_BY_ID[i] for i in dict.fromkeys(ids)]
