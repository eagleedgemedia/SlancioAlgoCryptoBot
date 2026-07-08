"""
Slancio Crypto Algo Treding Engine — Core Engine Orchestrator
=================================================
Ties all the modules together. Connects to the exchange,
fetches data, calculates sizing, manages signals, and places orders.
"""

from __future__ import annotations

import time
from loguru import logger
from core.config import get_settings
from core.exchange.client import DeltaExchangeClient
from core.exchange.data_feed import DataFeed
from core.strategy.indicators import prepare_strategy_dataframe
from core.strategy.signals import SignalGenerator
from core.risk.position_sizer import PositionSizer
from core.exchange.order_manager import OrderManager
from core.exchange.position_manager import PositionManager


class TradingEngine:
    def __init__(
        self, 
        api_key: str = None, 
        api_secret: str = None, 
        user_id: str = None,
        stop_loss_points: float = 400.0,
        ema_distance_points: int = 200
    ):
        self.settings = get_settings()
        self.client = DeltaExchangeClient(api_key=api_key, api_secret=api_secret)
        self.data_feed = DataFeed(client=self.client)
        self.signal_generator = SignalGenerator(
            stop_loss_points=stop_loss_points,
            min_distance_ema_low=ema_distance_points
        )
        self.position_sizer = PositionSizer(client=self.client)
        self.order_manager = OrderManager(client=self.client)
        self.position_manager = PositionManager()
        
        self.symbol = self.settings.trading_symbol
        self.resolution = self.settings.trading_timeframe
        
        mode = 'DRY RUN' if self.settings.dry_run else 'LIVE'
        logger.info(f"⚙️ Engine Initialized | User: {user_id} | Symbol: {self.symbol} | Mode: {mode}")

    def run_candle_cycle(self):
        """
        The main tick function. Called every time a new candle closes.
        """
        logger.info(f"\n{'=' * 50}\n🚀 STARTING CANDLE CYCLE ({self.symbol} {self.resolution})\n{'=' * 50}")
        
        # 1. Fetch Latest Data
        df = self.data_feed.fetch_historical_candles(
            symbol=self.symbol,
            resolution=self.resolution,
            num_candles=100
        )
        if df.empty:
            logger.error("No data fetched, skipping cycle.")
            return

        # 2. Prepare Strategy Indicators
        df = prepare_strategy_dataframe(df, ema_period=self.settings.ema_period)
        
        # We need the most recent EMA 7 Low to check dynamic Take Profit
        latest_ema_low = df.iloc[-1][f"ema_{self.settings.ema_period}_low"]
        current_price = df.iloc[-1]["close"]
        
        logger.info(f"📊 Current Price: {current_price} | Latest EMA Low: {latest_ema_low:.2f}")

        # 3. Position Management (Check exits if we have an active trade)
        if self.position_manager.has_active_position():
            # In live trading, you might poll a websocket for the live price here instead of using candle close
            live_price = self.data_feed.get_live_price(self.symbol) or current_price
            
            # Check TP
            if self.position_manager.check_take_profit(live_price, latest_ema_low):
                self._execute_exit(live_price, "TP Hit")
                return # Exit cycle, don't enter new trade immediately
                
            # Check SL (Fallback for Dry Run)
            if self.settings.dry_run and self.position_manager.check_stop_loss(live_price):
                self._execute_exit(live_price, "SL Hit")
                return
                
            logger.info("⏳ Position remains open. Waiting for exit conditions.")
            return  # If we have an active trade, we don't look for new entries (Condition #6)

        # 4. Signal Evaluation (Look for new entries)
        logger.info("🔍 Scanning for new setups...")
        signal = self.signal_generator.evaluate(
            df=df, 
            has_active_trade=self.position_manager.has_active_position()
        )
        
        if signal:
            self._execute_entry(signal)
        else:
            logger.info("⏸️ No valid setup found on this candle.")

    def _execute_entry(self, signal):
        """Handle position sizing and order placement for a new signal"""
        # A. Fetch Balances
        if self.settings.dry_run:
            available_balance = 10000.0  # Mock 10k USDT balance for paper trading
            logger.info(f"💸 Paper Trading Balance: {available_balance} USDT")
        else:
            try:
                # Actual balance logic (assuming USDT collateral)
                balances = self.client.get_wallet_balances()
                usdt_balance = next((b for b in balances if b.get("asset_symbol") == "USDT"), None)
                available_balance = float(usdt_balance.get("available_balance", 0)) if usdt_balance else 0.0
                logger.info(f"💸 Live Available Balance: {available_balance} USDT")
            except Exception as e:
                logger.error(f"Failed to fetch balance: {e}")
                return
                
        if available_balance <= 0:
            logger.error("Insufficient balance to execute trade.")
            return

        # B. Calculate Size
        contracts = self.position_sizer.calculate_position_size(
            symbol=self.symbol,
            current_price=signal.entry_price,
            available_balance=available_balance
        )
        
        if contracts <= 0:
            logger.error("Calculated size is 0 contracts. Trade aborted.")
            return

        # C. Execute Order
        try:
            order_data = self.order_manager.execute_signal(
                symbol=self.symbol,
                signal=signal,
                size=contracts
            )
            # D. Track in Memory
            self.position_manager.open_position(order_data, signal)
            
        except Exception as e:
            logger.error(f"Order Execution Failed: {e}")

    def _execute_exit(self, exit_price: float, reason: str):
        """Close current position"""
        active_pos = self.position_manager.active_position
        try:
            self.order_manager.close_position(
                symbol=active_pos.symbol,
                current_price=exit_price,
                size=active_pos.size,
                side=active_pos.side
            )
            self.position_manager.close_position()
            
            # Simple PnL calculation for logging
            if active_pos.is_short:
                pnl = active_pos.entry_price - exit_price
            else:
                pnl = exit_price - active_pos.entry_price
                
            logger.success(f"🎊 EXIT SUCCESS | Reason: {reason} | PnL: {pnl:.2f} per contract")
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
