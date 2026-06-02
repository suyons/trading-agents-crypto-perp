#!/usr/bin/env python3
"""
Gate.io USDT-perpetual futures adapter.

This is the ONLY Gate-specific file the trader talks to. It exposes the same
exchange-agnostic CLI as every other adapter (see exchanges/INTERFACE.md), so
switching exchanges is just changing `exchange:` in EXCHANGE_CONFIG.md.

Network is chosen by `network:` in EXCHANGE_CONFIG.md:
  - testnet (default) -> https://api-testnet.gateapi.io  (demo funds, real exec)
  - mainnet           -> https://api.gateio.ws           (real money)

Note: the older testnet host fx-api-testnet.gateio.ws is dead (returns 502);
the live testnet futures API host is api-testnet.gateapi.io.

Auth: Gate APIv4 (KEY / Timestamp / SIGN headers, HMAC-SHA512). Keys come from
secrets/.env as GATE_API_KEY / GATE_SECRET_KEY. Order size on Gate is in
*contracts*; this adapter converts coin quantity <-> contracts via each
contract's quanto_multiplier so the CLI stays in coin units.

Stdlib only — no third-party dependencies.
"""

import argparse
import gzip
import hashlib
import hmac
import json
import os
import sys
import time
from urllib import error, parse, request

PREFIX = "/api/v4"
SETTLE = "usdt"
HOSTS = {
    "testnet": "https://api-testnet.gateapi.io",
    "mainnet": "https://api.gateio.ws",
}

_HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS_PATH = os.path.join(_HERE, "..", "..", "secrets", ".env")
CONFIG_PATH = os.path.join(_HERE, "..", "EXCHANGE_CONFIG.md")

_INTERVAL_SECONDS = {
    "10s": 10, "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "8h": 28800, "1d": 86400, "7d": 604800,
}


# --- config / keys --------------------------------------------------------
def _config_value(key, default=None):
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + ":"):
                    return line.split(":", 1)[1].strip().split()[0].lower()
    except FileNotFoundError:
        pass
    return default


def _network():
    net = _config_value("network", "testnet")
    return net if net in HOSTS else "testnet"


def _mode():
    return _config_value("mode", "paper")


def _host():
    return HOSTS[_network()]


def _load_keys():
    keys = {}
    with open(SECRETS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    api, sec = keys.get("GATE_API_KEY"), keys.get("GATE_SECRET_KEY")
    if not api or not sec:
        raise SystemExit("ERROR: GATE_API_KEY/GATE_SECRET_KEY not found in secrets/.env")
    return api, sec


def normalize_symbol(sym):
    s = sym.upper().replace("/", "_").replace("-", "_").strip()
    if "_" in s:
        return s
    for q in ("USDT", "USDC", "USD"):
        if s.endswith(q):
            return s[: -len(q)] + "_" + q
    return s + "_USDT"


# --- http -----------------------------------------------------------------
def _read_json(req):
    with request.urlopen(req, timeout=20) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode())


def _public_get(endpoint, query=None):
    qs = parse.urlencode(query or {})
    url = _host() + PREFIX + endpoint + (("?" + qs) if qs else "")
    req = request.Request(url, headers={"Accept": "application/json", "Accept-Encoding": "gzip"})
    return _read_json(req)


def _signed(method, endpoint, query=None, body_obj=None):
    api, sec = _load_keys()
    qs = parse.urlencode(query or {})
    body = json.dumps(body_obj) if body_obj is not None else ""
    payload_hash = hashlib.sha512(body.encode()).hexdigest()
    ts = str(int(time.time()))
    sign_path = PREFIX + endpoint
    msg = "\n".join([method.upper(), sign_path, qs, payload_hash, ts])
    sign = hmac.new(sec.encode(), msg.encode(), hashlib.sha512).hexdigest()
    headers = {"KEY": api, "Timestamp": ts, "SIGN": sign,
               "Accept": "application/json", "Accept-Encoding": "gzip"}
    if body:
        headers["Content-Type"] = "application/json"
    url = _host() + sign_path + (("?" + qs) if qs else "")
    req = request.Request(url, data=body.encode() if body else None,
                          method=method.upper(), headers=headers)
    return _read_json(req)


def _ticker(contract):
    return _public_get(f"/futures/{SETTLE}/tickers", {"contract": contract})[0]


def _contract_spec(contract):
    return _public_get(f"/futures/{SETTLE}/contracts/{contract}")


# --- public market data ---------------------------------------------------
def cmd_price(args):
    c = normalize_symbol(args.symbol)
    t = _ticker(c)
    return {"symbol": c, "price": float(t["last"]), "time": int(time.time() * 1000)}


def cmd_funding(args):
    c = normalize_symbol(args.symbol)
    t = _ticker(c)
    spec = _contract_spec(c)
    return {
        "symbol": c,
        "markPrice": float(t["mark_price"]),
        "indexPrice": float(t["index_price"]),
        "lastFundingRate": float(t["funding_rate"]),
        "nextFundingTime": int(spec.get("funding_next_apply", 0)) * 1000,
    }


def cmd_ticker24h(args):
    c = normalize_symbol(args.symbol)
    t = _ticker(c)
    return {
        "symbol": c,
        "lastPrice": float(t["last"]),
        "priceChangePercent": float(t["change_percentage"]),
        "highPrice": float(t["high_24h"] or 0),
        "lowPrice": float(t["low_24h"] or 0),
        "volume": float(t.get("volume_24h_base") or 0),
        "quoteVolume": float(t.get("volume_24h_quote") or 0),
    }


def cmd_klines(args):
    c = normalize_symbol(args.symbol)
    rows = _public_get(
        f"/futures/{SETTLE}/candlesticks",
        {"contract": c, "interval": args.interval, "limit": args.limit},
    )
    step = _INTERVAL_SECONDS.get(args.interval, 3600) * 1000
    out = []
    for k in rows:
        ot = int(k["t"]) * 1000
        out.append({
            "openTime": ot,
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"]),
            "closeTime": ot + step - 1,
        })
    return out


def cmd_snapshot(args):
    c = normalize_symbol(args.symbol)
    t = _ticker(c)
    spec = _contract_spec(c)
    return {
        "symbol": c,
        "price": float(t["last"]),
        "priceChangePercent24h": float(t["change_percentage"]),
        "high24h": float(t["high_24h"] or 0),
        "low24h": float(t["low_24h"] or 0),
        "quoteVolume24h": float(t.get("volume_24h_quote") or 0),
        "markPrice": float(t["mark_price"]),
        "fundingRate": float(t["funding_rate"]),
        "nextFundingTime": int(spec.get("funding_next_apply", 0)) * 1000,
        "network": _network(),
    }


# --- account / trading (signed) -------------------------------------------
def cmd_balance(args):
    d = _signed("GET", f"/futures/{SETTLE}/accounts")
    avail = float(d.get("available") or 0)
    # `total` reads 0 in cross / single-currency margin accounts; derive equity as
    # available + locked margin + unrealised PnL. The locked margin appears as
    # cross_initial_margin in cross mode and position_margin/order_margin in
    # isolated mode (mutually exclusive), so summing all is safe across modes.
    equity = float(d.get("total") or 0)
    if equity <= 0:
        equity = (avail
                  + float(d.get("position_margin") or 0)
                  + float(d.get("order_margin") or 0)
                  + float(d.get("cross_initial_margin") or 0)
                  + float(d.get("cross_order_margin") or 0)
                  + float(d.get("unrealised_pnl") or 0))
    return [{
        "asset": SETTLE.upper(),
        "balance": round(equity, 6),
        "availableBalance": avail,
    }]


def cmd_positions(args):
    d = _signed("GET", f"/futures/{SETTLE}/positions")
    out = []
    for p in d:
        size = float(p["size"])
        if size == 0:
            continue
        qm = float(_contract_spec(p["contract"])["quanto_multiplier"])
        out.append({
            "symbol": p["contract"],
            "positionAmt": size * qm,
            "entryPrice": float(p["entry_price"]),
            "markPrice": float(p["mark_price"]),
            "unRealizedProfit": float(p["unrealised_pnl"]),
            "leverage": float(p["leverage"]),
        })
    return out


def _qty_to_contracts(contract, qty):
    qm = float(_contract_spec(contract)["quanto_multiplier"])
    n = int(round(float(qty) / qm))
    return max(n, 1)  # never round a real order down to zero


def cmd_order(args):
    if _mode() != "live" and not args.force:
        raise SystemExit(
            "Refusing to place order: EXCHANGE_CONFIG.md mode is not 'live'. "
            "Pass --force to override."
        )
    c = normalize_symbol(args.symbol)
    n = _qty_to_contracts(c, args.qty)
    size = n if args.side.upper() == "BUY" else -n
    body = {"contract": c, "size": size}
    if args.type.upper() == "MARKET":
        body["price"] = "0"
        body["tif"] = "ioc"
    else:
        body["price"] = str(args.price)
        body["tif"] = "gtc"
    if args.reduce_only:
        body["reduce_only"] = True
    result = {"entry": _signed("POST", f"/futures/{SETTLE}/orders", body_obj=body)}
    if args.stop:
        # Fail-safe: a filled entry with no stop is an unprotected position.
        # If the stop can't be placed, immediately close the entry and report.
        try:
            result["stop"] = _place_stop(c, args.side.upper(), args.stop)
        except Exception as e:
            unwind = {"contract": c, "size": 0, "price": "0", "tif": "ioc",
                      "auto_size": "close_long" if args.side.upper() == "BUY"
                      else "close_short", "reduce_only": True}
            try:
                undo = _signed("POST", f"/futures/{SETTLE}/orders", body_obj=unwind)
                result["stop_error"] = (f"stop failed ({e!r}); entry auto-closed "
                                        f"to avoid an unprotected position")
                result["auto_close"] = undo
            except Exception as e2:
                result["stop_error"] = (f"stop failed ({e!r}) AND auto-close failed "
                                        f"({e2!r}) -- POSITION MAY BE UNPROTECTED, "
                                        f"close {c} manually")
    return result


def _place_stop(contract, entry_side, trigger_price):
    # Protective stop = reduce-only price-triggered close, opposite the entry.
    # Long entry -> close when price falls (rule 2, <=); short -> rise (rule 1, >=).
    long = entry_side == "BUY"
    body = {
        "initial": {
            "contract": contract,
            "size": 0,
            "price": "0",
            "tif": "ioc",
            "reduce_only": True,
            "auto_size": "close_long" if long else "close_short",
        },
        "trigger": {
            "strategy_type": 0,
            "price_type": 0,
            "price": str(trigger_price),
            "rule": 2 if long else 1,
        },
    }
    return _signed("POST", f"/futures/{SETTLE}/price_orders", body_obj=body)


def cmd_close(args):
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing to close: mode is not 'live'. Pass --force.")
    c = normalize_symbol(args.symbol)
    pos = next((p for p in _signed("GET", f"/futures/{SETTLE}/positions")
                if p["contract"] == c and float(p["size"]) != 0), None)
    if not pos:
        return {"closed": False, "reason": f"no open position on {c}"}
    body = {"contract": c, "size": 0, "price": "0", "tif": "ioc",
            "auto_size": "close_long" if float(pos["size"]) > 0 else "close_short",
            "reduce_only": True}
    return {"closed": True, "order": _signed("POST", f"/futures/{SETTLE}/orders", body_obj=body)}


def cmd_stop(args):
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing to set stop: mode is not 'live'. Pass --force.")
    return _place_stop(normalize_symbol(args.symbol), args.side.upper(), args.price)


def cmd_cancel(args):
    # Cancels open orders for a contract: both resting limit orders and pending
    # price-triggered (stop) orders. Used to clean up before/after a position.
    if _mode() != "live" and not args.force:
        raise SystemExit("Refusing to cancel: mode is not 'live'. Pass --force.")
    c = normalize_symbol(args.symbol)
    return {
        "orders": _signed("DELETE", f"/futures/{SETTLE}/orders", query={"contract": c}),
        "price_orders": _signed("DELETE", f"/futures/{SETTLE}/price_orders",
                                query={"contract": c}),
    }


# --- dispatch -------------------------------------------------------------
def main(argv):
    p = argparse.ArgumentParser(description="Gate.io futures adapter (see exchanges/INTERFACE.md)")
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

    sp = sub.add_parser("close")
    sp.add_argument("symbol")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("stop")
    sp.add_argument("symbol")
    sp.add_argument("side", choices=["BUY", "SELL", "buy", "sell"],
                    help="the ENTRY side the stop protects (BUY=long)")
    sp.add_argument("price")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("cancel")
    sp.add_argument("symbol")
    sp.add_argument("--force", action="store_true")

    args = p.parse_args(argv)
    handler = globals()["cmd_" + args.cmd]

    try:
        result = handler(args)
    except error.HTTPError as e:
        raw = e.read()
        try:
            if e.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
        except Exception:
            pass
        sys.stderr.write(f"HTTP {e.code} from Gate: {raw.decode(errors='replace')}\n")
        return 1
    except error.URLError as e:
        sys.stderr.write(f"Network error reaching Gate: {e.reason}\n")
        return 1

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
