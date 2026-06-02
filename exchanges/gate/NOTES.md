# Gate.io adapter

Status: **VALIDATED LIVE on testnet (2026-06-02).** Implements the common
interface in `../INTERFACE.md`. `../EXCHANGE_CONFIG.md` is `mode: live`,
`network: testnet` (real order execution against Gate demo funds).

> Honesty note: an earlier session that built this adapter had a corrupted tool
> I/O channel (stale / duplicated / lagged output). Apparent successes from it
> ("balance ~$10k", "entry/close validated", a "400 stop bug") were **retracted**
> as unreliable. They have now been superseded by a clean re-validation (below);
> e.g. the real demo balance is ~1000 USDT (not $10k) and there is no 400 stop bug.

## Resolved blocker: the testnet API host had moved
The old host `fx-api-testnet.gateio.ws` is dead (returns HTTP 502 — that was the
whole "outage"/401 story). The live testnet futures API host is
**`api-testnet.gateapi.io`**. With the host corrected, the existing keys
authenticate fine (signed `/accounts` -> 200). The keys were never the problem.

## Validation round-trip (2026-06-02, clean single-call I/O)
- `balance` -> 1000.00 USDT available (note: `total` reads 0 in this cross /
  single-currency margin account; equity is derived from `available` instead).
- `order BTC BUY 0.0001 --force` -> filled @ 69651.1 (1 contract).
- `stop BTC BUY 68250 --force` -> accepted, status `open` (price-trigger works).
- `cancel BTC --force` -> stop -> `cancelled` (cancels orders + price_orders).
- `close BTC --force` -> filled @ 69647.4, position flat. Round-trip cost
  ~0.0073 USDT (fees + slippage on ~$7 notional).
- `order --stop` is now fail-safe: if the protective stop can't be placed, the
  entry is auto-closed so no unprotected position can persist.

- API: Gate APIv4 futures, USDT-settled perpetuals. Base URLs:
  - testnet: `https://api-testnet.gateapi.io`   (old `fx-api-testnet.gateio.ws` is dead/502)
  - mainnet: `https://api.gateio.ws`
  Selected by `network:` in `../EXCHANGE_CONFIG.md` (defaults to testnet).
- Auth: `GATE_API_KEY` / `GATE_SECRET_KEY` from `secrets/.env`, HMAC-SHA512
  (KEY / Timestamp / SIGN headers; body SHA-512 hashed into the sign string).
- Symbols use underscores (`BTC_USDT`); order size is in *contracts*. The adapter
  converts coin qty <-> contracts via each contract's `quanto_multiplier`.

## History of the (now-resolved) 502/401 blocker
For days, public reads returned 502 and signed reads 401 INVALID_KEY against
`fx-api-testnet.gateio.ws`. This was misdiagnosed as a "testnet outage." The real
cause: that host is permanently dead. Pointing the adapter at
`api-testnet.gateapi.io` made both public (200) and signed (200) reads work
immediately with the same keys. Lesson: when a *keyless* endpoint also fails,
suspect the host/URL before concluding "outage" — and test an alternate host.

## Gotcha
Testnet has ~no trading activity, so `volume` / `high24h` / `low24h` / candle
bodies read ~0; only `price` / `mark` / `funding` track the real index.
