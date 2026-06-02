# Active exchange configuration  (NO KEYS — keys live in secrets/.env)

exchange: gate             # folder under exchanges/ -> adapter at exchanges/gate/adapter.py
mode: live                 # live = real orders via the adapter (validated 2026-06-02 on
                           # testnet: full order/stop/cancel/close round-trip, see
                           # gate/NOTES.md). paper = simulate fills locally.
network: testnet           # testnet = Gate demo funds (no real money) | mainnet = real money
pairs:
  - BTC_USDT
  - ETH_USDT
  - SOL_USDT
