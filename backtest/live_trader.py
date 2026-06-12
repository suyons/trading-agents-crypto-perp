#!/usr/bin/env python3
"""
Coded-strategy live trader. Called each cycle by the orchestrator cron.

Generates signals from deterministic coded strategies (no LLM), sizes
positions at 2% risk per trade, places stop+TP atomically, logs, and commits.

Strategy assignments (5-yr Binance backtest, both IS+OOS Sharpe > 1):
  BTCUSDT → ema_cross  (IS 0.95 / OOS 1.80, 1823 OOS trades)
  ETHUSDT → donchian   (IS 1.82 / OOS 1.61, 1982 OOS trades)
  SOLUSDT → donchian   (IS 2.10 / OOS 1.57, 1763 OOS trades)
  XRPUSDT → donchian   (IS 1.34 / OOS 1.33, 2037 OOS trades)

rsi_mr failed on all 4 symbols over 5 years (OOS Sharpe negative).
Symbols use Binance format (BTCUSDT etc.).
"""
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backtest.strategies import REGISTRY

# ── Config ────────────────────────────────────────────────────────────────────

STRATEGY_MAP = {
    "BTCUSDT": "ema_cross",
    "ETHUSDT": "donchian",
    "SOLUSDT": "donchian",
    "XRPUSDT": "donchian",
}

RISK_PCT    = 0.02
MIN_RR      = 1.9   # reject if R:R at actual fill < this (allows small slippage vs 2.0)
WARMUP_BARS = 220   # bars needed to stabilise 200-period EMA

# Minimum tradeable qty per symbol (coin units)
MIN_QTY      = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 0.1, "XRPUSDT": 1.0}
QTY_DECIMALS = {"BTCUSDT": 3,     "ETHUSDT": 2,    "SOLUSDT": 1,   "XRPUSDT": 0}


# ── Adapter helper ────────────────────────────────────────────────────────────

def adp(*args):
    r = subprocess.run(
        ["python3", os.path.join(ROOT, "exchanges/binance/adapter.py")] + [str(a) for a in args],
        capture_output=True, text=True, cwd=ROOT, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"adapter {args[0]}: {r.stderr.strip()}")
    return json.loads(r.stdout)


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_completed_bars(symbol: str, count: int = 300) -> pd.DataFrame:
    """Fetch `count` completed 15m bars (drops in-progress last bar)."""
    bars = adp("klines", symbol, "15m", str(count + 1))
    now_ms = int(time.time() * 1000)
    # Drop in-progress bar (closeTime still in the future)
    if bars and bars[-1]["closeTime"] > now_ms:
        bars = bars[:-1]
    bars = bars[-count:]  # keep newest `count`
    df = pd.DataFrame(bars)
    df["ts"] = pd.to_datetime(df["openTime"], unit="ms", utc=True)
    return df.set_index("ts")[["open", "high", "low", "close", "volume"]]


def last_signal(df: pd.DataFrame, strat_name: str):
    """Return (signal, stop, tp) on the last completed bar, or (0, None, None)."""
    if len(df) < WARMUP_BARS:
        return 0, None, None
    strat_fn = REGISTRY[strat_name]
    sigs = strat_fn(df)
    row = sigs.iloc[-1]
    sig = int(row["signal"])
    if sig == 0 or not (np.isfinite(row["stop"]) and np.isfinite(row["tp"])):
        return 0, None, None
    return sig, float(row["stop"]), float(row["tp"])


# ── State helpers ─────────────────────────────────────────────────────────────

def read_stops() -> dict:
    """Return {symbol: stop_price} from TRADE_STATE.md."""
    path = os.path.join(ROOT, "state/TRADE_STATE.md")
    stops, sym = {}, None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("- symbol:"):
                    sym = line.split(":", 1)[1].strip()
                elif line.startswith("stop:") and sym:
                    try:
                        stops[sym] = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return stops


def read_floor() -> float:
    path = os.path.join(ROOT, "state/TRADE_STATE.md")
    try:
        with open(path) as f:
            for line in f:
                if line.strip().startswith("breaker_floor_usdt:"):
                    return float(line.split(":")[1].strip().split()[0])
    except FileNotFoundError:
        pass
    return 900.0


def write_state(balance: float, equity: float, positions: list, floor: float, stops: dict = None):
    from backtest.fetch import fetch_all  # just for the import guard
    path = os.path.join(ROOT, "state/TRADE_STATE.md")
    baseline = equity if equity > floor / 0.9 else floor / 0.9
    stops = stops or {}
    pos_yaml = "  []\n" if not positions else "".join(
        f"  - symbol: {p['symbol']}\n    size: {p['positionAmt']}\n"
        f"    entry: {p['entryPrice']}\n    mark: {p['markPrice']}\n"
        f"    upnl: {p.get('unrealisedPnl', 0)}\n"
        + (f"    stop: {stops[p['symbol']]}\n" if p['symbol'] in stops else "")
        for p in positions
    )
    content = (
        f"starting_balance_usdt: 1000.00\n"
        f"breaker_baseline_usdt: {max(equity, 1000.0):.2f}\n"
        f"breaker_floor_usdt: {floor:.2f}\n"
        f"equity_usdt: {equity:.2f}\n"
        f"positions:\n{pos_yaml}"
    )
    with open(path, "w") as f:
        f.write(content)


# ── Sizing ────────────────────────────────────────────────────────────────────

def size_qty(symbol: str, equity: float, entry: float, stop: float) -> float:
    """Return coin qty so that risk = RISK_PCT × equity. Returns 0 if below min."""
    risk_usd = equity * RISK_PCT
    stop_dist = abs(entry - stop)
    if stop_dist <= 0:
        return 0.0
    qty = risk_usd / stop_dist
    dec = QTY_DECIMALS.get(symbol, 2)
    qty = math.floor(qty * 10**dec) / 10**dec  # round DOWN to stay within risk
    return qty if qty >= MIN_QTY.get(symbol, 0.001) else 0.0


# ── Logging ───────────────────────────────────────────────────────────────────

def append_log(entry: str):
    path = os.path.join(ROOT, "state/TRADE_LOG.md")
    with open(path, "a") as f:
        f.write(entry + "\n\n---\n")
    subprocess.run(["git", "add", "state/TRADE_LOG.md"], cwd=ROOT, capture_output=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    subprocess.run(
        ["git", "commit", "-m", f"trade log: {ts} coded-strategy cycle"],
        cwd=ROOT, capture_output=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"  CODED STRATEGY CYCLE  {ts}")
    print(f"{'='*60}")

    # Exchange state
    balance  = float(adp("balance")[0]["balance"])
    raw_pos  = adp("positions")
    upnl     = sum(float(p.get("unrealisedPnl", 0)) for p in raw_pos)
    equity   = balance + upnl
    floor    = read_floor()
    stops    = read_stops()  # {symbol: stop_price} from last write_state

    open_by_sym = {p["symbol"]: p for p in raw_pos}
    print(f"  Balance ${balance:.2f}  uPnL ${upnl:+.2f}  Equity ${equity:.2f}  Floor ${floor:.2f}")

    decisions = []

    # Soft-stop check: close any position that has breached its stored stop price
    for sym, pos in list(open_by_sym.items()):
        if sym not in stops:
            continue
        stop_px  = stops[sym]
        mark_px  = float(pos["markPrice"])
        amt      = float(pos["positionAmt"])
        breached = (amt > 0 and mark_px <= stop_px) or (amt < 0 and mark_px >= stop_px)
        if breached:
            print(f"\n  [{sym}] SOFT-STOP triggered: mark {mark_px} vs stop {stop_px} — closing")
            try:
                adp("close", sym)
                adp("cancel", sym)  # cancel orphaned TP limit order
                decisions.append(f"STOP {sym} mark={mark_px} stop={stop_px}")
                del open_by_sym[sym]
            except Exception as e:
                print(f"    close failed: {e}")
                decisions.append(f"STOP FAILED {sym}: {e}")

    # Refresh equity after any stop closes
    if any(d.startswith("STOP ") for d in decisions):
        raw_pos  = adp("positions")
        balance  = float(adp("balance")[0]["balance"])
        upnl     = sum(float(p.get("unrealisedPnl", 0)) for p in raw_pos)
        equity   = balance + upnl
        open_by_sym = {p["symbol"]: p for p in raw_pos}

    # Floor breach — no new entries
    if equity <= floor:
        msg = f"FLOOR BREACH equity ${equity:.2f} ≤ floor ${floor:.2f} — no new entries"
        print(f"  ⚠  {msg}")
        decisions.append(msg)
    else:
        for symbol, strat_name in STRATEGY_MAP.items():
            print(f"\n  [{symbol}]")

            # Already in a position — TP limit (exchange) or soft-stop (next cycle) handles exit
            if symbol in open_by_sym:
                p = open_by_sym[symbol]
                stop_px = stops.get(symbol, "?")
                print(f"    HOLD — position open: size={p['positionAmt']} "
                      f"mark={p['markPrice']} stop={stop_px} uPnL={p.get('unrealisedPnl', '?')}")
                decisions.append(f"HOLD {symbol} (open position)")
                continue

            # Fetch data and generate signal
            try:
                df = fetch_completed_bars(symbol, count=300)
            except Exception as e:
                print(f"    DATA ERROR: {e}")
                decisions.append(f"HOLD {symbol} (data error: {e})")
                continue

            sig, stop, tp = last_signal(df, strat_name)

            if sig == 0:
                print(f"    HOLD — no signal from {strat_name}")
                decisions.append(f"HOLD {symbol} (no signal)")
                continue

            side = "BUY" if sig == 1 else "SELL"
            snap = adp("snapshot", symbol)
            entry = float(snap["price"])  # market entry price

            # Verify R:R at actual fill price
            risk   = (entry - stop) if sig == 1 else (stop - entry)
            reward = (tp - entry)   if sig == 1 else (entry - tp)

            if risk <= 0 or reward / risk < MIN_RR:
                rr = reward / risk if risk > 0 else 0
                print(f"    SKIP — R:R {rr:.2f} at market {entry:.4g} (need {MIN_RR})")
                decisions.append(f"HOLD {symbol} (R:R {rr:.2f} < {MIN_RR})")
                continue

            # Size
            qty = size_qty(symbol, equity, entry, stop)
            if qty <= 0:
                print(f"    SKIP — qty rounds to 0 or below minimum")
                decisions.append(f"HOLD {symbol} (qty too small)")
                continue

            # Floor math: if this trade stops out, stay above floor
            this_risk_usd = abs(entry - stop) * qty
            existing_risk = sum(
                abs(float(p["positionAmt"])) * abs(float(p["markPrice"]) - float(p.get("entryPrice", p["markPrice"]))) * 0.5
                for p in raw_pos
            )
            if equity - this_risk_usd < floor:
                print(f"    SKIP — floor math: equity ${equity:.2f} - risk ${this_risk_usd:.2f} < floor ${floor:.2f}")
                decisions.append(f"HOLD {symbol} (floor math fails)")
                continue

            rr = reward / risk
            print(f"    ENTER {side}  qty={qty}  entry≈{entry:.5g}  "
                  f"stop={stop:.5g}  tp={tp:.5g}  R:R={rr:.2f}")

            try:
                result = adp("order", symbol, side, str(qty),
                             "--stop", f"{stop:.6g}", "--tp", f"{tp:.6g}")
                # Persist the stop price so the soft-stop check can use it next cycle
                if "stop_price" in result:
                    stops[symbol] = result["stop_price"]
                print(f"    → {result}")
                decisions.append(
                    f"ENTER {symbol} {side} qty={qty} entry≈{entry:.5g} "
                    f"stop={stop:.5g} tp={tp:.5g} R:R={rr:.2f}"
                )
            except Exception as e:
                print(f"    → ORDER FAILED: {e}")
                decisions.append(f"ENTER FAILED {symbol}: {e}")

    # Re-query positions after any orders
    raw_pos2 = adp("positions")
    balance2 = float(adp("balance")[0]["balance"])
    upnl2    = sum(float(p.get("unrealisedPnl", 0)) for p in raw_pos2)
    equity2  = balance2 + upnl2

    # Only keep stops for symbols that still have open positions
    open_syms2  = {p["symbol"] for p in raw_pos2}
    stops_live  = {s: v for s, v in stops.items() if s in open_syms2}
    write_state(balance2, equity2, raw_pos2, floor, stops=stops_live)

    # Log entry
    pos_summary = (
        "FLAT" if not raw_pos2
        else ", ".join(
            f"{p['symbol']} {'LONG' if float(p['positionAmt']) > 0 else 'SHORT'} "
            f"{abs(float(p['positionAmt']))} @ {p['entryPrice']} "
            f"stop={stops_live.get(p['symbol'],'?')} uPnL={p.get('unrealisedPnl','?')}"
            for p in raw_pos2
        )
    )

    log = (
        f"## {ts} — gate live (testnet) — CODED STRATEGY\n"
        f"- Strategies: {', '.join(f'{s}→{v}' for s, v in STRATEGY_MAP.items())}\n"
        f"- Decisions: {' | '.join(decisions)}\n"
        f"- Equity: ${equity2:.2f} (balance ${balance2:.2f}, uPnL ${upnl2:+.2f}), "
        f"floor ${floor:.2f}\n"
        f"- Positions: {pos_summary}"
    )
    append_log(log)

    print(f"\n  Summary: {' | '.join(decisions)}")
    print(f"  Equity: ${equity2:.2f}  Positions: {pos_summary}")


if __name__ == "__main__":
    main()
