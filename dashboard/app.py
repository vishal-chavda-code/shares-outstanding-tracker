"""
Plotly Dash dashboard — US Equity Shares Outstanding Tracker.

Provides:
  - Tier distribution chart (pie)
  - Shares-outstanding time-series for a selected ticker
  - Buffer-zone ticker table
  - Recent alert log
  - Pipeline status indicators
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html
from loguru import logger

from config.settings import DATA_DIR

app = Dash(__name__, title="Shares Outstanding Tracker")

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

app.layout = html.Div(
    style={"fontFamily": "Inter, sans-serif", "padding": "20px"},
    children=[
        html.H1("US Equity Shares Outstanding Tracker", style={"marginBottom": "4px"}),
        html.P(
            "Data sourced from SEC EDGAR XBRL, Polygon.io, and FMP at zero licensing cost.",
            style={"color": "#666", "marginTop": 0},
        ),
        html.Hr(),

        # Tier distribution
        html.H2("Market-Cap Tier Distribution"),
        dcc.Graph(id="tier-pie"),

        html.Hr(),

        # Ticker search
        html.H2("Shares Outstanding — Ticker Time-Series"),
        dcc.Input(
            id="ticker-input",
            type="text",
            placeholder="Enter ticker (e.g. AAPL)",
            debounce=True,
            style={"width": "200px", "marginRight": "10px"},
        ),
        dcc.Graph(id="shares-timeseries"),

        html.Hr(),

        # Buffer zone table
        html.H2("Buffer-Zone Tickers (within 10% of tier boundary)"),
        dash_table.DataTable(
            id="buffer-zone-table",
            columns=[
                {"name": "Ticker", "id": "ticker"},
                {"name": "Market Cap ($)", "id": "market_cap"},
                {"name": "Tier", "id": "tier"},
                {"name": "Nearest Boundary", "id": "boundary_label"},
                {"name": "% From Boundary", "id": "pct_from_boundary"},
            ],
            style_table={"overflowX": "auto"},
            page_size=20,
        ),

        html.Hr(),

        # Alert log
        html.H2("Recent Alerts"),
        dcc.Graph(id="alert-bar"),

        # Polling interval — refresh every 60 s
        dcc.Interval(id="poll-interval", interval=60_000, n_intervals=0),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@app.callback(Output("tier-pie", "figure"), Input("poll-interval", "n_intervals"))
def update_tier_pie(_: int) -> go.Figure:
    """Render tier distribution pie chart from latest Parquet snapshot."""
    df = _load_shares()
    if df.empty or "tier" not in df.columns:
        return _empty_figure("No tier data available")
    counts = df.drop_duplicates("cik")["tier"].value_counts().reset_index()
    counts.columns = ["tier", "count"]
    return px.pie(counts, names="tier", values="count", title="Issuer Count by Tier")


@app.callback(
    Output("shares-timeseries", "figure"),
    Input("ticker-input", "value"),
)
def update_timeseries(ticker: str | None) -> go.Figure:
    """Render shares-outstanding time-series for the selected ticker."""
    if not ticker:
        return _empty_figure("Enter a ticker symbol above")
    df = _load_shares()
    if df.empty:
        return _empty_figure("No data loaded")
    mask = df["entity_name"].str.upper() == ticker.upper()
    if not mask.any() and "ticker" in df.columns:
        mask = df["ticker"].str.upper() == ticker.upper()
    subset = df[mask].sort_values("filed")
    if subset.empty:
        return _empty_figure(f"No data found for '{ticker}'")
    fig = px.line(
        subset,
        x="filed",
        y="val",
        color="concept",
        title=f"Shares Outstanding — {ticker.upper()}",
        labels={"val": "Shares", "filed": "Filing Date"},
    )
    return fig


@app.callback(
    Output("buffer-zone-table", "data"),
    Input("poll-interval", "n_intervals"),
)
def update_buffer_zone_table(_: int) -> list[dict]:
    """Populate the buffer-zone table from the market-caps Parquet file."""
    mc_path = DATA_DIR / "market_caps.parquet"
    if not mc_path.exists():
        return []
    from src.tier.buffer_zone import check_buffer_zone
    from src.tier.classifier import classify
    df = pd.read_parquet(mc_path)
    rows = []
    for _, row in df.iterrows():
        mc = row.get("market_cap")
        if mc is None:
            continue
        bz = check_buffer_zone(row.get("ticker", ""), float(mc))
        if bz.in_buffer_zone:
            rows.append(
                {
                    "ticker": bz.ticker,
                    "market_cap": f"${mc:,.0f}",
                    "tier": bz.tier.value,
                    "boundary_label": bz.boundary_label,
                    "pct_from_boundary": f"{(bz.pct_from_boundary or 0) * 100:.1f}%",
                }
            )
    return rows


@app.callback(Output("alert-bar", "figure"), Input("poll-interval", "n_intervals"))
def update_alert_bar(_: int) -> go.Figure:
    """Render a bar chart of recent alerts by severity."""
    from src.alerts.triggers import get_alert_log
    df = get_alert_log()
    if df.empty:
        return _empty_figure("No alerts yet")
    counts = df["severity"].value_counts().reset_index()
    counts.columns = ["severity", "count"]
    colour_map = {"high": "#d62728", "medium": "#ff7f0e", "low": "#2ca02c"}
    return px.bar(
        counts,
        x="severity",
        y="count",
        color="severity",
        color_discrete_map=colour_map,
        title="Alerts by Severity",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_shares() -> pd.DataFrame:
    path = DATA_DIR / "shares_outstanding.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load shares parquet: {}", exc)
        return pd.DataFrame()


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig.update_layout(xaxis_visible=False, yaxis_visible=False)
    return fig


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
