"""Property and topic catalogues."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from db import PROPERTIES, REVIEWS, TOPICS

from ..db import ro

# The contract's fixed property ids, in display order (the DB may add more).
KNOWN_PROPERTY_IDS = ("olympic-paddington", "potts-point", "central-sydney", "darling-harbour")
# Used only if the analysis step has not populated the topics collection yet.
FALLBACK_TOPICS = (
    ("cleanliness", "Cleanliness"),
    ("check_in", "Check-in & check-out"),
    ("staff", "Staff & reception"),
    ("noise", "Noise"),
    ("facilities", "Shared facilities"),
    ("location", "Location"),
    ("room_condition", "Room / pod condition"),
    ("value_for_money", "Value for money"),
    ("bathroom", "Bathrooms & showers"),
    ("bed_comfort", "Bed & sleep comfort"),
    ("wifi", "Wi-Fi & connectivity"),
    ("breakfast_food", "Breakfast & food"),
)
PROPERTY_FIELDS = {"name": 1, "short_name": 1, "booking_url": 1, "booking_score": 1}


def list_properties(only: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Properties (``id`` instead of ``_id``) in the contract's order, optionally restricted to ``only``."""
    rows = [
        {"id": d["_id"], **{k: d.get(k) for k in PROPERTY_FIELDS}} for d in ro(PROPERTIES).find({}, PROPERTY_FIELDS)
    ]
    order = {pid: i for i, pid in enumerate(KNOWN_PROPERTY_IDS)}
    rows.sort(key=lambda r: (order.get(r["id"], len(order)), r["name"] or ""))
    return [r for r in rows if r["id"] in only] if only else rows


def valid_property_ids() -> set[str]:
    """Allowlist for the ``properties`` parameter."""
    return {d["_id"] for d in ro(PROPERTIES).find({}, {"_id": 1})} | set(KNOWN_PROPERTY_IDS)


def topic_catalog() -> list[dict[str, Any]]:
    """Topics ordered by sort_order; falls back to the contract's fixed keys when the collection is empty."""
    docs = list(ro(TOPICS).find({}).sort([("sort_order", 1), ("_id", 1)]))
    if docs:
        return [
            {"key": d["_id"], "label": d.get("label") or d["_id"], "description": d.get("description")} for d in docs
        ]
    return [{"key": key, "label": label, "description": None} for key, label in FALLBACK_TOPICS]


def known_topic_keys() -> set[str]:
    """Allowlist for the ``topic`` parameter: catalogue keys plus any key used in reviews."""
    return {t["key"] for t in topic_catalog()} | {k for k in ro(REVIEWS).distinct("topics.topic") if isinstance(k, str)}


def topic_labels() -> dict[str, str]:
    return {t["key"]: t["label"] for t in topic_catalog()}


def label_for(labels: dict[str, str], key: str) -> str:
    """Display label for a topic key, tolerating keys missing from the catalogue."""
    return labels.get(key) or key.replace("_", " ").capitalize()


def topic_order() -> dict[str, int]:
    """Topic key -> catalogue position (for stable ordering)."""
    return {t["key"]: i for i, t in enumerate(topic_catalog())}
