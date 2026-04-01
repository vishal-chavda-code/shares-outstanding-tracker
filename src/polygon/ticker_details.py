"""
Polygon.io ticker details — market cap lookups for buffer-zone checks.

Used in Phase 3 to retrieve current market cap for securities that are
near tier boundaries so they can be promoted/demoted between monitoring
tiers in real-time.

Endpoint: GET https://api.polygon.io/v3/reference/tickers/{ticker}
"""

from __future__ import annotations

from typing import Optional

import requests
from loguru import logger

from config.settings import POLYGON_API_KEY


_TICKER_DETAILS_URL = "https://api.polygon.io/v3/reference/tickers/{ticker}"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {POLYGON_API_KEY}"} if POLYGON_API_KEY else {}


def get_market_cap(ticker: str) -> Optional[float]:
    """Fetch the current market capitalisation for *ticker* from Polygon.

    Args:
        ticker: Exchange ticker symbol (e.g. "AAPL").

    Returns:
        Market cap in USD, or None if unavailable.
    """
    if not POLYGON_API_KEY:
        logger.warning("POLYGON_API_KEY not set — cannot fetch market cap for {}", ticker)
        return None

    url = _TICKER_DETAILS_URL.format(ticker=ticker.upper())
    try:
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", {})
        market_cap = results.get("market_cap")
        logger.debug("{} market_cap = {}", ticker, market_cap)
        return float(market_cap) if market_cap is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.error("Polygon ticker_details failed for {}: {}", ticker, exc)
        return None


def get_shares_outstanding(ticker: str) -> Optional[float]:
    """Fetch the weighted outstanding share count for *ticker* from Polygon.

    Polygon includes share_class_shares_outstanding in the ticker details
    response, which provides a real-time cross-check against EDGAR data.

    Args:
        ticker: Exchange ticker symbol.

    Returns:
        Share count as a float, or None if unavailable.
    """
    if not POLYGON_API_KEY:
        return None

    url = _TICKER_DETAILS_URL.format(ticker=ticker.upper())
    try:
        resp = requests.get(url, headers=_headers(), timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", {})
        shares = results.get("share_class_shares_outstanding") or results.get("weighted_shares_outstanding")
        return float(shares) if shares is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.error("Polygon ticker_details failed for {}: {}", ticker, exc)
        return None
