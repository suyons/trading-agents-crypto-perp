# Active exchange configuration  (NO KEYS — keys live in secrets/.env)

exchange: gate             # folder under exchanges/ -> adapter at exchanges/gate/adapter.py
mode: paper                # HOLD (see gate/NOTES.md): signed Gate calls return 401
                           # INVALID_KEY -> live access unverified. Confirm the keys match
                           # the endpoint before flipping to live. live = real orders.
network: testnet           # testnet = Gate demo funds (no real money) | mainnet = real money
pairs:
  - BTC_USDT
  - ETH_USDT
  - SOL_USDT
