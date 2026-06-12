"""EMA crossover with trend filter and ATR-based stop/TP."""
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def ema_cross(
    df: pd.DataFrame,
    fast: int = 9,
    slow: int = 21,
    trend: int = 50,
    atr_mult: float = 1.5,
) -> pd.DataFrame:
    """
    Signal: fast EMA crosses slow EMA in the direction of the trend EMA.
    Stop:   atr_mult × ATR from signal-bar close.
    TP:     2:1 R:R from signal-bar close.

    Returns DataFrame[signal, stop, tp] aligned to df.index.
    """
    close = df["close"]
    atr = _atr(df)

    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    ema_t = close.ewm(span=trend, adjust=False).mean()

    diff = ema_f - ema_s
    # Crossover: sign change on diff
    cross_up = (diff > 0) & (diff.shift(fill_value=0.0) <= 0)
    cross_dn = (diff < 0) & (diff.shift(fill_value=0.0) >= 0)

    long_sig = cross_up & (close > ema_t)
    short_sig = cross_dn & (close < ema_t)

    dist = atr_mult * atr  # stop distance from close

    signals = pd.Series(0, index=df.index)
    stops = pd.Series(np.nan, index=df.index)
    tps = pd.Series(np.nan, index=df.index)

    signals[long_sig] = 1
    stops[long_sig] = close[long_sig] - dist[long_sig]
    tps[long_sig] = close[long_sig] + 2.0 * dist[long_sig]

    signals[short_sig] = -1
    stops[short_sig] = close[short_sig] + dist[short_sig]
    tps[short_sig] = close[short_sig] - 2.0 * dist[short_sig]

    return pd.DataFrame({"signal": signals, "stop": stops, "tp": tps})
