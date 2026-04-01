#!/usr/bin/env python3
"""
Run the Phase 2 quarterly refresh.

Usage:
    # Frames API refresh for the current quarter
    python scripts/run_quarterly_refresh.py --mode frames

    # Weekly diff (download new companyfacts.zip and upsert)
    python scripts/run_quarterly_refresh.py --mode weekly

    # Specific year/quarter
    python scripts/run_quarterly_refresh.py --mode frames --year 2024 --quarter 4
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from src.pipeline.quarterly_refresh import run_frames_refresh, run_weekly_diff


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: Quarterly Refresh")
    parser.add_argument(
        "--mode",
        choices=["frames", "weekly"],
        required=True,
        help="'frames' for EDGAR Frames API bulk pull, 'weekly' for companyfacts diff",
    )
    parser.add_argument("--year",    type=int, help="Calendar year (frames mode only)")
    parser.add_argument("--quarter", type=int, choices=[1, 2, 3, 4], help="Quarter (frames mode only)")
    args = parser.parse_args()

    if args.mode == "frames":
        df = run_frames_refresh(year=args.year, quarter=args.quarter)
        if df.empty:
            logger.warning("Frames refresh returned no data")
        else:
            logger.success("Frames refresh: {:,} rows", len(df))
    else:
        df = run_weekly_diff()
        if df.empty:
            logger.warning("Weekly diff returned no data")
        else:
            logger.success("Weekly diff: {:,} rows upserted", len(df))


if __name__ == "__main__":
    main()
