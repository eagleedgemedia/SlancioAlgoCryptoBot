"""
Slancio Crypto Algo Treding Engine — Historical & Live Data Feed
====================================================
Fetches historical OHLC candle data from Delta Exchange,
handles pagination for large datasets, and converts raw
API responses into clean Pandas DataFrames for indicator
calculations.

Usage:
    from core.exchange.data_feed import DataFeed
    
    feed = DataFeed()
    df = feed.fetch_historical_candles(symbol="BTCUSDT", resolution="1h", num_candles=500)
    print(df.tail())
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from loguru import logger

from core.config import get_settings, MAX_CANDLES_PER_REQUEST, TIMEFRAME_MAP
from core.exchange.client import DeltaExchangeClient, create_client


# Timeframe to seconds mapping for pagination calculations
TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "1d": 86400,
    "7d": 604800,
    "1w": 604800,
    "2w": 1209600,
    "30d": 2592000,
}


class DataFeed:
    """
    Market data feed for fetching and processing OHLC candle data.
    
    Handles:
        - Paginated historical data fetching (>2000 candles)
        - Raw API response → Pandas DataFrame conversion
        - Data validation and cleaning
        - Live price polling
    
    Args:
        client: Optional DeltaExchangeClient instance
    """

    def __init__(self, client: DeltaExchangeClient = None):
        self.client = client or create_client()
        self.settings = get_settings()
        self._product_cache: dict = {}

    # ═══════════════════════════════════════════════════
    # Historical Candle Data
    # ═══════════════════════════════════════════════════

    def fetch_historical_candles(
        self,
        symbol: str = None,
        resolution: str = None,
        num_candles: int = 200,
        end_time: int = None,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLC candle data and return as a DataFrame.
        
        Automatically handles pagination if num_candles > 2000 (API limit).
        Data is returned sorted by timestamp (oldest first).
        
        Args:
            symbol: Trading pair (defaults to settings.trading_symbol)
            resolution: Candle timeframe (defaults to settings.trading_timeframe)
            num_candles: Number of candles to fetch (handles pagination)
            end_time: End timestamp (Unix epoch seconds, defaults to now)
            
        Returns:
            DataFrame with columns: timestamp, datetime, open, high, low, close, volume
            
        Raises:
            ValueError: If resolution is not supported
        """
        symbol = symbol or self.settings.trading_symbol
        resolution = resolution or self.settings.trading_timeframe
        end_time = end_time or int(time.time())

        # Validate resolution
        if resolution not in TIMEFRAME_SECONDS:
            raise ValueError(
                f"Unsupported resolution '{resolution}'. "
                f"Supported: {list(TIMEFRAME_SECONDS.keys())}"
            )

        tf_seconds = TIMEFRAME_SECONDS[resolution]
        
        logger.info(
            f"📊 Fetching {num_candles} x {resolution} candles for {symbol} | "
            f"End: {datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()}"
        )

        all_candles = []
        remaining = num_candles
        current_end = end_time

        while remaining > 0:
            # Calculate batch size (capped at API limit)
            batch_size = min(remaining, MAX_CANDLES_PER_REQUEST)
            
            # Calculate start time for this batch
            start_time = current_end - (batch_size * tf_seconds)

            # Fetch batch from API
            try:
                raw_candles = self.client.get_candles(
                    symbol=symbol,
                    resolution=resolution,
                    start=start_time,
                    end=current_end,
                )
            except Exception as e:
                logger.error(f"Failed to fetch candles: {e}")
                break

            if not raw_candles:
                logger.warning(f"No candle data returned for period ending {current_end}")
                break

            all_candles.extend(raw_candles)
            remaining -= len(raw_candles)

            # Move the window back for the next batch
            current_end = start_time - 1

            # Avoid rate limiting
            if remaining > 0:
                time.sleep(0.5)

            logger.debug(
                f"  Batch: {len(raw_candles)} candles fetched | "
                f"Remaining: {remaining} | Total so far: {len(all_candles)}"
            )

        if not all_candles:
            logger.warning("No candle data fetched. Returning empty DataFrame.")
            return self._empty_dataframe()

        # Convert to DataFrame and clean
        df = self._candles_to_dataframe(all_candles)
        
        # Deduplicate (overlapping pagination) and sort
        df = df.drop_duplicates(subset=["timestamp"], keep="last")
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Trim to exact requested count
        if len(df) > num_candles:
            df = df.tail(num_candles).reset_index(drop=True)

        logger.info(
            f"✅ Fetched {len(df)} candles | "
            f"Range: {df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}"
        )

        return df

    def _candles_to_dataframe(self, raw_candles: list) -> pd.DataFrame:
        """
        Convert raw API candle data to a clean Pandas DataFrame.
        
        Delta Exchange returns candles as:
            {"time": 1625097600, "open": 34000, "high": 34500, "low": 33800, "close": 34200, "volume": 1234}
        
        Args:
            raw_candles: List of candle dictionaries from the API
            
        Returns:
            Cleaned DataFrame with proper types
        """
        df = pd.DataFrame(raw_candles)

        # Rename 'time' to 'timestamp' for clarity
        if "time" in df.columns:
            df = df.rename(columns={"time": "timestamp"})
        elif "t" in df.columns:
            df = df.rename(columns={"t": "timestamp"})

        # Handle alternative column names from API
        column_mapping = {
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
        }
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        # Ensure all required columns exist
        required_columns = ["timestamp", "open", "high", "low", "close"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns in candle data: {missing}")

        # Add 'volume' column if missing
        if "volume" not in df.columns:
            df["volume"] = 0

        # Convert types
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype(int)

        # Add human-readable datetime column
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)

        # Select and order columns
        df = df[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]

        # Drop any rows with NaN values in OHLC
        initial_count = len(df)
        df = df.dropna(subset=["open", "high", "low", "close"])
        if len(df) < initial_count:
            logger.warning(f"Dropped {initial_count - len(df)} rows with NaN OHLC values")

        return df

    def _empty_dataframe(self) -> pd.DataFrame:
        """Return an empty DataFrame with the standard candle columns."""
        return pd.DataFrame(
            columns=["timestamp", "datetime", "open", "high", "low", "close", "volume"]
        )

    # ═══════════════════════════════════════════════════
    # Live Price Data
    # ═══════════════════════════════════════════════════

    def get_live_price(self, symbol: str = None) -> Optional[float]:
        """
        Get the current mark/last price for a symbol.
        
        Args:
            symbol: Trading pair (defaults to settings)
            
        Returns:
            Current price as float, or None on error
        """
        symbol = symbol or self.settings.trading_symbol
        try:
            ticker = self.client.get_ticker(symbol)
            # Delta ticker returns mark_price or close
            price = float(ticker.get("mark_price") or ticker.get("close", 0))
            logger.debug(f"Live price {symbol}: {price}")
            return price
        except Exception as e:
            logger.error(f"Failed to get live price for {symbol}: {e}")
            return None

    def get_latest_candle(
        self,
        symbol: str = None,
        resolution: str = None,
    ) -> Optional[pd.Series]:
        """
        Fetch the most recently closed candle.
        
        Args:
            symbol: Trading pair
            resolution: Candle timeframe
            
        Returns:
            Pandas Series with candle data, or None on error
        """
        try:
            df = self.fetch_historical_candles(
                symbol=symbol,
                resolution=resolution,
                num_candles=2,  # Fetch 2 — the last closed + possibly current
            )
            if df.empty:
                return None
            # Return the second-to-last (most recently CLOSED candle)
            # The very last candle might still be forming
            return df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
        except Exception as e:
            logger.error(f"Failed to get latest candle: {e}")
            return None

    # ═══════════════════════════════════════════════════
    # Product Lookup
    # ═══════════════════════════════════════════════════

    def get_product_id(self, symbol: str = None) -> Optional[int]:
        """
        Look up the product_id for a given symbol.
        
        Delta Exchange order endpoints require product_id (integer),
        not the symbol string. This method caches the lookup.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Integer product_id, or None if not found
        """
        symbol = symbol or self.settings.trading_symbol
        
        # Check cache first
        if symbol in self._product_cache:
            return self._product_cache[symbol]

        try:
            product = self.client.get_product_by_symbol(symbol)
            product_id = product.get("id")
            if product_id:
                self._product_cache[symbol] = product_id
                logger.info(f"Product ID for {symbol}: {product_id}")
                return product_id
            logger.warning(f"Product ID not found for symbol: {symbol}")
            return None
        except Exception as e:
            logger.error(f"Failed to look up product ID for {symbol}: {e}")
            return None
