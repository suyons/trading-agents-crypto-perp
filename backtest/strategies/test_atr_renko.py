"""Self-check for the atr_renko strategy. Run: python3 backtest/strategies/test_atr_renko.py"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backtest.strategies.atr_renko import atr_renko


def _df(closes):
    """Build an OHLCV frame from a close path (high/low padded so ATR is stable)."""
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.ones_like(closes),
        },
        index=pd.date_range("2024-01-01", periods=len(closes), freq="15min", tz="UTC"),
    )


def test_flip_emits_signal_with_valid_levels():
    # Trend up to ~150, then reverse down to ~50: a down-flip must fire.
    up = list(range(100, 151))
    down = list(range(150, 49, -1))
    sigs = atr_renko(_df(up + down), atr_period=14, atr_mult=2.0)

    flips = sigs[sigs["signal"] != 0]
    assert len(flips) > 0, "a sustained reversal must produce at least one flip signal"

    # At least one SELL flip in the down leg, with a stop above price and tp below (RR≈2:1).
    sells = flips[flips["signal"] == -1]
    assert len(sells) > 0, "down leg must yield a short flip"
    row = sells.iloc[0]
    assert np.isfinite(row["stop"]) and np.isfinite(row["tp"])
    assert row["stop"] > row["tp"], "short: stop above tp"
    bar_close = _df(up + down)["close"].loc[sells.index[0]]
    risk = row["stop"] - bar_close
    reward = bar_close - row["tp"]
    assert abs(reward / risk - 2.0) < 1e-6, "TP must be 2:1 vs stop"


def test_flat_market_no_signal():
    flat = atr_renko(_df([100.0] * 80))
    assert (flat["signal"] == 0).all(), "no price movement → no bricks → no signals"


if __name__ == "__main__":
    test_flip_emits_signal_with_valid_levels()
    test_flat_market_no_signal()
    print("atr_renko self-check: PASS")
