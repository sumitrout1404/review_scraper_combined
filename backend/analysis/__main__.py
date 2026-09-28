"""CLI: ``python -m analysis [--method auto|rules|llm] [--reanalyse] [--upgrade-rules] [--limit N] ...``

Run from ``backend/``. Uses the MongoDB configured by ``MONGODB_URI`` (``backend/.env`` locally).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from analysis.pipeline import METHODS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m analysis", description="Classify review topics + sentiment.")
    parser.add_argument("--method", choices=METHODS, default="auto",
                        help="auto = LLM if GROQ_API_KEY is set, otherwise rules (default)")
    parser.add_argument("--reanalyse", action="store_true", help="re-analyse every review, ignoring the cache")
    parser.add_argument("--upgrade-rules", action="store_true",
                        help="re-run the LLM on in-window reviews previously analysed by rules")
    parser.add_argument("--limit", type=int, help="analyse at most N pending reviews")
    parser.add_argument("--time-budget", type=float, dest="time_budget_s", help="stop cleanly after N seconds")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from core.logging import configure_logging  # redacts secrets in every record
    configure_logging(logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)   # one INFO line per request is noise

    from analysis.pipeline import run_analysis
    from analysis.settings import load_settings
    settings = load_settings()                  # also loads backend/.env (MONGODB_URI, GROQ_*)
    try:
        stats = run_analysis(
            method=args.method, reanalyse=args.reanalyse, limit=args.limit,
            time_budget_s=args.time_budget_s, upgrade_rules=args.upgrade_rules or None, settings=settings,
        )
    except ValueError as exc:
        logging.getLogger("analysis").error("%s", exc)
        return 2
    sys.stdout.write(json.dumps(stats, indent=2) + "\n")
    return 1 if stats["errors"] and not stats["analysed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
