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

## Blocker: 401 INVALID_KEY on signed calls (testnet endpoint)
Signed requests to `fx-api-testnet.gateio.ws` returned `401 {"label":
"INVALID_KEY"}`. INVALID_KEY means the API key string is not recognized by THIS
endpoint (it is not a signature error). Most likely cause: **the keys were
generated for a different Gate environment than the one being hit.** Gate keeps
these separate:
  - Futures **testnet** keys (created on Gate's testnet site) work only on
    `fx-api-testnet.gateio.ws`.
  - **Mainnet** keys (gate.com) work only on `api.gateio.ws`.
  - Gate **"Demo Trading"** is yet another context.
Resolve by confirming where the "Demo" keys were created, then set `network:`
(and thus the base URL) to match. (A secondary possibility is an IP allowlist on
the key.)

## To validate (in a healthy session, once keys/endpoint match)
1. `balance` / `positions` (signed reads) — confirm `200`, not `401`.
2. Tiny market `order` + `close` round-trip; verify flat + balance after.
3. `stop` / `--stop` price-trigger, AND make `order --stop` fail-safe: if the
   stop can't be placed, auto-close the entry so no unprotected position persists.

## Gotcha
Testnet has ~no trading activity, so `volume` / `high24h` / `low24h` / candle
bodies read ~0; only `price` / `mark` / `funding` track the real index.
