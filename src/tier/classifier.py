"""
Market-cap tier classifier.

Implements the exact five-tier boundary scheme from the whitepaper:

    Tier        Market Cap
    ---------   ------------------
    MEGA        > $200 B
    LARGE       $10 B  – $200 B
    MID         $2 B   – $10 B
    SMALL       $300 M – $2 B
    MICRO       < $300 M
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import pandas as pd

from config.settings import TIERS


class Tier(str, Enum):
    """Market-cap tier labels."""
    MEGA  = "MEGA"
    LARGE = "LARGE"
    MID   = "MID"
    SMALL = "SMALL"
    MICRO = "MICRO"
    UNKNOWN = "UNKNOWN"


def classify(market_cap: Optional[float]) -> Tier:
    """Classify a single market cap value into its tier.

    Args:
        market_cap: Market capitalisation in USD.  None → UNKNOWN.

    Returns:
        :class:`Tier` enum member.
    """
    if market_cap is None or pd.isna(market_cap):
        return Tier.UNKNOWN
    if market_cap > TIERS.mega_cap_min:
        return Tier.MEGA
    if market_cap > TIERS.large_cap_min:
        return Tier.LARGE
    if market_cap > TIERS.mid_cap_min:
        return Tier.MID
    if market_cap > TIERS.small_cap_min:
        return Tier.SMALL
    return Tier.MICRO


def classify_series(market_caps: pd.Series) -> pd.Series:
    """Vectorised tier classification over a pandas Series.

    Args:
        market_caps: Series of float market-cap values.

    Returns:
        Series of :class:`Tier` string values (same index).
    """
    def _cls(v: float) -> str:
        return classify(v).value

    return market_caps.map(_cls)


def classify_dataframe(df: pd.DataFrame, market_cap_col: str = "market_cap") -> pd.DataFrame:
    """Add a *tier* column to *df* based on *market_cap_col*.

    Args:
        df: Input DataFrame containing a market-cap column.
        market_cap_col: Name of the column holding market-cap values.

    Returns:
        *df* with an additional "tier" column (mutated in place).
    """
    df = df.copy()
    df["tier"] = classify_series(df[market_cap_col])
    return df


def tier_boundaries() -> dict[str, tuple[Optional[float], Optional[float]]]:
    """Return tier boundary ranges as a dict for display/documentation.

    Returns:
        Dict mapping tier name → (lower_bound_exclusive, upper_bound_inclusive).
        None indicates no bound.
    """
    return {
        Tier.MEGA.value:  (TIERS.mega_cap_min, None),
        Tier.LARGE.value: (TIERS.large_cap_min, TIERS.mega_cap_min),
        Tier.MID.value:   (TIERS.mid_cap_min,   TIERS.large_cap_min),
        Tier.SMALL.value: (TIERS.small_cap_min,  TIERS.mid_cap_min),
        Tier.MICRO.value: (None,                 TIERS.small_cap_min),
    }
