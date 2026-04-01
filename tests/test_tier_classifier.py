"""Tests for the market-cap tier classifier and buffer-zone detection."""

import pytest
from src.tier.classifier import Tier, classify, classify_series, tier_boundaries
from src.tier.buffer_zone import check_buffer_zone
import pandas as pd


class TestTierClassifier:
    def test_mega_cap(self):
        assert classify(300_000_000_000) == Tier.MEGA   # $300 B

    def test_large_cap_at_boundary(self):
        # Exactly $200 B is NOT mega (> threshold required)
        assert classify(200_000_000_000) == Tier.LARGE

    def test_large_cap(self):
        assert classify(50_000_000_000) == Tier.LARGE   # $50 B

    def test_mid_cap(self):
        assert classify(5_000_000_000) == Tier.MID      # $5 B

    def test_small_cap(self):
        assert classify(1_000_000_000) == Tier.SMALL    # $1 B

    def test_micro_cap(self):
        assert classify(100_000_000) == Tier.MICRO      # $100 M

    def test_micro_cap_at_boundary(self):
        # Exactly $300 M is NOT small (> threshold required)
        assert classify(300_000_000) == Tier.MICRO

    def test_none_returns_unknown(self):
        assert classify(None) == Tier.UNKNOWN

    def test_nan_returns_unknown(self):
        assert classify(float("nan")) == Tier.UNKNOWN

    def test_classify_series(self):
        s = pd.Series([500e9, 50e9, 5e9, 500e6, 50e6])
        result = classify_series(s)
        assert list(result) == ["MEGA", "LARGE", "MID", "SMALL", "MICRO"]

    def test_tier_boundaries_keys(self):
        bounds = tier_boundaries()
        assert set(bounds.keys()) == {"MEGA", "LARGE", "MID", "SMALL", "MICRO"}


class TestBufferZone:
    def test_in_buffer_zone_near_large_mid_boundary(self):
        # $9.5 B is within 10% of $10 B LARGE/MID boundary
        result = check_buffer_zone("TEST", 9_500_000_000)
        assert result.in_buffer_zone is True
        assert result.boundary_label == "LARGE/MID"

    def test_not_in_buffer_zone(self):
        # $5 B is nowhere near any boundary
        result = check_buffer_zone("TEST", 5_000_000_000)
        assert result.in_buffer_zone is False

    def test_in_buffer_zone_near_mega_large_boundary(self):
        # $195 B is within 10% of $200 B MEGA/LARGE boundary
        result = check_buffer_zone("TEST", 195_000_000_000)
        assert result.in_buffer_zone is True
        assert result.boundary_label == "MEGA/LARGE"

    def test_pct_from_boundary_computed(self):
        result = check_buffer_zone("TEST", 9_000_000_000)
        assert result.pct_from_boundary is not None
        # 9B is 10% below 10B boundary — exactly on the edge
        assert abs(result.pct_from_boundary - 0.10) < 1e-6

    def test_tier_is_correct_regardless_of_buffer(self):
        # A $9.5 B company is classified as MID even if in buffer zone
        result = check_buffer_zone("TEST", 9_500_000_000)
        assert result.tier == Tier.MID
