# Active exchange configuration  (NO KEYS — keys live in secrets/.env)

exchange: gate             # folder under exchanges/ -> adapter at exchanges/gate/adapter.py
mode: paper                # SAFETY HOLD (see gate/NOTES.md): entry+close validated on
                           # testnet, but the protective-stop order errors (Gate 400), which
                           # can leave an unprotected position. live = real orders.
network: testnet           # testnet = Gate demo funds (no real money) | mainnet = real money
pairs:
  - BTC_USDT
  - ETH_USDT
  - SOL_USDT
