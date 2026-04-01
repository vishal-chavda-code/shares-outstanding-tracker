"""Tests for the EDGAR data-access modules."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.edgar.company_facts import extract_shares_outstanding
from src.edgar.frames import build_period_code
from src.utils.validation import (
    validate_dei_vs_gaap,
    detect_scaling_error,
    validate_time_series,
)


# ---------------------------------------------------------------------------
# company_facts
# ---------------------------------------------------------------------------

class TestExtractSharesOutstanding:
    def _make_company_json(self, dei_val: float = 1_000_000) -> dict:
        return {
            "cik": 12345,
            "entityName": "Test Corp",
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "accn": "0001234-24-000001",
                                    "form": "10-K",
                                    "filed": "2024-03-15",
                                    "end": "2023-12-31",
                                    "val": dei_val,
                                }
                            ]
                        }
                    }
                }
            },
        }

    def test_extracts_dei_concept(self):
        df = extract_shares_outstanding(self._make_company_json())
        assert not df.empty
        assert "dei:EntityCommonStockSharesOutstanding" in df["concept"].values

    def test_cik_zero_padded(self):
        df = extract_shares_outstanding(self._make_company_json())
        assert df["cik"].iloc[0] == "0000012345"

    def test_empty_facts_returns_empty_df(self):
        company_json = {"cik": 99999, "entityName": "Empty", "facts": {}}
        df = extract_shares_outstanding(company_json)
        assert df.empty

    def test_filed_is_datetime(self):
        df = extract_shares_outstanding(self._make_company_json())
        assert pd.api.types.is_datetime64_any_dtype(df["filed"])

    def test_val_preserved(self):
        df = extract_shares_outstanding(self._make_company_json(dei_val=5_000_000))
        assert df["val"].iloc[0] == 5_000_000


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------

class TestBuildPeriodCode:
    def test_quarterly_instant(self):
        assert build_period_code(2024, 4, instant=True) == "CY2024Q4I"

    def test_quarterly_duration(self):
        assert build_period_code(2024, 1, instant=False) == "CY2024Q1"

    def test_annual(self):
        assert build_period_code(2023) == "CY2023"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_dei_gaap_ok(self):
        ok, msg = validate_dei_vs_gaap(1_000_000, 1_020_000)  # 2% diff
        assert ok is True

    def test_dei_gaap_divergence(self):
        ok, msg = validate_dei_vs_gaap(1_000_000, 1_100_000)  # 10% diff
        assert ok is False
        assert "divergence" in msg.lower()

    def test_dei_zero(self):
        ok, msg = validate_dei_vs_gaap(0, 1_000_000)
        assert ok is False

    def test_none_values_pass(self):
        ok, _ = validate_dei_vs_gaap(None, 1_000_000)
        assert ok is True

    def test_scaling_error_high(self):
        has_err, msg = detect_scaling_error(1_000_000, 1_000_000_000)  # 1000x
        assert has_err is True

    def test_scaling_error_low(self):
        has_err, msg = detect_scaling_error(1_000_000, 500)  # 0.0005x
        assert has_err is True

    def test_no_scaling_error(self):
        has_err, _ = detect_scaling_error(1_000_000, 1_050_000)  # 5% change
        assert has_err is False

    def test_validate_time_series_adds_columns(self):
        df = pd.DataFrame(
            {
                "filed": pd.to_datetime(["2023-03-01", "2023-06-01", "2023-09-01"]),
                "val": [1_000_000, 1_050_000, 1_100_000],
            }
        )
        result = validate_time_series(df)
        assert "ratio" in result.columns
        assert "large_change_flag" in result.columns
        assert "scaling_error_flag" in result.columns
