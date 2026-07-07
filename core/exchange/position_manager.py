"""
Slancio Crypto Algo Treding Engine — Position Manager
=========================================
Tracks the state of the currently active trade in memory.
In production, this would synchronize with the database and exchange API.
"""

from __future__ import annotations
from typing import Optional
from dataclasses import dataclass
from loguru import logger
from core.strategy.signals import TradeSignal

@dataclass
class ActivePosition:
    symbol: str
    side: str  # "buy" or "sell"
    size: int
    entry_price: float
    stop_loss: float
    take_profit_target: float
    mode: str # "virtual_open" or "live_open"
    
    @property
    def is_short(self) -> bool:
        return self.side == "sell"


class PositionManager:
    def __init__(self):
        # In memory state for the active trade.
        # Since this bot focuses on 1 pair (BTCUSD) at 1 timeframe (1H),
        # we only track one active position at a time.
        self.active_position: Optional[ActivePosition] = None

    def has_active_position(self) -> bool:
        return self.active_position is not None

    def open_position(self, order_data: dict, signal: TradeSignal):
        """Record a newly opened position in state."""
        self.active_position = ActivePosition(
            symbol=order_data["symbol"],
            side=order_data["side"],
            size=order_data["size"],
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit_target=signal.take_profit_target,
            mode=order_data["status"]
        )
        logger.info(f"💾 Position saved to memory: {self.active_position}")

    def close_position(self):
        """Clear the active position from state."""
        if self.active_position:
            logger.info(f"🧹 Clearing active position from memory.")
            self.active_position = None

    def check_take_profit(self, current_price: float, ema_low: float) -> bool:
        """
        Check if the dynamic Take Profit condition is met.
        For a SHORT setup, TP is met when current_price touches (<=) EMA 7 Low.
        Note: The EMA Low target moves with every new candle.
        """
        if not self.active_position or not self.active_position.is_short:
            return False
            
        # Update our TP target dynamically to the latest EMA Low
        self.active_position.take_profit_target = ema_low
        
        # Check if price touched the target
        if current_price <= ema_low:
            logger.info(f"🎯 TAKE PROFIT HIT! Current Price ({current_price}) <= EMA Low ({ema_low})")
            return True
            
        return False
        
    def check_stop_loss(self, current_price: float) -> bool:
        """
        Check if SL is hit (fallback monitor, exchange should handle this for live orders,
        but we need it for DRY_RUN mode).
        """
        if not self.active_position or not self.active_position.is_short:
            return False
            
        if current_price >= self.active_position.stop_loss:
            logger.warning(f"💥 STOP LOSS HIT! Current Price ({current_price}) >= SL ({self.active_position.stop_loss})")
            return True
            
        return False
