"""Command-line interface: ``python -m collector {run,export,status,import}`` (cwd = backend/)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, replace
from pathlib import Path

from collector.export import export_samples
from collector.pipeline import run_collection
from collector.properties import PROPERTIES, PROPERTIES_BY_ID
from collector.settings import HTTP_STRATEGY, SAMPLES_DIR, Settings
from core.logging import configure_logging
from db import PROPERTIES as PROPERTIES_COLL
from db import REVIEWS, SCRAPE_RUNS, LeaseHeldError, collection, db_lease

logger = logging.getLogger("collector")

LEASE_NAME = "collect"
LEASE_TTL_S = 900
EXIT_OK, EXIT_PROBLEMS, EXIT_LOCKED = 0, 1, 3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m collector", description="Booking.com review collector")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="collect reviews (incremental by default)")
    run.add_argument("--full", action="store_true", help="page through the full history")
    run.add_argument("--property", dest="properties", action="append", choices=sorted(PROPERTIES_BY_ID),
                     help="limit to a property id (repeatable)")
    run.add_argument("--max-pages", type=int, help="cap pages per property")
    run.add_argument("--time-budget", type=float, help="stop cleanly after N seconds")
    run.add_argument("--no-analyse", action="store_true", help="skip the analysis step")
    run.add_argument("--http-only", action="store_true", help="disable browser fallbacks and the score probe")

    exp = sub.add_parser("export", help="write data/samples/reviews.json and reviews.csv")
    exp.add_argument("--out", type=Path, default=SAMPLES_DIR)

    st = sub.add_parser("status", help="show review counts and recent runs")
    st.add_argument("--limit", type=int, default=12)

    imp = sub.add_parser("import", help="idempotently import a legacy SQLite DB or an exported reviews.json")
    imp.add_argument("--from", dest="source", type=Path, required=True)
    return parser


def _run_analysis() -> None:
    try:
        from analysis import run_analysis
    except ImportError as exc:
        logger.warning("analysis package not importable, skipping: %s", exc)
        return
    try:
        logger.info("analysis: %s", run_analysis(method="auto"))
    except Exception:  # noqa: BLE001 - an analysis failure must not lose collected data
        logger.exception("analysis step failed")


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.http_only:
        settings = replace(settings, strategies=(HTTP_STRATEGY,), probe_headline_score=False)
    try:
        with db_lease(LEASE_NAME, ttl_s=LEASE_TTL_S):
            report = run_collection(
                mode="full" if args.full else "incremental", trigger="cli", time_budget_s=args.time_budget,
                properties=args.properties, max_pages=args.max_pages, settings=settings,
            )
            if not args.no_analyse and report.any_collected:
                _run_analysis()
    except LeaseHeldError as exc:
        logger.error("%s", exc)
        return EXIT_LOCKED
    print(json.dumps(report.to_dict(), indent=1))  # noqa: T201 - CLI output
    return EXIT_OK if report.status == "success" else EXIT_PROBLEMS


def cmd_export(args: argparse.Namespace) -> int:
    json_path, csv_path, count = export_samples(args.out)
    print(f"exported {count} reviews -> {json_path}, {csv_path}")  # noqa: T201
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    reviews = collection(REVIEWS, read_only=True)
    stats = {
        d["_id"]: d
        for d in reviews.aggregate([{"$group": {
            "_id": "$property_id", "n": {"$sum": 1}, "first": {"$min": "$review_date"},
            "last": {"$max": "$review_date"}, "avg": {"$avg": "$score"},
            "analysed": {"$sum": {"$cond": [{"$ifNull": ["$analysis", False]}, 1, 0]}},
        }}])
    }
    props = {p["_id"]: p for p in collection(PROPERTIES_COLL, read_only=True).find()}
    print("Reviews per property:")  # noqa: T201
    for p in PROPERTIES:
        s, meta = stats.get(p.id), props.get(p.id, {})
        booking = f"booking score={meta.get('booking_score')} count={meta.get('booking_review_count')}"
        if s:
            print(f"  {p.id:20} {s['n']:5d}  {s['first']} .. {s['last']}  avg={s['avg']:.2f}  "  # noqa: T201
                  f"analysed={s['analysed']}  {booking}")
        else:
            print(f"  {p.id:20}     0  {booking}")  # noqa: T201
    print("Recent runs:")  # noqa: T201
    for r in collection(SCRAPE_RUNS, read_only=True).find().sort("started_at", -1).limit(args.limit):
        print(f"  {r['started_at']} {r['run_id'][:8]} {r.get('property_id') or '-':20} {r['status']:9} "  # noqa: T201
              f"{r.get('mode') or '':11} {r.get('method') or '-':16} pages={r.get('pages_fetched')} "
              f"new={r.get('reviews_new')} upd={r.get('reviews_updated')} rej={r.get('reviews_rejected')}")
    return EXIT_OK


def cmd_import(args: argparse.Namespace) -> int:
    from collector.importer import import_reviews

    stats = import_reviews(args.source)
    print(json.dumps(asdict(stats), indent=1))  # noqa: T201
    return EXIT_OK if not stats.reviews_rejected else EXIT_PROBLEMS


_COMMANDS = {"run": cmd_run, "export": cmd_export, "status": cmd_status, "import": cmd_import}


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    configure_logging(logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise
    return _COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
