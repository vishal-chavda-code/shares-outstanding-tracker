# US Equity Shares Outstanding Tracker

Production system for tracking shares outstanding across all US-listed public companies using SEC EDGAR + Polygon.io + FMP at zero licensing cost.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Data Sources](#data-sources)
- [Tiered Margin Design](#tiered-margin-design)
- [Pipeline Phases](#pipeline-phases)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [Daily Operations](#daily-operations)
- [Fallback Escalation Ladder](#fallback-escalation-ladder)
- [8-Week Implementation Roadmap](#8-week-implementation-roadmap)
- [License](#license)

---

## Architecture Overview

The system is built on three complementary data sources, each serving a distinct role:

| Layer | Source | Role |
|-------|--------|------|
| Backbone | SEC EDGAR | Authoritative quarterly shares outstanding from regulatory filings |
| Real-Time Actions | Polygon.io | Corporate actions (splits, reverse splits) for intra-quarter adjustments |
| Cross-Validation | FMP | Independent cross-check to detect anomalies and confirm accuracy |

**Design principle:** EDGAR filings are the ground truth for point-in-time shares outstanding at each quarter end. Polygon.io split data bridges the gap between filing dates to keep figures current. FMP provides a lightweight cross-validation layer that catches discrepancies before they propagate downstream.

The system targets near-zero cost by operating entirely within free-tier API limits during normal conditions, with a defined escalation ladder for higher-volume needs.

---

## Data Sources

### SEC EDGAR XBRL

EDGAR is the primary source. All US public companies file 10-K (annual) and 10-Q (quarterly) reports containing XBRL-tagged shares outstanding data.

| Endpoint / Dataset | Description |
|--------------------|-------------|
| `companyfacts/{CIK}.json` | Per-company fact history including `dei:EntityCommonStockSharesOutstanding` |
| Frames API (`/frames/dei/EntityCommonStockSharesOutstanding/shares/{period}`) | Cross-sectional data for all filers in a given period (CY quarter or annual) |
| `companyfacts.zip` | Full bulk download (~1 GB compressed) of all company facts — used for historical load |

**Key XBRL concept:** `dei:EntityCommonStockSharesOutstanding` is the standardized tag for shares outstanding under the XBRL US GAAP taxonomy. It is reported as of the filing cover page date, which typically lags the period end by 30–90 days.

### Polygon.io

Polygon supplements EDGAR with real-time corporate action data, enabling intra-quarter share count adjustments.

| Endpoint | Description |
|----------|-------------|
| `GET /v3/reference/splits` | Stock split and reverse split history — **ticker parameter is optional**, enabling market-wide bulk queries |

The bulk-query capability of `/v3/reference/splits` (no ticker required) is a key architectural advantage: a single paginated call can retrieve all splits across all US tickers within a date range, allowing the system to stay current with minimal API call overhead.

### Financial Modeling Prep (FMP)

FMP serves as the cross-validation layer.

| Endpoint | Description |
|----------|-------------|
| `GET /api/v3/stock_split_calendar` | Upcoming and historical split calendar, used to cross-check Polygon split data |

---

## Tiered Margin Design

Companies are classified into market-cap tiers. Each tier carries a different tolerance for share-count discrepancies before triggering alerts, reflecting the practical reality that large-cap share counts are more stable and widely scrutinized.

| Tier | Market Cap Range | Staleness Tolerance | Discrepancy Threshold |
|------|-----------------|--------------------|-----------------------|
| Mega-Cap | > $200B | 1 business day | 0.1% |
| Large-Cap | $10B – $200B | 3 business days | 0.5% |
| Mid-Cap | $2B – $10B | 5 business days | 1.0% |
| Small-Cap | $300M – $2B | 10 business days | 2.0% |
| Micro-Cap | < $300M | 30 business days | 5.0% |

### Buffer Zone Protocol

Tier boundaries use a **10% buffer zone** to prevent companies from oscillating between tiers due to normal market cap fluctuation.

- A company must breach a tier boundary by at least 10% of that boundary before reclassification occurs.
- Example: A company with a $195B market cap is not reclassified from Mega-Cap to Large-Cap until its market cap falls below $180B (10% below the $200B boundary).
- This prevents unnecessary re-tiering and associated threshold changes for borderline companies.

---

## Pipeline Phases

### Phase 1: Historical Load

One-time bulk ingestion of historical shares outstanding for all US-listed companies.

- Download `companyfacts.zip` from EDGAR bulk data endpoint
- Parse `dei:EntityCommonStockSharesOutstanding` for every CIK
- Load into local database with point-in-time records keyed by (ticker, period_end_date)
- Backfill split adjustments using Polygon bulk splits endpoint

**Script:** `scripts/run_historical_load.py`

### Phase 2: Quarterly Bulk Refresh

Runs after each quarterly filing season (approximately 45 days after quarter end) to ingest new 10-Q/10-K filings.

- Query EDGAR Frames API for the latest completed quarter
- Identify companies with new filings since last refresh
- Update shares outstanding records
- Re-validate against FMP split calendar for the quarter

**Script:** `scripts/run_quarterly_refresh.py`

### Phase 3: Daily Monitoring

Lightweight daily job that keeps share counts current between quarterly filings.

- Fetch new corporate actions from Polygon `/v3/reference/splits` for the prior trading day
- Cross-reference against FMP split calendar
- Apply split adjustments to current shares outstanding
- Trigger tier-aware alerts for any discrepancies exceeding thresholds

**Script:** `scripts/run_daily_monitor.py`

---

## Project Structure

```
shares-outstanding-tracker/
├── config/
│   ├── __init__.py
│   └── settings.py              # Centralized configuration and env var loading
├── dashboard/
│   ├── __init__.py
│   └── app.py                   # Optional Streamlit/Dash monitoring dashboard
├── scripts/
│   ├── run_historical_load.py   # Phase 1: one-time bulk historical ingestion
│   ├── run_quarterly_refresh.py # Phase 2: quarterly EDGAR refresh
│   └── run_daily_monitor.py     # Phase 3: daily corporate actions monitoring
├── src/
│   ├── edgar/
│   │   ├── __init__.py
│   │   ├── company_facts.py     # Per-company XBRL facts fetcher
│   │   ├── efts.py              # EDGAR full-text search integration
│   │   └── frames.py            # EDGAR Frames API (cross-sectional queries)
│   ├── fmp/
│   │   ├── __init__.py
│   │   └── splits_calendar.py   # FMP split calendar fetcher and parser
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── daily_monitor.py     # Phase 3 pipeline logic
│   │   ├── historical_load.py   # Phase 1 pipeline logic
│   │   └── quarterly_refresh.py # Phase 2 pipeline logic
│   ├── polygon/
│   │   ├── __init__.py
│   │   ├── splits.py            # Polygon splits endpoint client
│   │   └── ticker_details.py    # Polygon ticker metadata (market cap, etc.)
│   ├── tier/
│   │   ├── __init__.py
│   │   ├── buffer_zone.py       # Buffer zone reclassification logic
│   │   └── classifier.py        # Market-cap tier classifier
│   ├── alerts/
│   │   ├── __init__.py
│   │   └── triggers.py          # Tier-aware alert triggers
│   └── utils/
│       ├── __init__.py
│       ├── db.py                # Database connection and ORM helpers
│       └── validation.py        # Cross-source validation utilities
├── tests/
│   ├── __init__.py
│   ├── test_edgar.py
│   ├── test_splits.py
│   └── test_tier_classifier.py
├── .env.example                 # Template for required environment variables
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Setup

```bash
git clone https://github.com/vishal-chavda-code/shares-outstanding-tracker.git
cd shares-outstanding-tracker

# Copy and populate environment variables
cp .env.example .env
# Edit .env with your API keys (see Environment Variables below)

pip install -r requirements.txt
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SEC_USER_AGENT` | Yes | Identifies your application to EDGAR (e.g., `"MyApp contact@example.com"`) — required by SEC fair-use policy |
| `POLYGON_API_KEY` | Yes | Polygon.io API key — free tier sufficient for daily monitoring |
| `FMP_API_KEY` | Yes | Financial Modeling Prep API key — free tier sufficient |
| `DATABASE_URL` | Yes | SQLAlchemy-compatible connection string (e.g., `sqlite:///shares.db` or PostgreSQL URL) |

See `.env.example` for the full template.

---

## Usage

### Phase 1: Historical Load (run once)

```bash
python scripts/run_historical_load.py
```

Downloads `companyfacts.zip` from EDGAR and populates the database with historical shares outstanding for all US-listed companies. Expect this to take 30–90 minutes on first run depending on database performance.

### Phase 2: Quarterly Refresh (run quarterly)

```bash
python scripts/run_quarterly_refresh.py
```

Ingests new filings from the most recently completed quarter. Schedule approximately 45–60 days after each quarter end (mid-February, mid-May, mid-August, mid-November).

### Phase 3: Daily Monitor (run daily)

```bash
python scripts/run_daily_monitor.py
```

Fetches prior-day corporate actions from Polygon, cross-validates with FMP, applies adjustments, and fires tier-aware alerts. Schedule via cron or task scheduler on each trading day.

---

## Daily Operations

In steady-state daily monitoring, the system operates well within free-tier API limits:

| Operation | API Calls/Day | Cost |
|-----------|--------------|------|
| Polygon splits bulk fetch | 1–2 paginated calls | $0/month (free tier) |
| FMP split calendar check | 1 call | $0/month (free tier) |
| EDGAR company facts (ad hoc) | 0–2 calls | $0/month (no key required) |
| **Total** | **3–5 calls/day** | **$0/month** |

---

## Fallback Escalation Ladder

If data quality or volume requirements exceed free-tier capabilities, escalate through the following tiers:

| Level | Provider(s) | Monthly Cost | When to Escalate |
|-------|------------|-------------|-----------------|
| **L0 (baseline)** | SEC EDGAR + Polygon free + FMP free | $0/month | Default — handles ~95% of use cases |
| **L1** | Polygon Starter plan | ~$29/month | Need higher Polygon API rate limits or real-time websocket access |
| **L2** | FMP paid + EODHD | ~$34–$63/month | Need broader international coverage or higher FMP call limits |
| **L3** | Commercial data feed (e.g., Quandl/Nasdaq Data Link) | ~$10K–$50K/year | Institutional SLA requirements or audit-grade data lineage |
| **L4** | Bloomberg Terminal / S&P CapIQ | ~$25K–$100K/year | Full enterprise integration, real-time streaming, compliance reporting |

The system is architected so that the data-source clients (`src/edgar/`, `src/polygon/`, `src/fmp/`) are decoupled from the pipeline logic, making it straightforward to swap in a higher-tier provider without rewriting the pipeline.

---

## 8-Week Implementation Roadmap

| Week | Milestone |
|------|-----------|
| 1 | Environment setup, database schema design, EDGAR bulk download and parse |
| 2 | Historical load pipeline complete — all companies with XBRL data loaded |
| 3 | Polygon splits client and backfill — historical splits applied to all records |
| 4 | Tier classifier and buffer zone logic — all companies classified |
| 5 | Quarterly refresh pipeline — EDGAR Frames API integration, filing detection |
| 6 | Daily monitor pipeline — Polygon + FMP daily delta, alert triggers |
| 7 | Cross-validation and testing — discrepancy detection, tier-aware thresholds |
| 8 | Dashboard, documentation, production hardening and scheduling |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
