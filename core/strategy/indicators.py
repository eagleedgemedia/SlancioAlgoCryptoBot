"""
Slancio Crypto Algo Treding Engine — Technical Indicators Module
====================================================
Vectorized indicator calculations using Pandas.
All functions accept a DataFrame and return it with new columns added.

Current Indicators:
    - EMA (Exponential Moving Average) — generic
    - EMA 7 High (EMA of candle highs, period 7)
    - EMA 7 Low (EMA of candle lows, period 7)

Design Principles:
    1. Pure functions — no side effects, no API calls
    2. Vectorized operations — fast on large datasets
    3. Column naming convention: {indicator}_{period}_{source}
       e.g., ema_7_high, ema_7_low

Usage:
    from core.strategy.indicators import calculate_ema_bands
    
    df = data_feed.fetch_historical_candles(num_candles=200)
    df = calculate_ema_bands(df, period=7)
    
    print(df[['close', 'ema_7_high', 'ema_7_low']].tail(10))
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from loguru import logger


def calculate_ema(
    series: pd.Series,
    period: int,
    adjust: bool = False,
) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA) on a Pandas Series.
    
    The EMA gives more weight to recent data points, making it more
    responsive to new information than a Simple Moving Average (SMA).
    
    Formula:
        EMA_t = α × Price_t + (1 - α) × EMA_{t-1}
        where α (smoothing factor) = 2 / (period + 1)
    
    Args:
        series: Pandas Series of price data (e.g., df['high'], df['close'])
        period: EMA lookback period (e.g., 7 for EMA 7)
        adjust: If True, uses adjusted EMA calculation (more accurate
                for early values but slower). Default False matches
                most trading platforms' behavior.
    
    Returns:
        Pandas Series with EMA values. First (period-1) values may be NaN.
    
    Example:
        >>> ema_7 = calculate_ema(df['close'], period=7)
    """
    if period < 1:
        raise ValueError(f"EMA period must be >= 1, got {period}")
    if series.empty:
        return series

    return series.ewm(span=period, adjust=adjust, min_periods=period).mean()


def calculate_ema_high(
    df: pd.DataFrame,
    period: int = 7,
    column_name: str = None,
) -> pd.DataFrame:
    """
    Calculate EMA of candle HIGH prices.
    
    This creates an upper envelope that tracks the trend of highs,
    useful for identifying resistance levels and bearish reversals.
    
    Args:
        df: DataFrame with 'high' column
        period: EMA lookback period (default: 7)
        column_name: Output column name (default: f"ema_{period}_high")
    
    Returns:
        DataFrame with new EMA High column added
        
    Raises:
        KeyError: If 'high' column is not present
    """
    if "high" not in df.columns:
        raise KeyError("DataFrame must contain a 'high' column")

    col = column_name or f"ema_{period}_high"
    df[col] = calculate_ema(df["high"], period=period)
    
    logger.debug(f"Calculated {col} | Latest: {df[col].iloc[-1]:.2f}")
    return df


def calculate_ema_low(
    df: pd.DataFrame,
    period: int = 7,
    column_name: str = None,
) -> pd.DataFrame:
    """
    Calculate EMA of candle LOW prices.
    
    This creates a lower envelope that tracks the trend of lows,
    useful for identifying support levels and take-profit targets.
    
    Args:
        df: DataFrame with 'low' column
        period: EMA lookback period (default: 7)
        column_name: Output column name (default: f"ema_{period}_low")
    
    Returns:
        DataFrame with new EMA Low column added
        
    Raises:
        KeyError: If 'low' column is not present
    """
    if "low" not in df.columns:
        raise KeyError("DataFrame must contain a 'low' column")

    col = column_name or f"ema_{period}_low"
    df[col] = calculate_ema(df["low"], period=period)
    
    logger.debug(f"Calculated {col} | Latest: {df[col].iloc[-1]:.2f}")
    return df


def calculate_ema_bands(
    df: pd.DataFrame,
    period: int = 7,
) -> pd.DataFrame:
    """
    Calculate both EMA High and EMA Low bands in one call.
    
    This is the primary indicator function for the KSL Short Setup strategy.
    It adds both ema_{period}_high and ema_{period}_low columns.
    
    The band between EMA High and EMA Low represents the "channel" within
    which price is expected to oscillate. Breaks above/below these bands
    with specific candle patterns generate entry signals.
    
    Args:
        df: DataFrame with 'high' and 'low' columns
        period: EMA lookback period (default: 7)
    
    Returns:
        DataFrame with both EMA band columns added
        
    Example:
        >>> df = calculate_ema_bands(df, period=7)
        >>> print(df[['close', 'ema_7_high', 'ema_7_low']].tail())
        
              close    ema_7_high   ema_7_low
        195   97500.0    97650.25    97120.50
        196   97300.0    97580.19    97080.38
        197   97450.0    97547.64    97090.28
        198   97200.0    97460.98    97060.21
        199   97100.0    97370.74    97070.16
    """
    if df.empty:
        logger.warning("Empty DataFrame passed to calculate_ema_bands")
        return df

    required_cols = {"high", "low"}
    missing = required_cols - set(df.columns)
    if missing:
        raise KeyError(f"DataFrame missing required columns: {missing}")

    df = calculate_ema_high(df, period=period)
    df = calculate_ema_low(df, period=period)

    # Calculate band width (useful for volatility assessment)
    high_col = f"ema_{period}_high"
    low_col = f"ema_{period}_low"
    df[f"ema_{period}_bandwidth"] = df[high_col] - df[low_col]

    logger.info(
        f"📈 EMA {period} Bands calculated | "
        f"Latest High: {df[high_col].iloc[-1]:.2f} | "
        f"Latest Low: {df[low_col].iloc[-1]:.2f} | "
        f"Bandwidth: {df[f'ema_{period}_bandwidth'].iloc[-1]:.2f}"
    )

    return df


def calculate_candle_properties(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add candle color and body size properties to the DataFrame.
    
    These properties are used by the signal generator to evaluate
    entry conditions (e.g., "candle is red").
    
    Adds columns:
        - is_red: True if Close < Open (bearish candle)
        - is_green: True if Close >= Open (bullish candle)
        - body_size: Absolute difference between Open and Close
        - upper_wick: High - max(Open, Close)
        - lower_wick: min(Open, Close) - Low
        - total_range: High - Low
    
    Args:
        df: DataFrame with OHLC columns
        
    Returns:
        DataFrame with candle property columns added
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"DataFrame missing required columns: {missing}")

    df["is_red"] = df["close"] < df["open"]
    df["is_green"] = df["close"] >= df["open"]
    df["body_size"] = (df["close"] - df["open"]).abs()
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["total_range"] = df["high"] - df["low"]

    logger.debug(
        f"Candle properties added | "
        f"Last candle: {'🔴 Red' if df['is_red'].iloc[-1] else '🟢 Green'} | "
        f"Body: {df['body_size'].iloc[-1]:.2f}"
    )

    return df


def prepare_strategy_dataframe(
    df: pd.DataFrame,
    ema_period: int = 7,
) -> pd.DataFrame:
    """
    One-call preparation of all indicators needed for the Short Setup strategy.
    
    This is the main entry point for the strategy module. It calculates:
        1. EMA 7 High and EMA 7 Low bands
        2. Candle color and body properties
        3. Distance metrics between price and EMA bands
    
    Args:
        df: Raw OHLC DataFrame from DataFeed
        ema_period: EMA period (default: 7)
    
    Returns:
        Fully enriched DataFrame ready for signal generation
    """
    if df.empty:
        logger.warning("Empty DataFrame — skipping indicator preparation")
        return df

    # Calculate EMA bands
    df = calculate_ema_bands(df, period=ema_period)

    # Calculate candle properties
    df = calculate_candle_properties(df)

    # Add distance metrics for signal generation
    high_col = f"ema_{ema_period}_high"
    low_col = f"ema_{ema_period}_low"

    # Distance from Close to EMA Low (positive = Close above EMA Low)
    df["close_to_ema_low"] = df["close"] - df[low_col]

    # Distance from Low to EMA Low (positive = candle Low above EMA Low)
    df["low_to_ema_low"] = df["low"] - df[low_col]

    # Whether candle Low has touched/crossed below EMA Low
    df["low_touched_ema_low"] = df["low"] <= df[low_col]

    # Whether Open is above EMA High
    df["open_above_ema_high"] = df["open"] > df[high_col]

    # Whether Close is below EMA High
    df["close_below_ema_high"] = df["close"] < df[high_col]

    # Drop NaN rows from EMA warmup period
    warmup_nans = df[high_col].isna().sum()
    if warmup_nans > 0:
        df = df.dropna(subset=[high_col, low_col]).reset_index(drop=True)
        logger.debug(f"Dropped {warmup_nans} warmup NaN rows")

    logger.info(
        f"✅ Strategy DataFrame prepared | "
        f"{len(df)} rows | "
        f"Columns: {list(df.columns)}"
    )

    return df
