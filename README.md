# trading-agents-crypto-perp

A testbed for **Claude Code's agent orchestration**. The workload is autonomous
crypto-futures trading, but the real subject under test is the *orchestration* —
how a coordinator runs, audits, and supervises a deterministic trading system.

> ⚠️ **Experimental.** Decisions come from backtested coded strategies applied to
> real market data. Runs on **Binance USDT-M futures testnet** (demo funds, no
> real money). Not financial advice.

**Contents:** [Design invariants](#design-invariants) ·
[Architecture](#architecture) · [Strategies](#strategies) ·
[Trading rules](#trading-rules) · [Usage](#usage) ·
[Configuration](#configuration) · [Layout](#project-layout) ·
[Safety](#safety) · [Status](#status) · [Roadmap](#roadmap)

## Design invariants

Two things are deliberately swappable and must never leak into names or structure
as hard dependencies:

| Swappable | Today | The rule |
|-----------|-------|----------|
| **Runtime** | Claude Code *(was OpenClaw / Gemini 3.1 Pro)* | Never bake `claude` / `openclaw` into a file or module name. |
| **Exchange** | Binance USDT-M futures (testnet) | A new venue is **one file** — `exchanges/<name>/adapter.py` implementing `exchanges/INTERFACE.md`. Never a rename or refactor of the orchestration. |

That separation is the whole point: swap the exchange, swap the runtime, or run
multiple traders in parallel without touching the orchestration logic.

## Architecture

```
Orchestrator — main Claude Code session ("Mission Control")
   audits and reconciles every cycle · never trades itself
        │
        ├─▶  A. Bar trader     backtest/live_trader.py
        │       hourly · 15m bars · one strategy per pair (STRATEGY_MAP)
        │
        └─▶  B. Renko runner   backtest/renko_live.py
                real-time · 1s polling · atr_renko brick reversals
                   └─ optional LLM veto · backtest/signal_filter.py
        │
        ▼
   Exchange adapter — exchanges/<name>/adapter.py
   exchange-agnostic CLI (exchanges/INTERFACE.md) ─▶ Binance USDT-M futures API
```

Both trader paths share the same risk rules and the same adapter; they differ
only in **cadence** and **signal source**.

| Component | File | Role |
|-----------|------|------|
| **Orchestrator** | *(Claude Code session)* | Coordinates and independently reconciles results against the exchange. Never places trades itself. |
| **Bar trader** | `backtest/live_trader.py` | Deterministic; one hourly cycle on completed 15m bars: signal → risk rules → execute → log. Runs the four pairs via `STRATEGY_MAP`. |
| **Renko runner** | `backtest/renko_live.py` | Real-time path **exclusive to `atr_renko`**. Polls price each second, builds ATR-sized Renko bricks, and on a brick **direction reversal** closes any opposite position and opens the new side. |
| **Reversal filter** | `backtest/signal_filter.py` | *Optional* runtime-agnostic LLM veto on `atr_renko` reversals (both paths honor it). Can only *remove* a trade, never create one. Off unless `FILTER_AGENT_CMD` is set. |
| **Exchange adapter** | `exchanges/<name>/adapter.py` | The only exchange-specific code. |

> **No LLM ever _generates_ a signal** — strategies are pure Python. An LLM may
> only *veto* an `atr_renko` reversal.

## Strategies

Deterministic coded strategies on 15-minute Binance USDT-M futures data,
validated on 5–6 years of history (2019–2026) with a 70/30 in-sample /
out-of-sample split. **Deployment gate: OOS Sharpe > 1.0.**

**Live assignments** (hourly bar trader):

| Symbol  | Strategy    | OOS Sharpe | OOS trades |
|---------|-------------|-----------:|-----------:|
| BTCUSDT | `ema_cross` |       1.80 |      1,823 |
| ETHUSDT | `donchian`  |       1.61 |      1,982 |
| SOLUSDT | `donchian`  |       1.57 |      1,763 |
| XRPUSDT | `donchian`  |       1.33 |      2,037 |

**`atr_renko`** — ported from the retired `trading-atr-renko-gate` bot (ATR-sized
Renko bricks, signal on a direction flip), measured on the same split:

| Symbol  | IS Sharpe | OOS Sharpe | OOS trades | Gate |
|---------|----------:|-----------:|-----------:|------|
| BTCUSDT |     −0.56 |       1.12 |      1,480 | OOS pass *(IS fail)* |
| ETHUSDT |      0.57 |       0.97 |      1,447 | fail |
| SOLUSDT |      0.41 |       0.05 |      1,327 | fail |
| XRPUSDT |      0.70 |       1.17 |      1,385 | OOS pass |

It clears the OOS gate on XRP and BTC, but the incumbent beats it on every symbol
(and BTC's IS Sharpe is negative). So it stays in the registry as a backtestable
strategy and powers the real-time runner, but holds **no live slot** in the bar
trader.

> `rsi_mr` failed on all 4 symbols over 5 years (OOS Sharpe negative). Its earlier
> Sharpe 3–5 on 28 days of Gate data was regime luck, not edge.

## Trading rules

**Contract**

- Signals come from backtested coded strategies only — never an LLM (an LLM may
  optionally *veto* an `atr_renko` reversal, never create one).
- Every strategy clears the gate (**OOS Sharpe > 1.0**) before it is assigned to a symbol.
- Every position gets **both a stop and a take-profit**, placed atomically at
  entry (`order --stop --tp`).
- **R:R < 1.9** at the actual fill price → skip.
- **Floor breach** (equity ≤ floor) → halt new entries, log, wait.
- Log every cycle to `state/TRADE_LOG.md` and git-commit immediately.

**Hard risk guardrails**

- Max risk **≤ 2% equity per trade**.
- **One position per asset**, up to **4 concurrent**.
- Max drawdown **10% of baseline** → halt new entries ($5,000 baseline → $4,500 floor).

## Usage

The adapter is a stdlib-only Python CLI (`requests` is the only dependency); every
command and JSON shape is documented in `exchanges/INTERFACE.md`. Keys live in
`secrets/.env` (`BINANCE_API_KEY`, `BINANCE_SECRET_KEY`).

### Exchange adapter — read & trade

```bash
python3 exchanges/binance/adapter.py balance
python3 exchanges/binance/adapter.py positions
python3 exchanges/binance/adapter.py snapshot BTCUSDT
python3 exchanges/binance/adapter.py klines   BTCUSDT 15m 100
python3 exchanges/binance/adapter.py order    BTCUSDT BUY 0.01 --stop 58000 --tp 62000
```

### Backtest pipeline

```bash
python3 backtest/run.py fetch    [--symbols BTCUSDT ...]                       # cache OHLCV history
python3 backtest/run.py backtest [--strategy ema_cross|donchian|rsi_mr|atr_renko|all]
python3 backtest/run.py gate     [--strategy ...] [--symbols ...]              # gate check (OOS Sharpe > 1.0)
```

Data: Binance USDT-M futures public API (`fapi.binance.com`), 5–6 yr history.
Cache: `backtest/cache/` (gitignored — regenerated on demand). Examples:

```bash
python3 backtest/run.py backtest --strategy atr_renko
python3 backtest/run.py backtest --strategy ema_cross --symbols BTCUSDT ETHUSDT --show-trades
python3 backtest/run.py gate     --strategy atr_renko --symbols XRPUSDT
```

### Live — bar trader (hourly)

Runs **one strategy per symbol**, set in `STRATEGY_MAP` (`backtest/live_trader.py`).
Change an assignment only after the strategy clears the gate on that symbol; the
next cycle picks it up, no other change needed.

```python
STRATEGY_MAP = {
    "BTCUSDT": "ema_cross",
    "ETHUSDT": "donchian",
    "SOLUSDT": "donchian",
    "XRPUSDT": "donchian",
}
```

```bash
python3 backtest/live_trader.py
```

### Live — real-time Renko runner

`atr_renko` is reversal-driven, so it also has a **second-by-second** runner that
ports the original Gate bot's behaviour onto the new adapter:

```bash
RENKO_SYMBOLS=XRPUSDT python3 backtest/renko_live.py
```

- Polls each symbol's price once a second, builds ATR-sized Renko bricks, and on a
  brick **direction reversal** closes any opposite position and opens the new side
  (stop + TP atomic). Same risk gates as the bar trader.
- `RENKO_SYMBOLS` is comma-separated; empty → no-op. Exchange comes from
  `EXCHANGE_CONFIG.md`, so it runs on whatever adapter is active.
- **A symbol belongs to one path only** — never both `STRATEGY_MAP` and
  `RENKO_SYMBOLS`, or the hourly trader would double-trade it.

### Optional reversal filter (LLM veto)

A runtime-agnostic veto on `atr_renko` entries, honored by **both** trader paths.
It replaces the retired Gate bot's ollama check; the runtime is whatever
`FILTER_AGENT_CMD` names:

```bash
FILTER_AGENT_CMD="claude -p" RENKO_SYMBOLS=XRPUSDT python3 backtest/renko_live.py
```

The agent receives the proposed trade + recent brick sequence and replies `ENTER`
or `SKIP`.

- **Unset → off** (pure deterministic signal).
- **Fails open** — any error, timeout, or unclear reply → `ENTER`. The
  deterministic signal has already cleared the gate, R:R, sizing and floor checks;
  the filter only ever *removes* trades.

## Configuration

Set in `exchanges/EXCHANGE_CONFIG.md` (no keys — those live in `secrets/.env`):

| Switch    | Values                | Meaning |
|-----------|-----------------------|---------|
| `mode`    | `live` / `paper`      | real orders vs. simulated fills at real prices |
| `network` | `testnet` / `mainnet` | demo funds vs. real money |

**Current: Binance · `mode: live` · `network: testnet`** — real order execution
against demo funds. Going to real money (`network: mainnet` + rotated keys) is
**always an explicit user decision**, never the agent's.

## Project layout

| Path | What |
|------|------|
| `README.md` / `CLAUDE.md` | this file — orchestration contract + project docs (symlinked) |
| `exchanges/EXCHANGE_CONFIG.md` | active exchange, mode, network, pairs (no keys) |
| `exchanges/INTERFACE.md` | CLI contract every adapter implements |
| `exchanges/binance/adapter.py` | active adapter: Binance USDT-M futures (HMAC-SHA256) |
| `exchanges/gate/adapter.py` | retired Gate.io adapter (kept for reference) |
| `backtest/strategies/` | coded strategies: `ema_cross`, `donchian`, `rsi_mr`, `atr_renko` |
| `backtest/live_trader.py` | hourly bar trader: signal → size → order → log |
| `backtest/renko_live.py` | real-time `atr_renko` runner: 1s polling, brick-reversal trades |
| `backtest/signal_filter.py` | optional runtime-agnostic LLM veto on reversals (`FILTER_AGENT_CMD`) |
| `backtest/engine.py` | walk-forward backtester (IS/OOS split, Sharpe gate) |
| `backtest/fetch.py` | OHLCV downloader (Binance mainnet public API) |
| `backtest/run.py` | CLI: fetch / backtest / gate |
| `state/TRADE_LOG.md` | append-only decision history (tracked) |
| `state/TRADE_STATE.md` | live capital/positions (gitignored — churns each cycle) |
| `secrets/.env` | API keys + Telegram token (gitignored — **never committed**) |
| `strategy/STRATEGY.md` | legacy LLM strategy doc (kept for reference) |
| `notify/telegram.py` | outbound Telegram notifier (currently disabled) |
| `notify/telegram_listen.py` | inbound Telegram NL bridge → orchestrator (currently disabled) |

## Safety

- **Never commit API keys.** They live in `secrets/.env` (gitignored) — not in
  `README.md`, `EXCHANGE_CONFIG.md`, or any tracked file. The Telegram bot token lives there too.
- Binance keys are **testnet/demo** (no real money). Real money requires
  `network: mainnet`, an explicit user decision.
- `TRADE_STATE.md` is gitignored (it churns every cycle); `TRADE_LOG.md` is the
  tracked, durable record.
- Live (testnet) execution is active by explicit user decision. Don't flip to
  `mainnet`, and don't widen risk guardrails, without an explicit ask.
- **Telegram is OFF entirely** (user decision 2026-06-09). `notify/telegram.py`
  and `notify/telegram_listen.py` are intact but not invoked; the hourly cron
  produces in-session summaries only. Don't send Telegram or start the bridge
  unless the user re-enables it.

## Status

**LIVE on Binance testnet** (`mode: live`, `network: testnet` — real order
execution, demo funds). The hourly **bar trader** runs across
BTCUSDT/ETHUSDT/SOLUSDT/XRPUSDT; Telegram off, in-session summaries only.

The real-time **Renko runner** and the **reversal filter** are *built and
self-checked but not enabled* — `RENKO_SYMBOLS` and `FILTER_AGENT_CMD` are unset,
so the live system is unchanged until a symbol is explicitly moved onto the renko
path.

### Live track record — 2026-06-12 → 2026-06-17 (6 days)

| Metric | Value |
|--------|-------|
| Starting balance | $5,000.00 |
| Realized balance | $3,860.46 |
| Realized P&L | −$1,139.54 (−22.8%) |
| Open position uPnL | +$284.28 (4 shorts: BTC/ETH/SOL/XRP) |
| Mark-to-market equity | $4,144.74 (−17.1% from start) |
| Trade entries | 28 |
| Floor (halt threshold) | $3,932.06 |

Baseline $5,000; floor $4,500, adjusted to $3,932 after realized drawdown.

## Roadmap

**Done**

- [x] Gate adapter built and validated (retired 2026-06-12).
- [x] Autonomous hourly trading with stop + take-profit on every position.
- [x] Five BINDING EV RULES added after post-mortem.
- [x] LLM trader replaced with coded strategies after confirmed negative edge.
- [x] Backtest pipeline: Binance 5-yr data, IS/OOS split, Sharpe > 1 gate.
- [x] Binance USDT-M futures adapter built; testnet validated ($5,000 demo).
- [x] Strategies validated on 5-yr data: `ema_cross` (BTC), `donchian` (ETH/SOL/XRP).
- [x] Merged `trading-atr-renko-gate` bot in as the `atr_renko` strategy
      (Gate/discord plumbing dropped — adapter + orchestration replace them).
- [x] Real-time `atr_renko` runner (`renko_live.py`): 1s polling, brick-reversal
      close-and-reverse, via the exchange-agnostic adapter.
- [x] Reversal filter (`signal_filter.py`): ollama veto replaced by a
      runtime-agnostic LLM veto (`FILTER_AGENT_CMD`); fails open, off by default.

**Next**

- [ ] Build a live track record under the coded strategies.
- [ ] Decide whether to put a symbol on the real-time renko path (and pull it
      from `STRATEGY_MAP`) once the runner has a paper/testnet track record.
- [ ] Retire the standalone `trading-atr-renko-gate` repo (its edge now lives here).
