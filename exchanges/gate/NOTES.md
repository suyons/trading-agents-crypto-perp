# Gate.io adapter

Status: **code complete; live access UNVERIFIED.** Implements the common
interface in `../INTERFACE.md`. Live execution is **held in paper**
(`../EXCHANGE_CONFIG.md mode: paper`) until signed access is confirmed.

> Honesty note: the session in which this adapter was built had a corrupted tool
> I/O channel (stale / duplicated / lagged output). Earlier apparent successes
> ("balance ~$10k", "entry/close validated", a "400 stop bug") came through that
> broken channel and are **retracted** — they were not reliably observed. The
> only coherent, multi-file-consistent signed result was **HTTP 401 INVALID_KEY**
> ("Invalid key provided"). Treat all live Gate behavior as UNCONFIRMED until
> re-run in a healthy session.

- API: Gate APIv4 futures, USDT-settled perpetuals. Base URLs:
  - testnet: `https://fx-api-testnet.gateio.ws`
  - mainnet: `https://api.gateio.ws`
  Selected by `network:` in `../EXCHANGE_CONFIG.md` (defaults to testnet).
- Auth: `GATE_API_KEY` / `GATE_SECRET_KEY` from `secrets/.env`, HMAC-SHA512
  (KEY / Timestamp / SIGN headers; body SHA-512 hashed into the sign string).
- Symbols use underscores (`BTC_USDT`); order size is in *contracts*. The adapter
  converts coin qty <-> contracts via each contract's `quanto_multiplier`.

## Blocker: Gate futures testnet appears DOWN
Diagnostic (5x each, all consistent):
  - public `…/contracts/BTC_USDT`  -> HTTP **502** (openresty gateway)  x5
  - signed `…/accounts` (balance)  -> HTTP **401 INVALID_KEY**          x5

Keyless public reads failing with 502 means the testnet gateway/backend itself
is unhealthy; the persistent 401 is most likely a symptom of that outage, not a
bad key. The keys are stored correctly and are testnet-origin (user-confirmed),
so the host matches.

Action: retry when the testnet recovers (public reads return 200). If signed
calls STILL 401 *after* public reads succeed, THEN it's a key issue — check the
testnet API key's Futures permission + IP allowlist, or regenerate it.

## To validate (in a healthy session, once keys/endpoint match)
1. `balance` / `positions` (signed reads) — confirm `200`, not `401`.
2. Tiny market `order` + `close` round-trip; verify flat + balance after.
3. `stop` / `--stop` price-trigger, AND make `order --stop` fail-safe: if the
   stop can't be placed, auto-close the entry so no unprotected position persists.

## Gotcha
Testnet has ~no trading activity, so `volume` / `high24h` / `low24h` / candle
bodies read ~0; only `price` / `mark` / `funding` track the real index.
