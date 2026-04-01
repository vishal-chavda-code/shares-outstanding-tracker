"""
EDGAR companyfacts.zip ETL.

Phase 1 (historical load) downloads the full companyfacts.zip archive
(~1 GB) from EDGAR and extracts dei:EntityCommonStockSharesOutstanding
for every filer.  Phase 2 weekly diff re-uses the same logic against a
smaller incremental archive.

Endpoint: https://data.sec.gov/Archives/edgar/full-index/companyfacts.zip
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Generator, Optional

import pandas as pd
import requests
from loguru import logger

from config.settings import (
    EDGAR_COMPANYFACTS_ZIP_URL,
    SEC_USER_AGENT,
    DEI_SHARES_CONCEPT,
    GAAP_SHARES_CONCEPT,
    DATA_DIR,
)


_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
_CONCEPT_KEYS = ("dei", "us-gaap")


def download_companyfacts_zip(dest: Optional[Path] = None, chunk_size: int = 1 << 20) -> Path:
    """Stream companyfacts.zip from EDGAR to *dest* on disk.

    Args:
        dest: Local path to write the archive.  Defaults to DATA_DIR/companyfacts.zip.
        chunk_size: Streaming chunk size in bytes (default 1 MiB).

    Returns:
        Path to the downloaded archive.
    """
    dest = dest or DATA_DIR / "companyfacts.zip"
    logger.info("Downloading companyfacts.zip → {}", dest)
    with requests.get(EDGAR_COMPANYFACTS_ZIP_URL, headers=_HEADERS, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=chunk_size):
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    logger.debug("  {:.1f}% ({} / {} bytes)", pct, downloaded, total)
    logger.info("Download complete: {}", dest)
    return dest


def iter_company_facts(zip_path: Path) -> Generator[dict, None, None]:
    """Iterate over per-company JSON blobs inside a companyfacts zip archive.

    Yields:
        Raw parsed JSON dict for each company file.
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json")]
        logger.info("companyfacts archive contains {} company JSON files", len(names))
        for name in names:
            try:
                with zf.open(name) as fh:
                    yield json.load(fh)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping {}: {}", name, exc)


def extract_shares_outstanding(company_json: dict) -> pd.DataFrame:
    """Extract shares-outstanding time-series from a single company's facts blob.

    Tries dei:EntityCommonStockSharesOutstanding first, falls back to
    us-gaap:CommonStockSharesOutstanding.  Both series are returned with a
    *concept* column so the caller can distinguish them.

    Args:
        company_json: Parsed JSON from an EDGAR companyfacts file.

    Returns:
        DataFrame with columns [cik, entity_name, concept, accn, form,
        filed, period_of_report, val, unit].
    """
    cik: str = str(company_json.get("cik", "")).zfill(10)
    entity: str = company_json.get("entityName", "")
    facts: dict = company_json.get("facts", {})

    rows: list[dict] = []
    for namespace, concept_suffix in [
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ]:
        concept_data = facts.get(namespace, {}).get(concept_suffix, {})
        units_block = concept_data.get("units", {})
        for unit_key, filings in units_block.items():
            for filing in filings:
                rows.append(
                    {
                        "cik": cik,
                        "entity_name": entity,
                        "concept": f"{namespace}:{concept_suffix}",
                        "accn": filing.get("accn"),
                        "form": filing.get("form"),
                        "filed": filing.get("filed"),
                        "period_of_report": filing.get("end"),
                        "val": filing.get("val"),
                        "unit": unit_key,
                    }
                )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
    df["period_of_report"] = pd.to_datetime(df["period_of_report"], errors="coerce")
    return df


def load_all_shares(zip_path: Path) -> pd.DataFrame:
    """Full ETL: download (if needed) and parse the entire companyfacts archive.

    Args:
        zip_path: Path to an existing companyfacts.zip.

    Returns:
        Concatenated DataFrame for all issuers.
    """
    frames: list[pd.DataFrame] = []
    for company_json in iter_company_facts(zip_path):
        df = extract_shares_outstanding(company_json)
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.warning("No shares-outstanding data extracted from {}", zip_path)
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info("Extracted {:,} rows for {:,} issuers", len(combined), combined["cik"].nunique())
    return combined
