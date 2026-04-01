"""
Cross-validation logic.

Provides helpers to:
  1. Compare DEI vs US-GAAP share counts for the same issuer/period.
  2. Detect unit/scaling anomalies (e.g. values reported in thousands vs units).
  3. Validate time-series continuity (large jumps without a corporate action).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from loguru import logger


# Thresholds
_DEI_GAAP_DIVERGENCE_THRESHOLD = 0.05   # 5 %
_LARGE_CHANGE_THRESHOLD        = 0.20   # 20 %
_SCALING_RATIO_HIGH            = 900.0  # >900x → likely units error
_SCALING_RATIO_LOW             = 0.002  # <0.002x → likely units error


def validate_dei_vs_gaap(
    dei_value: Optional[float],
    gaap_value: Optional[float],
    ticker: str = "",
) -> tuple[bool, str]:
    """Compare DEI and US-GAAP share counts for the same period.

    Args:
        dei_value: dei:EntityCommonStockSharesOutstanding value.
        gaap_value: us-gaap:CommonStockSharesOutstanding value.
        ticker: Ticker/CIK for logging context.

    Returns:
        (is_valid, message) — is_valid is False if divergence exceeds threshold.
    """
    if dei_value is None or gaap_value is None:
        return True, "One or both values missing — skipping cross-validation"
    if dei_value == 0:
        return False, f"[{ticker}] DEI value is zero — cannot compute divergence"

    div = abs(dei_value - gaap_value) / dei_value
    if div > _DEI_GAAP_DIVERGENCE_THRESHOLD:
        msg = (
            f"[{ticker}] DEI/GAAP divergence {div * 100:.2f}% exceeds "
            f"{_DEI_GAAP_DIVERGENCE_THRESHOLD * 100:.0f}% threshold "
            f"(dei={dei_value:,.0f}, gaap={gaap_value:,.0f})"
        )
        logger.warning(msg)
        return False, msg

    return True, "OK"


def detect_scaling_error(
    prev_value: float,
    curr_value: float,
    ticker: str = "",
) -> tuple[bool, str]:
    """Detect likely unit/scaling errors via ratio heuristic.

    Args:
        prev_value: Previous share count.
        curr_value: Current (potentially erroneous) share count.
        ticker: Ticker/CIK for logging.

    Returns:
        (has_error, message)
    """
    if prev_value <= 0:
        return False, "Previous value is zero/negative — cannot compute ratio"

    ratio = curr_value / prev_value
    if ratio > _SCALING_RATIO_HIGH:
        msg = (
            f"[{ticker}] Possible units error: current value is {ratio:.0f}x "
            f"previous ({prev_value:,.0f} → {curr_value:,.0f})"
        )
        logger.error(msg)
        return True, msg

    if ratio < _SCALING_RATIO_LOW:
        msg = (
            f"[{ticker}] Possible units error: current value is "
            f"{1 / ratio:.0f}x smaller than previous "
            f"({prev_value:,.0f} → {curr_value:,.0f})"
        )
        logger.error(msg)
        return True, msg

    return False, "OK"


def validate_time_series(df: pd.DataFrame, val_col: str = "val") -> pd.DataFrame:
    """Add validation columns to a shares time-series DataFrame.

    Computes period-over-period ratio and flags rows with large changes
    or likely scaling errors.

    Args:
        df: DataFrame sorted by date with a numeric value column.
        val_col: Name of the share-count column.

    Returns:
        *df* with additional columns: ["pct_change", "ratio",
        "large_change_flag", "scaling_error_flag"].
    """
    df = df.copy().sort_values("filed").reset_index(drop=True)
    df["ratio"] = df[val_col] / df[val_col].shift(1)
    df["pct_change"] = df["ratio"] - 1.0
    df["large_change_flag"] = df["pct_change"].abs() > _LARGE_CHANGE_THRESHOLD
    df["scaling_error_flag"] = (df["ratio"] > _SCALING_RATIO_HIGH) | (df["ratio"] < _SCALING_RATIO_LOW)
    return df
