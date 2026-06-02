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

**Fully autonomous, Claude-driven — no technical indicators.** Each cycle the
trader reasons over real market data (price, 24h range, funding, raw price
action, optional news) and decides discretionarily, stating a falsifiable thesis
and its invalidation. Unproven by design. **Live execution on Gate.io testnet**
(demo funds, ~$1k). Pairs BTC/ETH/SOL/XRP USDT perps (canonical list in
`exchanges/EXCHANGE_CONFIG.md`).

Risk guardrails (hard limits the autonomy lives inside):
- Max leverage 20x · 1 position per asset, no fixed total cap · risk ≤2% equity/trade
- Every position gets a stop loss AND a take-profit immediately (levels
  discretionary; stop loss ≤2% equity, aim ≥1.5:1 reward:risk)
- Max drawdown 10% → stop and alert
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

Channel is swappable like the exchange. Token + chat_id live in `secrets/.env`
(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). All notifications are best-effort — a
Telegram failure must never break a trading cycle.

**Outbound** — `notify/telegram.py` (send/test/chatid). The **orchestrator** sends
the *verified* hourly summary after reconciling against the exchange (the trader
doesn't notify); drawdown/position events are prefixed `🚨 ALERT:`.

**Inbound (natural language)** — `notify/telegram_listen.py` is a thin BRIDGE,
not a command parser. A script can't reason, so replies come from the Claude
orchestrator. The bridge long-polls Telegram; on a message from the authorized
`TELEGRAM_CHAT_ID` (others ignored) it appends to `state/bot_inbox.jsonl`, sends a
typing indicator, and EXITS (`__INBOX__ n`) — which wakes the orchestrator. It
runs only while the session is alive; the hourly cron relaunches it if it died.

**Orchestrator bridge protocol** — when the bridge exits with pending inbox (you
are notified the background task ended), do this, then continue:
1. Read `state/bot_inbox.jsonl` — the queued user message(s).
2. For each: interpret the free-form request, pull live data via the adapter,
   reason, and reply with `notify/telegram.py send "..."`. Take any requested
   action — analysis (just reply), `close`/`flatten` (adapter `close`+`cancel`),
   `pause`/`resume` (create/remove `state/trading.paused`), or a full cycle / new
   trade (spawn the `trader` sub-agent). Honor the same risk rules and chat-lock.
3. Truncate `state/bot_inbox.jsonl` (only after replying).
4. Relaunch the bridge in the background: `python3 notify/telegram_listen.py`.

State files (all gitignored): `bot_inbox.jsonl` (queue), `bot_offset` (getUpdates
cursor — prevents message loss across the exit/relaunch handoff), `trading.paused`
(pause flag the hourly cron honors). Each message round-trips through an
orchestrator turn, so expect ~tens of seconds of latency.

```
python3 notify/telegram.py test            # outbound: connection ping
python3 notify/telegram.py send "text"     # outbound: send to the configured chat
python3 notify/telegram_listen.py          # inbound: run the NL bridge (background)
```

## Status

**LIVE on Gate.io testnet (validated 2026-06-02).** The Gate adapter
(`exchanges/gate/adapter.py`, Gate APIv4 / HMAC-SHA512) runs real order execution
against demo funds: `mode: live`, `network: testnet`. A full
`order -> stop -> cancel -> close` round-trip was validated with clean I/O, and
the trader runs **hourly** (session-only cron, `:07`) across BTC/ETH/SOL/XRP, each
position bracketed with a stop + take-profit, and a verified summary is pushed to
Telegram each cycle (`notify/telegram.py`).

The earlier "401 / outage" blocker is **resolved**: the old testnet host
`fx-api-testnet.gateio.ws` is permanently dead (502); the live host is
`api-testnet.gateapi.io`. The keys were always valid. Prior corrupted-I/O claims
(a "$10k balance", a "400 stop bug") are retracted and superseded — see
`exchanges/gate/NOTES.md`.

## TODO

Done:
- [x] Baseline committed under the `young` (`suyons`) identity; secrets verified
      never to leak (`secrets/` + `state/TRADE_STATE.md` gitignored).
- [x] Built the Gate adapter to `exchanges/INTERFACE.md`; resolved the access
      blocker (testnet host had moved) and validated a live order/stop/cancel/close
      round-trip. Made `order --stop` fail-safe; added `cancel` and take-profit.
- [x] Autonomous, no-indicator strategy with mandatory stop+take-profit and a
      falsifiable thesis + invalidation per decision.
- [x] Flipped `mode: live` (network stays `testnet` = demo funds); hourly trader
      schedule armed.

Next:
- [ ] Build a testnet track record (the hourly cycles accumulate it).
- [ ] Rotate the GitHub PAT embedded in the git remote URL before any real money.
- [ ] Only then consider `network: mainnet` (real money) — an explicit user
      decision, never the agent's.
