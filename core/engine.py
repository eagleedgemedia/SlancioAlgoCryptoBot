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
        ema_distance_points: int = 200,
        telegram_chat_id: str = None
    ):
        self.settings = get_settings()
        self.symbol = self.settings.trading_symbol
        self.resolution = self.settings.trading_timeframe
        self.is_dry_run = self.settings.dry_run or not api_key
        
        self.client = DeltaExchangeClient(api_key=api_key, api_secret=api_secret)
        self.data_feed = DataFeed(client=self.client)
        self.signal_generator = SignalGenerator(
            stop_loss_points=stop_loss_points,
            min_distance_ema_low=ema_distance_points
        )
        self.position_sizer = PositionSizer(client=self.client)
        self.order_manager = OrderManager(client=self.client, is_dry_run=self.is_dry_run)
        self.position_manager = PositionManager()
        self.telegram_chat_id = telegram_chat_id or self.settings.telegram_chat_id
        
        mode = 'DRY RUN' if self.is_dry_run else 'LIVE'
        logger.info(f"⚙️ Engine Initialized | User: {user_id} | Symbol: {self.symbol} | Mode: {mode}")

    def run_candle_cycle(self):
        """
        The main tick function. Called every time a new candle closes.
        """
        events = []
        logger.info(f"\n{'=' * 50}\n🚀 STARTING CANDLE CYCLE ({self.symbol} {self.resolution})\n{'=' * 50}")
        
        # 1. Fetch Latest Data
        df = self.data_feed.fetch_historical_candles(
            symbol=self.symbol,
            resolution=self.resolution,
            num_candles=100
        )
        if df.empty:
            logger.error("No data fetched, skipping cycle.")
            return events

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
                res = self._execute_exit(live_price, "TP Hit")
                if res:
                    events.append({"type": "close", "pnl": res[0], "reason": res[1], "exit_price": res[2]})
                return events
                
            # Check SL (Fallback for Dry Run)
            if self.settings.dry_run and self.position_manager.check_stop_loss(live_price):
                res = self._execute_exit(live_price, "SL Hit")
                if res:
                    events.append({"type": "close", "pnl": res[0], "reason": res[1], "exit_price": res[2]})
                return events
                
            logger.info("⏳ Position remains open. Waiting for exit conditions.")
            return events  # If we have an active trade, we don't look for new entries (Condition #6)

        # 4. Signal Evaluation (Look for new entries)
        logger.info("🔍 Scanning for new setups...")
        signal = self.signal_generator.evaluate(
            df=df, 
            has_active_trade=self.position_manager.has_active_position()
        )
        
        if signal:
            order_data = self._execute_entry(signal)
            if order_data:
                events.append({"type": "open", "order_data": order_data, "signal": signal})
        else:
            logger.info("⏸️ No valid setup found on this candle.")
            
        return events

    def _execute_entry(self, signal):
        """Handle position sizing and order placement for a new signal"""
        # A. Fetch Balances
        if self.is_dry_run:
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
            
            # --- Telegram Alert ---
            trade_type = "🟢 LONG" if signal.is_long else "🔴 SHORT"
            contract_size = self.position_sizer._get_contract_size(self.symbol)
            
            # Financial calculations
            margin_required = (contracts * contract_size * signal.entry_price) / self.settings.max_leverage
            sl_amount = (abs(signal.entry_price - signal.stop_loss) * contracts * contract_size)
            tp_amount = (abs(signal.take_profit - signal.entry_price) * contracts * contract_size)
            
            msg = (
                f"🚨 *NEW TRADE EXECUTED*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 Pair: `{self.symbol}`\n"
                f"🎯 Type: *{trade_type}*\n"
                f"💰 Entry Price: `{signal.entry_price:.2f}`\n"
                f"🛑 Stoploss: `{signal.stop_loss:.2f}`\n"
                f"✅ Target: `{signal.take_profit:.2f}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💸 Margin Required: `{margin_required:.2f} USDT` (₹{margin_required * 89.0:,.2f})\n"
                f"📉 SL Risk Amount: `-{sl_amount:.2f} USDT` (₹-{sl_amount * 89.0:,.2f})\n"
                f"📈 Target Reward: `+{tp_amount:.2f} USDT` (₹+{tp_amount * 89.0:,.2f})\n"
                f"📊 Conditions: `Liquidity Sweep + MTF Trend Alignment`\n"
            )
            self._send_telegram_alert(msg)
            return order_data
            
        except Exception as e:
            logger.error(f"Order Execution Failed: {e}")
            return None

    def _send_telegram_alert(self, message: str):
        if not self.settings.telegram_bot_token or not self.telegram_chat_id:
            return
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        try:
            import httpx
            with httpx.Client(timeout=10) as client:
                client.post(url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                })
        except Exception as e:
            logger.warning(f"Telegram alert failed: {e}")

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
            
            # --- Telegram Alert ---
            trade_type = "🔴 SHORT" if active_pos.is_short else "🟢 LONG"
            contract_size = self.position_sizer._get_contract_size(active_pos.symbol)
            total_pnl_usdt = pnl * active_pos.size * contract_size
            
            emoji = "🤑" if total_pnl_usdt > 0 else "🩸"
            msg = (
                f"{emoji} *TRADE CLOSED*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 Pair: `{active_pos.symbol}`\n"
                f"🎯 Type: *{trade_type}*\n"
                f"💰 Entry: `{active_pos.entry_price:.2f}`\n"
                f"🏁 Exit: `{exit_price:.2f}`\n"
                f"🔔 Reason: `{reason}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Realized PnL: `{'=' if total_pnl_usdt==0 else '+' if total_pnl_usdt>0 else ''}{total_pnl_usdt:.2f} USDT` (₹{'=' if total_pnl_usdt==0 else '+' if total_pnl_usdt>0 else ''}{total_pnl_usdt * 89.0:,.2f})\n"
            )
            self._send_telegram_alert(msg)
            return pnl, reason, exit_price
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return None
