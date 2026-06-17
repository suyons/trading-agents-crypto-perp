# trading-agents-crypto-perp

A testbed for **Claude Code's agent orchestration**. The workload is autonomous
crypto-futures trading, but the real subject under test is the *orchestration*:
how a coordinator runs, audits, and supervises a deterministic trading system.

Two things are deliberately swappable and must never leak into names or
structure as hard dependencies:

- **The runtime.** Migrated from OpenClaw (Gemini 3.1 Pro) → Claude Code. May
  change again. Don't bake `claude`/`openclaw` into file or module names.
- **The exchange.** Currently Binance USDT-M futures (testnet). Other exchanges
  must be a one-file swap — a new `exchanges/<name>/adapter.py` implementing
  `exchanges/INTERFACE.md` — never a rename or a refactor of the orchestration.

> **Experimental.** Trading decisions are made by backtested coded strategies
> applied to real market data. Runs on **Binance USDT-M futures testnet
> (demo funds, no real money).** Not financial advice.

## How it works

```
Orchestrator (main Claude Code session)
   │  audits cycles, never trades itself
   ▼
Coded trader (backtest/live_trader.py)  ──reads──▶  backtest/strategies/
   │  pure Python, deterministic, no LLM            state/TRADE_STATE.md
   │  one decision cycle per hour
   ▼
Exchange adapter (exchanges/binance/adapter.py)  ──▶  Binance USDT-M futures API
   exchange-agnostic CLI defined in exchanges/INTERFACE.md
```

- **Orchestrator ("Mission Control")** — coordinates and independently reconciles
  results against the exchange. Does **not** place trades itself. Runs
  `backtest/live_trader.py` each cycle.
- **Coded trader** (`backtest/live_trader.py`) — pure Python, no LLM. Generates
  signals from backtested strategies, applies risk rules, executes, and logs.
- **Exchange adapter** — the only exchange-specific code. Swapping venues means
  adding one `exchanges/<name>/adapter.py` that implements `INTERFACE.md`.

This separation is the whole point: swap the exchange, swap the runtime, or run
multiple traders in parallel without touching the orchestration logic.

## Strategies

Deterministic coded strategies on 15-minute Binance USDT-M futures data,
validated on 5–6 years of history (2019–2026) with a 70/30 in-sample /
out-of-sample split. Deployment gate: OOS Sharpe > 1.0.

| Symbol  | Strategy  | OOS Sharpe | OOS trades |
|---------|-----------|------------|------------|
| BTCUSDT | ema_cross | 1.80       | 1823       |
| ETHUSDT | donchian  | 1.61       | 1982       |
| SOLUSDT | donchian  | 1.57       | 1763       |
| XRPUSDT | donchian  | 1.33       | 2037       |

`rsi_mr` failed on all 4 symbols over 5 years (OOS Sharpe negative) — what
appeared as Sharpe 3–5 on 28 days of Gate data was regime luck, not edge.

## Coded trader contract

- Signals come from backtested coded strategies only — no LLM interpretation.
- Every strategy must pass the deployment gate: **OOS Sharpe > 1.0** on a proper
  IS/OOS split before being assigned to a symbol.
- Risk first: every position gets **both a stop loss and a take-profit**, placed
  atomically at entry (`order --stop --tp`). Max risk 2% equity per trade.
- R:R < 1.9 at actual fill price → skip the trade.
- Floor breach (equity ≤ floor) → halt new entries, log, wait.
- Log every cycle to `state/TRADE_LOG.md` and git commit immediately after.

### Risk guardrails (hard limits)

- Max risk ≤ 2% equity per trade · one position per asset (up to 4 concurrent)
- Every position: stop loss + take-profit set atomically at entry
- Max drawdown 10% of baseline → halt new entries ($5,000 baseline → $4,500 floor)

## Backtest pipeline

```bash
python3 backtest/run.py fetch [--symbols BTCUSDT ...]   # download & cache OHLCV history
python3 backtest/run.py backtest [--strategy all]        # IS/OOS metrics
python3 backtest/run.py gate [--strategy all]            # deployment gate check (Sharpe > 1.0)
```

Data: Binance USDT-M futures public API (`fapi.binance.com`), 5–6 yr history.
Cache: `backtest/cache/` (gitignored — regenerated on demand).

## Modes (set in `exchanges/EXCHANGE_CONFIG.md`)

| switch    | values                | meaning |
|-----------|-----------------------|---------|
| `mode`    | `live` / `paper`      | real orders vs. simulated fills at real prices |
| `network` | `testnet` / `mainnet` | demo funds vs. real money |

**Current: Binance, `mode: live`, `network: testnet`** — real order execution
against demo funds. Going to real money = `network: mainnet` (+ rotated keys),
which is an explicit user decision, never the agent's. Keys from `secrets/.env`.

## Layout

| path | what |
|------|------|
| `README.md` / `CLAUDE.md` | this file — orchestration contract + project docs (symlinked) |
| `exchanges/EXCHANGE_CONFIG.md` | active exchange, mode, network, pairs (no keys) |
| `exchanges/INTERFACE.md` | CLI contract every adapter implements |
| `exchanges/binance/adapter.py` | active adapter: Binance USDT-M futures (HMAC-SHA256) |
| `exchanges/gate/adapter.py` | retired Gate.io adapter (kept for reference) |
| `backtest/strategies/` | coded strategies: `ema_cross`, `donchian`, `rsi_mr` |
| `backtest/live_trader.py` | live execution: signal → size → order → log |
| `backtest/engine.py` | walk-forward backtester (IS/OOS split, Sharpe gate) |
| `backtest/fetch.py` | OHLCV downloader (Binance mainnet public API) |
| `backtest/run.py` | CLI: fetch / backtest / gate |
| `state/TRADE_LOG.md` | append-only decision history (tracked) |
| `state/TRADE_STATE.md` | live capital/positions (gitignored — churns each cycle) |
| `secrets/.env` | API keys + Telegram token (gitignored — **never committed**) |
| `strategy/STRATEGY.md` | legacy LLM strategy doc (kept for reference) |
| `notify/telegram.py` | outbound Telegram notifier (currently disabled) |
| `notify/telegram_listen.py` | inbound Telegram NL bridge → orchestrator (currently disabled) |

## Usage

The adapter is a stdlib-only Python CLI (`requests` is the only dependency):

```bash
python3 exchanges/binance/adapter.py balance
python3 exchanges/binance/adapter.py positions
python3 exchanges/binance/adapter.py snapshot BTCUSDT
python3 exchanges/binance/adapter.py klines BTCUSDT 15m 100
python3 exchanges/binance/adapter.py order BTCUSDT BUY 0.01 --stop 58000 --tp 62000
```

Trading runs hourly via `backtest/live_trader.py`. Keys go in `secrets/.env`
(`BINANCE_API_KEY`, `BINANCE_SECRET_KEY`).

## Safety

- **Never commit API keys.** They go in `secrets/.env`, which is gitignored —
  not in `README.md`, not in `EXCHANGE_CONFIG.md`, not in any tracked file.
- The Telegram bot token lives in `secrets/.env` too.
- Binance keys are testnet/demo (no real money). Real money requires
  `network: mainnet`, an explicit user decision.
- `TRADE_STATE.md` is gitignored (it churns every cycle); `TRADE_LOG.md` is
  tracked as the durable record.
- Live (testnet) execution is active by explicit user decision. Don't flip to
  `mainnet`, and don't widen risk guardrails, without an explicit ask.

## Notifications (Telegram)

**Telegram is currently OFF entirely** (user decision 2026-06-09). The code
(`notify/telegram.py`, `notify/telegram_listen.py`) is intact but not invoked.
The hourly cron produces in-session summaries only. Do NOT send Telegram or
start the bridge unless the user explicitly re-enables it.

## Status

**LIVE on Binance testnet** (`mode: live`, `network: testnet` — real order
execution, demo funds, $5,000 balance). Binance adapter
(`exchanges/binance/adapter.py`, USDT-M futures, HMAC-SHA256) active.
Coded trader runs **hourly** via `backtest/live_trader.py` across BTCUSDT/
ETHUSDT/SOLUSDT/XRPUSDT. Telegram off; in-session summaries only.

**Active strategies (2026-06-12):** validated on 5-yr Binance data.
BTC → ema_cross (OOS Sharpe 1.80). ETH/SOL/XRP → donchian (OOS Sharpe 1.33–1.61).
Baseline $5,000; floor $4,500.

## TODO

Done:
- [x] Gate adapter built and validated (retired 2026-06-12).
- [x] Autonomous hourly trading with stop+take-profit on every position.
- [x] Five BINDING EV RULES added after post-mortem.
- [x] LLM trader replaced with coded strategies after confirmed negative edge.
- [x] Backtest pipeline built: Binance 5-yr data, IS/OOS split, Sharpe > 1 gate.
- [x] Binance USDT-M futures adapter built; testnet validated ($5,000 demo).
- [x] Strategies validated on 5-yr data: ema_cross (BTC), donchian (ETH/SOL/XRP).

Next:
- [ ] Build a live track record under the coded strategies.
