"""
Buffer-zone detection and enhanced monitoring.

Securities whose market cap is within BUFFER_ZONE_PCT (default 10 %) of
any tier boundary are placed in a "buffer zone" and promoted to enhanced
daily monitoring regardless of their nominal tier.

Example: a company with a $9.2 B market cap is in the SMALL tier but within
10 % of the $10 B LARGE boundary → buffer zone → daily refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import TIERS
from src.tier.classifier import Tier, classify


@dataclass
class BufferZoneResult:
    """Result of a buffer-zone check for a single issuer."""
    ticker: str
    market_cap: float
    tier: Tier
    in_buffer_zone: bool
    nearest_boundary: Optional[float]
    boundary_label: Optional[str]
    pct_from_boundary: Optional[float]


_BOUNDARIES: list[tuple[float, str]] = [
    (TIERS.mega_cap_min,  "MEGA/LARGE"),
    (TIERS.large_cap_min, "LARGE/MID"),
    (TIERS.mid_cap_min,   "MID/SMALL"),
    (TIERS.small_cap_min, "SMALL/MICRO"),
]


def check_buffer_zone(ticker: str, market_cap: float) -> BufferZoneResult:
    """Determine whether *ticker* is in a buffer zone.

    Args:
        ticker: Exchange ticker symbol.
        market_cap: Current market capitalisation in USD.

    Returns:
        :class:`BufferZoneResult` with full diagnostics.
    """
    tier = classify(market_cap)
    nearest_boundary: Optional[float] = None
    boundary_label: Optional[str] = None
    pct_from_boundary: Optional[float] = None
    in_buffer = False

    for boundary, label in _BOUNDARIES:
        pct_diff = abs(market_cap - boundary) / boundary
        if pct_diff <= TIERS.buffer_zone_pct:
            in_buffer = True
            nearest_boundary = boundary
            boundary_label = label
            pct_from_boundary = pct_diff
            break  # report only the closest breach

    if not in_buffer:
        # Find the nearest boundary even if not in zone (for diagnostics)
        diffs = [(abs(market_cap - b) / b, b, lbl) for b, lbl in _BOUNDARIES]
        pct_from_boundary, nearest_boundary, boundary_label = min(diffs, key=lambda x: x[0])

    return BufferZoneResult(
        ticker=ticker,
        market_cap=market_cap,
        tier=tier,
        in_buffer_zone=in_buffer,
        nearest_boundary=nearest_boundary,
        boundary_label=boundary_label,
        pct_from_boundary=pct_from_boundary,
    )


def identify_buffer_zone_tickers(
    df: Optional[pd.DataFrame] = None,
    ticker_col: str = "ticker",
    market_cap_col: str = "market_cap",
) -> list[str]:
    """Return tickers from *df* that are currently in a buffer zone.

    If *df* is None, loads the latest known market caps from the local
    Parquet store (a stub in the current implementation).

    Args:
        df: DataFrame containing ticker and market-cap columns.
        ticker_col: Name of the ticker column.
        market_cap_col: Name of the market-cap column.

    Returns:
        List of ticker symbols in the buffer zone.
    """
    if df is None:
        df = _load_market_caps()

    if df.empty or market_cap_col not in df.columns:
        logger.debug("No market-cap data available for buffer-zone check")
        return []

    buffer_tickers: list[str] = []
    for _, row in df.iterrows():
        ticker = row.get(ticker_col, "")
        mc = row.get(market_cap_col)
        if mc and pd.notna(mc):
            result = check_buffer_zone(ticker, float(mc))
            if result.in_buffer_zone:
                buffer_tickers.append(ticker)
                logger.debug(
                    "{} is in buffer zone ({:.1f}% from {} boundary)",
                    ticker,
                    (result.pct_from_boundary or 0) * 100,
                    result.boundary_label,
                )

    logger.info("Buffer zone: {:,} tickers identified", len(buffer_tickers))
    return buffer_tickers


def _load_market_caps() -> pd.DataFrame:
    """Stub: load the most recent market-cap snapshot from local storage.

    In production this would query PostgreSQL or read from a Parquet file
    maintained by the quarterly refresh pipeline.
    """
    from config.settings import DATA_DIR
    mc_path = DATA_DIR / "market_caps.parquet"
    if mc_path.exists():
        return pd.read_parquet(mc_path)
    logger.warning("No market_caps.parquet found at {}", mc_path)
    return pd.DataFrame()
