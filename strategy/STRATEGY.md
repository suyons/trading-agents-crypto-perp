# Trading Strategy — Autonomous (Claude-driven)

The edge under test is **Claude's own judgment**, not a mechanical system. There
are **no technical indicators** — no moving averages, RSI, MACD, fixed
candle/volume triggers, or backtested signals. Each cycle, Claude reads the real
market state and decides with reasoning. This is intentionally discretionary and
unproven; the risk guardrails below are the hard limits that keep it survivable.

## How decisions are made (no indicators)

Every spawn, the trader pulls **real market data** via the active exchange
adapter and reasons over it:

- Current price, mark price, 24h change, 24h range (high/low), 24h volume
- Funding rate and next funding time (crowding / cost-of-carry signal)
- Recent raw price action (klines as *context to reason over*, never as an
  indicator trigger)
- Optionally: news / catalysts / sentiment via web search

From that, Claude forms a thesis: direction, conviction, and a reason. **Enter
only with a clear, stateable thesis.** No thesis → hold. Most cycles will be
holds; that is correct, not failure.

## Risk guardrails (HARD rules — non-negotiable)

These are not discretionary. The autonomy lives *inside* these limits.

1. Symbols: BTCUSDT, ETHUSDT, SOLUSDT perpetuals (Aster).
2. Max leverage: 20x.
3. Max risk per trade: **2% of equity**. Size so (entry→stop distance) × size ≤ 2% equity.
4. Max open positions: 2 — one per asset.
5. Max drawdown: 10% of starting capital → **stop trading and alert** (circuit breaker).
6. **Every position gets a stop loss, set the moment the position is opened.**
   The stop *level* is Claude's call, but the resulting loss must be ≤ 2% equity.

## Decision menu (every spawn ends in one)

- **ENTER** — clear thesis + acceptable risk. Set stop immediately. Optional
  take-profit at Claude's discretion (aim for ≥1.5:1 reward:risk when reasonable).
- **EXIT** — thesis invalidated, target reached, or risk/time no longer justified.
- **ADJUST** — move stop (e.g. to breakeven once meaningfully in profit), trim,
  or add within risk limits. No averaging *down* on losers.
- **HOLD** — no clear edge, or already correctly positioned. The default.

## Discipline (what NOT to do)

- Don't chase a move you missed — wait for the next setup.
- Don't average down on a loser — the stop handles it.
- Don't overtrade — "no setup, hold" is a valid and frequent outcome.
- Don't hold through known high-impact news/announcements.
- Don't override the risk guardrails for any reason.

## Mode

Paper by default (simulate fills at real prices). Live places real orders; switch
only on explicit user instruction via `exchanges/EXCHANGE_CONFIG.md`.
