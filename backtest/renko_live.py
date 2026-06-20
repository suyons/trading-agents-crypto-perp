#!/usr/bin/env python3
"""
Real-time ATR-Renko runner — second-by-second REST polling, EXCLUSIVE to the
atr_renko strategy.

The hourly `live_trader.py` works on completed 15m bars; that cadence is wrong
for Renko, which reacts to live price. This runner ports the retired Gate bot's
behaviour to the new repo:

  * poll each symbol's price once a second via the exchange-agnostic adapter
  * feed ticks into an ATR-sized Renko brick builder
  * on a brick DIRECTION REVERSAL → close any opposite position and open the new
    side, with stop + take-profit placed atomically
  * gate every reversal through the same risk rules as live_trader (2% risk,
    R:R ≥ MIN_RR, drawdown floor) and the optional LLM reversal filter

Exchange comes from `exchanges/EXCHANGE_CONFIG.md` (not hard-coded), so this runs
on whatever adapter is active. Symbols come from the env var RENKO_SYMBOLS
(comma-separated); empty → nothing to do. Those symbols must NOT also appear in
live_trader's STRATEGY_MAP, or both would trade them.

    RENKO_SYMBOLS=XRPUSDT FILTER_AGENT_CMD="claude -p" python3 backtest/renko_live.py
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backtest import signal_filter
from backtest.strategies.atr_renko import _atr
from backtest.live_trader import size_qty, read_floor, append_log, RISK_PCT, MIN_RR

# ── Config ────────────────────────────────────────────────────────────────────

POLL_SECS    = 1       # second-by-second polling (the whole point of this runner)
ATR_PERIOD   = 14
ATR_MULT     = 2.0     # stop distance = ATR_MULT × brick; TP = 2:1
BRICK_TF     = "15m"   # timeframe whose ATR sizes the brick
BRICK_BARS   = 100     # bars fetched to seed/refresh the brick size
REFRESH_SECS = 3600    # recompute brick size from fresh ATR this often


def _symbols() -> list[str]:
    raw = os.environ.get("RENKO_SYMBOLS", "").strip()
    return [s.strip() for s in raw.split(",") if s.strip()]


def _active_exchange() -> str:
    """Read `exchange:` from EXCHANGE_CONFIG.md so the adapter stays swappable."""
    path = os.path.join(ROOT, "exchanges/EXCHANGE_CONFIG.md")
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line.startswith("exchange:"):
                return line.split(":", 1)[1].strip()
    raise RuntimeError("no `exchange:` in EXCHANGE_CONFIG.md")


ADAPTER = os.path.join(ROOT, "exchanges", _active_exchange(), "adapter.py")


def adp(*args):
    r = subprocess.run(
        ["python3", ADAPTER] + [str(a) for a in args],
        capture_output=True, text=True, cwd=ROOT, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"adapter {args[0]}: {r.stderr.strip()}")
    return json.loads(r.stdout)


# ── Tick-driven Renko ─────────────────────────────────────────────────────────

class RenkoTracker:
    """Builds Renko bricks one price tick at a time. `update` returns +1/-1 only
    on a brick that REVERSES the prior direction (the trade trigger), else 0."""

    def __init__(self, brick_size: float):
        self.brick_size = brick_size
        self.last_close: float | None = None
        self.last_dir = 0  # +1 up, -1 down, 0 = none yet
        self.bricks: list[dict] = []

    def update(self, price: float) -> int:
        bs = self.brick_size
        if bs <= 0:
            return 0
        if self.last_close is None:
            self.last_close = round(price / bs) * bs
            return 0

        diff = price - self.last_close
        if diff == 0:
            return 0

        direction = 1 if diff > 0 else -1
        threshold = bs if self.last_dir in (0, direction) else 2 * bs
        if abs(diff) < threshold:
            return 0

        flipped = self.last_dir != 0 and direction != self.last_dir

        remaining = abs(diff) - threshold
        extra = int(remaining // bs) if remaining >= 0 else 0
        open_level = self.last_close
        self.last_close += direction * (threshold + extra * bs)
        self.last_dir = direction
        self.bricks.append(
            {"open": open_level, "close": self.last_close, "direction": direction}
        )
        self.bricks = self.bricks[-50:]

        return direction if flipped else 0


def brick_size_from_atr(symbol: str) -> float:
    bars = adp("klines", symbol, BRICK_TF, str(BRICK_BARS))
    df = pd.DataFrame(bars)[["high", "low", "close"]].astype(float)
    return float(_atr(df, ATR_PERIOD).iloc[-1])


# ── Execution ─────────────────────────────────────────────────────────────────

def position_for(symbol: str):
    """Return (side, amt) for the open position, or (None, 0.0)."""
    for p in adp("positions"):
        if p["symbol"] == symbol and float(p["positionAmt"]) != 0:
            amt = float(p["positionAmt"])
            return ("BUY" if amt > 0 else "SELL"), amt
    return None, 0.0


def equity_and_floor() -> tuple[float, float]:
    balance = float(adp("balance")[0]["balance"])
    upnl = sum(float(p.get("unrealisedPnl", 0)) for p in adp("positions"))
    return balance + upnl, read_floor()


def handle_reversal(symbol: str, tracker: RenkoTracker, direction: int):
    """A brick just reversed. Apply risk rules + filter, then reverse position."""
    side = "BUY" if direction == 1 else "SELL"
    held_side, _ = position_for(symbol)
    if held_side == side:
        print(f"    {symbol}: already {side} — ignore reversal")
        return

    equity, floor = equity_and_floor()
    if equity <= floor:
        print(f"    {symbol}: FLOOR BREACH equity ${equity:.2f} ≤ ${floor:.2f} — no entry")
        return

    entry = float(adp("price", symbol)["price"])
    dist = ATR_MULT * tracker.brick_size
    stop = entry - direction * dist
    tp = entry + direction * 2.0 * dist

    risk = (entry - stop) if direction == 1 else (stop - entry)
    reward = (tp - entry) if direction == 1 else (entry - tp)
    if risk <= 0 or reward / risk < MIN_RR:
        print(f"    {symbol}: SKIP R:R {reward / risk if risk > 0 else 0:.2f} < {MIN_RR}")
        return

    qty = size_qty(symbol, equity, entry, stop)
    if qty <= 0:
        print(f"    {symbol}: SKIP qty below minimum")
        return
    if equity - abs(entry - stop) * qty < floor:
        print(f"    {symbol}: SKIP floor math (risk would breach floor)")
        return

    if signal_filter.is_enabled():
        sym_upnl = next(
            (float(p.get("unrealisedPnl", 0)) for p in adp("positions") if p["symbol"] == symbol),
            0.0,
        )
        if signal_filter.should_skip(
            symbol, side, entry, stop, tp, equity, sym_upnl, tracker.bricks[-6:]
        ):
            print(f"    {symbol}: FILTERED — reversal vetoed as likely chop")
            _log(symbol, f"FILTERED reversal {side} (chop veto)")
            return

    # Reverse: close the opposite position (if any) before opening the new side.
    if held_side and held_side != side:
        adp("close", symbol)
        adp("cancel", symbol)  # clear the old stop/TP orders

    rr = reward / risk
    print(f"    {symbol}: ENTER {side} qty={qty} entry≈{entry:.6g} "
          f"stop={stop:.6g} tp={tp:.6g} R:R={rr:.2f}")
    try:
        result = adp("order", symbol, side, str(qty),
                     "--stop", f"{stop:.6g}", "--tp", f"{tp:.6g}")
        print(f"      → {result}")
        _log(symbol, f"ENTER {side} qty={qty} entry≈{entry:.6g} "
                     f"stop={stop:.6g} tp={tp:.6g} R:R={rr:.2f}")
    except Exception as e:
        print(f"      → ORDER FAILED: {e}")
        _log(symbol, f"ORDER FAILED {side}: {e}")


def _log(symbol: str, detail: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    append_log(f"## {ts} — renko-live — {symbol}\n- {detail}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    symbols = _symbols()
    if not symbols:
        print("RENKO_SYMBOLS is empty — set it (comma-separated) and ensure those "
              "symbols are NOT in live_trader's STRATEGY_MAP. Nothing to do.")
        return

    print(f"renko-live: exchange={_active_exchange()} symbols={symbols} "
          f"poll={POLL_SECS}s filter={'on' if signal_filter.is_enabled() else 'off'}")

    trackers = {s: RenkoTracker(brick_size_from_atr(s)) for s in symbols}
    for s, t in trackers.items():
        print(f"  {s}: brick_size={t.brick_size:.6g}")
    last_refresh = time.time()

    while True:
        for symbol, tracker in trackers.items():
            try:
                price = float(adp("price", symbol)["price"])
                if tracker.update(price):
                    direction = tracker.last_dir
                    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {symbol} "
                          f"REVERSAL {'up' if direction == 1 else 'down'} @ {price:.6g}")
                    handle_reversal(symbol, tracker, direction)
            except Exception as e:
                print(f"  {symbol}: error {e}")

        if time.time() - last_refresh >= REFRESH_SECS:
            for symbol, tracker in trackers.items():
                try:
                    tracker.brick_size = brick_size_from_atr(symbol)
                except Exception as e:
                    print(f"  {symbol}: brick refresh failed {e}")
            last_refresh = time.time()

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
