"""Fetch and cache OHLCV history from Gate.io mainnet (public, no auth required)."""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

BASE = "https://api.gateio.ws"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


def _get(url: str) -> list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_all(symbol: str, interval: str = "15m", max_age_secs: int = 3600) -> pd.DataFrame:
    """Return a DataFrame of OHLCV bars, fetching from Gate if cache is stale."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_{interval}.csv")

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < max_age_secs:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            df.index = pd.DatetimeIndex(df.index, tz="UTC")
            print(f"[fetch] cache hit ({symbol} {interval}): {len(df)} bars, "
                  f"oldest {df.index[0].date()}, newest {df.index[-1].date()}")
            return df

    print(f"[fetch] downloading {symbol} {interval} from Gate mainnet …")
    all_bars: list = []
    to_ts = int(time.time())

    while True:
        url = (
            f"{BASE}/api/v4/futures/usdt/candlesticks"
            f"?contract={symbol}&interval={interval}&limit=1000&to={to_ts}"
        )
        try:
            chunk = _get(url)
        except Exception as e:
            print(f"[fetch] stopped at to={to_ts}: {e}")
            break

        if not chunk:
            break

        all_bars = chunk + all_bars  # prepend (paginating backward)
        oldest_ts = chunk[0]["t"]
        oldest_dt = datetime.fromtimestamp(oldest_ts, timezone.utc)
        print(f"[fetch]   {len(all_bars)} bars, oldest {oldest_dt.date()}")

        to_ts = oldest_ts - 1
        time.sleep(0.25)  # be polite

    if not all_bars:
        raise RuntimeError(f"No data returned for {symbol} {interval}")

    rows = [
        {
            "timestamp": datetime.fromtimestamp(b["t"], timezone.utc),
            "open": float(b["o"]),
            "high": float(b["h"]),
            "low": float(b["l"]),
            "close": float(b["c"]),
            "volume": float(b["v"]),
        }
        for b in all_bars
    ]
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    df.to_csv(cache_path)
    print(f"[fetch] saved {len(df)} bars → {cache_path}")
    return df
