# Aster DEX adapter

Status: **built** — `adapter.py` implements the common interface in
`../INTERFACE.md`. The trader calls that CLI, never raw Aster endpoints.

- Futures API base: `https://fapi.asterdex.com` (Binance-compatible futures API).
- Pairs are **USDT perpetuals** (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`). Aster has no
  USDC perps — `BTCUSDC`/`ETHUSDC` return `Invalid symbol`.
- Supports very high leverage (advertised up to 1001x) — strategy caps it at 20x.
- Auth: `API_KEY` / `SECRET_KEY` from `secrets/.env`, HMAC-SHA256 request signing
  (`X-MBX-APIKEY` header). Public market data needs no keys; account/order
  endpoints do. `order` refuses to run unless mode is `live` (or `--force`).
- Endpoints used: `/fapi/v1/ticker/price`, `/fapi/v1/ticker/24hr`,
  `/fapi/v1/premiumIndex`, `/fapi/v1/klines`, `/fapi/v2/balance`,
  `/fapi/v2/positionRisk`, `/fapi/v1/order`.

Reference (alternative exchange, for parity when generalizing the interface):
- Hyperliquid API base: `https://api.hyperliquid.xyz`

To stay exchange-agnostic, the adapter should expose a small common interface
(get prices / funding / volume, place order, get positions, set stop+TP) so
swapping to Binance / Bybit / Gate is a new `exchanges/<name>/` folder, nothing
more.
