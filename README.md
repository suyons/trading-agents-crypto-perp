# trading-agents

A testbed for **Claude Code's agent orchestration**. The workload is autonomous
crypto-futures trading, but the real subject under test is the *orchestration*:
how a coordinator spawns, directs, and supervises trading sub-agents — and how
cleanly the exchange and the runtime underneath can be swapped.

> **Experimental.** Trading decisions are made by an LLM applying a four-layer
> technical analysis framework to real market data. It runs on **Gate.io testnet
> (demo funds, no real money).** Not financial advice.

## How it works

```
Orchestrator (main Claude Code session)
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
  reconciles the trader's results against the exchange. Places no trades itself.
- **Trader sub-agent** (`.claude/agents/trader.md`) — spawned each cycle: pulls
  real market data, applies the TA framework, sizes against risk, executes, reports.
- **Exchange adapter** — the only exchange-specific code. Swapping venues means
  adding one `exchanges/<name>/adapter.py` that implements `INTERFACE.md`.

## The decision cycle

Each cycle the trader:

1. **Reconciles** live balance and positions from the exchange
2. **Pulls** 100 completed 15m candles per pair + snapshot (price, funding, 24h range)
3. **Applies four TA layers** to every pair:
   - **Price action** — trend structure (HH/HL vs LH/LL), key S/R, regime
   - **Order blocks** — last significant candle before an impulse move (institutional zones; support on retrace for bullish OBs, resistance for bearish OBs)
   - **Fibonacci retracement** — 0.382 / 0.5 / 0.618 pullback levels on the most recent impulse leg; confluence with OBs = high-probability zone
   - **Elliott Wave** — 5-wave impulse / 3-wave corrective count; Wave 3 entries preferred (strongest, longest move)
4. **Gates any setup** through five BINDING EV RULES (see below)
5. **Decides**: ENTER, EXIT, ADJUST, or HOLD — every spawn ends in one

Entry requires **multi-framework confluence** (≥2 layers pointing to the same level
and direction). A single-layer signal requires strong price action confirmation.
Zero confluence → HOLD.

### Five BINDING EV RULES (post-mortem, non-negotiable)

1. **≥2:1 reward:risk, hard** — compute from real structural stop + realistic TP
2. **Let winners run** — no trailing to breakeven while barely green; trail only after ≥1.5R behind a confirmed structural pivot
3. **With momentum** — no fading without confirmed rejection; no buying resistance / shorting support
4. **No mid-range entries** — only range edges or OB/Fib confluence pullback targets
5. **No churn** — favor action only among setups that clear rules 1–4

### Risk guardrails (hard limits)

- Max leverage 20x · risk ≤ 2% equity per trade · one position per asset (up to 4 concurrent)
- Every position carries **both a stop loss and a take-profit**, set atomically at entry
- 10% max drawdown from baseline → stop trading and alert (current: $1,000 baseline → $900 floor)
- No chasing, no averaging down, no holding through known high-impact news

## Modes (set in `exchanges/EXCHANGE_CONFIG.md`)

| switch    | values                  | meaning |
|-----------|-------------------------|---------|
| `mode`    | `live` / `paper`        | real orders vs. simulated fills at real prices |
| `network` | `testnet` / `mainnet`   | demo funds vs. real money |

**Currently `gate` / `live` / `testnet`** — real execution against demo funds.
Moving to real money (`mainnet`) is always an explicit human decision.

## Layout

| path | what |
|------|------|
| `strategy/STRATEGY.md` | canonical trading rules (four-layer TA + EV rules + risk guardrails) |
| `exchanges/EXCHANGE_CONFIG.md` | active exchange, mode, network, pairs (no keys) |
| `exchanges/INTERFACE.md` | CLI contract every adapter implements |
| `exchanges/gate/` | active Gate.io adapter + notes |
| `state/TRADE_LOG.md` | append-only decision history (tracked) |
| `state/TRADE_STATE.md` | live capital/positions (gitignored — churns each cycle) |
| `secrets/.env` | API keys + Telegram token (gitignored — **never committed**) |
| `.claude/agents/trader.md` | trader sub-agent definition |
| `notify/telegram.py` | outbound Telegram notifier (currently disabled) |
| `notify/telegram_listen.py` | inbound Telegram NL bridge → orchestrator (currently disabled) |
| `CLAUDE.md` | full orchestration contract + project instructions |

## Usage

The adapter is a stdlib-only Python CLI (no dependencies beyond `requests`):

```bash
python3 exchanges/gate/adapter.py balance
python3 exchanges/gate/adapter.py positions
python3 exchanges/gate/adapter.py snapshot BTC_USDT
python3 exchanges/gate/adapter.py klines BTC_USDT 15m 100
python3 exchanges/gate/adapter.py order BTC_USDT BUY 0.02 --stop 58000 --tp 62000
```

Trading runs through Claude Code: open a session in this directory, the orchestrator
drives the hourly cron. Keys go in `secrets/.env` (`GATE_API_KEY`, `GATE_SECRET_KEY`).

## Notifications (Telegram)

Telegram is currently **off** (user decision). The code is intact — re-enable by
starting `notify/telegram_listen.py` and uncommenting the send call in the cron.
Token + chat_id live in `secrets/.env`.

## Safety

Keys live only in gitignored `secrets/.env`. The git remote URL embeds a GitHub
PAT — rotate it before any real-money use. Testnet is the safe default; real money
(`mainnet`) is never the agent's call.
