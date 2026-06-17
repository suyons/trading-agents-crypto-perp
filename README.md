# trading-agents-crypto-perp

A testbed for **Claude Code's agent orchestration**. The workload is autonomous
crypto-futures trading, but the real subject under test is the *orchestration*:
how a coordinator runs, audits, and supervises a deterministic trading system —
and how cleanly the exchange and runtime can be swapped without touching
orchestration logic.

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
  results against the exchange. Places no trades itself.
- **Coded trader** (`backtest/live_trader.py`) — pure Python, no LLM. Generates
  signals from backtested strategies, applies risk rules, executes, and logs.
- **Exchange adapter** — the only exchange-specific code. Swapping venues means
  adding one `exchanges/<name>/adapter.py` that implements `INTERFACE.md`.

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

### Risk guardrails (hard limits)

- Max risk ≤ 2% equity per trade · one position per asset (up to 4 concurrent)
- Every position carries **both a stop loss and a take-profit**, set atomically at entry
- R:R < 1.9 at actual fill price → skip the trade
- Max drawdown 10% from baseline → halt new entries ($5,000 baseline → $4,500 floor)

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

**Currently `binance` / `live` / `testnet`** — real execution against demo funds.
Moving to real money (`mainnet`) is always an explicit human decision.

## Layout

| path | what |
|------|------|
| `exchanges/EXCHANGE_CONFIG.md` | active exchange, mode, network, pairs (no keys) |
| `exchanges/INTERFACE.md` | CLI contract every adapter implements |
| `exchanges/binance/` | active Binance USDT-M futures adapter (HMAC-SHA256) |
| `exchanges/gate/` | retired Gate.io adapter (kept for reference) |
| `backtest/strategies/` | coded strategies: `ema_cross`, `donchian`, `rsi_mr` |
| `backtest/live_trader.py` | live execution: signal → size → order → log |
| `backtest/engine.py` | walk-forward backtester (IS/OOS split, Sharpe gate) |
| `backtest/fetch.py` | OHLCV downloader (Binance mainnet public API) |
| `state/TRADE_LOG.md` | append-only decision history (tracked) |
| `state/TRADE_STATE.md` | live capital/positions (gitignored — churns each cycle) |
| `secrets/.env` | API keys (gitignored — **never committed**) |
| `notify/telegram.py` | outbound Telegram notifier (currently disabled) |
| `notify/telegram_listen.py` | inbound Telegram NL bridge → orchestrator (currently disabled) |
| `CLAUDE.md` | full orchestration contract + project instructions |

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

Keys live only in gitignored `secrets/.env` — never in any tracked file.
Testnet is the safe default; switching to real money (`mainnet`) is never
the agent's call.

## Notifications (Telegram)

Telegram is currently **off**. The code is intact — re-enable by starting
`notify/telegram_listen.py` and wiring the send call back into the cron.
Token + chat_id live in `secrets/.env`.
