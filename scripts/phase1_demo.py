"""
Slancio Crypto Algo Treding Engine — Phase 1 Demo Runner
============================================
Connects to Delta Exchange, fetches BTCUSDT 1H candles,
calculates EMA 7 High/Low, and evaluates the Short Setup.

Run: python -m scripts.phase1_demo
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from core.exchange.client import DeltaExchangeClient
from core.exchange.data_feed import DataFeed
from core.strategy.indicators import prepare_strategy_dataframe
from core.strategy.signals import SignalGenerator


def main():
    logger.info("=" * 60)
    logger.info("  SLANCIO CRYPTO ALGO TREDING ENGINE — Phase 1 Demo")
    logger.info("=" * 60)

    # Step 1: Test connection
    logger.info("\n📡 Step 1: Testing Delta Exchange API connection...")
    client = DeltaExchangeClient()
    
    if not client.test_connection():
        logger.error("Cannot connect to Delta Exchange. Check your internet.")
        return

    # Step 2: Fetch candles
    logger.info("\n📊 Step 2: Fetching historical 1H candles...")
    feed = DataFeed(client=client)
    df = feed.fetch_historical_candles(num_candles=100)

    if df.empty:
        logger.error("No candle data received.")
        return

    logger.info(f"\nRaw Data (last 5 candles):\n{df.tail().to_string()}")

    # Step 3: Calculate indicators
    logger.info("\n📈 Step 3: Calculating EMA 7 High/Low bands...")
    df = prepare_strategy_dataframe(df, ema_period=7)

    cols = ["datetime", "open", "high", "low", "close", "ema_7_high", "ema_7_low", "is_red"]
    logger.info(f"\nEnriched Data (last 10):\n{df[cols].tail(10).to_string()}")

    # Step 4: Evaluate signal
    logger.info("\n🔍 Step 4: Evaluating Short Setup on latest candle...")
    generator = SignalGenerator()
    signal = generator.evaluate(df, has_active_trade=False)

    if signal:
        logger.info(f"\n🚨 SIGNAL: {signal}")
        logger.info(f"   Risk:Reward = 1:{signal.risk_reward_ratio}")
    else:
        logger.info("\n⏸️  No signal on the current candle.")

    # Step 5: Scan recent candles
    logger.info("\n📋 Step 5: Scanning last 20 candles for signals...")
    count = 0
    for i in range(max(0, len(df) - 20), len(df)):
        subset = df.iloc[:i + 1].copy()
        sig = generator.evaluate(subset, has_active_trade=False)
        if sig:
            count += 1
            logger.info(f"  Signal #{count} at {subset.iloc[-1]['datetime']}: {sig}")

    logger.info(f"\n✅ Found {count} signals in the last 20 candles.")
    logger.info("=" * 60)
    logger.info("  Phase 1 Demo Complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
