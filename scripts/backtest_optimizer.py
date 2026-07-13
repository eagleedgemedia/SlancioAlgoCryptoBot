"""
Backtest and optimize the current Slancio EMA short strategy.

This runner fetches public Delta Exchange candles, simulates the implemented
short-only strategy, and compares timeframe/entry/SL/TP parameter sets.

Run examples:
    python scripts/backtest_optimizer.py
    python scripts/backtest_optimizer.py --symbol BTCUSD --years 5
    python scripts/backtest_optimizer.py --no-fetch --data-dir data/backtests
"""

from __future__ import annotations

import argparse
import csv
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


BASE_URLS = {
    "india": "https://api.india.delta.exchange",
    "global": "https://api.delta.exchange",
}

TIMEFRAME_SECONDS = {
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
}


@dataclass(frozen=True)
class StrategyParams:
    timeframe: str
    entry_mode: str
    stop_loss_points: float
    min_distance_from_ema_low: float
    take_profit_mode: str
    fixed_rr: float | None = None
    ema_period: int = 7


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: str
    entry: float
    exit: float
    stop_loss: float
    take_profit: float
    pnl_points: float
    bars_held: int
    exit_reason: str


def fetch_delta_candles(
    symbol: str,
    timeframe: str,
    years: float,
    region: str,
    data_dir: Path,
    force_fetch: bool,
) -> pd.DataFrame:
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_path = data_dir / f"{symbol}_{timeframe}_{years:g}y.csv"
    if cache_path.exists() and not force_fetch:
        return pd.read_csv(cache_path, parse_dates=["datetime"])

    tf_seconds = TIMEFRAME_SECONDS[timeframe]
    end_ts = int(time.time())
    start_limit = end_ts - int(years * 365.25 * 24 * 60 * 60)
    current_end = end_ts
    all_rows: list[dict] = []
    base_url = BASE_URLS[region].rstrip("/")

    while current_end > start_limit:
        current_start = max(start_limit, current_end - (2000 * tf_seconds))
        params = {
            "symbol": symbol,
            "resolution": timeframe,
            "start": str(current_start),
            "end": str(current_end),
        }
        response = requests.get(f"{base_url}/v2/history/candles", params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success", True):
            raise RuntimeError(f"Delta API returned error: {payload}")
        rows = payload.get("result", payload)
        if not rows:
            break
        all_rows.extend(rows)
        current_end = current_start - 1
        time.sleep(0.2)

    if not all_rows:
        raise RuntimeError(f"No candle data returned for {symbol} {timeframe}")

    df = pd.DataFrame(all_rows)
    if "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = df["timestamp"].astype(int)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    df = df[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]
    df.to_csv(cache_path, index=False)
    return df


def prepare_indicators(df: pd.DataFrame, ema_period: int) -> pd.DataFrame:
    out = df.copy()
    out[f"ema_{ema_period}_high"] = out["high"].ewm(span=ema_period, adjust=False, min_periods=ema_period).mean()
    out[f"ema_{ema_period}_low"] = out["low"].ewm(span=ema_period, adjust=False, min_periods=ema_period).mean()
    return out.dropna().reset_index(drop=True)


def signal_on_row(row: pd.Series, params: StrategyParams) -> bool:
    ema_high = row[f"ema_{params.ema_period}_high"]
    ema_low = row[f"ema_{params.ema_period}_low"]
    return bool(
        row["open"] > ema_high
        and row["close"] < ema_high
        and row["close"] < row["open"]
        and row["low"] > ema_low
        and (row["close"] - ema_low) >= params.min_distance_from_ema_low
    )


def initial_take_profit(entry: float, ema_low: float, params: StrategyParams) -> float:
    if params.take_profit_mode == "ema_low":
        return ema_low
    if params.take_profit_mode == "fixed_rr" and params.fixed_rr:
        return entry - (params.stop_loss_points * params.fixed_rr)
    raise ValueError(f"Unsupported take profit mode: {params.take_profit_mode}")


def backtest(df: pd.DataFrame, params: StrategyParams) -> list[Trade]:
    prepared = prepare_indicators(df, params.ema_period)
    trades: list[Trade] = []
    in_trade = False
    entry = stop_loss = take_profit = 0.0
    entry_time = None
    entry_index = 0

    for idx in range(len(prepared) - 1):
        row = prepared.iloc[idx]

        if in_trade:
            ema_low = row[f"ema_{params.ema_period}_low"]
            if params.take_profit_mode == "ema_low":
                take_profit = ema_low

            exit_price = None
            exit_reason = None

            if row["high"] >= stop_loss:
                exit_price = stop_loss
                exit_reason = "stop_loss"
            elif row["low"] <= take_profit:
                exit_price = take_profit
                exit_reason = "take_profit"

            if exit_price is not None:
                trades.append(
                    Trade(
                        entry_time=entry_time,
                        exit_time=row["datetime"],
                        side="short",
                        entry=entry,
                        exit=exit_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        pnl_points=entry - exit_price,
                        bars_held=idx - entry_index,
                        exit_reason=exit_reason,
                    )
                )
                in_trade = False
            continue

        if not signal_on_row(row, params):
            continue

        next_row = prepared.iloc[idx + 1]
        if params.entry_mode == "signal_close":
            entry = float(row["close"])
            entry_time = row["datetime"]
            entry_index = idx
        elif params.entry_mode == "next_open":
            entry = float(next_row["open"])
            entry_time = next_row["datetime"]
            entry_index = idx + 1
        else:
            raise ValueError(f"Unsupported entry mode: {params.entry_mode}")

        ema_low_at_signal = float(row[f"ema_{params.ema_period}_low"])
        stop_loss = entry + params.stop_loss_points
        take_profit = initial_take_profit(entry, ema_low_at_signal, params)
        if take_profit >= entry:
            continue
        in_trade = True

    if in_trade:
        last = prepared.iloc[-1]
        trades.append(
            Trade(
                entry_time=entry_time,
                exit_time=last["datetime"],
                side="short",
                entry=entry,
                exit=float(last["close"]),
                stop_loss=stop_loss,
                take_profit=take_profit,
                pnl_points=entry - float(last["close"]),
                bars_held=len(prepared) - 1 - entry_index,
                exit_reason="end_of_data",
            )
        )

    return trades


def max_drawdown(equity: Iterable[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def summarize(params: StrategyParams, trades: list[Trade]) -> dict:
    pnls = [t.pnl_points for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = sum(pnls)
    equity = []
    running = 0.0
    for pnl in pnls:
        running += pnl
        equity.append(running)
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and abs(sum(losses)) > 0 else math.inf
    return {
        "timeframe": params.timeframe,
        "entry_mode": params.entry_mode,
        "stop_loss_points": params.stop_loss_points,
        "min_distance_from_ema_low": params.min_distance_from_ema_low,
        "take_profit_mode": params.take_profit_mode,
        "fixed_rr": params.fixed_rr or "",
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round((len(wins) / len(trades) * 100) if trades else 0, 2),
        "net_points": round(total, 2),
        "avg_points": round((total / len(trades)) if trades else 0, 2),
        "profit_factor": round(profit_factor, 3) if math.isfinite(profit_factor) else "inf",
        "max_drawdown_points": round(max_drawdown(equity), 2),
        "avg_bars_held": round(sum(t.bars_held for t in trades) / len(trades), 2) if trades else 0,
        "take_profit_exits": sum(1 for t in trades if t.exit_reason == "take_profit"),
        "stop_loss_exits": sum(1 for t in trades if t.exit_reason == "stop_loss"),
    }


def build_param_grid(timeframe: str) -> list[StrategyParams]:
    stop_losses = [200, 300, 400, 500, 600, 800, 1000]
    min_distances = [50, 100, 150, 200, 300, 400, 600]
    entry_modes = ["signal_close", "next_open"]
    params: list[StrategyParams] = []
    for entry_mode in entry_modes:
        for sl in stop_losses:
            for dist in min_distances:
                params.append(
                    StrategyParams(
                        timeframe=timeframe,
                        entry_mode=entry_mode,
                        stop_loss_points=float(sl),
                        min_distance_from_ema_low=float(dist),
                        take_profit_mode="ema_low",
                    )
                )
                for rr in [1.0, 1.5, 2.0, 3.0]:
                    params.append(
                        StrategyParams(
                            timeframe=timeframe,
                            entry_mode=entry_mode,
                            stop_loss_points=float(sl),
                            min_distance_from_ema_low=float(dist),
                            take_profit_mode="fixed_rr",
                            fixed_rr=rr,
                        )
                    )
    return params


def write_trades(path: Path, trades: list[Trade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "entry_time",
                "exit_time",
                "side",
                "entry",
                "exit",
                "stop_loss",
                "take_profit",
                "pnl_points",
                "bars_held",
                "exit_reason",
            ],
        )
        writer.writeheader()
        for t in trades:
            writer.writerow(
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "side": t.side,
                    "entry": round(t.entry, 2),
                    "exit": round(t.exit, 2),
                    "stop_loss": round(t.stop_loss, 2),
                    "take_profit": round(t.take_profit, 2),
                    "pnl_points": round(t.pnl_points, 2),
                    "bars_held": t.bars_held,
                    "exit_reason": t.exit_reason,
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--years", type=float, default=5)
    parser.add_argument("--region", choices=BASE_URLS.keys(), default="india")
    parser.add_argument("--timeframes", nargs="+", default=["1h", "2h", "4h", "1d"])
    parser.add_argument("--data-dir", default="data/backtests")
    parser.add_argument("--output-dir", default="reports/backtests")
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []
    best_overall: tuple[dict, list[Trade]] | None = None

    for timeframe in args.timeframes:
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        if args.no_fetch:
            csv_path = data_dir / f"{args.symbol}_{timeframe}_{args.years:g}y.csv"
            df = pd.read_csv(csv_path, parse_dates=["datetime"])
        else:
            df = fetch_delta_candles(args.symbol, timeframe, args.years, args.region, data_dir, args.force_fetch)

        for params in build_param_grid(timeframe):
            trades = backtest(df, params)
            row = summarize(params, trades)
            all_results.append(row)
            if (
                row["trades"] >= 10
                and (best_overall is None or row["net_points"] > best_overall[0]["net_points"])
            ):
                best_overall = (row, trades)

    result_df = pd.DataFrame(all_results)
    result_df = result_df.sort_values(
        ["net_points", "profit_factor", "max_drawdown_points"],
        ascending=[False, False, False],
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_path = output_dir / f"optimization_results_{args.symbol}_{args.years:g}y_{timestamp}.csv"
    result_df.to_csv(results_path, index=False)

    print(f"Saved optimization report: {results_path}")
    print()
    print("Top 20 parameter sets:")
    print(result_df.head(20).to_string(index=False))

    if best_overall:
        best_row, best_trades = best_overall
        trades_path = output_dir / f"best_trades_{args.symbol}_{args.years:g}y_{timestamp}.csv"
        write_trades(trades_path, best_trades)
        print()
        print(f"Saved best-trade ledger: {trades_path}")
        print("Best setting:")
        print(best_row)


if __name__ == "__main__":
    main()
