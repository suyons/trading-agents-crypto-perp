# Gate.io adapter

Status: **built; reads + market entry/close validated live; protective stop has
a bug.** Implements the common interface in `../INTERFACE.md`. Live execution is
currently **held in paper** (`../EXCHANGE_CONFIG.md mode: paper`) until the stop
path is fixed and revalidated.

- API: Gate APIv4 futures, USDT-settled perpetuals. Base URLs:
  - testnet: `https://fx-api-testnet.gateio.ws` (demo funds — no real money)
  - mainnet: `https://api.gateio.ws` (real money)
  Selected by `network:` in `../EXCHANGE_CONFIG.md` (defaults to testnet).
- Auth: `GATE_API_KEY` / `GATE_SECRET_KEY` from `secrets/.env`, HMAC-SHA512
  signing (KEY / Timestamp / SIGN headers; request body is SHA-512 hashed into
  the signature string). Public market data needs no keys.
- Symbols use underscores (`BTC_USDT`). Order size on Gate is in **contracts**;
  the adapter converts coin qty <-> contracts via each contract's
  `quanto_multiplier`, so the CLI stays in coin units.
- `close`/`stop` adapt to the account's one-way vs hedge (dual) position mode at
  runtime. `cancel` clears resting + price-triggered orders for a contract.

## Validated live (testnet)
- `price` / `snapshot` — real prices via the index (BTC ~111,400).
- `balance` — demo account funded **~$10,005 USDT** (signing works).
- `positions` — reads correctly.
- `order` (market entry) + `close` — a tiny BTC round-trip opened then closed a
  real testnet position; account returned flat with balance ~$10,005.

## Known bug — protective stop (`--stop` / `stop` / `_place_stop`)
Gate rejects the price-triggered stop:
`400 INVALID_PARAM_VALUE: "trigger price 108075.6 must <= 111385.7 (mark price)
for a buy-to-open stop, or use rule 1"` — the price-order is built with the
wrong side/rule. And because `order --stop` places the entry FIRST and the stop
SECOND, a stop failure leaves an **unprotected position** (the test had to close
it manually). Fixes needed:
1. Correct the price-order side/rule: long stop = sell-to-close, trigger below
   mark; short = buy-to-close, trigger above. Verify against Gate's docs.
2. Make `order --stop` fail-safe: if the stop can't be placed, auto-close the
   entry so no unprotected position can persist.
Revalidate in a healthy session — this one's tool I/O was corrupting output.

## Gotcha
Testnet has ~no trading activity, so `volume` / `high24h` / `low24h` / candle
bodies read ~0; only `price` / `mark` / `funding` track the real index. The
autonomous trader should lean on price + funding + web research for context, not
testnet volume/range.
