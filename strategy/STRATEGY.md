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

From that, Claude forms a thesis: direction, conviction, and a reason. **Favor
action — but only among setups that clear the five BINDING EV RULES below**
(≥2:1 reward:risk, with-momentum, at a range edge, right regime, let winners run).
"Favor action" means: when a setup DOES clear those gates, take it — don't sit out
a qualifying trade waiting for perfection. It does NOT mean take low-quality fills:
a medium-confidence lean that can't make ≥2:1 from a clean structural stop, or that
fades a move / sits mid-range, is a **HOLD**, not a trade. The post-mortem proved
that taking marginal setups "to be active" is exactly what produced −12%. Quality
gates first; action within them.

This is a deliberate, user-directed setting and it has swung (all 2026-06-03 →
2026-06-04): lowered to "trade more often" → raised to A+-only after a 5-trade
losing streak → **lowered again 2026-06-04** when the user said, on this *demo*
account, to stop sitting out and "be free to open any positions." Current setting:
**favor action / low bar.** This governs only *how readily* you act — it does NOT
relax the hard guardrails below. Two safety floors are NON-NEGOTIABLE regardless
of the bar: **every position gets a stop AND a take-profit (never naked), and risk
stays ≤2% equity/trade**, and the 10% drawdown breaker still halts trading. Within
those, take setups freely.

## What the track record says — BINDING EV RULES (added 2026-06-09 post-mortem)

A full reverse-engineering of the first ~23 closed trades ($999.99 → ~$877, −12%)
found the losing was **structural, not bad luck**. The numbers:
**26% win rate** at a realized **~1.37:1** reward:risk → breakeven needs **42%** →
**expectancy −$4.46/trade.** Plus ~$43 bled to fees/funding from over-trading chop.
The five leaks and their fixes are now RULES, ranked by impact:

1. **Minimum reward:risk = 2:1, HARD. Below 2:1 → NO TRADE (HOLD).** The math:
   at our ~26–35% hit rate we need ≥2:1 just to survive; we were taking 1.16–1.5:1.
   This is the single biggest fix. Compute it from the *real* stop/TP before entry;
   if the clean structural stop and the realistic target don't give ≥2:1, pass.

2. **Stop truncating winners. LET WINNERS RUN TO THE TP.** Every win that actually
   paid HIT its take-profit (or a stop trailed only after a real run). Every trade
   we "managed" by trailing to breakeven while it was barely green got SCRATCHED to
   ~$0 (2+ SOL longs gave back +$8 / +$18 peaks). Therefore:
   - Do NOT move the stop to breakeven while a trade is only marginally green.
   - Move the stop ONLY after ≥**1.5R** of open profit, and ONLY behind a
     **confirmed** structural pivot (a *completed* higher-low for a long / lower-high
     for a short) — NEVER into the live noise band, NEVER "to BE because it's green."
   - Default to letting price reach the pre-set TP. The TP is the plan; honor it.

3. **Trade WITH momentum, not against it.** The loss cluster is counter-trend
   FADES in chop — shorting bounces, buying tops, catching knives. Every winner was
   with-structure / with-trend. RULE: no fading a move without a *confirmed
   rejection* at a level; no buying into resistance; no shorting into support.

4. **Regime filter — NO MID-RANGE ENTRIES.** In a range/chop regime, trade ONLY the
   range EDGES (buy a support reclaim, short a resistance rejection) and only with
   ≥2:1 to the opposite edge. In a trend, trade with-trend pullbacks. Mid-range
   "favor-action" fills repeatedly scratched — they are now BANNED.

5. **Don't overtrade chop (fees are real).** "Favor action" means do not skip a
   QUALIFYING setup (≥2:1 + with-momentum + at an edge); it does NOT mean take
   marginal ones. Frequency is fine when quality holds; churning low-EV trades just
   feeds fees. Patience at the edge IS the edge in chop.

**One-line soul:** *small losses, big winners — take only ≥2:1 with-momentum setups
at range edges, and let them run to target.* These rules sit ABOVE "favor action":
favor action operates only among setups that already clear all five.

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
   **Running MULTIPLE concurrent positions is explicitly endorsed by the user
   (2026-06-04, "I'm greedy than conservative") — use it, don't default to one at a
   time.** Caveat (judgment, not a ban): BTC/ETH/SOL/XRP are highly correlated, so
   N like-direction crypto positions ≈ one N×-sized bet — size each so the
   *aggregate* worst-case (all stopping together) still leaves a buffer above the
   10% breaker, and prefer the best 2–4 theses over forcing all four.
5. Max drawdown: 10% of the **breaker baseline** → **stop trading and alert**
   (circuit breaker). **Baseline RESET to $908.45 on 2026-06-04** (was the original
   $999.99) — user's explicit decision after a ~-9% drawdown left the account
   pinned at the old breaker, to give fresh room to keep trading. So the active
   breaker floor is **$817.6** (10% below $908.45), NOT $900. If equity ≤ $817.6 →
   no new positions, flatten/protect, ALERT. (Note: real cumulative loss from the
   true $999.99 start is larger than 10% if this floor is hit — the user accepted
   that tradeoff when resetting.)
6. **Every position gets BOTH a stop loss and a take-profit, set the moment the
   position is opened — decide both levels *before* entering.** Place them with
   the entry in one shot: `order <SYM> <SIDE> <QTY> --stop <SL> --tp <TP>`. The
   *levels* are Claude's call, but the stop's loss must be ≤ 2% equity, and the
   take-profit must be **≥2:1 reward:risk — HARD minimum (EV rule 1); below 2:1 do
   NOT enter.** The stop is the hard safety net (if it can't be placed, the entry is
   auto-closed); the take-profit is the target — let price reach it (EV rule 2). No
   naked positions — never hold without a stop.

## Decision menu (every spawn ends in one)

Before acting, articulate the decision as a **falsifiable thesis + an explicit
invalidation** (the concrete condition that proves it wrong). If you cannot state
a clear invalidation, you do not have a trade — default to HOLD. Both are recorded
in every `TRADE_LOG.md` entry (see its format). State the thesis as a claim you
could be proven wrong on, not a vague lean; the invalidation must be observable
(a price level / structural break), and for an ENTER it should line up with where
the stop sits.

- **ENTER** — clear thesis + explicit invalidation + acceptable risk, AND it clears
  all five EV rules: ≥2:1 reward:risk, with-momentum (not a fade lacking a confirmed
  rejection), at a range EDGE (not mid-range), in the right regime. Decide stop AND
  take-profit first, then enter with both attached (`--stop` + `--tp`). If it doesn't
  clear ≥2:1 at a clean structural stop, it is NOT a trade — HOLD.
- **EXIT** — thesis invalidated, target reached, or risk/time no longer justified.
- **ADJUST** — trail the stop ONLY after ≥1.5R of open profit and ONLY behind a
  *confirmed* structural pivot (completed higher-low for a long / lower-high for a
  short) — NEVER to breakeven just because it's green, NEVER into the live noise band
  (EV rule 2: that scratched our winners). Trim/add within risk limits. No averaging
  *down* on losers. Default: leave the position to run to its pre-set TP.
- **HOLD** — only when you genuinely have no directional lean, or you're already
  correctly positioned. NOT the default: if you can state a thesis + invalidation
  with a sensible stop and target, take it. When you do hold, state what you're
  watching: the trigger that would create a setup.

## Discipline (what NOT to do)

- Don't chase a move you missed — wait for the next setup.
- Don't average down on a loser — the stop handles it.
- **Don't take any setup under 2:1 reward:risk** — it's negative-EV at our hit rate.
- **Don't fade a move without a confirmed rejection** (no shorting into support / no
  buying into resistance / no knife-catching) — trade WITH momentum.
- **Don't enter mid-range** — only range edges (support reclaim / resistance reject).
- **Don't trail to breakeven while barely green** — it scratched our winners; trail
  only after ≥1.5R behind confirmed structure, else let the TP work.
- **Don't churn the chop to "stay active"** — fees compound; patience at the edge is
  the edge. Favor action only among setups that clear the five EV rules.
- Don't hold through known high-impact news/announcements.
- Don't override the risk guardrails for any reason.

## Mode

Set in `exchanges/EXCHANGE_CONFIG.md`. Currently **Gate.io `mode: live`,
`network: testnet`** — real order execution against demo funds (no real money).
`paper` simulates fills at real prices; `network: mainnet` is real money and only
ever on explicit user instruction.
