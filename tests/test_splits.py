"""Tests for Polygon splits and FMP calendar modules."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestPolygonSplits:
    """Tests for src.polygon.splits — mocks all HTTP traffic."""

    def _mock_response(self, results: list[dict], next_url: str | None = None) -> MagicMock:
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.return_value = {"results": results, "next_url": next_url}
        return mock

    @patch("src.polygon.splits.POLYGON_API_KEY", "test_key")
    @patch("src.polygon.splits.requests.get")
    def test_fetch_splits_returns_dataframe(self, mock_get):
        mock_get.return_value = self._mock_response(
            [{"ticker": "TSLA", "execution_date": "2024-08-25", "split_from": 1, "split_to": 3}]
        )
        from src.polygon.splits import fetch_splits
        df = fetch_splits()
        assert not df.empty
        assert "ticker" in df.columns
        assert df["ticker"].iloc[0] == "TSLA"

    @patch("src.polygon.splits.POLYGON_API_KEY", None)
    def test_returns_empty_without_api_key(self):
        from src.polygon.splits import fetch_splits
        df = fetch_splits()
        assert df.empty

    @patch("src.polygon.splits.POLYGON_API_KEY", "test_key")
    @patch("src.polygon.splits.requests.get")
    def test_paginates_through_all_pages(self, mock_get):
        page1 = self._mock_response(
            [{"ticker": "AAPL", "execution_date": "2024-06-10", "split_from": 1, "split_to": 4}],
            next_url="https://api.polygon.io/v3/reference/splits?cursor=abc",
        )
        page2 = self._mock_response(
            [{"ticker": "NVDA", "execution_date": "2024-06-11", "split_from": 1, "split_to": 10}]
        )
        mock_get.side_effect = [page1, page2]
        from src.polygon.splits import fetch_splits
        df = fetch_splits()
        assert len(df) == 2
        assert set(df["ticker"]) == {"AAPL", "NVDA"}


class TestFMPSplitsCalendar:
    """Tests for src.fmp.splits_calendar — mocks all HTTP traffic."""

    @patch("src.fmp.splits_calendar.FMP_API_KEY", None)
    def test_returns_empty_without_api_key(self):
        from src.fmp.splits_calendar import fetch_split_calendar
        df = fetch_split_calendar()
        assert df.empty

    @patch("src.fmp.splits_calendar.FMP_API_KEY", "test_key")
    @patch("src.fmp.splits_calendar.requests.get")
    def test_fetch_calendar_returns_dataframe(self, mock_get):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.return_value = [
            {
                "date": "2024-09-15",
                "label": "September 15, 24",
                "symbol": "PLTR",
                "numerator": 2,
                "denominator": 1,
            }
        ]
        mock_get.return_value = mock
        from src.fmp.splits_calendar import fetch_split_calendar
        df = fetch_split_calendar()
        assert not df.empty
        assert df["symbol"].iloc[0] == "PLTR"
        assert "split_ratio" in df.columns
        assert df["split_ratio"].iloc[0] == pytest.approx(2.0)

    @patch("src.fmp.splits_calendar.FMP_API_KEY", "test_key")
    @patch("src.fmp.splits_calendar.requests.get")
    def test_empty_response_returns_empty_df(self, mock_get):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.return_value = []
        mock_get.return_value = mock
        from src.fmp.splits_calendar import fetch_split_calendar
        df = fetch_split_calendar()
        assert df.empty
