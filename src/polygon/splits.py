"""
Polygon.io splits endpoint.

Fetches forward and reverse stock splits via the Polygon REST API.
This is the primary real-time corporate-actions layer in Phase 3.

Endpoint: GET https://api.polygon.io/v3/reference/splits
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
from loguru import logger

from config.settings import POLYGON_API_KEY, POLYGON_SPLITS_URL


def _build_headers() -> dict[str, str]:
    if POLYGON_API_KEY:
        return {"Authorization": f"Bearer {POLYGON_API_KEY}"}
    return {}


def fetch_splits(
    execution_date_gte: Optional[str] = None,
    execution_date_lte: Optional[str] = None,
    ticker: Optional[str] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch stock splits from the Polygon v3 reference/splits endpoint.

    Automatically paginates through all result pages.

    Args:
        execution_date_gte: ISO date lower bound (inclusive), e.g. "2024-01-01".
                            Defaults to yesterday.
        execution_date_lte: ISO date upper bound (inclusive).  Defaults to today.
        ticker: Filter to a single ticker symbol.
        limit: Page size (max 1000 per Polygon docs).

    Returns:
        DataFrame with columns [execution_date, split_from, split_to, ticker].
        Returns empty DataFrame if API key is missing or no results found.
    """
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — skipping Polygon splits fetch")
        return pd.DataFrame()

    execution_date_gte = execution_date_gte or (date.today() - timedelta(days=1)).isoformat()
    execution_date_lte = execution_date_lte or date.today().isoformat()

    params: dict = {
        "execution_date.gte": execution_date_gte,
        "execution_date.lte": execution_date_lte,
        "limit": limit,
    }
    if ticker:
        params["ticker"] = ticker

    all_results: list[dict] = []
    url: Optional[str] = POLYGON_SPLITS_URL
    headers = _build_headers()

    while url:
        logger.debug("Polygon splits page: {}", url)
        resp = requests.get(url, params=params if url == POLYGON_SPLITS_URL else None,
                            headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        all_results.extend(payload.get("results", []))
        url = payload.get("next_url")  # None when exhausted

    if not all_results:
        logger.info("Polygon splits: no results for {} → {}", execution_date_gte, execution_date_lte)
        return pd.DataFrame()

    df = pd.DataFrame(all_results)
    df["execution_date"] = pd.to_datetime(df.get("execution_date"), errors="coerce")
    logger.info("Polygon splits: {:,} records fetched", len(df))
    return df


def fetch_recent_splits(days_back: int = 1) -> pd.DataFrame:
    """Convenience wrapper — fetch splits executed in the last *days_back* days.

    Args:
        days_back: Number of calendar days to look back.

    Returns:
        DataFrame from :func:`fetch_splits`.
    """
    gte = (date.today() - timedelta(days=days_back)).isoformat()
    return fetch_splits(execution_date_gte=gte)
