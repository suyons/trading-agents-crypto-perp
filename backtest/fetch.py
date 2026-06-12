"""Fetch and cache OHLCV history from Binance USDT-M futures (public, no auth).

Binance has 5-6 years of 15m history for BTC/ETH/SOL/XRP — far more than the
~100 days available on Gate mainnet. Symbols use Binance format (BTCUSDT etc.)
but the helper accepts Gate-style names too (BTC_USDT → BTCUSDT).
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

BASE      = "https://fapi.binance.com"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


def _normalize(symbol: str) -> str:
    """BTC_USDT / BTC/USDT / BTCUSDT / BTC  →  BTCUSDT"""
    s = symbol.upper().replace("/", "").replace("_", "").strip()
    return s if s.endswith("USDT") else s + "USDT"


def _get_chunk(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    url = (
        f"{BASE}/fapi/v1/klines"
        f"?symbol={symbol}&interval={interval}"
        f"&startTime={start_ms}&endTime={end_ms}&limit=1500"
    )
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_all(symbol: str, interval: str = "15m", max_age_secs: int = 3600) -> pd.DataFrame:
    """Return a DataFrame of OHLCV bars, fetching from Binance if cache is stale."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    sym = _normalize(symbol)
    cache_path = os.path.join(CACHE_DIR, f"{sym}_{interval}.csv")

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < max_age_secs:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            df.index = pd.DatetimeIndex(df.index, tz="UTC")
            print(f"[fetch] cache hit ({sym} {interval}): {len(df)} bars, "
                  f"{df.index[0].date()} → {df.index[-1].date()}")
            return df

    print(f"[fetch] downloading {sym} {interval} from Binance …")
    step_ms  = INTERVAL_SECONDS[interval] * 1000
    chunk_ms = 1500 * step_ms
    now_ms   = int(time.time() * 1000)
    all_bars: list = []

    # Paginate forward from earliest available data
    # Start far enough back; Binance returns empty list before contract start
    start_ms = now_ms - 7 * 365 * 24 * 3600 * 1000  # 7 years back

    while start_ms < now_ms:
        end_ms = min(start_ms + chunk_ms, now_ms)
        for attempt in range(5):
            try:
                chunk = _get_chunk(sym, interval, start_ms, end_ms)
                break
            except Exception as e:
                wait = 2 ** attempt * 5
                print(f"[fetch] error (attempt {attempt+1}): {e} — retrying in {wait}s")
                time.sleep(wait)
        else:
            print(f"[fetch] giving up at {start_ms}")
            break

        if not chunk:
            start_ms = end_ms + step_ms
            continue

        all_bars.extend(chunk)
        last_ts = chunk[-1][0]
        dt = datetime.fromtimestamp(last_ts / 1000, timezone.utc)
        print(f"[fetch]   {len(all_bars):>6} bars, up to {dt.date()}")

        start_ms = last_ts + step_ms
        time.sleep(0.3)  # ~200 req/min, well within 1200/min limit

    if not all_bars:
        raise RuntimeError(f"No data returned for {sym} {interval}")

    df = pd.DataFrame(
        [{
            "timestamp": datetime.fromtimestamp(b[0] / 1000, timezone.utc),
            "open":   float(b[1]),
            "high":   float(b[2]),
            "low":    float(b[3]),
            "close":  float(b[4]),
            "volume": float(b[5]),
        } for b in all_bars],
    ).set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    df.to_csv(cache_path)
    print(f"[fetch] saved {len(df)} bars → {cache_path}")
    return df
