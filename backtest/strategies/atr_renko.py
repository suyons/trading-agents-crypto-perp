"""ATR-Renko direction-flip strategy with ATR-based stop/TP.

Ported from the retired `trading-atr-renko-gate` bot. Renko bricks are built
from close prices using an ATR-sized brick (adaptive per bar, so it scales over
multi-year history). A signal fires on the bar where a new brick forms in the
OPPOSITE direction to the prior brick — i.e. the trend flips. The original bot's
ollama "false-signal" filter is intentionally dropped: judgement now lives in
the Claude Code orchestration layer, not inside the deterministic strategy.
"""
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def atr_renko(
    df: pd.DataFrame,
    atr_period: int = 14,
    atr_mult: float = 2.0,
) -> pd.DataFrame:
    """
    Signal: a new Renko brick forms reversing the previous brick's direction.
            Brick size = ATR at the forming bar (reversal needs 2× brick).
    Stop:   atr_mult × ATR from the signal-bar close.
    TP:     2:1 R:R.

    Returns DataFrame[signal, stop, tp] aligned to df.index.
    """
    close = df["close"].values
    atr = _atr(df, atr_period).values
    n = len(df)

    signals = np.zeros(n, dtype=int)
    stops = np.full(n, np.nan)
    tps = np.full(n, np.nan)

    last_level = None  # last brick close level
    last_dir = 0       # +1 up, -1 down, 0 = none yet

    for i in range(n):
        brick = atr[i]
        if not np.isfinite(brick) or brick <= 0:
            continue

        price = close[i]
        if last_level is None:
            last_level = round(price / brick) * brick
            continue

        diff = price - last_level
        if diff == 0:
            continue

        direction = 1 if diff > 0 else -1
        # A reversal must clear two bricks before the first new brick forms.
        threshold = brick if last_dir in (0, direction) else 2 * brick

        if abs(diff) < threshold:
            continue

        flipped = last_dir != 0 and direction != last_dir

        # Advance the brick level past every brick this move completed.
        remaining = abs(diff) - threshold
        extra_bricks = int(remaining // brick) if remaining >= 0 else 0
        last_level += direction * (threshold + extra_bricks * brick)
        last_dir = direction

        if flipped:
            dist = atr_mult * brick
            signals[i] = direction
            stops[i] = price - direction * dist
            tps[i] = price + direction * 2.0 * dist

    idx = df.index
    return pd.DataFrame(
        {"signal": signals, "stop": stops, "tp": tps}, index=idx
    )
