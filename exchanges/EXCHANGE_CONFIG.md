# Active exchange configuration  (NO KEYS — keys live in secrets/.env)

exchange: gate             # folder under exchanges/ -> adapter at exchanges/gate/adapter.py
mode: live                 # live = adapter places REAL orders | paper = simulate fills
network: testnet           # testnet = Gate demo funds (no real money) | mainnet = real money
pairs:
  - BTC_USDT
  - ETH_USDT
  - SOL_USDT
