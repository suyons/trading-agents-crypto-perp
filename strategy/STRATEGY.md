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

From that, Claude forms a thesis: direction, conviction, and a reason. **Bias to
action: take any setup backed by a reasonable, stateable thesis and a clean
invalidation — you do not need high conviction.** A *medium*-confidence read with
sound risk:reward is a trade, not a hold. Reserve HOLD for when there is genuinely
no edge, or you're already correctly positioned — not for mild uncertainty.

This is a deliberate, user-directed setting (a *lower conviction bar*, set
2026-06-03). It changes only *how readily* you act — it never widens the hard
guardrails below: a looser entry bar is not a bigger bet, a wider stop, more
leverage, or licence to chase. Size, stop discipline, and the no-chasing rule are
unchanged. The point is to express more views, not to take reckless ones.

## Risk guardrails (HARD rules — non-negotiable)

These are not discretionary. The autonomy lives *inside* these limits.

1. Symbols: BTC, ETH, SOL, XRP USDT perpetuals — the active exchange's native
   symbols (see `exchanges/EXCHANGE_CONFIG.md`; currently Gate `BTC_USDT` etc.).
2. Max leverage: 20x.
3. Max risk per trade: **2% of equity**. Size so (entry→stop distance) × size ≤ 2% equity.
4. Max open positions: **no fixed total cap** — but still **one position per
   asset** (no stacking/averaging the same symbol). With the current 4-symbol
   universe that is effectively up to 4 concurrent positions. Aggregate risk is
   now bounded by per-trade risk × positions (≤2% each) and the drawdown circuit
   breaker below, not by a position count.
5. Max drawdown: 10% of starting capital → **stop trading and alert** (circuit breaker).
6. **Every position gets BOTH a stop loss and a take-profit, set the moment the
   position is opened — decide both levels *before* entering.** Place them with
   the entry in one shot: `order <SYM> <SIDE> <QTY> --stop <SL> --tp <TP>`. The
   *levels* are Claude's call, but the stop's loss must be ≤ 2% equity, and aim
   for a take-profit of ≥1.5:1 reward:risk when reasonable. The stop is the hard
   safety net (if it can't be placed, the entry is auto-closed); the take-profit
   is the target. No naked positions — never hold without a stop.

## Decision menu (every spawn ends in one)

Before acting, articulate the decision as a **falsifiable thesis + an explicit
invalidation** (the concrete condition that proves it wrong). If you cannot state
a clear invalidation, you do not have a trade — default to HOLD. Both are recorded
in every `TRADE_LOG.md` entry (see its format). State the thesis as a claim you
could be proven wrong on, not a vague lean; the invalidation must be observable
(a price level / structural break), and for an ENTER it should line up with where
the stop sits.

- **ENTER** — clear thesis + explicit invalidation + acceptable risk. Decide stop
  AND take-profit levels first, then enter with both attached (`--stop` + `--tp`).
  Aim for ≥1.5:1 reward:risk when reasonable.
- **EXIT** — thesis invalidated, target reached, or risk/time no longer justified.
- **ADJUST** — move stop (e.g. to breakeven once meaningfully in profit), trim,
  or add within risk limits. No averaging *down* on losers.
- **HOLD** — *genuinely* no edge, or already correctly positioned. Not the
  fallback for mild uncertainty: if you can state a thesis + invalidation with
  acceptable risk, take it. Still state what you're watching: the concrete trigger
  that would create a setup.

## Discipline (what NOT to do)

- Don't chase a move you missed — wait for the next setup.
- Don't average down on a loser — the stop handles it.
- Don't overtrade *for its own sake* — but don't sit out a real setup either.
  "No setup, hold" is valid only when there's genuinely no edge, not as a default.
- Don't hold through known high-impact news/announcements.
- Don't override the risk guardrails for any reason.

## Mode

Set in `exchanges/EXCHANGE_CONFIG.md`. Currently **Gate.io `mode: live`,
`network: testnet`** — real order execution against demo funds (no real money).
`paper` simulates fills at real prices; `network: mainnet` is real money and only
ever on explicit user instruction.
