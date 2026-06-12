# Active exchange configuration  (NO KEYS — keys live in secrets/.env)

exchange: binance          # folder under exchanges/ -> adapter at exchanges/binance/adapter.py
mode: live                 # live = real orders via the adapter | paper = simulate locally
network: testnet           # testnet = Binance futures testnet (demo funds) | mainnet = real money
pairs:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
  - XRPUSDT
