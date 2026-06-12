"""
Walk-forward backtester.

Simulation rules (no lookahead):
  - Signal computed at close of bar i  →  entry at open of bar i+1
  - Stop and TP checked against high/low of each subsequent bar
  - If both stop and TP on the same bar, stop wins (conservative)
  - Risk per trade: risk_pct × equity at entry
  - One position at a time
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# ── Core simulator ──────────────────────────────────────────────────────────

def simulate(
    df: pd.DataFrame,
    signals_df: pd.DataFrame,
    risk_pct: float = 0.02,
    starting_equity: float = 1000.0,
) -> tuple[list[dict[str, Any]], float]:
    """
    Returns (trades, final_equity).

    trades: list of dicts with entry_time, exit_time, side, entry, exit,
            stop, tp, reason, pnl, equity_after.
    """
    equity = starting_equity
    trades: list[dict] = []
    open_trade: tuple | None = None  # (entry, stop, tp, side, entry_time, entry_eq)

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    times = df.index
    sigs = signals_df["signal"].values
    raw_stops = signals_df["stop"].values
    raw_tps = signals_df["tp"].values

    n = len(df)
    for i in range(n):
        # ── Check exit for open trade ────────────────────────────────────────
        if open_trade is not None:
            entry, stop, tp, side, entry_time, entry_eq = open_trade
            lo, hi = lows[i], highs[i]

            if side == 1:
                hit_stop = lo <= stop
                hit_tp = hi >= tp
            else:
                hit_stop = hi >= stop
                hit_tp = lo <= tp

            if hit_stop or hit_tp:
                exit_price = stop if hit_stop else tp
                reason = "stop" if hit_stop else "tp"

                raw_risk = abs(entry - stop) / entry
                size_mult = (risk_pct / raw_risk) if raw_risk > 0 else 0.0

                ret = (exit_price - entry) / entry if side == 1 else (entry - exit_price) / entry
                trade_pnl = ret * size_mult * entry_eq
                equity += trade_pnl

                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": times[i],
                        "side": side,
                        "entry": entry,
                        "exit": exit_price,
                        "stop": stop,
                        "tp": tp,
                        "reason": reason,
                        "pnl": trade_pnl,
                        "equity_after": equity,
                    }
                )
                open_trade = None

        # ── Check for new entry (signal from prior bar) ──────────────────────
        if open_trade is None and i > 0:
            sig = sigs[i - 1]
            if sig != 0 and np.isfinite(raw_stops[i - 1]) and np.isfinite(raw_tps[i - 1]):
                entry = opens[i]
                stop = raw_stops[i - 1]
                tp = raw_tps[i - 1]

                risk = (entry - stop) if sig == 1 else (stop - entry)
                reward = (tp - entry) if sig == 1 else (entry - tp)

                # Enforce 2:1 at actual fill price (not just signal-bar close)
                if risk > 0 and reward / risk >= 1.9:
                    # Check if entry bar itself sweeps the stop or TP.
                    # We enter at opens[i]; the rest of bar i can hit our levels.
                    lo_i, hi_i = lows[i], highs[i]
                    if sig == 1:
                        entry_hit_stop = lo_i <= stop
                        entry_hit_tp   = hi_i >= tp
                    else:
                        entry_hit_stop = hi_i >= stop
                        entry_hit_tp   = lo_i <= tp

                    if entry_hit_stop or entry_hit_tp:
                        # Resolve on the entry bar itself (stop beats TP, conservative)
                        exit_price = stop if entry_hit_stop else tp
                        reason = "stop" if entry_hit_stop else "tp"
                        raw_risk = risk / entry
                        size_mult = (risk_pct / raw_risk) if raw_risk > 0 else 0.0
                        ret = (exit_price - entry) / entry if sig == 1 else (entry - exit_price) / entry
                        trade_pnl = ret * size_mult * equity
                        equity += trade_pnl
                        trades.append({
                            "entry_time": times[i],
                            "exit_time":  times[i],
                            "side": int(sig),
                            "entry": entry,
                            "exit": exit_price,
                            "stop": stop,
                            "tp": tp,
                            "reason": reason,
                            "pnl": trade_pnl,
                            "equity_after": equity,
                        })
                    else:
                        open_trade = (entry, stop, tp, int(sig), times[i], equity)

    return trades, equity


# ── Performance metrics ──────────────────────────────────────────────────────

def sharpe(trades: list[dict], starting_equity: float = 1000.0) -> float:
    """Annualized Sharpe on daily equity returns."""
    if len(trades) < 5:
        return 0.0

    # Build equity curve
    sorted_trades = sorted(trades, key=lambda t: t["exit_time"])
    equity_points = [(sorted_trades[0]["entry_time"], starting_equity)]
    eq = starting_equity
    for t in sorted_trades:
        eq += t["pnl"]
        equity_points.append((t["exit_time"], eq))

    ts, vals = zip(*equity_points)
    eq_series = pd.Series(list(vals), index=pd.DatetimeIndex(list(ts)))
    daily = eq_series.resample("1D").last().ffill()
    daily_ret = daily.pct_change().dropna()

    if len(daily_ret) < 2 or daily_ret.std() == 0:
        return 0.0

    return float((daily_ret.mean() / daily_ret.std()) * np.sqrt(252))


def stats(trades: list[dict], starting_equity: float = 1000.0) -> dict:
    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
            "sharpe": 0.0,
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    eq = starting_equity
    equity_curve = [eq]
    for p in pnls:
        eq += p
        equity_curve.append(eq)
    arr = np.array(equity_curve)
    peak = np.maximum.accumulate(arr)
    max_dd = float(((arr - peak) / peak).min())

    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")

    return {
        "n_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_pnl": float(np.mean(pnls)),
        "total_pnl": float(sum(pnls)),
        "profit_factor": pf,
        "max_dd_pct": max_dd,
        "sharpe": sharpe(trades, starting_equity),
    }


# ── Walk-forward split ───────────────────────────────────────────────────────

def walk_forward_split(df: pd.DataFrame, is_frac: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split df into in-sample and out-of-sample slices by bar count."""
    n = len(df)
    split = int(n * is_frac)
    return df.iloc[:split], df.iloc[split:]
