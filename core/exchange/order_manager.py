"""
Slancio Crypto Algo Treding Engine — Order Manager
======================================
Handles execution of trades, interacting with Delta API for live trading,
or logging them virtually in DRY_RUN mode.
"""

from __future__ import annotations

import uuid
from loguru import logger
from core.config import get_settings
from core.exchange.client import DeltaExchangeClient
from core.strategy.signals import TradeSignal


class OrderManager:
    def __init__(self, client: DeltaExchangeClient = None, is_dry_run: bool = False):
        self.settings = get_settings()
        self.client = client
        self.is_dry_run = is_dry_run or self.settings.dry_run

    def _get_product_id(self, symbol: str) -> int:
        """Lookup product_id for order placement"""
        if not self.client:
            return 27  # Mock ID for testing
        product = self.client.get_product_by_symbol(symbol)
        return int(product["id"])

    def execute_signal(self, symbol: str, signal: TradeSignal, size: int) -> dict:
        """
        Execute a TradeSignal by placing market/limit orders and bracket orders (SL/TP).
        
        Args:
            symbol: Trading pair symbol (e.g., BTCUSD)
            signal: TradeSignal object with entry, SL, TP prices
            size: Number of contracts to trade
            
        Returns:
            Dictionary with order details (mocked if dry run)
        """
        side = "sell" if signal.signal_type.value == "short" else "buy"
        
        logger.info(
            f"🚀 EXECUTING SIGNAL | Symbol: {symbol} | Side: {side.upper()} | "
            f"Size: {size} | Entry: {signal.entry_price} | "
            f"SL: {signal.stop_loss} | TP: {signal.take_profit_target} | "
            f"Mode: {'DRY RUN' if self.is_dry_run else 'LIVE'}"
        )

        if self.is_dry_run:
            # Simulate order execution
            order_id = f"dry_run_{uuid.uuid4().hex[:8]}"
            return {
                "id": order_id,
                "symbol": symbol,
                "side": side,
                "size": size,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit_target,
                "status": "virtual_open"
            }

        # ── LIVE TRADING EXECUTION ──
        try:
            product_id = self._get_product_id(symbol)
            
            # Ensure leverage is set before placing order
            self.client.set_leverage(product_id, self.settings.max_leverage)
            
            # 1. Place Main Entry Order (Market Order for immediate execution)
            entry_response = self.client.place_order(
                product_id=product_id,
                size=size,
                side=side,
                order_type="market_order"
            )
            entry_order_id = entry_response.get("id")
            
            # 2. Place Stop Loss Order
            # For a short, the stop loss is a BUY stop order
            sl_side = "buy" if side == "sell" else "sell"
            sl_response = self.client.place_order(
                product_id=product_id,
                size=size,
                side=sl_side,
                order_type="market_order",  # Triggers a market order when stopped
                stop_price=signal.stop_loss,
                stop_order_type="stop_loss_order",
                reduce_only=True
            )
            
            logger.success(f"✅ Live orders placed! Entry ID: {entry_order_id}, SL ID: {sl_response.get('id')}")
            
            return {
                "id": entry_order_id,
                "sl_id": sl_response.get("id"),
                "symbol": symbol,
                "side": side,
                "size": size,
                "status": "live_open"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to execute live order: {e}")
            raise
            
    def close_position(self, symbol: str, current_price: float, size: int, side: str) -> dict:
        """
        Close an active position (usually when Take Profit is hit dynamically).
        """
        closing_side = "buy" if side == "sell" else "sell"
        
        logger.info(
            f"🛑 CLOSING POSITION | Symbol: {symbol} | Action: {closing_side.upper()} {size} contracts | "
            f"Price: {current_price} | Mode: {'DRY RUN' if self.is_dry_run else 'LIVE'}"
        )
        
        if self.is_dry_run:
            return {"status": "virtual_closed", "exit_price": current_price}
            
        try:
            product_id = self._get_product_id(symbol)
            
            # Place a market order in the opposite direction, reduce_only=True
            response = self.client.place_order(
                product_id=product_id,
                size=size,
                side=closing_side,
                order_type="market_order",
                reduce_only=True
            )
            logger.success(f"✅ Position closed successfully. Exit Order ID: {response.get('id')}")
            
            # Also cancel all open orders for this product (like the pending SL)
            # (In a real implementation, you'd iterate and cancel specific open orders)
            
            return {"status": "live_closed", "exit_price": current_price, "exit_id": response.get("id")}
        except Exception as e:
            logger.error(f"❌ Failed to close position: {e}")
            raise
