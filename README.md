# trading-agents

A testbed for **Claude Code's agent orchestration**. The workload is autonomous
crypto-futures trading, but the real subject under test is the *orchestration*:
how a coordinator spawns, directs, and supervises trading sub-agents — and how
cleanly the exchange and the runtime underneath can be swapped.

> ⚠️ **Experimental.** Trading decisions are made by an LLM reasoning over raw
> market data with **no technical indicators and no backtest** — "unproven by
> design." It currently runs on **Gate.io testnet (demo funds, no real money).**
> Not financial advice; don't point it at real money casually.

## How it works

```
Orchestrator (main session)
   │  spawns + audits, never trades itself
   ▼
Trader sub-agent  ──reads──▶  strategy/STRATEGY.md   (the rules)
   │                          state/TRADE_STATE.md   (positions, capital)
   │  one decision cycle
   ▼
Exchange adapter (exchanges/gate/adapter.py)  ──▶  Gate.io futures API
   exchange-agnostic CLI defined in exchanges/INTERFACE.md
```

- **Orchestrator ("Mission Control")** — coordinates, reviews, and independently
  reconciles the trader's reported results against the exchange. Places no trades.
- **Trader sub-agent** (`.claude/agents/trader.md`) — spawned to run one decision
  cycle: pull real data, form a thesis, size against risk, execute, report.
- **Exchange adapter** — the only exchange-specific code. Swapping venues means
  adding one `exchanges/<name>/adapter.py` that implements `INTERFACE.md`; the
  orchestration never changes.

## The decision cycle

Each cycle the trader: **reconciles** live balance/positions from the exchange →
**gathers** real data (price, 24h range, funding, raw candles, optional news) →
forms a **falsifiable thesis** with an explicit **invalidation** → checks the
**risk gate** → decides exactly one of **ENTER / EXIT / ADJUST / HOLD** (HOLD is
the default). Every decision is logged to `state/TRADE_LOG.md`.

### Risk guardrails (hard limits)
- Max leverage 20x · risk ≤ 2% of equity per trade · one position per asset
- Every position carries **both a stop loss and a take-profit**, set at entry
  (the stop is fail-safe — if it can't be placed, the entry is auto-closed)
- 10% max drawdown → stop trading and alert
- No chasing, no averaging down, no holding through known high-impact news

## Modes (set in `exchanges/EXCHANGE_CONFIG.md`)

| switch    | values              | meaning |
|-----------|---------------------|---------|
| `mode`    | `live` / `paper`    | place real orders vs. simulate fills at real prices |
| `network` | `testnet` / `mainnet` | demo funds vs. real money (exchanges with a testnet) |

**Currently `gate` / `live` / `testnet`** — real execution against demo funds.
Moving to real money (`mainnet`) is always an explicit human decision.

## Layout

| path | what |
|------|------|
| `strategy/STRATEGY.md` | canonical trading rules |
| `exchanges/EXCHANGE_CONFIG.md` | active exchange, mode, network, pairs (no keys) |
| `exchanges/INTERFACE.md` | the CLI contract every adapter implements |
| `exchanges/gate/` | active Gate.io adapter + notes |
| `state/TRADE_LOG.md` | append-only decision history (tracked) |
| `state/TRADE_STATE.md` | live capital/positions (gitignored — churns) |
| `secrets/.env` | API keys + Telegram token (gitignored — **never committed**) |
| `.claude/agents/trader.md` | trader sub-agent definition |
| `notify/telegram.py` | outbound Telegram notifier (channel-swappable) |
| `CLAUDE.md` | full orchestration + project contract |

## Usage

The adapter is a stdlib-only Python CLI (no dependencies):

```bash
python3 exchanges/gate/adapter.py snapshot BTC        # price / 24h / funding
python3 exchanges/gate/adapter.py balance             # account equity
python3 exchanges/gate/adapter.py positions           # open positions
python3 exchanges/gate/adapter.py order BTC SELL 0.02 --stop 70450 --tp 68000
```

Trading itself runs through Claude Code: ask the orchestrator to spawn the trader
for a cycle, or let the hourly schedule drive it. Provide keys in `secrets/.env`
(`GATE_API_KEY`, `GATE_SECRET_KEY`).

## Notifications

Outbound trade summaries and risk alerts go to Telegram via `notify/telegram.py`
(stdlib, channel-swappable). After each hourly cycle the orchestrator sends a
*verified* digest — equity/P&L, open positions with their stop/target — and
prefixes `🚨 ALERT:` on drawdown or position events. Set up with a BotFather
token in `secrets/.env`, message the bot once, then `chatid --save`:

```bash
python3 notify/telegram.py chatid --save   # after messaging the bot
python3 notify/telegram.py test            # connection ping
```

## Safety

Keys live only in gitignored `secrets/.env`. The git remote URL embeds a GitHub
PAT — rotate it before any real-money use. Paper/testnet is the safe default;
real money is never the agent's call.
