#!/usr/bin/env python3
"""
Aster DEX exchange adapter.

This is the ONLY Aster-specific file the trader talks to. It exposes a small,
exchange-agnostic CLI (see exchanges/INTERFACE.md). To swap exchanges, add a new
exchanges/<name>/adapter.py implementing the same commands + JSON shapes, then
set `exchange:` in exchanges/EXCHANGE_CONFIG.md. Nothing else changes.

Stdlib only — no third-party dependencies.
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from urllib import error, parse, request

BASE_URL = "https://fapi.asterdex.com"
RECV_WINDOW = 5000

_HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS_PATH = os.path.join(_HERE, "..", "..", "secrets", ".env")
CONFIG_PATH = os.path.join(_HERE, "..", "EXCHANGE_CONFIG.md")

_QUOTES = ("USDT", "USDC", "USD1", "USD")


# --- helpers --------------------------------------------------------------
def normalize_symbol(sym):
    s = sym.upper().replace("/", "").replace("-", "").strip()
    if any(s.endswith(q) for q in _QUOTES):
        return s
    return s + "USDT"  # bare base like "BTC" -> "BTCUSDT"


def _get(path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + parse.urlencode(params)
    req = request.Request(url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _load_keys():
    keys = {}
    with open(SECRETS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    api, sec = keys.get("API_KEY"), keys.get("SECRET_KEY")
    if not api or not sec:
        raise SystemExit("ERROR: API_KEY/SECRET_KEY not found in secrets/.env")
    return api, sec


def _signed(method, path, params=None):
    api, sec = _load_keys()
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = RECV_WINDOW
    query = parse.urlencode(params)
    sig = hmac.new(sec.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{BASE_URL}{path}?{query}&signature={sig}"
    req = request.Request(url, method=method, headers={"X-MBX-APIKEY": api})
    with request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _mode():
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("mode:"):
                    return line.split(":", 1)[1].strip().split()[0].lower()
    except FileNotFoundError:
        pass
    return "paper"


# --- public market data ---------------------------------------------------
def cmd_price(args):
    d = _get("/fapi/v1/ticker/price", {"symbol": normalize_symbol(args.symbol)})
    return {"symbol": d["symbol"], "price": float(d["price"]), "time": d.get("time")}


def cmd_funding(args):
    d = _get("/fapi/v1/premiumIndex", {"symbol": normalize_symbol(args.symbol)})
    return {
        "symbol": d["symbol"],
        "markPrice": float(d["markPrice"]),
        "indexPrice": float(d.get("indexPrice") or 0),
        "lastFundingRate": float(d["lastFundingRate"]),
        "nextFundingTime": d["nextFundingTime"],
    }


def cmd_ticker24h(args):
    d = _get("/fapi/v1/ticker/24hr", {"symbol": normalize_symbol(args.symbol)})
    return {
        "symbol": d["symbol"],
        "lastPrice": float(d["lastPrice"]),
        "priceChangePercent": float(d["priceChangePercent"]),
        "highPrice": float(d["highPrice"]),
        "lowPrice": float(d["lowPrice"]),
        "volume": float(d["volume"]),
        "quoteVolume": float(d["quoteVolume"]),
    }


def cmd_klines(args):
    rows = _get(
        "/fapi/v1/klines",
        {"symbol": normalize_symbol(args.symbol), "interval": args.interval, "limit": args.limit},
    )
    return [
        {
            "openTime": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "closeTime": k[6],
        }
        for k in rows
    ]


def cmd_snapshot(args):
    sym = normalize_symbol(args.symbol)
    t = cmd_ticker24h(argparse.Namespace(symbol=sym))
    f = cmd_funding(argparse.Namespace(symbol=sym))
    return {
        "symbol": sym,
        "price": t["lastPrice"],
        "priceChangePercent24h": t["priceChangePercent"],
        "high24h": t["highPrice"],
        "low24h": t["lowPrice"],
        "quoteVolume24h": t["quoteVolume"],
        "markPrice": f["markPrice"],
        "fundingRate": f["lastFundingRate"],
        "nextFundingTime": f["nextFundingTime"],
    }


# --- account / trading (signed) -------------------------------------------
def cmd_balance(args):
    d = _signed("GET", "/fapi/v2/balance")
    rows = [
        {
            "asset": b["asset"],
            "balance": float(b["balance"]),
            "availableBalance": float(b.get("availableBalance", 0)),
        }
        for b in d
    ]
    return [b for b in rows if b["balance"] != 0] or rows


def cmd_positions(args):
    d = _signed("GET", "/fapi/v2/positionRisk")
    return [
        {
            "symbol": p["symbol"],
            "positionAmt": float(p["positionAmt"]),
            "entryPrice": float(p["entryPrice"]),
            "markPrice": float(p["markPrice"]),
            "unRealizedProfit": float(p["unRealizedProfit"]),
            "leverage": float(p.get("leverage", 0)),
        }
        for p in d
        if float(p["positionAmt"]) != 0
    ]


def cmd_order(args):
    if _mode() != "live" and not args.force:
        raise SystemExit(
            "Refusing to place order: EXCHANGE_CONFIG.md mode is not 'live' "
            "(paper mode simulates fills). Pass --force to override."
        )
    params = {
        "symbol": normalize_symbol(args.symbol),
        "side": args.side.upper(),
        "type": args.type.upper(),
        "quantity": args.qty,
    }
    if args.price:
        params["price"] = args.price
        params["timeInForce"] = "GTC"
    if args.stop:
        params["stopPrice"] = args.stop
    if args.reduce_only:
        params["reduceOnly"] = "true"
    return _signed("POST", "/fapi/v1/order", params)


# --- dispatch -------------------------------------------------------------
def main(argv):
    p = argparse.ArgumentParser(description="Aster DEX adapter (see exchanges/INTERFACE.md)")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("price", "funding", "ticker24h", "snapshot"):
        sp = sub.add_parser(name)
        sp.add_argument("symbol")

    sp = sub.add_parser("klines")
    sp.add_argument("symbol")
    sp.add_argument("interval", nargs="?", default="1h")
    sp.add_argument("limit", nargs="?", type=int, default=24)

    sub.add_parser("balance")
    sub.add_parser("positions")

    sp = sub.add_parser("order")
    sp.add_argument("symbol")
    sp.add_argument("side", choices=["BUY", "SELL", "buy", "sell"])
    sp.add_argument("qty")
    sp.add_argument("--type", default="MARKET")
    sp.add_argument("--price")
    sp.add_argument("--stop")
    sp.add_argument("--reduce-only", action="store_true")
    sp.add_argument("--force", action="store_true")

    args = p.parse_args(argv)
    handler = globals()["cmd_" + args.cmd]

    try:
        result = handler(args)
    except error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.stderr.write(f"HTTP {e.code} from Aster: {body}\n")
        return 1
    except error.URLError as e:
        sys.stderr.write(f"Network error reaching Aster: {e.reason}\n")
        return 1

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
