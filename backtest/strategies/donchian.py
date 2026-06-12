"""Donchian channel breakout with ATR-based stop/TP."""
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def donchian_breakout(
    df: pd.DataFrame,
    period: int = 20,
    atr_mult: float = 2.0,
) -> pd.DataFrame:
    """
    Signal: close breaks above N-bar rolling high (long) or below N-bar rolling low (short).
    Only the FIRST bar of a new breakout triggers (state-change, not continuous).
    Stop:   atr_mult × ATR from signal-bar close.
    TP:     2:1 R:R.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    atr = _atr(df)

    # Use .shift() so current bar is excluded from the rolling window (no lookahead)
    roll_high = high.shift(1).rolling(period).max()
    roll_low = low.shift(1).rolling(period).min()

    above_high = close > roll_high
    below_low = close < roll_low

    # Only first bar of each breakout (state change)
    new_break_up = above_high & ~above_high.shift(fill_value=False)
    new_break_dn = below_low & ~below_low.shift(fill_value=False)

    dist = atr_mult * atr

    signals = pd.Series(0, index=df.index)
    stops = pd.Series(np.nan, index=df.index)
    tps = pd.Series(np.nan, index=df.index)

    signals[new_break_up] = 1
    stops[new_break_up] = close[new_break_up] - dist[new_break_up]
    tps[new_break_up] = close[new_break_up] + 2.0 * dist[new_break_up]

    signals[new_break_dn] = -1
    stops[new_break_dn] = close[new_break_dn] + dist[new_break_dn]
    tps[new_break_dn] = close[new_break_dn] - 2.0 * dist[new_break_dn]

    return pd.DataFrame({"signal": signals, "stop": stops, "tp": tps})
