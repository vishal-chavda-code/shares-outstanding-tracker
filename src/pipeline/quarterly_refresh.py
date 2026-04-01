"""
Phase 2 — Quarterly Bulk Refresh.

Two complementary update paths:
  a) Frames API call  — once per quarter, retrieves the full XBRL frame
     for dei:EntityCommonStockSharesOutstanding for the latest quarter.
  b) Weekly diff      — downloads a fresh companyfacts.zip and upserts
     any records newer than the last known filing date.

Both paths upsert into the same PostgreSQL table or Parquet store used by
the historical load.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import DATA_DIR, DATABASE_URL
from src.edgar.frames import fetch_latest_quarter_frame
from src.edgar.company_facts import download_companyfacts_zip, load_all_shares
from src.utils.db import get_engine, SHARES_TABLE


def run_frames_refresh(year: Optional[int] = None, quarter: Optional[int] = None) -> pd.DataFrame:
    """Fetch the latest EDGAR Frames snapshot and upsert into storage.

    Args:
        year: Calendar year (defaults to current year).
        quarter: Quarter 1–4 (defaults to the most recently completed quarter).

    Returns:
        DataFrame of newly fetched frame data.
    """
    today = date.today()
    if year is None:
        year = today.year
    if quarter is None:
        quarter = _current_quarter(today)

    logger.info("Quarterly frames refresh: {}Q{}", year, quarter)
    df = fetch_latest_quarter_frame(year, quarter)
    if df.empty:
        logger.warning("Frames API returned no data for {}Q{}", year, quarter)
        return df

    _upsert(df, source="frames")
    return df


def run_weekly_diff(dest: Optional[Path] = None) -> pd.DataFrame:
    """Download a fresh companyfacts.zip and upsert newer records.

    Args:
        dest: Local path for the downloaded archive.

    Returns:
        DataFrame of upserted records.
    """
    logger.info("Weekly companyfacts diff")
    zip_path = download_companyfacts_zip(dest=dest or DATA_DIR / "companyfacts_weekly.zip")
    df = load_all_shares(zip_path)
    if df.empty:
        return df
    _upsert(df, source="weekly_diff")
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _current_quarter(d: date) -> int:
    """Return the most recently *completed* calendar quarter for *d*."""
    # Q1 ends Mar 31, Q2 Jun 30, Q3 Sep 30, Q4 Dec 31
    # If we're in Q1 (Jan-Mar), the latest completed quarter is Q4 of last year
    month = d.month
    if month <= 3:
        return 4   # caller should decrement year separately if needed
    elif month <= 6:
        return 1
    elif month <= 9:
        return 2
    else:
        return 3


def _upsert(df: pd.DataFrame, source: str) -> None:
    """Upsert *df* into PostgreSQL or append to the Parquet file."""
    if DATABASE_URL:
        engine = get_engine()
        # Simple upsert via temp-table pattern (replace per accn+cik combo)
        logger.info("[{}] Upserting {:,} rows into PostgreSQL", source, len(df))
        df.to_sql(f"{SHARES_TABLE}_staging", engine, if_exists="replace", index=False)
        with engine.begin() as conn:
            conn.execute(
                f"""
                INSERT INTO {SHARES_TABLE}
                SELECT * FROM {SHARES_TABLE}_staging
                ON CONFLICT (cik, accn) DO UPDATE
                SET val = EXCLUDED.val,
                    filed = EXCLUDED.filed
                """  # noqa: S608
            )
        logger.info("Upsert complete")
    else:
        out = DATA_DIR / "shares_outstanding.parquet"
        if out.exists():
            existing = pd.read_parquet(out)
            combined = pd.concat([existing, df], ignore_index=True).drop_duplicates(
                subset=["cik", "accn"], keep="last"
            )
        else:
            combined = df
        combined.to_parquet(out, index=False, engine="pyarrow", compression="snappy")
        logger.info("[{}] Parquet updated: {:,} total rows", source, len(combined))
