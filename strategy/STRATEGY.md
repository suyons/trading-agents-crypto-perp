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

From that, Claude forms a thesis: direction, conviction, and a reason. **Be
willing to trade: open a position on any reasonable directional thesis with a
clean invalidation — you do NOT need an A+ / high-conviction setup.** A
medium-confidence lean with a sensible stop and target is a trade, not a hold.
**Favor action**; HOLD only when you genuinely have no directional lean at all, or
you're already correctly positioned.

This is a deliberate, user-directed setting and it has swung (all 2026-06-03 →
2026-06-04): lowered to "trade more often" → raised to A+-only after a 5-trade
losing streak → **lowered again 2026-06-04** when the user said, on this *demo*
account, to stop sitting out and "be free to open any positions." Current setting:
**favor action / low bar.** This governs only *how readily* you act — it does NOT
relax the hard guardrails below. Two safety floors are NON-NEGOTIABLE regardless
of the bar: **every position gets a stop AND a take-profit (never naked), and risk
stays ≤2% equity/trade**, and the 10% drawdown breaker still halts trading. Within
those, take setups freely.

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
- **HOLD** — only when you genuinely have no directional lean, or you're already
  correctly positioned. NOT the default: if you can state a thesis + invalidation
  with a sensible stop and target, take it. When you do hold, state what you're
  watching: the trigger that would create a setup.

## Discipline (what NOT to do)

- Don't chase a move you missed — wait for the next setup.
- Don't average down on a loser — the stop handles it.
- Don't force a trade with *no* directional lean at all — but a reasonable thesis
  is enough; you needn't wait for the perfect setup (user-set: favor action on this
  demo). Every trade still carries a stop + take-profit and risks ≤2% equity.
- Don't hold through known high-impact news/announcements.
- Don't override the risk guardrails for any reason.

## Mode

Set in `exchanges/EXCHANGE_CONFIG.md`. Currently **Gate.io `mode: live`,
`network: testnet`** — real order execution against demo funds (no real money).
`paper` simulates fills at real prices; `network: mainnet` is real money and only
ever on explicit user instruction.
