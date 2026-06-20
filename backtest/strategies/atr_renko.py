"""ATR-Renko direction-flip strategy with ATR-based stop/TP.

Ported from the retired `trading-atr-renko-gate` bot. Renko bricks are built
from close prices using an ATR-sized brick (adaptive per bar, so it scales over
multi-year history). A signal fires on the bar where a new brick forms in the
OPPOSITE direction to the prior brick — i.e. the trend flips. The original bot's
ollama "false-signal" filter is not part of the deterministic strategy; an
optional, runtime-agnostic veto lives in `backtest/signal_filter.py` and reads
the brick context exposed here via `recent_bricks`.
"""
import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _renko_bricks(df: pd.DataFrame, atr_period: int = 14) -> list[dict]:
    """Build the Renko brick sequence from close prices with an ATR-sized brick.

    Returns one dict per bar that completed at least one brick:
    {index, open, close, atr, direction (+1/-1), flip}. `flip` marks a reversal
    of the prior brick's direction — the entry trigger.
    """
    close = df["close"].values
    atr = _atr(df, atr_period).values
    bricks: list[dict] = []

    last_level = None  # last brick close level
    last_dir = 0       # +1 up, -1 down, 0 = none yet

    for i in range(len(df)):
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

        flip = last_dir != 0 and direction != last_dir

        # Advance the brick level past every brick this move completed.
        remaining = abs(diff) - threshold
        extra_bricks = int(remaining // brick) if remaining >= 0 else 0
        open_level = last_level
        last_level += direction * (threshold + extra_bricks * brick)
        last_dir = direction

        bricks.append(
            {
                "index": i,
                "open": open_level,
                "close": last_level,
                "atr": brick,
                "direction": direction,
                "flip": flip,
            }
        )

    return bricks


def recent_bricks(df: pd.DataFrame, atr_period: int = 14, count: int = 5) -> list[dict]:
    """The last `count` Renko bricks — context for the optional signal filter."""
    return _renko_bricks(df, atr_period)[-count:]


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
    n = len(df)
    close = df["close"].values

    signals = np.zeros(n, dtype=int)
    stops = np.full(n, np.nan)
    tps = np.full(n, np.nan)

    for brick in _renko_bricks(df, atr_period):
        if not brick["flip"]:
            continue
        i = brick["index"]
        direction = brick["direction"]
        dist = atr_mult * brick["atr"]
        price = close[i]
        signals[i] = direction
        stops[i] = price - direction * dist
        tps[i] = price + direction * 2.0 * dist

    return pd.DataFrame(
        {"signal": signals, "stop": stops, "tp": tps}, index=df.index
    )
