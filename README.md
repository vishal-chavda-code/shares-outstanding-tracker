# US Equity Shares Outstanding Tracker

A production-grade Python system for tracking common stock shares outstanding across all US-listed public companies (~8,000+ issuers) using SEC EDGAR as the authoritative quarterly backbone and Polygon.io as a real-time corporate-actions layer — at **zero licensing cost**.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Sources](#data-sources)
3. [Tiered Monitoring Design](#tiered-monitoring-design)
4. [Project Structure](#project-structure)
5. [Setup](#setup)
6. [Environment Variables](#environment-variables)
7. [Usage](#usage)
8. [Daily Operations & API Call Budget](#daily-operations--api-call-budget)
9. [Fallback Escalation Ladder](#fallback-escalation-ladder)
10. [Storage Options](#storage-options)
11. [Anomaly Detection](#anomaly-detection)
12. [Implementation Roadmap](#implementation-roadmap)
13. [Running Tests](#running-tests)
14. [License](#license)

---

## Architecture Overview

The system is organized as a **three-phase pipeline**, each phase operating on a different cadence:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Three-Phase Pipeline                           │
├─────────────────┬──────────────────────────┬─────────────────────────┤
│  Phase 1        │  Phase 2                 │  Phase 3                │
│  Historical     │  Quarterly Refresh       │  Daily Monitor          │
│  Load           │                          │                         │
│  (one-time)     │  · Frames API snapshot   │  · Polygon splits       │
│                 │    (per quarter)         │  · EDGAR EFTS 8-K scan  │
│  companyfacts   │  · companyfacts diff     │  · FMP split calendar   │
│  .zip ETL       │    (weekly)              │  · Buffer-zone refresh  │
│  ~8,000 issuers │                          │                         │
└─────────────────┴──────────────────────────┴─────────────────────────┘
```

**Phase 1 — Historical Load (one-time)**
Downloads the full EDGAR `companyfacts.zip` archive (~1 GB), extracts `dei:EntityCommonStockSharesOutstanding` and `us-gaap:CommonStockSharesOutstanding` for every filer, and writes the baseline dataset.

**Phase 2 — Quarterly Refresh (ongoing)**
- **Frames API mode** (`--mode frames`): pulls a bulk XBRL snapshot for the current quarter across all filers in a single request.
- **Weekly diff mode** (`--mode weekly`): re-downloads `companyfacts.zip`, diffs against the stored baseline, and applies incremental updates.

**Phase 3 — Daily Monitor (ongoing)**
Runs each morning at 06:00 UTC. Consumes at most 3–5 API calls to detect executed splits (Polygon), announced splits (FMP), and split-related 8-K filings (EDGAR EFTS). Triggers per-ticker validation for confirmed events and promotes buffer-zone securities to enhanced monitoring.

---

## Data Sources

| Source | Endpoint | Cost | Use |
|--------|----------|------|-----|
| SEC EDGAR XBRL | `companyfacts.zip` | Free | Phase 1 historical baseline |
| SEC EDGAR Frames API | `/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}` | Free | Phase 2 quarterly bulk snapshot |
| SEC EDGAR EFTS | `efts.sec.gov/hits.json` | Free | Phase 3 split 8-K detection |
| Polygon.io | `/v3/reference/splits` | Free tier | Phase 3 executed splits |
| FMP | `/v3/stock_split_calendar` | Free tier | Phase 3 upcoming announced splits |

### XBRL Concepts Tracked

| Concept | Role |
|---------|------|
| `dei:EntityCommonStockSharesOutstanding` | Primary share count (DEI taxonomy) |
| `us-gaap:CommonStockSharesOutstanding` | Cross-validation (US-GAAP taxonomy) |

A divergence of more than **5%** between the two concepts for the same issuer and period is flagged as a data-quality anomaly.

---

## Tiered Monitoring Design

Securities are classified into five market-cap tiers that determine monitoring frequency and data-refresh priority.

### Tier Boundaries

| Tier | Market Cap Range | Default Refresh Cadence |
|------|-----------------|------------------------|
| **Mega-Cap** | > $200 B | Daily (Phase 3) |
| **Large-Cap** | $10 B – $200 B | Daily (Phase 3) |
| **Mid-Cap** | $2 B – $10 B | Quarterly (Phase 2) + split watch |
| **Small-Cap** | $300 M – $2 B | Quarterly (Phase 2) |
| **Micro-Cap** | < $300 M | Quarterly (Phase 2) |

### Buffer Zone Protocol

Any security whose market cap falls within **10%** of a tier boundary is automatically promoted to the monitoring cadence of the higher tier — regardless of its nominal classification.

**Examples:**
- A $9.2 B company (within 10% of the $10 B Large-Cap threshold) receives daily monitoring.
- A $275 M company (within 10% of the $300 M Small-Cap threshold) receives the same refresh cadence as Small-Cap.

Buffer-zone membership is re-evaluated each time Phase 3 refreshes market-cap data via Polygon ticker details.

---

## Project Structure

```
shares-outstanding-tracker/
├── .env.example                 # Template for required credentials
├── .gitignore
├── README.md
├── requirements.txt
│
├── config/
│   └── settings.py              # Tier boundaries, API keys, constants
│
├── src/
│   ├── edgar/
│   │   ├── company_facts.py     # companyfacts.zip download & ETL
│   │   ├── frames.py            # EDGAR Frames API (quarterly bulk)
│   │   └── efts.py              # EDGAR full-text search (8-K split detection)
│   ├── polygon/
│   │   ├── splits.py            # Executed splits endpoint (daily)
│   │   └── ticker_details.py    # Market cap & share count (buffer zone)
│   ├── fmp/
│   │   └── splits_calendar.py   # Upcoming announced splits calendar
│   ├── pipeline/
│   │   ├── historical_load.py   # Phase 1 orchestration
│   │   ├── quarterly_refresh.py # Phase 2 orchestration
│   │   └── daily_monitor.py     # Phase 3 orchestration
│   ├── tier/
│   │   ├── classifier.py        # Market-cap tier classification logic
│   │   └── buffer_zone.py       # Buffer-zone boundary detection
│   ├── alerts/
│   │   └── triggers.py          # Anomaly detection & alert dispatch
│   └── utils/
│       ├── db.py                # PostgreSQL / Parquet storage abstraction
│       └── validation.py        # DEI vs US-GAAP cross-validation
│
├── dashboard/
│   └── app.py                   # Plotly Dash web UI
│
├── docs/                        # Supporting documentation & reports
│
├── scripts/
│   ├── run_historical_load.py   # CLI entry point — Phase 1
│   ├── run_quarterly_refresh.py # CLI entry point — Phase 2
│   └── run_daily_monitor.py     # CLI entry point — Phase 3
│
└── tests/
    ├── test_edgar.py
    ├── test_tier_classifier.py
    └── test_splits.py
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/vishal-chavda-code/shares-outstanding-tracker.git
cd shares-outstanding-tracker
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure credentials

```bash
cp .env.example .env
# Open .env and fill in the values described below
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SEC_USER_AGENT` | Yes | Identifies your application to EDGAR per the SEC fair-use policy. Format: `"Your Name your@email.com"` |
| `POLYGON_API_KEY` | Yes | Polygon.io API key. Free tier is sufficient; sign up at [polygon.io](https://polygon.io). |
| `FMP_API_KEY` | Yes | Financial Modeling Prep key. Free tier covers the split calendar. Sign up at [financialmodelingprep.com](https://financialmodelingprep.com). |
| `DATABASE_URL` | No | PostgreSQL connection string. Omit to use the default Parquet-based local storage instead. Format: `postgresql://user:password@host:5432/dbname` |
| `DATA_DIR` | No | Override the default `./data` directory for Parquet file storage. |

---

## Usage

### Phase 1 — Historical Load (run once)

Downloads the full EDGAR `companyfacts.zip` archive and builds the baseline dataset for all ~8,000 US-listed issuers.

```bash
# Full run (downloads ~1 GB archive)
python scripts/run_historical_load.py

# Skip the download if the archive is already present
python scripts/run_historical_load.py --skip-download
```

### Phase 2 — Quarterly Refresh

**Frames API snapshot** — single bulk request for the current quarter:

```bash
python scripts/run_quarterly_refresh.py --mode frames
```

**Weekly diff** — re-download `companyfacts.zip` and apply incremental changes:

```bash
python scripts/run_quarterly_refresh.py --mode weekly
```

Schedule Phase 2 via cron or Task Scheduler. Recommended cadence: Frames API once per quarter (2–3 weeks after quarter-end), weekly diff every Sunday.

### Phase 3 — Daily Monitor

**One-shot run:**

```bash
python scripts/run_daily_monitor.py
```

**Daemon mode** (self-scheduling via the `schedule` library at 06:00 UTC):

```bash
python scripts/run_daily_monitor.py --daemon
```

### Dashboard

```bash
python dashboard/app.py
# Open http://localhost:8050
```

---

## Daily Operations & API Call Budget

Phase 3 is designed to consume **at most 5 API calls per day**, keeping the system well within free-tier limits at **$0/month** in API costs.

| Call # | Source | Endpoint | Purpose | Conditional? |
|--------|--------|----------|---------|--------------|
| 1 | Polygon.io | `/v3/reference/splits` | Executed splits since yesterday | No |
| 2 | EDGAR EFTS | `efts.sec.gov/hits.json` | 8-K filings mentioning "stock split" | No |
| 3 | FMP | `/v3/stock_split_calendar` | Upcoming splits in next 30 days | No |
| 4 | Polygon.io | `/v3/reference/tickers/{ticker}` | Market cap refresh for buffer-zone securities | Yes — only if buffer-zone issuers exist |
| 5 | EDGAR | `/api/xbrl/companyfacts/{cik}.json` | Per-ticker share count validation | Yes — only on confirmed split events |

---

## Fallback Escalation Ladder

When a primary data source is unavailable, the system escalates through a defined sequence rather than failing silently.

| Level | Trigger | Action |
|-------|---------|--------|
| **L1** | Polygon splits endpoint unavailable | Retry with exponential back-off (3 attempts, max 60 s delay) |
| **L2** | Polygon still unavailable after L1 | Fall back to EDGAR EFTS 8-K scan as the sole split-detection signal |
| **L3** | EDGAR EFTS also unavailable | Use FMP split calendar as the only inbound signal; suppress share-count updates |
| **L4** | All three sources unavailable | Emit a critical alert, skip the daily run, and schedule a catch-up run at next available window |

Each escalation event is logged with a severity label and optionally surfaced in the dashboard.

---

## Storage Options

| Option | How to Enable | Notes |
|--------|--------------|-------|
| **Parquet** (default) | Leave `DATABASE_URL` unset | Files written to `./data/`; portable, no infrastructure required |
| **PostgreSQL** | Set `DATABASE_URL` | Required for concurrent access, production deployments, or multi-process pipelines |

The storage abstraction in `src/utils/db.py` is backend-agnostic; switching between Parquet and PostgreSQL requires only a change to the environment variable.

---

## Anomaly Detection

The validation layer in `src/alerts/triggers.py` and `src/utils/validation.py` flags the following conditions:

| Anomaly | Threshold | Likely Cause |
|---------|-----------|--------------|
| Large share-count change without a confirmed corporate action | > 20% | Data error or unreported split |
| DEI / US-GAAP divergence for the same issuer and period | > 5% | Filing inconsistency or XBRL tagging error |
| Scaling jump (e.g., shares reported in thousands vs. units) | 1,000× change | Units mismatch in XBRL filing |
| Stale filing (no EDGAR update detected) | > 120 days | Filing delay, ticker change, or delisting |

Flagged records are written to the `anomalies` table (PostgreSQL) or `data/anomalies.parquet` and surfaced in the dashboard.

---

## Implementation Roadmap

| Week | Milestone | Deliverables |
|------|-----------|-------------|
| **1** | Data-source validation | Confirm EDGAR, Polygon, and FMP endpoints are accessible; validate XBRL concept coverage across a sample of 100 tickers |
| **2** | Phase 1 — Historical Load | `company_facts.py` ETL complete; baseline Parquet/DB populated for all ~8,000 issuers |
| **3** | Tier classifier & buffer zone | `classifier.py` and `buffer_zone.py` fully tested; tier assignments written to storage |
| **4** | Phase 2 — Quarterly Refresh | Frames API integration and weekly-diff logic complete; end-to-end refresh tested against a full quarter |
| **5** | Phase 3 — Daily Monitor (core) | Polygon splits + EDGAR EFTS + FMP calendar integrated; daily run executes within 5-call budget |
| **6** | Validation & anomaly detection | Cross-validation logic, scaling-error detection, and stale-filing alerts complete |
| **7** | Dashboard & fallback ladder | Plotly Dash UI live; L1–L4 fallback logic implemented and tested under simulated outages |
| **8** | Hardening & documentation | Full test suite passing; logging structured; README and inline docs finalized; production deployment verified |

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Test modules:

| File | Coverage |
|------|----------|
| `tests/test_edgar.py` | EDGAR ETL parsing, Frames API response handling, EFTS query logic |
| `tests/test_tier_classifier.py` | Tier boundary assignments, buffer-zone edge cases |
| `tests/test_splits.py` | Polygon splits ingestion, FMP calendar parsing, split-ratio application |

---

## License

MIT
