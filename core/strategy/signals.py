"""
Slancio Crypto Algo Treding Engine — Signal Generator
=========================================
Evaluates Short Setup entry conditions and generates trade signals.

Short Setup Entry Conditions (ALL must be true):
    1. Open > EMA 7 High
    2. Close < EMA 7 High
    3. Candle is Red
    4. Low has NOT touched EMA 7 Low
    5. Close >= 200 pts above EMA 7 Low
    6. No active trades
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger
from core.config import get_settings


class SignalType(str, Enum):
    SHORT = "short"
    LONG = "long"
    NO_SIGNAL = "no_signal"


@dataclass
class TradeSignal:
    signal_type: SignalType
    entry_price: float
    stop_loss: float
    take_profit_target: float
    timestamp: int
    candle_data: dict = field(default_factory=dict)
    ema_high: float = 0.0
    ema_low: float = 0.0
    close_to_ema_low_distance: float = 0.0
    conditions_met: dict = field(default_factory=dict)

    @property
    def risk_reward_ratio(self) -> float:
        risk = abs(self.stop_loss - self.entry_price)
        reward = abs(self.entry_price - self.take_profit_target)
        return round(reward / risk, 2) if risk > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit_target": self.take_profit_target,
            "risk_reward_ratio": self.risk_reward_ratio,
            "timestamp": self.timestamp,
            "ema_high": self.ema_high,
            "ema_low": self.ema_low,
            "conditions_met": self.conditions_met,
        }

    def __str__(self) -> str:
        return (
            f"SHORT SIGNAL | Entry: {self.entry_price:.2f} | "
            f"SL: {self.stop_loss:.2f} | TP: {self.take_profit_target:.2f} | "
            f"R:R = 1:{self.risk_reward_ratio}"
        )


class SignalGenerator:
    def __init__(self, ema_period=None, stop_loss_points=None, min_distance_ema_low=None):
        settings = get_settings()
        self.ema_period = ema_period or settings.ema_period
        self.stop_loss_points = stop_loss_points or settings.stop_loss_points
        self.min_distance_ema_low = min_distance_ema_low or settings.min_distance_from_ema_low
        self._ema_high_col = f"ema_{self.ema_period}_high"
        self._ema_low_col = f"ema_{self.ema_period}_low"

    def evaluate_short_setup(self, df: pd.DataFrame, has_active_trade: bool = False) -> Optional[TradeSignal]:
        if df.empty or len(df) < 2:
            return None

        candle = df.iloc[-1]
        o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
        ema_h = candle[self._ema_high_col]
        ema_l = candle[self._ema_low_col]
        ts = int(candle.get("timestamp", 0))
        dist = c - ema_l

        conds = {
            "open_above_ema_high": o > ema_h,
            "close_below_ema_high": c < ema_h,
            "candle_is_red": c < o,
            "low_not_touched_ema_low": l > ema_l,
            "close_above_min_distance": dist >= self.min_distance_ema_low,
            "no_active_trade": not has_active_trade,
        }

        all_met = all(conds.values())
        status = "SIGNAL" if all_met else "No signal"
        logger.info(
            f"Short Setup [{status}] | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f} | "
            f"EMA_H:{ema_h:.2f} EMA_L:{ema_l:.2f} | Dist:{dist:.2f} | "
            f"Conds: {conds}"
        )

        if not all_met:
            return None

        return TradeSignal(
            signal_type=SignalType.SHORT,
            entry_price=c,
            stop_loss=c + self.stop_loss_points,
            take_profit_target=ema_l,
            timestamp=ts,
            candle_data={"open": o, "high": h, "low": l, "close": c},
            ema_high=ema_h, ema_low=ema_l,
            close_to_ema_low_distance=dist,
            conditions_met=conds,
        )

    def evaluate(self, df: pd.DataFrame, has_active_trade: bool = False) -> Optional[TradeSignal]:
        return self.evaluate_short_setup(df, has_active_trade)
