"""
Phase 1 — Historical Load (one-time bootstrap).

Downloads the full companyfacts.zip from EDGAR (~1 GB), extracts
dei:EntityCommonStockSharesOutstanding for every US-listed public company,
and persists the result to PostgreSQL (if DATABASE_URL is configured) or
Parquet files on disk.

Run once, then rely on Phase 2 for incremental updates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import DATA_DIR, DATABASE_URL
from src.edgar.company_facts import download_companyfacts_zip, load_all_shares
from src.utils.db import get_engine, SHARES_TABLE


def run(
    zip_path: Optional[Path] = None,
    skip_download: bool = False,
) -> pd.DataFrame:
    """Execute the full historical load.

    Args:
        zip_path: Path to an already-downloaded companyfacts.zip.
                  If None, the archive is downloaded from EDGAR.
        skip_download: If True and *zip_path* is None, look for the archive
                       at the default location (DATA_DIR/companyfacts.zip)
                       without downloading.

    Returns:
        DataFrame of all extracted shares-outstanding records.
    """
    # ------------------------------------------------------------------
    # Step 1: Obtain the archive
    # ------------------------------------------------------------------
    if zip_path is None:
        default_zip = DATA_DIR / "companyfacts.zip"
        if skip_download and default_zip.exists():
            logger.info("Using existing archive at {}", default_zip)
            zip_path = default_zip
        else:
            logger.info("Step 1/3 — Downloading companyfacts.zip")
            zip_path = download_companyfacts_zip(dest=default_zip)
    else:
        logger.info("Step 1/3 — Using supplied archive: {}", zip_path)

    # ------------------------------------------------------------------
    # Step 2: Parse all company facts
    # ------------------------------------------------------------------
    logger.info("Step 2/3 — Parsing companyfacts archive")
    df = load_all_shares(zip_path)
    if df.empty:
        logger.error("Historical load produced no data — aborting")
        return df

    # ------------------------------------------------------------------
    # Step 3: Persist
    # ------------------------------------------------------------------
    logger.info("Step 3/3 — Persisting {:,} rows", len(df))
    if DATABASE_URL:
        _write_to_postgres(df)
    else:
        _write_to_parquet(df)

    logger.success("Historical load complete")
    return df


def _write_to_postgres(df: pd.DataFrame) -> None:
    """Bulk-insert *df* into the shares_outstanding table via SQLAlchemy."""
    engine = get_engine()
    logger.info("Writing to PostgreSQL table '{}'", SHARES_TABLE)
    df.to_sql(SHARES_TABLE, engine, if_exists="replace", index=False, chunksize=10_000)
    logger.info("PostgreSQL write complete")


def _write_to_parquet(df: pd.DataFrame) -> None:
    """Write *df* to DATA_DIR/shares_outstanding.parquet."""
    out = DATA_DIR / "shares_outstanding.parquet"
    df.to_parquet(out, index=False, engine="pyarrow", compression="snappy")
    logger.info("Parquet written: {}", out)
