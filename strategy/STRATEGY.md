# Trading Strategy — Autonomous (Claude-driven)

## Technical Analysis Framework

Primary timeframe: **15m candles** — pull the last 100 bars per pair (`klines <PAIR> 15m 100` = ~25h of data). The last **completed (closed)** 15m bar is the primary structure reference. Never base a decision on the in-progress candle.

Each cycle the trader applies four analysis layers, then gates any setup through the five BINDING EV RULES before acting.

---

### Layer 1 — Price Action

- Map the **trend structure**: higher-highs / higher-lows (uptrend), lower-highs / lower-lows (downtrend), or range-bound chop.
- Identify **key levels**: recent swing highs/lows, structure breaks (the last level that broke and flipped), and range edges (the most recent swing high = resistance, swing low = support).
- Read **candlestick context at levels**: rejection wicks, engulfing bars, inside bars. These confirm or deny a level hold — they don't trigger trades on their own, but they add weight.
- Classify the current regime: trending, ranging, or transitional. The regime governs which entries are valid (Rule 4 below).

---

### Layer 2 — Order Blocks (OBs)

An order block is the **last significant candle before a strong impulsive move** — it marks where institutional orders were placed.

- **Bullish OB**: the last *down-close* (red) candle (or cluster of red candles) immediately before a strong bullish impulse. Price often returns to this zone for support on retracements.
- **Bearish OB**: the last *up-close* (green) candle (or cluster) immediately before a strong bearish impulse. Price often returns to this zone for resistance on retracements.
- **OB zone**: use the body (open–close) of the OB candle as the core zone. Wicks extending beyond are noted as the full range but the body is the primary magnet.
- **Validity**: only mark OBs that preceded a *strong, impulsive, multi-candle move* away from them. A weak drift does not validate an OB. Fresh OBs (not yet revisited) are stronger than stale ones (already tapped ≥2 times).
- **Using OBs**: enter long at a bullish OB on a pullback (look for a rejection wick or confirmation candle closing back above the OB's high). Enter short at a bearish OB on a retrace (look for a rejection candle closing back below the OB's low). Stop goes just beyond the OB's extreme (below the wick low for a bullish OB long, above the wick high for a bearish OB short).

---

### Layer 3 — Fibonacci Retracement

- Identify the **most significant recent swing leg** on the 15m chart — the impulse move that matters (the last strong directional leg, not noise).
- Apply standard Fib levels: **0.236 / 0.382 / 0.5 / 0.618 / 0.786**.
- **In an uptrend**: look for long entries at the **0.382–0.618 retracement** of the most recent bullish impulse leg. The 0.618 is the "golden ratio" retracement — deep but still valid; below it suggests the prior impulse is failing.
- **In a downtrend**: look for short entries at the **0.382–0.618 retracement** of the most recent bearish impulse leg.
- **Confluence is everything**: a Fib level landing on an OB zone, a structural S/R level, or an Elliott Wave target is a high-probability entry area. A lone Fib level with no other confluence is weak — weight it accordingly.
- Stop placement: below the swing low (for longs) or above the swing high (for shorts) — not inside the Fib zone. This is also where the 2:1 R:R check starts.

---

### Layer 4 — Elliott Wave

Basic 5-wave impulse (Waves 1–5) in the direction of the trend; 3-wave correction (A–B–C) against it.

**Hard rules (violations invalidate the count):**
- Wave 2 never retraces more than 100% of Wave 1.
- Wave 3 is never the shortest among Waves 1, 3, 5.
- Wave 4 never overlaps Wave 1's price territory (in a standard non-diagonal impulse).

**How to use it:**
- Identify which wave the current price action is in. Label from the most recent clear swing low (for a bullish count) or high (for a bearish count).
- **Wave 3 trades** (highest conviction): strong, extended moves — target ≥1.618× Wave 1's length from the Wave 2 low. Enter at the Wave 2 retracement (ideally at 0.382–0.618 Fib + bullish OB).
- **Wave 5 trades** (lower conviction): often truncates or shows momentum divergence — use tighter targets (equal to Wave 1, or 0.618× Wave 1 if waves 1–3 are extended). Watch for divergence; exit before the target if momentum fades.
- **After a 5-wave impulse**: expect a 3-wave A–B–C correction back to at minimum the Wave 4 territory. Use this to anticipate where the next impulsive leg begins.
- **A–B–C corrective targets**: Wave C often equals Wave A in length. Wave B retraces 0.382–0.786 of Wave A.
- Apply Elliott counts primarily to **BTC** (clearest structure); use as confirmation on ETH/SOL/XRP, which follow BTC's lead.

---

### Confluence — the entry standard

**Strongest setups (take decisively):** ≥2 frameworks agree on the same level/direction.
- **Long**: price retraces to a Fib 0.382–0.618 that lands on a bullish OB, within Wave 2 or Wave 4 territory, AND price action shows a confirmed rejection (wick or engulfing candle closing back above the OB high).
- **Short**: price retraces to a Fib 0.382–0.618 that lands on a bearish OB, within Wave B or at a key resistance level, AND a rejection candle confirms.

**Single-framework setups (require stronger confirmation):** only one layer is calling the level. These are lower conviction — require a very clear price action confirmation (full engulfing candle, sharp rejection wick) before entering. Still must clear all five EV rules.

**No-confluence setups: DO NOT ENTER** — if none of the four layers agree on a level/direction, there is no trade. HOLD.

---

## Risk guardrails (HARD — non-negotiable)

1. **Symbols**: BTC, ETH, SOL, XRP USDT perpetuals — Gate `BTC_USDT` / `ETH_USDT` / `SOL_USDT` / `XRP_USDT` (per `exchanges/EXCHANGE_CONFIG.md`).
2. **Max leverage**: 20x.
3. **Max risk per trade**: **2% of equity**. Size so `(entry − stop) × qty ≤ 2% equity`.
4. **Positions**: one per asset (no stacking/averaging the same symbol). Up to 4 concurrent positions. Multiple concurrent positions are explicitly endorsed — use the best 2–4 theses, don't force all four. Caveat: BTC/ETH/SOL/XRP are correlated — size so the aggregate worst-case (all stopping together) still clears the drawdown floor.
5. **Max drawdown**: 10% of the breaker baseline → **stop trading and alert**. Active baseline: **$1,000.00** (testnet reload 2026-06-11), floor **$900.00**. If equity ≤ $900 → no new positions, flatten, alert.
6. **Every position gets BOTH a stop loss AND a take-profit**, set atomically on entry: `order <SYM> <SIDE> <QTY> --stop <SL> --tp <TP>`. Stop ≤ 2% equity loss. TP must give ≥2:1 R:R. No naked positions, ever.

---

## Five BINDING EV RULES (post-mortem 2026-06-09 — non-negotiable)

1. **≥2:1 reward:risk, HARD.** Compute from the real structural stop + realistic TP. Below 2:1 → HOLD, no exceptions.
2. **Let winners run to the TP.** No trailing to breakeven while barely green — it scratches winners. Trail only after ≥1.5R open profit behind a *confirmed* structural pivot (completed higher-low for long / lower-high for short). Never trail into the live noise band. Default: let the TP work.
3. **Trade WITH momentum.** No fading without a confirmed rejection. No buying into resistance. No shorting into support. No knife-catching.
4. **No mid-range entries.** Only range edges (support reclaim / resistance rejection) in chop; with-trend pullbacks to OB/Fib confluence in a trend. Mid-range = no edge = banned.
5. **Don't churn chop.** Favor action ONLY among setups that clear (1)–(4). Otherwise HOLD.

---

## Decision menu

Every spawn ends in one of these. State a **falsifiable thesis + explicit invalidation** before acting.

- **ENTER** — multi-framework confluence (≥2 layers agree), ≥2:1 R:R, with-momentum, at a range edge or corrective pullback target. Place stop + TP atomically on entry. If it can't clear ≥2:1 at a clean structural stop, HOLD.
- **EXIT** — thesis invalidated, TP reached, or risk/time no longer justified.
- **ADJUST** — trail stop only after ≥1.5R open profit, behind a confirmed structural pivot. Never to BE while barely green. Never into noise. Default: let TP work.
- **HOLD** — no qualifying setup. State the specific level and condition that would create one.

---

## Discipline

- No chasing missed moves.
- No averaging down.
- No setup under 2:1 R:R.
- No fading without confirmed rejection.
- No mid-range entries.
- No trailing to BE while barely green.
- No churning chop.
- No holding through known high-impact news.
- No overriding risk guardrails.

---

## Mode

`exchanges/EXCHANGE_CONFIG.md`: currently **Gate.io `mode: live`, `network: testnet`** — real execution, demo funds. `network: mainnet` = real money, explicit user decision only.
