"""Seed a DEVELOPMENT MongoDB database with synthetic reviews.

Creates ~600 realistic-looking reviews across the four properties over the last ~6 months
(with embedded analysis/topics, ~8% left unanalysed) plus scrape_runs rows, so the API and
frontend can be developed without touching real data.

Safety: it refuses to run against the production database name ``scraper``. The target
defaults to ``MONGODB_DB=scraper_dev`` (same cluster, separate database).

Usage (from backend/):
    MONGODB_DB=scraper_dev python scripts/seed_dev.py [--n 600] [--seed 42]
    MONGODB_DB=scraper_dev uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make backend/ importable

os.environ.setdefault("MONGODB_DB", "scraper_dev")  # before db reads .env (which may say 'scraper')

from db import PROPERTIES as PROPERTIES_COLL  # noqa: E402
from db import REVIEWS, SCRAPE_RUNS, collection, collection_prefix, database_name, ensure_indexes  # noqa: E402
from db import TOPICS as TOPICS_COLL  # noqa: E402

try:
    from zoneinfo import ZoneInfo

    SYD = ZoneInfo("Australia/Sydney")
except Exception:  # pragma: no cover - tzdata missing
    SYD = None

PRODUCTION_DB = "scraper"
DAYS_OF_HISTORY = 183
ANALYSED_SHARE = 0.92

PROPERTIES = [
    # id, name, short_name, pagename, booking_score, quality bias (added to score)
    ("olympic-paddington", "Olympic Hotel Paddington", "Paddington", "olympic-paddington", 7.6, -0.3),
    ("potts-point", "Azzurro Potts Point", "Potts Point", "venus-potts-point-sydney", 8.1, 0.3),
    ("central-sydney", "Azzurro Central Sydney", "Central Sydney", "venus-surry-hills", 7.9, 0.0),
    ("darling-harbour", "Azzurro Darling Harbour", "Darling Harbour", "chateau-de-venus", 8.3, 0.5),
]

TOPICS = [
    ("cleanliness", "Cleanliness", "Room and public-area cleanliness, housekeeping"),
    ("check_in", "Check-in & check-out", "Arrival, check-in/out process, waiting times, keys"),
    ("staff", "Staff & reception", "Friendliness and helpfulness of staff and reception"),
    ("noise", "Noise", "Street, neighbour, building or party noise"),
    ("facilities", "Shared facilities", "Lifts, kitchen, laundry, parking, common areas"),
    ("location", "Location", "Neighbourhood, transport, proximity to attractions"),
    ("room_condition", "Room / pod condition", "Wear and tear, maintenance, size, air-conditioning"),
    ("value_for_money", "Value for money", "Price versus quality"),
    ("bathroom", "Bathrooms & showers", "Shower, water pressure, toiletries, mould"),
    ("bed_comfort", "Bed & sleep comfort", "Mattress, pillows, linen"),
    ("wifi", "Wi-Fi & connectivity", "Internet connectivity and speed"),
    ("breakfast_food", "Breakfast & food", "Breakfast, food and drink"),
]

PRAISE = {
    "cleanliness": [
        "The room was spotless and freshly cleaned.",
        "Very clean throughout.",
        "Housekeeping did a great job every day.",
    ],
    "check_in": [
        "Check-in was quick and easy.",
        "Early check-in was accommodated, which was lovely.",
        "Smooth self check-in.",
    ],
    "staff": [
        "Staff were friendly and helpful.",
        "The receptionist went out of her way to help us.",
        "Lovely, welcoming team at reception.",
    ],
    "noise": ["Surprisingly quiet at night.", "Nice and quiet room."],
    "facilities": ["The kitchenette was handy.", "Good laundry facilities.", "Lift and common areas were well kept."],
    "location": [
        "Great location, close to cafes and transport.",
        "Perfect location for exploring the city.",
        "Walking distance to everything.",
    ],
    "room_condition": ["Room was modern and well maintained.", "Spacious room with good air-con."],
    "value_for_money": ["Great value for Sydney.", "Very good value for money."],
    "bathroom": ["Great shower with strong water pressure.", "Bathroom was clean and modern."],
    "bed_comfort": ["The bed was really comfortable.", "Comfy bed and nice pillows."],
    "wifi": ["Wi-Fi was fast and reliable."],
    "breakfast_food": ["Breakfast was tasty with a good selection.", "Nice coffee at breakfast."],
}

COMPLAINTS = {
    "cleanliness": [
        "The room was not very clean, dust under the bed.",
        "Hair in the bathroom and stained towels.",
        "Carpet looked dirty.",
    ],
    "check_in": [
        "Had to wait 40 minutes to check in.",
        "Nobody at reception when we arrived late.",
        "Room was not ready at check-in time.",
    ],
    "staff": [
        "Reception staff were rude and unhelpful.",
        "Staff seemed disinterested.",
        "The night receptionist was unfriendly.",
    ],
    "noise": [
        "Very noisy at night from the street.",
        "Thin walls, could hear neighbours.",
        "Loud music from the bar until late.",
    ],
    "facilities": ["The lift was out of order.", "No parking available.", "Kitchen facilities were limited."],
    "location": ["The area felt a bit unsafe at night.", "A bit far from the train station."],
    "room_condition": [
        "The room was tired and needs renovating.",
        "Air-con didn't work properly.",
        "Room was very small.",
    ],
    "value_for_money": ["Overpriced for what you get.", "Too expensive for the quality."],
    "bathroom": ["Shower had poor water pressure.", "Mould in the bathroom.", "The toilet kept running all night."],
    "bed_comfort": ["The mattress was uncomfortable and saggy.", "Pillows were flat."],
    "wifi": ["Wi-Fi kept dropping out.", "Internet was very slow."],
    "breakfast_food": ["Breakfast was overpriced and limited.", "Coffee at breakfast was poor."],
}

# Complaint weights per property to make the data "interesting".
COMPLAINT_WEIGHTS = {
    "olympic-paddington": {"noise": 5, "room_condition": 4, "bathroom": 3, "cleanliness": 3},
    "potts-point": {"noise": 3, "check_in": 3, "facilities": 2},
    "central-sydney": {"cleanliness": 4, "staff": 3, "wifi": 2},
    "darling-harbour": {"value_for_money": 3, "check_in": 2, "breakfast_food": 2},
}

TITLES_POS = [
    "Exceptional",
    "Wonderful stay",
    "Great location",
    "Very good",
    "Would stay again",
    "Fabulous",
    "Lovely hotel",
]
TITLES_NEU = ["Good", "Pleasant", "OK for the price", "Decent stay", "Fine for a short stay"]
TITLES_NEG = ["Disappointing", "Not great", "Poor", "Would not recommend", "Needs improvement"]
ROOM_TYPES = ["Queen Room", "Double Room", "Twin Room", "Deluxe King Room", "Studio Apartment", "Standard Double Room"]
TRAVELLERS = ["Couple", "Solo traveller", "Family", "Group", "Business traveller"]
COUNTRIES = ["Australia"] * 6 + [
    "New Zealand",
    "United Kingdom",
    "United States",
    "Singapore",
    "Japan",
    "Germany",
    "China",
    "India",
    "Canada",
]
LANGS = ["en"] * 9 + ["de", "ja", "zh"]
RESPONSES = [
    "Thank you for your feedback. We're sorry to hear about your experience and have passed your comments to our team.",
    "Thanks for staying with us! We're glad you enjoyed the location and hope to welcome you back.",
    "We apologise for the inconvenience and have addressed this with housekeeping.",
]


def sydney_today() -> date:
    if SYD is None:
        return date.today()
    return datetime.now(SYD).date()


def weighted_topic(rng: random.Random, prop_id: str) -> str:
    keys = [t[0] for t in TOPICS]
    w = [1 + COMPLAINT_WEIGHTS[prop_id].get(k, 0) for k in keys]
    return rng.choices(keys, weights=w, k=1)[0]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(n: int, seed: int) -> dict[str, list[dict]]:
    """Synthetic documents per logical collection, shaped as in ``db/collections.py``."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_s = _iso(now)
    docs: dict[str, list[dict]] = {PROPERTIES_COLL: [], TOPICS_COLL: [], REVIEWS: [], SCRAPE_RUNS: []}

    for pid, name, short, page, bscore, _ in PROPERTIES:
        docs[PROPERTIES_COLL].append(
            {"_id": pid, "name": name, "short_name": short, "booking_pagename": page, "booking_cc": "au",
             "booking_url": f"https://www.booking.com/hotel/au/{page}.html", "booking_score": bscore,
             "booking_review_count": rng.randint(400, 2500), "updated_at": now_s}
        )  # fmt: skip
    for i, (key, label, desc) in enumerate(TOPICS):
        docs[TOPICS_COLL].append({"_id": key, "label": label, "description": desc, "sort_order": i})

    today = sydney_today()
    for i in range(n):
        pid, _, _, _, _, bias = rng.choice(PROPERTIES)
        offset = int(DAYS_OF_HISTORY * (rng.random() ** 1.15))  # skew towards recent reviews
        rdate = today - timedelta(days=offset)
        dip = -1.2 if (pid == "olympic-paddington" and offset < 14) else 0.0  # recent dip -> interesting insights
        raw = min(10.0, max(1.0, rng.gauss(7.9 + bias + dip, 1.6)))
        score = float(round(raw) if rng.random() < 0.7 else round(raw, 1))
        sentiment = "positive" if score >= 8 else ("neutral" if score >= 6 else "negative")

        n_pos = rng.choice([1, 1, 2, 2, 3]) if score >= 6 else rng.choice([0, 0, 1])
        if score >= 8:
            n_neg = rng.choice([0, 0, 0, 1])
        else:
            n_neg = rng.choice([1, 1, 2]) if score >= 6 else rng.choice([1, 2, 2, 3])
        pos_topics = list(
            dict.fromkeys(rng.choice([t[0] for t in TOPICS[:8]] + ["location", "staff"]) for _ in range(n_pos))
        )
        neg_topics = list(dict.fromkeys(weighted_topic(rng, pid) for _ in range(n_neg)))
        pos_sent = [rng.choice(PRAISE[t]) for t in pos_topics]
        neg_sent = [rng.choice(COMPLAINTS[t]) for t in neg_topics]
        positive_text = " ".join(pos_sent) or None
        negative_text = " ".join(neg_sent) or None
        if negative_text is None and rng.random() < 0.3:
            negative_text = "Nothing, everything was great."
        titles = TITLES_POS if sentiment == "positive" else TITLES_NEU if sentiment == "neutral" else TITLES_NEG
        title = rng.choice(titles)
        content = "|".join([pid, rdate.isoformat(), str(score), title, positive_text or "", negative_text or ""])
        chash = hashlib.sha1(content.encode()).hexdigest()
        seen = _iso(datetime.combine(rdate, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1))
        review = {
            "_id": f"dev_{i:05d}", "property_id": pid, "source_review_id": f"src{i}", "content_hash": chash,
            "score": score, "title": title, "positive_text": positive_text, "negative_text": negative_text,
            "language": rng.choice(LANGS), "review_date": rdate.isoformat(),
            "stay_month": (rdate - timedelta(days=rng.randint(1, 20))).strftime("%Y-%m"),
            "nights": rng.choice([1, 1, 2, 2, 3, 4, 7]), "room_type": rng.choice(ROOM_TYPES),
            "traveller_type": rng.choice(TRAVELLERS), "reviewer_country": rng.choice(COUNTRIES),
            "hotel_response": rng.choice(RESPONSES) if rng.random() < (0.5 if score < 6 else 0.15) else None,
            "helpful_votes": rng.choice([0, 0, 0, 1, 2]), "first_seen_at": seen, "last_seen_at": now_s,
            "updated_at": now_s, "topics": [],
        }  # fmt: skip
        if rng.random() < ANALYSED_SHARE:  # leave some unanalysed to exercise the score fallback
            use_llm = rng.random() < 0.7
            bits = []
            if pos_topics:
                bits.append("liked " + ", ".join(t.replace("_", " ") for t in pos_topics))
            if neg_topics:
                bits.append("disliked " + ", ".join(t.replace("_", " ") for t in neg_topics))
            review["analysis"] = {
                "sentiment": sentiment,
                "sentiment_score": round(max(-1.0, min(1.0, (score - 7) / 3 + rng.uniform(-0.1, 0.1))), 2),
                "summary": ("Guest " + " but ".join(bits) + ".") if (use_llm and bits) else None,
                "method": "llm:llama-3.1-8b-instant" if use_llm else "rules",
                "content_hash": chash,
                "analysed_at": now_s,
            }
            review["topics"] = [
                {"topic": t, "polarity": "positive", "evidence": ev[:120]} for t, ev in zip(pos_topics, pos_sent)
            ] + [{"topic": t, "polarity": "negative", "evidence": ev[:120]} for t, ev in zip(neg_topics, neg_sent)]
        docs[REVIEWS].append(review)

    for d in range(10, 0, -1):  # one cron run per day for the last 10 days
        started = now - timedelta(days=d, hours=2)
        for pid, *_ in PROPERTIES:
            status = "success" if rng.random() > 0.1 else rng.choice(["partial", "failed"])
            docs[SCRAPE_RUNS].append(
                {"run_id": started.strftime("run-%Y%m%dT%H%M%S"), "property_id": pid, "trigger": "cron",
                 "started_at": _iso(started), "finished_at": _iso(started + timedelta(minutes=3)), "status": status,
                 "method": "http", "mode": "incremental", "watermark_date": (started - timedelta(days=1)).date().isoformat(),
                 "pages_fetched": rng.randint(1, 4), "reviews_seen": rng.randint(10, 75),
                 "reviews_new": rng.randint(0, 6), "reviews_updated": rng.randint(0, 2),
                 "reviews_rejected": rng.randint(0, 1),
                 "errors": [] if status == "success" else ["Timeout fetching page 3"]}
            )  # fmt: skip
    return docs


def write(docs: dict[str, list[dict]]) -> None:
    """Replace this app's collections in the (non-production) target database."""
    for name, items in docs.items():
        coll = collection(name)
        coll.delete_many({})
        if items:
            coll.insert_many(items)
    ensure_indexes()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    target = database_name()
    if target == PRODUCTION_DB:
        print(f"Refusing to seed synthetic data into the '{PRODUCTION_DB}' database. Set MONGODB_DB=scraper_dev.",
              file=sys.stderr)  # fmt: skip
        return 2
    write(generate(args.n, args.seed))
    print(f"Wrote {args.n} synthetic reviews to database '{target}' (prefix '{collection_prefix()}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
