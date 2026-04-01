"""
EDGAR Full-Text Search (EFTS) — scan for 8-K split announcements.

EFTS lets us search the full text of recent SEC filings for keywords
associated with stock splits (e.g. "stock split", "reverse split").
This is one of three daily API calls in Phase 3.

EDGAR EFTS base: https://efts.sec.gov/LATEST/search-index?q=...
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
from loguru import logger

from config.settings import SEC_USER_AGENT


_EFTS_BASE = "https://efts.sec.gov/LATEST/search-index"
_HEADERS = {"User-Agent": SEC_USER_AGENT}

_SPLIT_KEYWORDS = [
    '"stock split"',
    '"reverse stock split"',
    '"reverse split"',
    '"forward split"',
]


def search_split_filings(
    days_back: int = 1,
    forms: tuple[str, ...] = ("8-K",),
    extra_keywords: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Search EDGAR EFTS for recent split-related 8-K filings.

    Constructs a full-text search query combining the standard split
    keywords and optionally any caller-supplied extras, filtered to the
    specified form types and date range.

    Args:
        days_back: How many calendar days back to search (default 1).
        forms: SEC form types to include (default 8-K).
        extra_keywords: Additional search terms to OR into the query.

    Returns:
        DataFrame with columns [accession_no, file_date, form_type, entity_name, cik].
        Empty DataFrame if no results or on error.
    """
    keywords = list(_SPLIT_KEYWORDS) + (extra_keywords or [])
    query_str = " OR ".join(keywords)
    start_date = (date.today() - timedelta(days=days_back)).isoformat()
    end_date = date.today().isoformat()

    params: dict = {
        "q": query_str,
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
        "forms": ",".join(forms),
        "_source": "file_date,form_type,entity_name,file_num,period_of_report",
        "hits.hits._source": "true",
    }

    logger.info("EFTS split search: {} → {}", start_date, end_date)
    try:
        resp = requests.get(_EFTS_BASE, params=params, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("EFTS request failed: {}", exc)
        return pd.DataFrame()

    hits = payload.get("hits", {}).get("hits", [])
    if not hits:
        logger.info("EFTS: no split filings found in range")
        return pd.DataFrame()

    rows = []
    for hit in hits:
        src = hit.get("_source", {})
        rows.append(
            {
                "accession_no": hit.get("_id", ""),
                "file_date": src.get("file_date"),
                "form_type": src.get("form_type"),
                "entity_name": src.get("entity_name"),
                "cik": src.get("file_num", ""),
            }
        )

    df = pd.DataFrame(rows)
    logger.info("EFTS: found {} split-related filings", len(df))
    return df
