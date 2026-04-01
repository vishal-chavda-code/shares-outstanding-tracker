"""
Application settings loaded from environment variables.

Defines tier boundaries, buffer zone width, and API credentials.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# API credentials
# ---------------------------------------------------------------------------

SEC_USER_AGENT: str = os.environ.get("SEC_USER_AGENT", "shares-outstanding-tracker admin@example.com")
POLYGON_API_KEY: Optional[str] = os.environ.get("POLYGON_API_KEY")
FMP_API_KEY: Optional[str] = os.environ.get("FMP_API_KEY")
DATABASE_URL: Optional[str] = os.environ.get("DATABASE_URL")

# Local data directory (used when DATABASE_URL is not set)
DATA_DIR: Path = Path(os.environ.get("DATA_DIR", str(_PROJECT_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Market-cap tier boundaries (USD)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierBoundaries:
    """Market-cap tier thresholds as defined in the whitepaper.

    Tiers (exclusive lower bound, inclusive upper bound):
        MEGA   : > $200 B
        LARGE  : $10 B  – $200 B
        MID    : $2 B   – $10 B
        SMALL  : $300 M – $2 B
        MICRO  : < $300 M
    """
    mega_cap_min:  float = 200_000_000_000   # $200 B
    large_cap_min: float =  10_000_000_000   # $10 B
    mid_cap_min:   float =   2_000_000_000   # $2 B
    small_cap_min: float =     300_000_000   # $300 M
    # micro-cap is anything below small_cap_min

    # Buffer zone: securities within this fraction of a boundary get
    # promoted to enhanced daily monitoring
    buffer_zone_pct: float = 0.10  # 10 %


TIERS = TierBoundaries()


# ---------------------------------------------------------------------------
# EDGAR constants
# ---------------------------------------------------------------------------

EDGAR_BASE_URL = "https://data.sec.gov"
EDGAR_COMPANYFACTS_ZIP_URL = f"{EDGAR_BASE_URL}/Archives/edgar/full-index/companyfacts.zip"
EDGAR_FRAMES_URL = f"{EDGAR_BASE_URL}/api/xbrl/frames"

# XBRL concepts tracked
DEI_SHARES_CONCEPT = "dei:EntityCommonStockSharesOutstanding"
GAAP_SHARES_CONCEPT = "us-gaap:CommonStockSharesOutstanding"

# Maximum age of a filing before it is considered stale (days)
STALE_FILING_DAYS: int = 120


# ---------------------------------------------------------------------------
# Polygon constants
# ---------------------------------------------------------------------------

POLYGON_SPLITS_URL = "https://api.polygon.io/v3/reference/splits"


# ---------------------------------------------------------------------------
# FMP constants
# ---------------------------------------------------------------------------

FMP_BASE_URL = "https://financialmodelingprep.com/api"
FMP_SPLITS_CALENDAR_PATH = "/v3/stock_split_calendar"


# ---------------------------------------------------------------------------
# Pipeline schedule
# ---------------------------------------------------------------------------

# Hour (UTC) at which the daily monitor runs
DAILY_MONITOR_UTC_HOUR: int = 6

# Day of week for weekly companyfacts diff (0 = Monday)
WEEKLY_DIFF_DOW: int = 0
