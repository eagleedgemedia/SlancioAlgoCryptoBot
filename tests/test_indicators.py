"""
Slancio Crypto Algo Treding Engine — Unit Tests for Indicators
==================================================
Tests EMA calculations with known values to ensure accuracy.
"""

import pytest
import pandas as pd
import numpy as np
from core.strategy.indicators import (
    calculate_ema,
    calculate_ema_high,
    calculate_ema_low,
    calculate_ema_bands,
    calculate_candle_properties,
    prepare_strategy_dataframe,
)


def _make_sample_df(n: int = 20) -> pd.DataFrame:
    """Create a sample OHLC DataFrame for testing."""
    np.random.seed(42)
    base = 97000
    closes = base + np.cumsum(np.random.randn(n) * 50)
    return pd.DataFrame({
        "timestamp": range(1000, 1000 + n),
        "datetime": pd.date_range("2026-01-01", periods=n, freq="1h"),
        "open": closes + np.random.randn(n) * 30,
        "high": closes + abs(np.random.randn(n) * 80),
        "low": closes - abs(np.random.randn(n) * 80),
        "close": closes,
        "volume": np.random.randint(100, 5000, n),
    })


class TestEMACalculation:
    def test_ema_basic(self):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        ema = calculate_ema(series, period=3)
        assert len(ema) == 10
        assert ema.iloc[-1] > ema.iloc[3]  # EMA should trend upward

    def test_ema_period_1(self):
        series = pd.Series([10, 20, 30], dtype=float)
        ema = calculate_ema(series, period=1)
        pd.testing.assert_series_equal(ema, series)

    def test_ema_invalid_period(self):
        with pytest.raises(ValueError):
            calculate_ema(pd.Series([1, 2, 3]), period=0)

    def test_ema_empty_series(self):
        result = calculate_ema(pd.Series(dtype=float), period=7)
        assert result.empty


class TestEMABands:
    def test_ema_high_added(self):
        df = _make_sample_df()
        df = calculate_ema_high(df, period=7)
        assert "ema_7_high" in df.columns

    def test_ema_low_added(self):
        df = _make_sample_df()
        df = calculate_ema_low(df, period=7)
        assert "ema_7_low" in df.columns

    def test_ema_bands_both(self):
        df = _make_sample_df()
        df = calculate_ema_bands(df, period=7)
        assert "ema_7_high" in df.columns
        assert "ema_7_low" in df.columns
        assert "ema_7_bandwidth" in df.columns

    def test_ema_high_above_low(self):
        df = _make_sample_df(50)
        df = calculate_ema_bands(df, period=7)
        valid = df.dropna(subset=["ema_7_high", "ema_7_low"])
        assert (valid["ema_7_high"] >= valid["ema_7_low"]).all()

    def test_missing_column_raises(self):
        df = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(KeyError):
            calculate_ema_high(df)


class TestCandleProperties:
    def test_red_candle(self):
        df = pd.DataFrame({
            "open": [100.0], "high": [105.0],
            "low": [95.0], "close": [98.0],
        })
        df = calculate_candle_properties(df)
        assert df["is_red"].iloc[0] == True
        assert df["is_green"].iloc[0] == False

    def test_green_candle(self):
        df = pd.DataFrame({
            "open": [100.0], "high": [105.0],
            "low": [95.0], "close": [103.0],
        })
        df = calculate_candle_properties(df)
        assert df["is_green"].iloc[0] == True

    def test_body_size(self):
        df = pd.DataFrame({
            "open": [100.0], "high": [110.0],
            "low": [90.0], "close": [105.0],
        })
        df = calculate_candle_properties(df)
        assert df["body_size"].iloc[0] == 5.0


class TestPrepareStrategyDF:
    def test_full_preparation(self):
        df = _make_sample_df(30)
        result = prepare_strategy_dataframe(df, ema_period=7)
        expected_cols = [
            "ema_7_high", "ema_7_low", "is_red", "is_green",
            "close_to_ema_low", "low_touched_ema_low",
            "open_above_ema_high", "close_below_ema_high",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_no_nans_after_prep(self):
        df = _make_sample_df(30)
        result = prepare_strategy_dataframe(df, ema_period=7)
        assert result["ema_7_high"].isna().sum() == 0
        assert result["ema_7_low"].isna().sum() == 0

    def test_empty_df(self):
        df = pd.DataFrame()
        result = prepare_strategy_dataframe(df)
        assert result.empty
