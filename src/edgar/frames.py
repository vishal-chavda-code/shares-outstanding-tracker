"""
EDGAR Frames API — quarterly bulk refresh.

The Frames API returns every XBRL value for a given concept and period
in a single JSON response, making it ideal for the quarterly bulk-refresh
phase (Phase 2).

Endpoint pattern:
    GET https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json

Example:
    /api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY2024Q4I.json
"""

from __future__ import annotations

from typing import Optional
import requests
import pandas as pd
from loguru import logger

from config.settings import EDGAR_FRAMES_URL, SEC_USER_AGENT


_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}

# EDGAR period codes
# CY{YYYY}       — annual instant
# CY{YYYY}Q{N}I  — quarterly instant (e.g. CY2024Q4I)
# CY{YYYY}Q{N}   — quarterly duration (less common for shares)


def build_period_code(year: int, quarter: Optional[int] = None, instant: bool = True) -> str:
    """Build an EDGAR frames period code.

    Args:
        year: Calendar year (e.g. 2024).
        quarter: Quarter 1–4.  If None, returns an annual code.
        instant: Whether to append the 'I' instant suffix for quarterly codes.

    Returns:
        Period code string, e.g. "CY2024Q4I".
    """
    if quarter is None:
        return f"CY{year}"
    suffix = "I" if instant else ""
    return f"CY{year}Q{quarter}{suffix}"


def fetch_frame(
    concept: str,
    period_code: str,
    taxonomy: str = "dei",
    unit: str = "shares",
) -> pd.DataFrame:
    """Fetch a single EDGAR Frames response and return it as a DataFrame.

    Args:
        concept: XBRL concept name without namespace prefix,
                 e.g. "EntityCommonStockSharesOutstanding".
        period_code: EDGAR period code, e.g. "CY2024Q4I".
        taxonomy: XBRL taxonomy namespace ("dei" or "us-gaap").
        unit: Unit string ("shares" for share counts).

    Returns:
        DataFrame with columns [accn, cik, entityName, loc, end, val].
        Returns empty DataFrame on HTTP 404 (period not yet published).
    """
    url = f"{EDGAR_FRAMES_URL}/{taxonomy}/{concept}/{unit}/{period_code}.json"
    logger.info("Fetching EDGAR frame: {}", url)
    resp = requests.get(url, headers=_HEADERS, timeout=60)
    if resp.status_code == 404:
        logger.warning("Frame not found (404): {}", url)
        return pd.DataFrame()
    resp.raise_for_status()

    payload = resp.json()
    data = payload.get("data", [])
    columns = payload.get("fields", ["accn", "cik", "entityName", "loc", "end", "val"])
    df = pd.DataFrame(data, columns=columns)
    df["period_code"] = period_code
    df["concept"] = f"{taxonomy}:{concept}"
    df["cik"] = df["cik"].astype(str).str.zfill(10)
    logger.info("  → {:,} rows", len(df))
    return df


def fetch_latest_quarter_frame(year: int, quarter: int) -> pd.DataFrame:
    """Convenience wrapper: fetch dei:EntityCommonStockSharesOutstanding for a quarter.

    Args:
        year: Calendar year.
        quarter: Quarter (1–4).

    Returns:
        DataFrame from :func:`fetch_frame`.
    """
    period_code = build_period_code(year, quarter, instant=True)
    return fetch_frame(
        concept="EntityCommonStockSharesOutstanding",
        period_code=period_code,
        taxonomy="dei",
        unit="shares",
    )
