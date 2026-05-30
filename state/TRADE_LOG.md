# Trade Log

Append-only record of every decision (entries, exits, adjustments, and holds).
This is the durable history — it is tracked in git, unlike `TRADE_STATE.md`.

Format per entry:

```
## YYYY-MM-DD HH:MM UTC — <exchange> <mode>
- Decision: ENTER | EXIT | ADJUST | HOLD
- Symbol / side / size / leverage:
- Entry / stop / take-profit:
- Thesis: ONE falsifiable sentence — the directional claim and why (the edge),
  grounded in the real data observed this cycle.
- Invalidation: the SPECIFIC, observable condition that proves the thesis wrong
  and forces an exit — a price level or structural break, not a vibe. For an
  ENTER this is normally where the stop sits (and why there). For a HOLD, state
  instead the concrete trigger that WOULD create a setup (what you're waiting for).
- Reason: supporting detail / data / context (funding, range, news).
- Resulting state: capital, open positions
```

The Thesis/Invalidation discipline is deliberate: stating a falsifiable claim and
its kill-condition up front forces tighter reasoning and makes every call
auditable after the fact. Every entry — including HOLDs — fills both lines.

---
