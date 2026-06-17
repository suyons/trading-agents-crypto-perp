# trading-agents

A testbed for **Claude Code's agent orchestration**. The workload happens to be
autonomous crypto trading, but the *subject under test* is the orchestration:
how a coordinator spawns, directs, and supervises trading sub-agents.

Two things are deliberately swappable and must never leak into names or
structure as hard dependencies:

- **The runtime.** Migrated from OpenClaw (Gemini 3.1 Pro) → Claude Code. May
  change again. Don't bake `claude`/`openclaw` into file or module names.
- **The exchange.** Currently Binance USDT-M futures (testnet). Other exchanges
  must be a one-file swap — a new `exchanges/<name>/adapter.py` implementing
  `exchanges/INTERFACE.md` — never a rename or a refactor of the orchestration.

## Orchestration model

- **Orchestrator ("Mission Control")** — the main session. Coordinates, reviews,
  and audits the coded trader against the exchange. Does **not** place trades
  itself. Runs `backtest/live_trader.py` each cycle.
- **Coded trader** — `backtest/live_trader.py`. Pure Python, deterministic. No
  LLM involved in trade decisions. Generates signals from backtested strategies,
  applies risk rules, executes, and logs.
- **Exchange adapter** — isolated under `exchanges/<name>/`. The trader talks to
  the adapter's exchange-agnostic CLI (`exchanges/INTERFACE.md`), never to a
  specific exchange's quirks directly.

This separation is the whole point: swap the exchange, swap the runtime, or run
multiple traders in parallel without touching the orchestration logic.

## Layout

```
CLAUDE.md                        # this file — orchestration + project contract
README.md                        # human-facing overview
.gitignore                       # keys/state excluded
strategy/STRATEGY.md             # legacy LLM strategy doc (kept for reference)
exchanges/EXCHANGE_CONFIG.md     # active exchange + mode + network + pairs (NO keys)
exchanges/INTERFACE.md           # the exchange-agnostic CLI contract every adapter implements
exchanges/binance/adapter.py     # active adapter: Binance USDT-M futures (HMAC-SHA256)
exchanges/gate/adapter.py        # retired adapter (Gate APIv4, kept for reference)
state/TRADE_STATE.md             # capital, open positions (gitignored — churns each cycle)
state/TRADE_LOG.md               # append-only decision log (tracked — durable history)
secrets/.env                     # API keys + Telegram token (gitignored — NEVER committed)
backtest/fetch.py                # fetch OHLCV from Binance mainnet (5-6 yr history)
backtest/engine.py               # walk-forward backtester (IS/OOS split, Sharpe gate)
backtest/strategies/             # coded strategies: ema_cross, rsi_mr, donchian
backtest/live_trader.py          # live execution: signal → size → order → log
backtest/run.py                  # CLI: fetch / backtest / gate
notify/telegram.py               # outbound notifier (currently disabled)
notify/telegram_listen.py        # inbound NL bridge (currently disabled)
```

## Coded trader contract

- Signals come from backtested coded strategies only — no LLM interpretation.
- Every strategy must pass the deployment gate: **OOS Sharpe > 1.0** on a proper
  IS/OOS split before being assigned to a symbol.
- Risk first: every position gets **both a stop loss and a take-profit**, placed
  atomically at entry (`order --stop --tp`). Max risk 2% equity per trade.
- Floor breach (equity ≤ floor) → halt new entries, log, wait.
- Log every cycle to `TRADE_LOG.md` and git commit immediately after.

## Current strategy (backtested — canonical in `backtest/strategies/`)

**Deterministic coded strategies on 15m Binance USDT-M futures data.**
Validated on 5-6 years of history (2019–2026), 70/30 IS/OOS split.

| Symbol  | Strategy   | OOS Sharpe | OOS trades |
|---------|------------|------------|------------|
| BTCUSDT | ema_cross  | 1.80       | 1823       |
| ETHUSDT | donchian   | 1.61       | 1982       |
| SOLUSDT | donchian   | 1.57       | 1763       |
| XRPUSDT | donchian   | 1.33       | 2037       |

`rsi_mr` failed on all 4 symbols over 5 years (OOS Sharpe negative) — what
appeared as Sharpe 3–5 on 28 days of Gate data was regime luck, not edge.

Risk guardrails (hard limits):
- Max risk ≤ 2% equity per trade · 1 position per asset (up to 4 concurrent)
- Every position: stop loss + take-profit set atomically at entry
- Max drawdown 10% of baseline → halt new entries ($5,000 baseline → $4,500 floor)
- R:R < 1.9 at actual fill price → skip

## Modes

Two independent switches in `EXCHANGE_CONFIG.md`:

- **mode** — `live` places real orders via the adapter; `paper` simulates fills
  at real prices (local-memory only). Both read real market data.
- **network** — `testnet` uses demo funds (no real money); `mainnet` is real money.

**Current: Binance, `mode: live`, `network: testnet`** — real order execution
against demo funds. Going to real money = `network: mainnet` (+ rotated keys),
which is an explicit user decision, never the agent's. Keys from `secrets/.env`.

## Backtest pipeline

```bash
python3 backtest/run.py fetch [--symbols BTCUSDT ...]   # download & cache history
python3 backtest/run.py backtest [--strategy all]        # IS/OOS metrics
python3 backtest/run.py gate [--strategy all]            # deployment gate check
```

Data: Binance USDT-M futures public API (`fapi.binance.com`), 5-6 yr history.
Gate: OOS Sharpe > 1.0 required before a strategy is deployed to live trading.
Cache: `backtest/cache/` (gitignored — regenerated on demand).

## Secrets & safety — read before committing

- **Never commit API keys.** They go in `secrets/.env`, which is gitignored.
  Not in `CLAUDE.md`, not in `EXCHANGE_CONFIG.md`, not in any tracked file.
- The git remote URL embeds a GitHub PAT — **rotate it before any real-money use.**
- The Telegram bot token lives in `secrets/.env` too.
- Binance keys are testnet/demo (no real money). Real money requires
  `network: mainnet`, an explicit user decision.
- `TRADE_STATE.md` is gitignored (it churns every cycle); `TRADE_LOG.md` is
  tracked as the durable record.
- Live (testnet) execution is active by explicit user decision. Don't flip to
  `mainnet`, and don't widen risk guardrails, without an explicit ask.

## Notifications & control (Telegram)

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
- [ ] Rotate the GitHub PAT embedded in the git remote URL before any real money.
- [ ] Only then consider `network: mainnet` (real money) — explicit user decision.
