#!/usr/bin/env python3
"""
Run the Phase 1 historical load.

Usage:
    python scripts/run_historical_load.py [--zip PATH] [--skip-download]
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from src.pipeline.historical_load import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1: Historical Load")
    parser.add_argument(
        "--zip",
        metavar="PATH",
        help="Path to an existing companyfacts.zip (skips download)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use the cached archive at DATA_DIR/companyfacts.zip if present",
    )
    args = parser.parse_args()

    zip_path = Path(args.zip) if args.zip else None
    df = run(zip_path=zip_path, skip_download=args.skip_download)

    if df.empty:
        logger.error("Historical load returned no data")
        sys.exit(1)

    logger.success("Historical load complete: {:,} rows, {:,} issuers", len(df), df["cik"].nunique())


if __name__ == "__main__":
    main()
