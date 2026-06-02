# trading-agents

A testbed for **Claude Code's agent orchestration**. The workload happens to be
autonomous crypto trading, but the *subject under test* is the orchestration:
how a coordinator spawns, directs, and supervises trading sub-agents.

Two things are deliberately swappable and must never leak into names or
structure as hard dependencies:

- **The runtime.** Migrated from OpenClaw (Gemini 3.1 Pro) → Claude Code. May
  change again. Don't bake `claude`/`openclaw` into file or module names.
- **The exchange.** Currently Gate.io futures (testnet); the Aster adapter is
  retained but deactivated. Binance / Bybit / others must be a one-file swap
  (see `exchanges/`), never a rename or a refactor.

## Orchestration model

- **Orchestrator ("Mission Control")** — the main session. Coordinates, reviews,
  reports. Does **not** place trades itself. Spawns the trader for decisions.
- **Trader sub-agent** — defined in `.claude/agents/trader.md`. Spawned to make
  and execute one decision cycle, then report. Stays in its lane (see contract).
- **Exchange adapter** — isolated under `exchanges/<name>/`. The trader talks to
  an adapter interface, never to a specific exchange's quirks directly.

This separation is the whole point: swap the exchange, swap the runtime, or run
multiple traders in parallel without touching the orchestration logic.

## Target layout

```
CLAUDE.md                     # this file — orchestration + project contract
.gitignore                    # keys/state excluded (already in place)
strategy/STRATEGY.md          # canonical trading rules (to migrate)
exchanges/EXCHANGE_CONFIG.md  # active exchange + mode + pairs (NO keys)
exchanges/aster/              # adapter: endpoints, request signing, mappers
state/TRADE_STATE.md          # capital, open positions (gitignored — churns)
state/TRADE_LOG.md            # append-only decision log
secrets/.env                  # API keys (gitignored — NEVER committed)
.claude/agents/trader.md      # trader sub-agent definition
```

Migration from `/root/.openclaw/workspace/agents/trader/` is pending; populate
the above from those files (strategy, exchange config, state) — **except keys.**

## Trader contract (ported from the OpenClaw SOUL)

- Execute the strategy with precision. The user's rules are rules, not
  suggestions. If `STRATEGY.md` is missing/incomplete, ask before trading.
- Risk first: every position gets a stop loss set immediately. Never update
  state files until a trade is **confirmed**.
- Every spawn ends in a decision — enter, exit, adjust, or hold. "No setup, hold"
  is a valid and frequent outcome. Don't overtrade.
- Stay in your lane: read/write only this project's trading files. Anything
  outside, ask the orchestrator.
- Reporting is tight: P&L (·$ and %), open positions, last action + why, next
  watch. 3–5 lines, no essays.

## Current strategy (summary — canonical lives in `strategy/STRATEGY.md`)

**Fully autonomous, Claude-driven — no technical indicators.** Each cycle the
trader reasons over real market data (price, 24h range, funding, raw price
action, optional news) and decides discretionarily. Unproven by design.
**Live execution on Gate.io testnet** (demo funds, ~$1k). Pairs BTC/ETH/SOL/XRP
USDT perps (canonical list in `exchanges/EXCHANGE_CONFIG.md`).

Risk guardrails (hard limits the autonomy lives inside):
- Max leverage 20x · 1 position per asset, no fixed total cap · risk ≤2% equity/trade
- Every position gets a stop loss immediately (level discretionary, loss ≤2%)
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
- The Aster keys carried over from OpenClaw were exposed in plaintext —
  **rotate them on Aster** before any live use.
- `TRADE_STATE.md` is gitignored (it churns every spawn); `TRADE_LOG.md` is
  tracked as the durable record.
- Paper mode is the safe default. Don't switch to live without an explicit ask.

## Status

**LIVE on Gate.io testnet (validated 2026-06-02).** The Gate adapter
(`exchanges/gate/adapter.py`, Gate APIv4 / HMAC-SHA512) is running real order
execution against demo funds: `mode: live`, `network: testnet`. A full
`order -> stop -> cancel -> close` round-trip was validated with clean I/O
(balance ~1000 USDT, BTC entry 69651.1 / exit 69647.4, flat after).

The earlier "401 / outage" blocker is **resolved**: the old testnet host
`fx-api-testnet.gateio.ws` is permanently dead (502); the live host is
`api-testnet.gateapi.io`. The keys were always valid. The prior corrupted-I/O
claims (a "$10k balance", a "400 stop bug") are retracted and superseded — see
`exchanges/gate/NOTES.md`. The Aster paper adapter is retained, deactivated.

Security note: keys stay in gitignored `secrets/.env` (Aster + Gate, namespaced).
The Aster keys were exposed in plaintext during migration, and the git remote URL
embeds a GitHub PAT — rotate both before any real-money use. The Gate keys are
testnet/demo (no real money). Real money requires `network: mainnet`, an explicit
user decision.

## TODO

- [x] **Commit the baseline** under the `young` (`suyons`) identity — done.
- [x] **Verify secrets never leak** — `git status --ignored` keeps `secrets/` and
      `state/TRADE_STATE.md` ignored; re-check after any `.gitignore` edit.
- [x] **Aster keys** — using the existing keys per user decision. They were
      exposed in plaintext during migration; rotate on Aster before real money.
- [x] **Build the `exchanges/aster/` adapter** — `adapter.py` implements the
      common interface in `exchanges/INTERFACE.md` (public data + signed
      account/order, with a paper-safe order guard).
- [x] **Run a first paper decision cycle** — `trader` sub-agent spawned; decision
      logged to `state/TRADE_LOG.md`.
- [x] **Replace the starter strategy** — swapped to a fully autonomous,
      Claude-driven, no-indicator strategy (`strategy/STRATEGY.md`).

- [x] **Resolve the Gate access blocker** — the testnet API host had moved
      (`fx-api-testnet.gateio.ws` 502 -> `api-testnet.gateapi.io`). Same keys, 200.
- [x] **Validate the live round-trip on testnet** — order/stop/cancel/close all
      confirmed (2026-06-02); `order --stop` made fail-safe; `cancel` added.
- [x] **Flip `mode: live`** (network stays `testnet` = demo funds).

Next:
- [ ] Build a testnet track record (spawn `trader` for real decision cycles).
- [ ] Rotate the Aster keys **and** the GitHub PAT embedded in the git remote
      URL before any real-money use.
- [ ] Only then consider `network: mainnet` (real money) — an explicit user
      decision, never the agent's.
