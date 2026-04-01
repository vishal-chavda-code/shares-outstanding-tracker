"""
Database connection and SQLAlchemy model definitions.

Supports PostgreSQL (via psycopg2) when DATABASE_URL is set, otherwise
the pipeline falls back to Parquet files in DATA_DIR.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from loguru import logger
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

from config.settings import DATABASE_URL

SHARES_TABLE = "shares_outstanding"

_metadata = MetaData()

# SQLAlchemy Core table definition (used for schema creation)
shares_outstanding_table = Table(
    SHARES_TABLE,
    _metadata,
    Column("cik",              String(10),  nullable=False),
    Column("entity_name",      String(255), nullable=True),
    Column("concept",          String(80),  nullable=False),
    Column("accn",             String(25),  nullable=True),
    Column("form",             String(20),  nullable=True),
    Column("filed",            Date,        nullable=True),
    Column("period_of_report", Date,        nullable=True),
    Column("val",              Float,       nullable=True),
    Column("unit",             String(20),  nullable=True),
    Column("period_code",      String(20),  nullable=True),
)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine.

    Raises:
        RuntimeError: If DATABASE_URL is not configured.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure it in .env or use Parquet storage."
        )
    logger.info("Connecting to database: {}", _redact_url(DATABASE_URL))
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def ensure_schema() -> None:
    """Create the shares_outstanding table if it does not exist."""
    engine = get_engine()
    _metadata.create_all(engine, checkfirst=True)
    logger.info("Database schema ensured")


def get_latest_shares(cik: str, engine: Optional[Engine] = None) -> Optional[float]:
    """Fetch the most recent share count for *cik* from PostgreSQL.

    Args:
        cik: 10-digit CIK string.
        engine: SQLAlchemy engine (defaults to :func:`get_engine`).

    Returns:
        Latest share count, or None if not found.
    """
    eng = engine or get_engine()
    query = text(
        f"""
        SELECT val
        FROM {SHARES_TABLE}
        WHERE cik = :cik
          AND concept = 'dei:EntityCommonStockSharesOutstanding'
        ORDER BY filed DESC
        LIMIT 1
        """  # noqa: S608
    )
    with eng.connect() as conn:
        row = conn.execute(query, {"cik": cik}).fetchone()
    return float(row[0]) if row else None


def _redact_url(url: str) -> str:
    """Replace the password in a connection URL with ***."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(parsed.password, "***")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:  # noqa: BLE001
        pass
    return url
