"""
Slancio Crypto Algo Treding Engine — Phase 2 Paper Trading Demo
===================================================
Runs the core engine in DRY_RUN mode against live market data.

Run: python -m scripts.phase2_demo
"""

import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from core.engine import TradingEngine

def main():
    logger.info("=" * 60)
    logger.info("  SLANCIO CRYPTO ALGO TREDING ENGINE — Phase 2 Paper Trading Demo")
    logger.info("=" * 60)

    # Initialize Engine (Will auto-load .env config, ensure DRY_RUN=True)
    engine = TradingEngine()
    
    if not engine.settings.dry_run:
        logger.warning("DRY_RUN IS FALSE! THIS WILL PLACE REAL ORDERS. Aborting demo.")
        return

    logger.info("Started engine in Paper Trading Mode. Connecting to Delta Exchange...")
    if not engine.client.test_connection():
        return

    # In a real environment, you would use a scheduler (like APScheduler)
    # or a websocket to trigger this precisely at the close of every 1H candle.
    # For this demo, we will trigger it manually once, and then simulate a few ticks.
    
    # Tick 1: Current market state
    engine.run_candle_cycle()
    
    logger.info("\n" + "=" * 60)
    logger.info("Simulating manual trigger (e.g. 1 hour later)...")
    logger.info("=" * 60 + "\n")
    
    time.sleep(2)  # Pause for readability
    engine.run_candle_cycle()
    
    logger.info("\n" + "=" * 60)
    logger.info("Demo complete. To run continuously, use a scheduler (APScheduler).")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
