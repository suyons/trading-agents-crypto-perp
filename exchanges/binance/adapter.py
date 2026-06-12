#!/usr/bin/env python3
"""
Binance USDT-M Futures adapter.

Implements exchanges/INTERFACE.md for Binance futures.
  testnet  -> https://testnet.binancefuture.com   (demo funds)
  mainnet  -> https://fapi.binance.com             (real money)

Market data (klines, snapshot, price, funding) always fetched from MAINNET
regardless of network setting — testnet uses same prices as mainnet.

Keys: secrets/.env  BINANCE_API_KEY / BINANCE_SECRET_KEY
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse as parse
import urllib.request as request
from urllib.error import HTTPError

# ---------------------------------------------------------------------------
SETTLE   = "usdt"    # USDT-margined futures
PREFIX   = ""        # no path prefix; full paths used below

HOSTS = {
    "testnet": "https://testnet.binancefuture.com",
    "mainnet": "https://fapi.binance.com",
}
MAINNET = HOSTS["mainnet"]

SECRETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "secrets", ".env",
)
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "exchanges", "EXCHANGE_CONFIG.md",
)

_INTERVAL_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}


# ── Config helpers ──────────────────────────────────────────────────────────

def _config_value(key, default=""):
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                if line.strip().startswith(key + ":"):
                    return line.split(":", 1)[1].strip().split()[0]
    except FileNotFoundError:
        pass
    return default


def _network():
    n = _config_value("network", "testnet")
    return n if n in HOSTS else "testnet"


def _mode():
    return _config_value("mode", "paper")


def _host():
    return HOSTS[_network()]


# ── Symbol normalisation ────────────────────────────────────────────────────

def normalize_symbol(sym: str) -> str:
    """BTC / BTC_USDT / BTCUSDT / BTC/USDT  →  BTCUSDT"""
    s = sym.upper().replace("/", "").replace("_", "").strip()
    if s.endswith("USDT"):
        return s
    return s + "USDT"


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _get(url: str, params: dict | None = None) -> object:
    qs = parse.urlencode(params or {})
    full = url + ("?" + qs if qs else "")
    req = request.Request(full, headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} GET {full}\n{body}") from e


def _load_keys():
    keys = {}
    with open(SECRETS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    api = keys.get("BINANCE_API_KEY")
    sec = keys.get("BINANCE_SECRET_KEY")
    if not api or not sec:
        raise SystemExit("ERROR: BINANCE_API_KEY / BINANCE_SECRET_KEY not in secrets/.env")
    return api, sec


def _signed_get(path: str, params: dict | None = None) -> object:
    api, sec = _load_keys()
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    qs = parse.urlencode(p)
    sig = hmac.new(sec.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = _host() + path + "?" + qs + "&signature=" + sig
    req = request.Request(url, headers={
        "Accept": "application/json",
        "X-MBX-APIKEY": api,
    })
    try:
        with request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} GET {url}\n{body}") from e


def _signed_post(path: str, params: dict | None = None) -> object:
    api, sec = _load_keys()
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    qs = parse.urlencode(p)
    sig = hmac.new(sec.encode(), qs.encode(), hashlib.sha256).hexdigest()
    body = (qs + "&signature=" + sig).encode()
    url = _host() + path
    req = request.Request(url, data=body, method="POST", headers={
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-MBX-APIKEY": api,
    })
    try:
        with request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body_str = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} POST {path}\n{body_str}") from e


def _signed_delete(path: str, params: dict | None = None) -> object:
    api, sec = _load_keys()
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    qs = parse.urlencode(p)
    sig = hmac.new(sec.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = _host() + path + "?" + qs + "&signature=" + sig
    req = request.Request(url, method="DELETE", headers={
        "Accept": "application/json",
        "X-MBX-APIKEY": api,
    })
    try:
        with request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} DELETE {url}\n{body}") from e


# ── Market data (always mainnet) ─────────────────────────────────────────────

def cmd_price(args):
    c = normalize_symbol(args.symbol)
    d = _get(MAINNET + "/fapi/v1/ticker/price", {"symbol": c})
    return {"symbol": c, "price": float(d["price"]), "time": int(time.time() * 1000)}


def cmd_funding(args):
    c = normalize_symbol(args.symbol)
    mark = _get(MAINNET + "/fapi/v1/premiumIndex", {"symbol": c})
    return {
        "symbol": c,
        "markPrice": float(mark["markPrice"]),
        "indexPrice": float(mark["indexPrice"]),
        "lastFundingRate": float(mark["lastFundingRate"]),
        "nextFundingTime": int(mark["nextFundingTime"]),
    }


def cmd_ticker24h(args):
    c = normalize_symbol(args.symbol)
    d = _get(MAINNET + "/fapi/v1/ticker/24hr", {"symbol": c})
    return {
        "symbol": c,
        "lastPrice": float(d["lastPrice"]),
        "priceChangePercent": float(d["priceChangePercent"]),
        "highPrice": float(d["highPrice"]),
        "lowPrice": float(d["lowPrice"]),
        "volume": float(d["volume"]),
        "quoteVolume": float(d["quoteVolume"]),
    }


def cmd_klines(args):
    c = normalize_symbol(args.symbol)
    rows = _get(MAINNET + "/fapi/v1/klines", {
        "symbol": c, "interval": args.interval, "limit": args.limit,
    })
    step = _INTERVAL_SECONDS.get(args.interval, 3600) * 1000
    return [
        {
            "openTime":  int(k[0]),
            "open":      float(k[1]),
            "high":      float(k[2]),
            "low":       float(k[3]),
            "close":     float(k[4]),
            "volume":    float(k[5]),
            "closeTime": int(k[6]),
        }
        for k in rows
    ]


def cmd_snapshot(args):
    c = normalize_symbol(args.symbol)
    t24  = _get(MAINNET + "/fapi/v1/ticker/24hr", {"symbol": c})
    mark = _get(MAINNET + "/fapi/v1/premiumIndex",  {"symbol": c})
    return {
        "symbol": c,
        "price": float(t24["lastPrice"]),
        "priceChangePercent24h": float(t24["priceChangePercent"]),
        "high24h": float(t24["highPrice"]),
        "low24h":  float(t24["lowPrice"]),
        "quoteVolume24h": float(t24["quoteVolume"]),
        "markPrice":   float(mark["markPrice"]),
        "fundingRate": float(mark["lastFundingRate"]),
        "nextFundingTime": int(mark["nextFundingTime"]),
        "network": _network(),
    }


# ── Account / trading (signed, uses testnet/mainnet per config) ──────────────

def cmd_balance(args):
    d = _signed_get("/fapi/v2/account")
    usdt = next(
        (a for a in d.get("assets", []) if a["asset"] == "USDT"),
        None,
    )
    if not usdt:
        return [{"asset": "USDT", "balance": 0.0, "availableBalance": 0.0}]
    return [{
        "asset": "USDT",
        "balance": float(usdt["walletBalance"]),
        "availableBalance": float(usdt["availableBalance"]),
    }]


def cmd_positions(args):
    d = _signed_get("/fapi/v2/account")
    out = []
    for p in d.get("positions", []):
        amt = float(p["positionAmt"])
        if amt == 0:
            continue
        out.append({
            "symbol":          p["symbol"],
            "positionAmt":     amt,
            "entryPrice":      float(p["entryPrice"]),
            "markPrice":       float(p.get("markPrice") or 0),
            "unrealisedPnl":   float(p["unrealizedProfit"]),
            "leverage":        int(p.get("leverage") or 1),
        })
    return out


def _precision(symbol: str) -> tuple[int, int]:
    """Return (price_precision, qty_precision) for the symbol."""
    info = _get(MAINNET + "/fapi/v1/exchangeInfo")
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            pp = next((int(f["pricePrecision"]) for f in [s] if "pricePrecision" in s), 2)
            qp = next((int(f["quantityPrecision"]) for f in [s] if "quantityPrecision" in s), 3)
            return pp, qp
    return 2, 3


def cmd_order(args):
    if _mode() != "live" and not args.force:
        raise SystemExit(
            "Refusing: mode is not 'live'. Pass --force to override."
        )

    c = normalize_symbol(args.symbol)
    side = args.side.upper()

    # Qty and price precision from exchange info
    info = _get(MAINNET + "/fapi/v1/exchangeInfo")
    sym_info = next((s for s in info["symbols"] if s["symbol"] == c), None)
    price_prec = int(sym_info["pricePrecision"]) if sym_info else 2
    qty_prec   = int(sym_info["quantityPrecision"]) if sym_info else 3

    qty = round(float(args.qty), qty_prec)

    # Main market order
    order_params = {
        "symbol":   c,
        "side":     side,
        "type":     "MARKET",
        "quantity": qty,
    }
    order = _signed_post("/fapi/v1/order", order_params)
    result = {"order": order}

    # Stop-loss (opposite side, STOP_MARKET, reduceOnly)
    if args.stop:
        stop_side = "SELL" if side == "BUY" else "BUY"
        stop_price = round(float(args.stop), price_prec)
        try:
            stop_order = _signed_post("/fapi/v1/order", {
                "symbol":           c,
                "side":             stop_side,
                "type":             "STOP_MARKET",
                "stopPrice":        stop_price,
                "quantity":         qty,
                "reduceOnly":       "true",
                "workingType":      "MARK_PRICE",
                "timeInForce":      "GTC",
            })
            result["stop"] = stop_order
        except SystemExit as e:
            # Stop failed — close the position to avoid leaving it naked
            print(f"WARN: stop placement failed ({e}), closing position", file=sys.stderr)
            _signed_post("/fapi/v1/order", {
                "symbol": c, "side": stop_side, "type": "MARKET",
                "quantity": qty, "reduceOnly": "true",
            })
            raise

    # Take-profit (opposite side, TAKE_PROFIT_MARKET, reduceOnly)
    if args.tp:
        tp_side = "SELL" if side == "BUY" else "BUY"
        tp_price = round(float(args.tp), price_prec)
        try:
            tp_order = _signed_post("/fapi/v1/order", {
                "symbol":           c,
                "side":             tp_side,
                "type":             "TAKE_PROFIT_MARKET",
                "stopPrice":        tp_price,
                "quantity":         qty,
                "reduceOnly":       "true",
                "workingType":      "MARK_PRICE",
                "timeInForce":      "GTC",
            })
            result["tp"] = tp_order
        except SystemExit as e:
            print(f"WARN: TP placement failed ({e}), stop still live", file=sys.stderr)

    return result


def cmd_close(args):
    c = normalize_symbol(args.symbol)
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing: mode is not 'live'.")
    pos = cmd_positions(argparse.Namespace())
    p = next((x for x in pos if x["symbol"] == c), None)
    if not p:
        return {"msg": f"no open position on {c}"}
    amt = p["positionAmt"]
    side = "SELL" if amt > 0 else "BUY"
    info = _get(MAINNET + "/fapi/v1/exchangeInfo")
    sym_info = next((s for s in info["symbols"] if s["symbol"] == c), None)
    qty_prec = int(sym_info["quantityPrecision"]) if sym_info else 3
    return _signed_post("/fapi/v1/order", {
        "symbol": c, "side": side, "type": "MARKET",
        "quantity": round(abs(amt), qty_prec), "reduceOnly": "true",
    })


def cmd_stop(args):
    """Place a standalone reduce-only stop. BUY/SELL = entry side being protected."""
    c = normalize_symbol(args.symbol)
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing: mode is not 'live'.")
    side = "SELL" if args.side.upper() == "BUY" else "BUY"
    info = _get(MAINNET + "/fapi/v1/exchangeInfo")
    sym_info = next((s for s in info["symbols"] if s["symbol"] == c), None)
    price_prec = int(sym_info["pricePrecision"]) if sym_info else 2
    pos = cmd_positions(argparse.Namespace())
    p = next((x for x in pos if x["symbol"] == c), None)
    if not p:
        raise SystemExit(f"No open position on {c} to protect")
    qty_prec = int(sym_info["quantityPrecision"]) if sym_info else 3
    return _signed_post("/fapi/v1/order", {
        "symbol":      c,
        "side":        side,
        "type":        "STOP_MARKET",
        "stopPrice":   round(float(args.trigger), price_prec),
        "quantity":    round(abs(p["positionAmt"]), qty_prec),
        "reduceOnly":  "true",
        "workingType": "MARK_PRICE",
        "timeInForce": "GTC",
    })


def cmd_tp(args):
    """Place a standalone reduce-only take-profit."""
    c = normalize_symbol(args.symbol)
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing: mode is not 'live'.")
    side = "SELL" if args.side.upper() == "BUY" else "BUY"
    info = _get(MAINNET + "/fapi/v1/exchangeInfo")
    sym_info = next((s for s in info["symbols"] if s["symbol"] == c), None)
    price_prec = int(sym_info["pricePrecision"]) if sym_info else 2
    pos = cmd_positions(argparse.Namespace())
    p = next((x for x in pos if x["symbol"] == c), None)
    if not p:
        raise SystemExit(f"No open position on {c} to protect")
    qty_prec = int(sym_info["quantityPrecision"]) if sym_info else 3
    return _signed_post("/fapi/v1/order", {
        "symbol":      c,
        "side":        side,
        "type":        "TAKE_PROFIT_MARKET",
        "stopPrice":   round(float(args.trigger), price_prec),
        "quantity":    round(abs(p["positionAmt"]), qty_prec),
        "reduceOnly":  "true",
        "workingType": "MARK_PRICE",
        "timeInForce": "GTC",
    })


def cmd_cancel(args):
    c = normalize_symbol(args.symbol)
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing: mode is not 'live'.")
    result = _signed_delete("/fapi/v1/allOpenOrders", {"symbol": c})
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Binance USDT-M Futures adapter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("price", "funding", "ticker24h", "balance", "positions"):
        sp = sub.add_parser(name)
        if name in ("price", "funding", "ticker24h"):
            sp.add_argument("symbol")

    sp = sub.add_parser("klines")
    sp.add_argument("symbol")
    sp.add_argument("interval", nargs="?", default="15m")
    sp.add_argument("limit",    nargs="?", type=int, default=100)

    sp = sub.add_parser("snapshot")
    sp.add_argument("symbol")

    sp = sub.add_parser("order")
    sp.add_argument("symbol")
    sp.add_argument("side", choices=["BUY", "SELL", "buy", "sell"])
    sp.add_argument("qty")
    sp.add_argument("--type",  default="MARKET")
    sp.add_argument("--price", default=None)
    sp.add_argument("--stop",  default=None, help="stop-loss trigger price")
    sp.add_argument("--tp",    default=None, help="take-profit trigger price")
    sp.add_argument("--reduce-only", action="store_true")
    sp.add_argument("--force",       action="store_true")

    sp = sub.add_parser("close")
    sp.add_argument("symbol")
    sp.add_argument("--force", action="store_true")

    for name in ("stop", "tp"):
        sp = sub.add_parser(name)
        sp.add_argument("symbol")
        sp.add_argument("side", choices=["BUY", "SELL", "buy", "sell"])
        sp.add_argument("trigger")
        sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("cancel")
    sp.add_argument("symbol")
    sp.add_argument("--force", action="store_true")

    args = parser.parse_args()
    fn = {
        "price":    cmd_price,    "funding":   cmd_funding,
        "ticker24h": cmd_ticker24h, "klines":  cmd_klines,
        "snapshot": cmd_snapshot,  "balance":  cmd_balance,
        "positions": cmd_positions, "order":   cmd_order,
        "close":    cmd_close,    "stop":      cmd_stop,
        "tp":       cmd_tp,       "cancel":    cmd_cancel,
    }[args.cmd]
    print(json.dumps(fn(args), indent=2))


if __name__ == "__main__":
    main()
