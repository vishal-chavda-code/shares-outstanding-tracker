"""
Manual review triggers and anomaly detection.

Anomalies that warrant manual review:
  1. Share count changes > 20 % with no confirmed corporate-action event
  2. DEI vs US-GAAP value divergence > 5 %
  3. Scaling errors (e.g. 1,000x / 0.001x jumps suggesting a units mismatch)
  4. Stale filings (no update in > STALE_FILING_DAYS days)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import STALE_FILING_DAYS

# In-memory alert log (replaced by DB/queue in production)
_alert_log: list[dict] = []


def check_anomalies(
    ticker: str,
    source: str = "unknown",
    prev_shares: Optional[float] = None,
    curr_shares: Optional[float] = None,
    dei_shares: Optional[float] = None,
    gaap_shares: Optional[float] = None,
    last_filed: Optional[date] = None,
) -> list[str]:
    """Run all anomaly checks for a single ticker and return messages.

    Args:
        ticker: Exchange ticker symbol.
        source: Data source label for logging.
        prev_shares: Previous known share count.
        curr_shares: Current share count.
        dei_shares: DEI concept value (for cross-validation).
        gaap_shares: US-GAAP concept value (for cross-validation).
        last_filed: Date of the most recent EDGAR filing.

    Returns:
        List of anomaly description strings (empty if all checks pass).
    """
    messages: list[str] = []

    # Check 1: Large unexplained share-count change
    if prev_shares and curr_shares and prev_shares > 0:
        ratio = curr_shares / prev_shares
        if ratio > 1.20 or ratio < 0.80:
            messages.append(
                f"Share count changed by {(ratio - 1) * 100:.1f}% "
                f"({prev_shares:,.0f} → {curr_shares:,.0f}) without confirmed event"
            )

    # Check 2: Scaling error heuristic (1000x jump or 0.001x drop)
    if prev_shares and curr_shares and prev_shares > 0:
        ratio = curr_shares / prev_shares
        if ratio > 900 or ratio < 0.002:
            messages.append(
                f"Possible units/scaling error: ratio={ratio:.1f} "
                f"({prev_shares:,.0f} → {curr_shares:,.0f})"
            )

    # Check 3: DEI vs US-GAAP divergence
    if dei_shares and gaap_shares and dei_shares > 0:
        div = abs(dei_shares - gaap_shares) / dei_shares
        if div > 0.05:
            messages.append(
                f"DEI/GAAP divergence {div * 100:.1f}%: "
                f"dei={dei_shares:,.0f}, gaap={gaap_shares:,.0f}"
            )

    # Check 4: Stale filing
    if last_filed is not None:
        age = (date.today() - last_filed).days
        if age > STALE_FILING_DAYS:
            messages.append(
                f"Stale filing: last update was {age} days ago (threshold={STALE_FILING_DAYS})"
            )

    if messages:
        logger.warning("[{}] {} anomaly/anomalies for {}: {}", source, len(messages), ticker, messages)

    return messages


def fire_alert(
    ticker: str,
    reason: str,
    severity: str = "medium",
    source: str = "unknown",
) -> None:
    """Record and emit an alert.

    In production this would push to a queue, send an email, or write to
    a database.  For now it logs at the appropriate level and appends to
    the in-memory log.

    Args:
        ticker: Affected ticker.
        reason: Human-readable description of the anomaly.
        severity: "low", "medium", or "high".
        source: Data source that triggered the alert.
    """
    entry = {
        "ts": date.today().isoformat(),
        "ticker": ticker,
        "reason": reason,
        "severity": severity,
        "source": source,
    }
    _alert_log.append(entry)

    if severity == "high":
        logger.error("[ALERT][{}] {} — {}", source, ticker, reason)
    elif severity == "medium":
        logger.warning("[ALERT][{}] {} — {}", source, ticker, reason)
    else:
        logger.info("[ALERT][{}] {} — {}", source, ticker, reason)


def get_alert_log() -> pd.DataFrame:
    """Return the current in-memory alert log as a DataFrame."""
    return pd.DataFrame(_alert_log)


def clear_alert_log() -> None:
    """Clear the in-memory alert log (useful between test runs)."""
    global _alert_log
    _alert_log = []
