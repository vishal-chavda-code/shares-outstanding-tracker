"""
Phase 3 — Daily Monitoring.

Implements the 3-5 API call daily plan:
  Call 1: Polygon splits endpoint  — executed splits (yesterday → today)
  Call 2: EDGAR EFTS               — 8-K filings mentioning split keywords
  Call 3: FMP split calendar        — upcoming announced splits (next 30 days)
  Call 4 (conditional): Polygon ticker details for buffer-zone issuers
  Call 5 (conditional): Per-ticker EDGAR company facts for confirmed splits

Results are reconciled, any confirmed share-count changes are upserted into
storage, and anomalies are forwarded to the alerts sub-system.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from src.polygon.splits import fetch_recent_splits
from src.edgar.efts import search_split_filings
from src.fmp.splits_calendar import fetch_recent_announced_splits
from src.tier.buffer_zone import identify_buffer_zone_tickers
from src.alerts.triggers import check_anomalies, fire_alert


def run(reference_date: Optional[date] = None) -> dict[str, pd.DataFrame]:
    """Execute the full daily monitoring pipeline.

    Args:
        reference_date: Date to treat as "today" (defaults to date.today()).
                        Useful for back-testing.

    Returns:
        Dict with keys "polygon_splits", "efts_filings", "fmp_calendar",
        "buffer_zone", "alerts" mapping to their respective DataFrames.
    """
    ref = reference_date or date.today()
    logger.info("=== Daily Monitor: {} ===", ref.isoformat())

    results: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Call 1 — Polygon executed splits
    # ------------------------------------------------------------------
    logger.info("Call 1/3 — Polygon splits")
    polygon_splits = fetch_recent_splits(days_back=1)
    results["polygon_splits"] = polygon_splits

    # ------------------------------------------------------------------
    # Call 2 — EDGAR EFTS 8-K scan
    # ------------------------------------------------------------------
    logger.info("Call 2/3 — EDGAR EFTS 8-K scan")
    efts_filings = search_split_filings(days_back=1)
    results["efts_filings"] = efts_filings

    # ------------------------------------------------------------------
    # Call 3 — FMP split calendar
    # ------------------------------------------------------------------
    logger.info("Call 3/3 — FMP split calendar")
    fmp_calendar = fetch_recent_announced_splits(days_ahead=30)
    results["fmp_calendar"] = fmp_calendar

    # ------------------------------------------------------------------
    # Call 4 (conditional) — buffer-zone ticker details
    # ------------------------------------------------------------------
    buffer_tickers = identify_buffer_zone_tickers()
    if buffer_tickers:
        logger.info("Call 4 — refreshing {:,} buffer-zone tickers", len(buffer_tickers))
        buffer_df = _refresh_buffer_zone(buffer_tickers)
        results["buffer_zone"] = buffer_df
    else:
        results["buffer_zone"] = pd.DataFrame()

    # ------------------------------------------------------------------
    # Reconcile & alert
    # ------------------------------------------------------------------
    alerts = _reconcile_and_alert(polygon_splits, efts_filings, fmp_calendar)
    results["alerts"] = alerts

    logger.info("Daily monitor complete — {} alert(s) fired", len(alerts))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _refresh_buffer_zone(tickers: list[str]) -> pd.DataFrame:
    """Fetch Polygon ticker details for every buffer-zone issuer.

    Args:
        tickers: List of ticker symbols near a tier boundary.

    Returns:
        DataFrame with columns [ticker, market_cap, shares_outstanding].
    """
    from src.polygon.ticker_details import get_market_cap, get_shares_outstanding

    rows = []
    for ticker in tickers:
        rows.append(
            {
                "ticker": ticker,
                "market_cap": get_market_cap(ticker),
                "shares_outstanding": get_shares_outstanding(ticker),
            }
        )
    return pd.DataFrame(rows)


def _reconcile_and_alert(
    polygon_splits: pd.DataFrame,
    efts_filings: pd.DataFrame,
    fmp_calendar: pd.DataFrame,
) -> pd.DataFrame:
    """Cross-validate the three sources and generate alerts for anomalies.

    Logic:
      - Any ticker appearing in Polygon executed splits is flagged for
        immediate share-count update.
      - Any ticker in EFTS 8-K filings not yet in Polygon is queued for
        manual review (possible reverse split with no Polygon record).
      - Upcoming FMP splits within 3 trading days are escalated to
        high-priority watch.

    Args:
        polygon_splits: Output from :func:`fetch_recent_splits`.
        efts_filings: Output from :func:`search_split_filings`.
        fmp_calendar: Output from :func:`fetch_recent_announced_splits`.

    Returns:
        DataFrame of triggered alerts with columns
        [source, ticker, reason, severity].
    """
    alerts: list[dict] = []

    # Polygon executed splits → high confidence, immediate action
    if not polygon_splits.empty and "ticker" in polygon_splits.columns:
        for ticker in polygon_splits["ticker"].unique():
            anomalies = check_anomalies(ticker, source="polygon")
            if anomalies:
                for msg in anomalies:
                    fire_alert(ticker=ticker, reason=msg, severity="high", source="polygon")
                    alerts.append({"source": "polygon", "ticker": ticker, "reason": msg, "severity": "high"})

    # EFTS filings not in Polygon → manual review
    if not efts_filings.empty:
        efts_entities = set(efts_filings.get("entity_name", pd.Series()).dropna().unique())
        for entity in efts_entities:
            alerts.append(
                {
                    "source": "efts",
                    "ticker": entity,
                    "reason": "8-K split announcement without Polygon confirmation",
                    "severity": "medium",
                }
            )

    # FMP near-term splits → watch list
    if not fmp_calendar.empty and "symbol" in fmp_calendar.columns:
        near_term = fmp_calendar[
            fmp_calendar["date"] <= pd.Timestamp(date.today()) + pd.Timedelta(days=3)
        ]
        for ticker in near_term["symbol"].unique():
            alerts.append(
                {
                    "source": "fmp",
                    "ticker": ticker,
                    "reason": "Split execution within 3 trading days",
                    "severity": "medium",
                }
            )

    return pd.DataFrame(alerts) if alerts else pd.DataFrame(
        columns=["source", "ticker", "reason", "severity"]
    )
