# Exchange adapter interface (the swap contract)

Every exchange lives in `exchanges/<name>/` and provides an `adapter.py` that
implements the SAME command-line interface and the SAME JSON output shapes
documented here. The trader only ever calls this interface — never a specific
exchange's raw endpoints. To add Binance / Bybit / Gate: drop in
`exchanges/<name>/adapter.py` implementing these commands, then set
`exchange: <name>` in `EXCHANGE_CONFIG.md`. Nothing else changes.

Invocation:

    python3 exchanges/<name>/adapter.py <command> [args...]

Output: a single JSON value on stdout. Errors: non-zero exit + message on stderr.

## Public market data (no keys required)

| command                              | output |
|--------------------------------------|--------|
| `price <SYMBOL>`                     | `{symbol, price, time}` |
| `funding <SYMBOL>`                   | `{symbol, markPrice, indexPrice, lastFundingRate, nextFundingTime}` |
| `ticker24h <SYMBOL>`                 | `{symbol, lastPrice, priceChangePercent, highPrice, lowPrice, volume, quoteVolume}` |
| `klines <SYMBOL> [interval] [limit]` | `[ {openTime, open, high, low, close, volume, closeTime}, ... ]` |
| `snapshot <SYMBOL>`                  | `{symbol, price, priceChangePercent24h, high24h, low24h, quoteVolume24h, markPrice, fundingRate, nextFundingTime}` |

`snapshot` is the convenience call the trader uses each cycle — one shot for the
context it reasons over.

## Account / trading (keys from secrets/.env; used in LIVE mode)

| command   | output |
|-----------|--------|
| `balance`   | `[ {asset, balance, availableBalance}, ... ]` |
| `positions` | `[ {symbol, positionAmt, entryPrice, markPrice, unRealizedProfit, leverage}, ... ]` |
| `order <SYMBOL> <BUY\|SELL> <QTY> [--type MARKET\|LIMIT] [--price P] [--stop S] [--reduce-only] [--force]` | exchange order response |

`order` (and any write) **refuses to run unless `EXCHANGE_CONFIG.md` mode is
`live`** — pass `--force` to override. Paper mode never places real orders; the
trader simulates fills at the real price from `price`/`snapshot`.

## Symbol normalization

`SYMBOL` is flexible: `BTC`, `BTCUSDT`, and `BTC/USDT` all normalize to the
exchange symbol. A bare base (`BTC`) becomes the USDT perpetual (`BTCUSDT`).
