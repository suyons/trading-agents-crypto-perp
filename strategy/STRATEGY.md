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

From that, Claude forms a thesis: direction, conviction, and a reason. **High
conviction only: enter solely on a clean, A+ setup — a clear structure (decisive
break-with-room or a clean rejection/held higher-low), thesis + invalidation, and
R:R ≥ 2.** A merely medium or messy read is a HOLD, not a trade. **HOLD is the
default**; most cycles will and should be holds. Quality over activity.

This selectivity is a deliberate, user-directed setting (the conviction bar was
*lowered* on 2026-06-03 to "trade more often", then **raised back up on 2026-06-03
after that produced a 5-trade losing streak in a whipsaw tape** — ~-4% drawdown).
The lesson stuck: in a chop/whipsaw regime, trading more often just bleeds via
small risk-capped losses, so the bar is high again — take few, clean, high-R:R
setups and sit out the rest. This changes only *how readily* you act; it never
touches the hard guardrails below (size, stop discipline, no chasing). When in
doubt, HOLD — capital preservation beats forcing a marginal trade.

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
- **HOLD** — **the default.** No A+ setup, only a medium/messy read, or already
  correctly positioned. If the setup isn't clean and high-R:R (≥2), HOLD and state
  what you're watching: the concrete trigger that would create a real setup. Most
  cycles end here — that is correct, not failure.

## Discipline (what NOT to do)

- Don't chase a move you missed — wait for the next setup.
- Don't average down on a loser — the stop handles it.
- Don't overtrade — "no setup, hold" is a valid and frequent outcome, and the
  default whenever the setup isn't clean and high-R:R. In a chop/whipsaw tape,
  sitting out is the edge.
- Don't hold through known high-impact news/announcements.
- Don't override the risk guardrails for any reason.

## Mode

Set in `exchanges/EXCHANGE_CONFIG.md`. Currently **Gate.io `mode: live`,
`network: testnet`** — real order execution against demo funds (no real money).
`paper` simulates fills at real prices; `network: mainnet` is real money and only
ever on explicit user instruction.
