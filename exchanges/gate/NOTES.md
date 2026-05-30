# Gate.io adapter

Status: **built; reads validated live.** Order/close/stop/cancel are wired but
**pending a live round-trip validation** — Gate testnet was returning
intermittent `502 Bad Gateway` during setup, so a clean execution test hasn't
been confirmed yet. Implements the common interface in `../INTERFACE.md`.

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
- `price` / `snapshot` — real prices via the index (e.g. BTC ~111,449).
- `balance` — demo account funded **~$10,005 USDT** (signing confirmed working).
- `positions` — empty.

## Pending validation
- `order`, `close`, `stop`, `cancel` — need a clean window without testnet 502s.

## Gotcha
Testnet has ~no trading activity, so `volume` / `high24h` / `low24h` / candle
bodies read ~0; only `price` / `mark` / `funding` track the real index. The
autonomous trader should lean on price + funding + web research for context, not
testnet volume/range.
