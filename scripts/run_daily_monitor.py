#!/usr/bin/env python3
"""
Run the Phase 3 daily monitor.

Can be run manually or via a cron job / task scheduler at 06:00 UTC.

Usage:
    python scripts/run_daily_monitor.py
    python scripts/run_daily_monitor.py --daemon   # loop via schedule library
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import schedule
import time
from loguru import logger
from src.pipeline.daily_monitor import run
from config.settings import DAILY_MONITOR_UTC_HOUR


def _job() -> None:
    results = run()
    alert_count = len(results.get("alerts", []))
    logger.info(
        "Daily monitor finished — polygon={} splits, efts={} filings, "
        "fmp={} upcoming, {} alert(s)",
        len(results.get("polygon_splits", [])),
        len(results.get("efts_filings", [])),
        len(results.get("fmp_calendar", [])),
        alert_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: Daily Monitor")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode (scheduled via 'schedule' library)",
    )
    args = parser.parse_args()

    if args.daemon:
        schedule.every().day.at(f"{DAILY_MONITOR_UTC_HOUR:02d}:00").do(_job)
        logger.info("Daemon mode: daily monitor scheduled at {:02d}:00 UTC", DAILY_MONITOR_UTC_HOUR)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        _job()


if __name__ == "__main__":
    main()
