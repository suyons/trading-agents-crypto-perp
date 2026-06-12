"""RSI mean-reversion with 200 EMA trend filter and ATR-based stop/TP."""
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def rsi_mr(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: int = 30,
    overbought: int = 70,
    trend_ema: int = 200,
    atr_mult: float = 1.5,
) -> pd.DataFrame:
    """
    Signal: RSI crosses out of oversold/overbought zone, only with the trend.
    Stop:   atr_mult × ATR from signal-bar close.
    TP:     2:1 R:R.
    """
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(span=rsi_period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=rsi_period, adjust=False).mean()
    rs = gain / loss.replace(0.0, np.nan)
    rsi = 100 - 100 / (1 + rs)

    ema_t = close.ewm(span=trend_ema, adjust=False).mean()
    atr = _atr(df)

    # RSI rises back above oversold threshold → long bounce
    rsi_cross_up = (rsi >= oversold) & (rsi.shift(fill_value=100.0) < oversold)
    # RSI falls back below overbought threshold → short fade
    rsi_cross_dn = (rsi <= overbought) & (rsi.shift(fill_value=0.0) > overbought)

    long_sig = rsi_cross_up & (close > ema_t)
    short_sig = rsi_cross_dn & (close < ema_t)

    dist = atr_mult * atr

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
