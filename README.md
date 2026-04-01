# US Equity Shares Outstanding Tracker

A production-grade Python system for tracking common stock shares outstanding across all US-listed public companies (~8,000+ issuers). Uses **SEC EDGAR** as the authoritative quarterly backbone and **Polygon.io** as a real-time corporate-actions layer — at **zero licensing cost**.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     Three-Phase Pipeline                       │
├───────────────┬──────────────────────┬────────────────────────┤
│  Phase 1      │  Phase 2             │  Phase 3               │
│  Historical   │  Quarterly Refresh   │  Daily Monitor         │
│  Load         │                      │                        │
│  (one-time)   │  · Frames API (qtrly)│  · Polygon splits      │
│               │  · companyfacts diff │  · EDGAR EFTS 8-K scan │
│  companyfacts │    (weekly)          │  · FMP split calendar  │
│  .zip ETL     │                      │  · Buffer-zone refresh │
└───────────────┴──────────────────────┴────────────────────────┘
```

---

## Data Sources

| Source | Endpoint | Cost | Use |
|--------|----------|------|-----|
| SEC EDGAR XBRL | `companyfacts.zip` / Frames API | Free | Primary share counts |
| SEC EDGAR EFTS | Full-text search | Free | Split 8-K detection |
| Polygon.io | `/v3/reference/splits` | Free tier | Executed splits |
| FMP | `/v3/stock_split_calendar` | Free tier | Upcoming splits |

### XBRL Concepts Tracked
- `dei:EntityCommonStockSharesOutstanding` (primary)
- `us-gaap:CommonStockSharesOutstanding` (cross-validation)

---

## Market-Cap Tier System

| Tier | Threshold |
|------|-----------|
| **Mega-Cap** | > $200 B |
| **Large-Cap** | $10 B – $200 B |
| **Mid-Cap** | $2 B – $10 B |
| **Small-Cap** | $300 M – $2 B |
| **Micro-Cap** | < $300 M |

**Buffer Zone:** Securities within **10%** of any tier boundary are promoted to enhanced daily monitoring regardless of their nominal tier.

---

## Project Structure

```
shares-outstanding-tracker/
├── config/
│   └── settings.py          # Tier boundaries, API keys, constants
├── src/
│   ├── edgar/
│   │   ├── company_facts.py # companyfacts.zip ETL
│   │   ├── frames.py        # EDGAR Frames API (quarterly bulk)
│   │   └── efts.py          # EDGAR full-text search (8-K splits)
│   ├── polygon/
│   │   ├── splits.py        # Executed splits (daily)
│   │   └── ticker_details.py# Market cap / shares (buffer zone)
│   ├── fmp/
│   │   └── splits_calendar.py # Upcoming announced splits
│   ├── pipeline/
│   │   ├── historical_load.py   # Phase 1
│   │   ├── quarterly_refresh.py # Phase 2
│   │   └── daily_monitor.py     # Phase 3
│   ├── tier/
│   │   ├── classifier.py    # Market-cap tier classification
│   │   └── buffer_zone.py   # Buffer-zone detection
│   ├── alerts/
│   │   └── triggers.py      # Anomaly detection & alerts
│   └── utils/
│       ├── db.py             # PostgreSQL / Parquet storage
│       └── validation.py     # DEI vs GAAP cross-validation
├── dashboard/
│   └── app.py               # Plotly Dash UI
├── scripts/
│   ├── run_historical_load.py
│   ├── run_quarterly_refresh.py
│   └── run_daily_monitor.py
└── tests/
    ├── test_edgar.py
    ├── test_tier_classifier.py
    └── test_splits.py
```

---

## Quick Start

### 1. Clone & set up environment

```bash
git clone https://github.com/YOUR_USERNAME/shares-outstanding-tracker.git
cd shares-outstanding-tracker
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env with your credentials:
#   SEC_USER_AGENT  — required by EDGAR fair-use policy
#   POLYGON_API_KEY — free at polygon.io
#   FMP_API_KEY     — free at financialmodelingprep.com
#   DATABASE_URL    — optional; omit to use Parquet files
```

### 3. Run the historical load (Phase 1)

Downloads the full EDGAR companyfacts archive (~1 GB) and builds the baseline dataset.

```bash
python scripts/run_historical_load.py
# Re-use an existing download:
python scripts/run_historical_load.py --skip-download
```

### 4. Quarterly refresh (Phase 2)

```bash
# EDGAR Frames API snapshot for the current quarter
python scripts/run_quarterly_refresh.py --mode frames

# Weekly companyfacts diff
python scripts/run_quarterly_refresh.py --mode weekly
```

### 5. Daily monitor (Phase 3)

```bash
# One-shot run
python scripts/run_daily_monitor.py

# Daemon mode (scheduled at 06:00 UTC via `schedule` library)
python scripts/run_daily_monitor.py --daemon
```

### 6. Launch the dashboard

```bash
python dashboard/app.py
# Open http://localhost:8050
```

---

## Daily API Call Budget

Phase 3 uses at most **5 API calls** per day:

| Call | Source | Purpose |
|------|--------|---------|
| 1 | Polygon splits | Executed splits (yesterday → today) |
| 2 | EDGAR EFTS | 8-K filings mentioning "stock split" |
| 3 | FMP calendar | Upcoming splits (next 30 days) |
| 4 *(conditional)* | Polygon ticker details | Market cap refresh for buffer-zone issuers |
| 5 *(conditional)* | EDGAR company facts | Per-ticker validation for confirmed splits |

---

## Storage Options

| Option | Config | Notes |
|--------|--------|-------|
| **Parquet** (default) | No `DATABASE_URL` | Files in `data/`; portable, no infra required |
| **PostgreSQL** | Set `DATABASE_URL` | Required for concurrent access or production use |

---

## Anomaly Detection

The validation layer flags:

- Share count change **> 20%** without a confirmed corporate action
- **DEI / US-GAAP divergence > 5%** for the same period
- **Scaling errors** (1,000× jumps suggesting a units mismatch — shares vs thousands)
- **Stale filings** (no EDGAR update in > 120 days)

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## License

MIT
