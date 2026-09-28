"""Draw a stratified sample of real reviews for hand-labelling.

    python -m analysis.eval.sample_gold --n 90 --out analysis/eval/gold_candidates.jsonl

Stratified by property, score band and language (English vs other), only reviews with some text, deterministic seed.
Labels (``topics``, ``sentiment``) are left empty for a human to fill in; the labelled
file becomes ``gold.jsonl``.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from analysis import text as tx
from analysis.sentiment import score_bucket

_FIELDS = ("property_id", "score", "title", "positive_text", "negative_text", "language", "review_date")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=90)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("gold_candidates.jsonl"))
    args = parser.parse_args(argv)

    from analysis.settings import load_settings
    from db import REVIEWS, collection
    load_settings()   # loads backend/.env
    cursor = collection(REVIEWS, read_only=True).find({}, {f: 1 for f in _FIELDS}).sort("_id", 1)
    rows = [{"id": d.pop("_id"), **d} for d in cursor]
    strata: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if tx.meaningful_text(row["positive_text"]) or tx.meaningful_text(row["negative_text"]):
            lang = "en" if (row.get("language") or "en") == "en" else "other"
            strata[(row["property_id"], score_bucket(float(row["score"])), lang)].append(row)
    rng = random.Random(args.seed)   # noqa: S311 - sampling, not security
    for bucket in strata.values():
        rng.shuffle(bucket)
    picked: list[dict] = []
    while len(picked) < args.n and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(picked) < args.n:
                picked.append(strata[key].pop())
    with args.out.open("w", encoding="utf-8") as handle:
        for row in picked:
            handle.write(json.dumps({**row, "source": "real", "sentiment": None, "topics": []},
                                    ensure_ascii=False) + "\n")
    print(f"wrote {len(picked)} candidates to {args.out}")  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
