"""Booking.com review collector for the Azzurro Hotels insights dashboard.

Public API::

    from collector import run_collection
    report = run_collection(mode="incremental", trigger="cron", time_budget_s=200)
"""

from collector.pipeline import PropertyReport, RunReport, run_collection

__all__ = ["PropertyReport", "RunReport", "run_collection"]
