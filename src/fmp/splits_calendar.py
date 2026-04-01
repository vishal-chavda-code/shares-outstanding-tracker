"""
FMP splits calendar — forward-looking split announcements.

FMP's stock_split_calendar endpoint returns announced (but not yet
executed) splits, complementing Polygon's executed-splits data.
This is the third of three daily API calls in Phase 3.

Endpoint: GET https://financialmodelingprep.com/api/v3/stock_split_calendar
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
from loguru import logger

from config.settings import FMP_API_KEY, FMP_BASE_URL, FMP_SPLITS_CALENDAR_PATH


_URL = f"{FMP_BASE_URL}{FMP_SPLITS_CALENDAR_PATH}"


def fetch_split_calendar(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch the FMP stock split calendar.

    Args:
        from_date: ISO start date (default: today).
        to_date: ISO end date (default: 30 days from today).

    Returns:
        DataFrame with columns [date, label, symbol, numerator, denominator].
        Returns empty DataFrame when FMP_API_KEY is missing or no results.
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping FMP split calendar fetch")
        return pd.DataFrame()

    from_date = from_date or date.today().isoformat()
    to_date = to_date or (date.today() + timedelta(days=30)).isoformat()

    params = {"from": from_date, "to": to_date, "apikey": FMP_API_KEY}

    logger.info("FMP split calendar: {} → {}", from_date, to_date)
    try:
        resp = requests.get(_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("FMP request failed: {}", exc)
        return pd.DataFrame()

    if not data:
        logger.info("FMP split calendar: no upcoming splits found")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")

    # Compute implied ratio for downstream use
    if {"numerator", "denominator"}.issubset(df.columns):
        df["split_ratio"] = df["numerator"].astype(float) / df["denominator"].astype(float)

    logger.info("FMP split calendar: {:,} upcoming splits", len(df))
    return df


def fetch_recent_announced_splits(days_ahead: int = 14) -> pd.DataFrame:
    """Convenience wrapper — fetch splits announced for the next *days_ahead* days.

    Args:
        days_ahead: Number of calendar days to look forward.

    Returns:
        DataFrame from :func:`fetch_split_calendar`.
    """
    to_date = (date.today() + timedelta(days=days_ahead)).isoformat()
    return fetch_split_calendar(to_date=to_date)
