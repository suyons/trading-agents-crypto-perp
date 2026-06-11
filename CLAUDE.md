# trading-agents

A testbed for **Claude Code's agent orchestration**. The workload happens to be
autonomous crypto trading, but the *subject under test* is the orchestration:
how a coordinator spawns, directs, and supervises trading sub-agents.

Two things are deliberately swappable and must never leak into names or
structure as hard dependencies:

- **The runtime.** Migrated from OpenClaw (Gemini 3.1 Pro) → Claude Code. May
  change again. Don't bake `claude`/`openclaw` into file or module names.
- **The exchange.** Currently Gate.io futures (testnet). Binance / Bybit / others
  must be a one-file swap — a new `exchanges/<name>/adapter.py` implementing
  `exchanges/INTERFACE.md` — never a rename or a refactor of the orchestration.

## Orchestration model

- **Orchestrator ("Mission Control")** — the main session. Coordinates, reviews,
  reports, and *audits the trader against the exchange*. Does **not** place trades
  itself. Spawns the trader for decisions.
- **Trader sub-agent** — defined in `.claude/agents/trader.md`. Spawned to make
  and execute one decision cycle, then report. Stays in its lane (see contract).
- **Exchange adapter** — isolated under `exchanges/<name>/`. The trader talks to
  the adapter's exchange-agnostic CLI (`exchanges/INTERFACE.md`), never to a
  specific exchange's quirks directly.

This separation is the whole point: swap the exchange, swap the runtime, or run
multiple traders in parallel without touching the orchestration logic.

## Layout

```
CLAUDE.md                     # this file — orchestration + project contract
README.md                     # human-facing overview
.gitignore                    # keys/state excluded
strategy/STRATEGY.md          # canonical trading rules
exchanges/EXCHANGE_CONFIG.md  # active exchange + mode + network + pairs (NO keys)
exchanges/INTERFACE.md        # the exchange-agnostic CLI contract every adapter implements
exchanges/gate/adapter.py     # active adapter: Gate APIv4 futures (HMAC-SHA512)
exchanges/gate/NOTES.md       # adapter notes / gotchas / validation record
state/TRADE_STATE.md          # capital, open positions (gitignored — churns each spawn)
state/TRADE_LOG.md            # append-only decision log (tracked — durable history)
secrets/.env                  # API keys + Telegram token (gitignored — NEVER committed)
.claude/agents/trader.md      # trader sub-agent definition
notify/telegram.py            # outbound notifier (Telegram alerts; channel-swappable)
notify/telegram_listen.py     # inbound NL bridge -> orchestrator (two-way; chat-locked)
```

## Trader contract

- Execute the strategy with precision. The user's rules are rules, not
  suggestions. If `STRATEGY.md` is missing/incomplete, ask before trading.
- Risk first: every position gets **both a stop loss and a take-profit**, decided
  before entry and set the moment it opens (atomic `order --stop --tp`). Never
  update state files until a trade is **confirmed**.
- Every decision states a **falsifiable thesis + an explicit invalidation**; no
  clear invalidation → no trade. Both go in every `TRADE_LOG.md` entry.
- Every spawn ends in a decision — enter, exit, adjust, or hold. "No setup, hold"
  is a valid and frequent outcome. Don't overtrade.
- Stay in your lane: read/write only this project's trading files. Anything
  outside, ask the orchestrator.
- Reporting is tight: P&L ($ and %), open positions, last action + why, next
  watch. 3–5 lines, no essays.

## Current strategy (summary — canonical lives in `strategy/STRATEGY.md`)

**Fully autonomous, Claude-driven — four-layer TA framework on 15m candles.**
Each cycle the trader pulls the last 100 completed 15m bars per pair and applies:
1. **Price action** — trend structure, key S/R, regime classification
2. **Order blocks** — last significant candle before an impulse (institutional zones)
3. **Fibonacci retracement** — 0.382–0.618 pullback levels on recent impulse legs
4. **Elliott Wave** — 5-wave impulse / 3-wave corrective count; Wave 3 entries preferred

Entries require **multi-framework confluence (≥2 layers agree)** plus all five
BINDING EV RULES: ≥2:1 R:R (hard), let winners run, with-momentum, no
mid-range, no churn. **Live execution on Gate.io testnet** (demo funds, $1k
reset 2026-06-11). Pairs BTC/ETH/SOL/XRP USDT perps.

Risk guardrails (hard limits the autonomy lives inside):
- Max leverage 20x · 1 position per asset, no fixed total cap · risk ≤2% equity/trade
- Every position gets a stop loss AND a take-profit immediately (≥2:1 R:R hard minimum)
- Max drawdown 10% of baseline ($1,000 baseline → $900 floor) → stop and alert
- No chasing, no averaging down, no holding through known news

## Modes

Two independent switches in `EXCHANGE_CONFIG.md`:

- **mode** — `live` places real orders via the adapter; `paper` simulates fills
  at real prices (local-memory only). Both read real market data.
- **network** (exchanges that have a testnet, e.g. Gate) — `testnet` uses demo
  funds (no real money); `mainnet` is real money.

**Current: Gate.io, `mode: live`, `network: testnet`** — real order execution
against demo funds. Going to real money = `network: mainnet` (+ rotated keys),
which is an explicit user decision, never the agent's. Keys come from
`secrets/.env`.

## Secrets & safety — read before committing

- **Never commit API keys.** They go in `secrets/.env`, which is gitignored.
  Not in `CLAUDE.md`, not in `EXCHANGE_CONFIG.md`, not in any tracked file.
- The git remote URL embeds a GitHub PAT — **rotate it before any real-money use.**
- The Telegram bot token lives in `secrets/.env` too. It was pasted in plaintext
  during setup, so consider `/revoke` in BotFather and replacing it.
- The Gate keys are testnet/demo (no real money). Real money requires
  `network: mainnet`, an explicit user decision.
- `TRADE_STATE.md` is gitignored (it churns every spawn); `TRADE_LOG.md` is
  tracked as the durable record.
- Live (testnet) execution is active by explicit user decision. Don't flip to
  `mainnet`, and don't widen risk guardrails, without an explicit ask.

## Notifications & control (Telegram)

**Telegram is currently OFF entirely** (user decision 2026-06-09). The code
(`notify/telegram.py`, `notify/telegram_listen.py`) is intact but not invoked.
The hourly cron produces in-session summaries only — no outbound Telegram sends,
no inbound bridge. Do NOT send Telegram or start the bridge unless the user
explicitly re-enables it. Token + chat_id remain in `secrets/.env` for when it's
re-enabled.

When Telegram is active, the protocol is:

**Outbound** — `notify/telegram.py` (send/test/chatid). The **orchestrator** sends
the *verified* hourly summary; drawdown/position events are prefixed `🚨 ALERT:`.

**Inbound (natural language)** — `notify/telegram_listen.py` long-polls Telegram;
on a message from the authorized `TELEGRAM_CHAT_ID` it appends to
`state/bot_inbox.jsonl` and EXITS — waking the orchestrator. Orchestrator reads the
inbox, interprets the request, pulls live data, replies, acts, truncates the inbox,
and relaunches the bridge.

```
python3 notify/telegram.py test            # outbound: connection ping
python3 notify/telegram.py send "text"     # outbound: send to the configured chat
python3 notify/telegram_listen.py          # inbound: run the NL bridge (background)
```

## Status

**LIVE on Gate.io testnet** (`mode: live`, `network: testnet` — real order execution,
demo funds). Gate adapter (`exchanges/gate/adapter.py`, APIv4 / HMAC-SHA512) fully
validated: `order → stop → cancel → close` round-trip clean. Trader runs **hourly**
(session-only cron, fires at `:00`) across BTC/ETH/SOL/XRP with stop + take-profit
on every position. Telegram is off; in-session summaries only.

**Active strategy (2026-06-11):** four-layer TA on 15m candles — price action,
order blocks, Fibonacci retracement, Elliott Wave. Entries require multi-framework
confluence (≥2 layers). Testnet reloaded to $1,000; floor $900.

Testnet host note: the old host `fx-api-testnet.gateio.ws` is dead (502); the live
host is `api-testnet.gateapi.io`. Keys are valid. See `exchanges/gate/NOTES.md`.

## TODO

Done:
- [x] Gate adapter built, testnet host blocker resolved, live order round-trip validated.
- [x] Autonomous hourly trading with stop+take-profit on every position.
- [x] Five BINDING EV RULES added after post-mortem (≥2:1 R:R, let winners run,
      with-momentum, no mid-range, no churn).
- [x] Strategy rebuilt (2026-06-11): 15m candles, order blocks, Fibonacci,
      Elliott Wave — multi-framework confluence required to enter.
- [x] Testnet reloaded to $1,000; new baseline/floor set ($1,000/$900).

Next:
- [ ] Build a track record under the new 4-layer TA strategy.
- [ ] Rotate the GitHub PAT embedded in the git remote URL before any real money.
- [ ] Only then consider `network: mainnet` (real money) — an explicit user
      decision, never the agent's.
