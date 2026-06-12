#!/usr/bin/env python3
"""
Backtest pipeline — fetch data, run strategies, gate deployment.

Usage:
  python3 backtest/run.py fetch [--symbols BTC_USDT ETH_USDT SOL_USDT XRP_USDT]
  python3 backtest/run.py backtest [--strategy ema_cross|rsi_mr|donchian|all]
                                   [--symbols ...] [--show-trades]
  python3 backtest/run.py gate    [--strategy ema_cross|rsi_mr|donchian|all]
                                   [--symbols ...]

Deployment gate: OOS Sharpe > 1.0 required to print DEPLOYABLE.
"""
import argparse
import sys
import os

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backtest.fetch import fetch_all
from backtest.engine import simulate, stats, walk_forward_split
from backtest.strategies import REGISTRY

SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT"]
SHARPE_THRESHOLD = 1.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(s: dict, label: str) -> str:
    return (
        f"  {label}: "
        f"n={s['n_trades']}  "
        f"win={s['win_rate']:.0%}  "
        f"pnl=${s['total_pnl']:+.2f}  "
        f"pf={s['profit_factor']:.2f}  "
        f"maxDD={s['max_dd_pct']:.1%}  "
        f"Sharpe={s['sharpe']:.3f}"
    )


def run_one(symbol: str, strat_name: str, df_full, show_trades: bool = False) -> dict:
    """Run a single strategy/symbol combination, return OOS stats."""
    df_is, df_oos = walk_forward_split(df_full, is_frac=0.70)
    strat_fn = REGISTRY[strat_name]

    # Compute signals on the FULL series so OOS indicators are warmed up with IS history.
    # Then slice — no IS data is used during OOS simulation, only during signal generation.
    sig_full = strat_fn(df_full)
    sig_is   = sig_full.iloc[:len(df_is)].reset_index(drop=True)
    sig_oos  = sig_full.iloc[len(df_is):].reset_index(drop=True)

    df_is_r  = df_is.reset_index(drop=True)
    df_oos_r = df_oos.reset_index(drop=True)
    # Re-attach timestamps as integer index but keep times array correct in engine
    df_is_r.index  = df_is.index
    df_oos_r.index = df_oos.index
    sig_is.index   = df_is.index
    sig_oos.index  = df_oos.index

    trades_is, _ = simulate(df_is_r, sig_is)
    s_is = stats(trades_is)

    trades_oos, _ = simulate(df_oos_r, sig_oos)
    s_oos = stats(trades_oos)

    print(f"\n{'─'*60}")
    print(f"  {symbol}  ·  {strat_name}")
    print(f"  IS  ({len(df_is)} bars, {df_is.index[0].date()} → {df_is.index[-1].date()})")
    print(_fmt(s_is, "IS "))
    print(f"  OOS ({len(df_oos)} bars, {df_oos.index[0].date()} → {df_oos.index[-1].date()})")
    print(_fmt(s_oos, "OOS"))

    if show_trades and trades_oos:
        print("\n  OOS trades:")
        for t in trades_oos:
            side = "L" if t["side"] == 1 else "S"
            print(
                f"    {t['entry_time'].strftime('%m-%d %H:%M')} {side} "
                f"entry={t['entry']:.4g} exit={t['exit']:.4g} "
                f"({t['reason']}) pnl=${t['pnl']:+.2f}"
            )

    return s_oos


# ── Subcommands ──────────────────────────────────────────────────────────────

def cmd_fetch(args):
    for sym in args.symbols:
        fetch_all(sym, interval="15m", max_age_secs=0)  # force refresh


def cmd_backtest(args):
    strats = list(REGISTRY.keys()) if args.strategy == "all" else [args.strategy]
    for sym in args.symbols:
        df = fetch_all(sym)
        for strat in strats:
            run_one(sym, strat, df, show_trades=args.show_trades)


def cmd_gate(args):
    """
    Deployment gate: print DEPLOYABLE if OOS Sharpe > threshold for any combo.
    Caller decides whether to start the cron.
    """
    strats = list(REGISTRY.keys()) if args.strategy == "all" else [args.strategy]
    results = []

    for sym in args.symbols:
        df = fetch_all(sym)
        for strat in strats:
            s_oos = run_one(sym, strat, df)
            results.append((sym, strat, s_oos))

    print(f"\n{'═'*60}")
    print(f"  GATE CHECK  (threshold: OOS Sharpe > {SHARPE_THRESHOLD})")
    print(f"{'═'*60}")
    passed = [(sym, strat, s) for sym, strat, s in results if s["sharpe"] > SHARPE_THRESHOLD]
    failed = [(sym, strat, s) for sym, strat, s in results if s["sharpe"] <= SHARPE_THRESHOLD]

    if passed:
        print(f"\n  ✓ DEPLOYABLE ({len(passed)} combo(s) passed):")
        for sym, strat, s in sorted(passed, key=lambda x: -x[2]["sharpe"]):
            print(f"    {sym} / {strat}  OOS Sharpe={s['sharpe']:.3f}  "
                  f"n={s['n_trades']}  win={s['win_rate']:.0%}  pnl=${s['total_pnl']:+.2f}")
    else:
        print(f"\n  ✗ NOT DEPLOYABLE — no combo cleared Sharpe > {SHARPE_THRESHOLD}")

    if failed:
        print(f"\n  Failed ({len(failed)} combo(s)):")
        for sym, strat, s in sorted(failed, key=lambda x: -x[2]["sharpe"]):
            print(f"    {sym} / {strat}  OOS Sharpe={s['sharpe']:.3f}  n={s['n_trades']}")

    print()
    if not passed:
        sys.exit(1)  # non-zero exit → caller can gate deployment in scripts


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backtest pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # fetch
    p_fetch = sub.add_parser("fetch", help="Download and cache OHLCV data")
    p_fetch.add_argument("--symbols", nargs="+", default=SYMBOLS)

    # backtest
    p_bt = sub.add_parser("backtest", help="Run IS/OOS backtest")
    p_bt.add_argument("--strategy", default="all",
                      choices=list(REGISTRY.keys()) + ["all"])
    p_bt.add_argument("--symbols", nargs="+", default=SYMBOLS)
    p_bt.add_argument("--show-trades", action="store_true")

    # gate
    p_gate = sub.add_parser("gate", help="Check deployment gate (OOS Sharpe > 1)")
    p_gate.add_argument("--strategy", default="all",
                        choices=list(REGISTRY.keys()) + ["all"])
    p_gate.add_argument("--symbols", nargs="+", default=SYMBOLS)

    args = parser.parse_args()
    {"fetch": cmd_fetch, "backtest": cmd_backtest, "gate": cmd_gate}[args.cmd](args)


if __name__ == "__main__":
    main()
