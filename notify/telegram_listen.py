#!/usr/bin/env python3
"""
Telegram command listener — two-way control for the trading bot.

Long-polls getUpdates and responds to commands from the AUTHORIZED chat only
(TELEGRAM_CHAT_ID; messages from anyone else are ignored). Runs as a background
process; like the hourly cron it only works while the Claude Code session is alive.

Handled inline (no orchestrator needed):
  status | positions | balance | pnl | log [n] | help
  close <SYM> | flatten | pause | resume

'run' needs the LLM trader (an agent only the orchestrator can spawn): it writes
state/bot_run.request, acks, then EXITS with marker __RUN_REQUESTED__ so the
orchestrator is re-invoked to run a cycle and relaunch this listener. The hourly
cron also drains state/bot_run.request as a backstop.

pause writes state/trading.paused; the hourly cron skips trading while it exists.

Stdlib only.
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
from urllib import error, parse, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, "secrets", ".env")
PAUSE_FLAG = os.path.join(ROOT, "state", "trading.paused")
RUN_REQUEST = os.path.join(ROOT, "state", "bot_run.request")
ADAPTER = os.path.join(ROOT, "exchanges", "gate", "adapter.py")
LOG = os.path.join(ROOT, "state", "TRADE_LOG.md")


def _env():
    d = {}
    with open(SECRETS) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


E = _env()
TOKEN = E.get("TELEGRAM_BOT_TOKEN")
CHAT = E.get("TELEGRAM_CHAT_ID")

_spec = importlib.util.spec_from_file_location("gate", ADAPTER)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def api(method, params=None, timeout=40):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = parse.urlencode(params).encode() if params else None
    try:
        with request.urlopen(request.Request(url, data=data), timeout=timeout) as r:
            return json.load(r)
    except error.HTTPError as ex:
        try:
            return json.load(ex)
        except Exception:
            return {"ok": False, "description": f"HTTP {ex.code}"}
    except Exception as ex:
        return {"ok": False, "description": str(ex)}


def say(text):
    api("sendMessage", {"chat_id": CHAT, "text": text[:4096],
                        "disable_web_page_preview": "true"})


def _adapter(*args):
    r = subprocess.run([sys.executable, ADAPTER, *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _account():
    S = gate.SETTLE
    a = gate._signed("GET", f"/futures/{S}/accounts")
    eq = (float(a.get("available") or 0) + float(a.get("cross_initial_margin") or 0)
          + float(a.get("unrealised_pnl") or 0))
    pos = [p for p in gate._signed("GET", f"/futures/{S}/positions")
           if float(p["size"]) != 0]
    po = gate._signed("GET", f"/futures/{S}/price_orders", query={"status": "open"})
    return a, eq, pos, po


def fmt_status():
    a, eq, pos, po = _account()
    paused = " | ⏸ PAUSED" if os.path.exists(PAUSE_FLAG) else ""
    lines = [f"📊 Equity ${eq:,.2f} | uPnL ${float(a.get('unrealised_pnl') or 0):+,.2f}{paused}"]
    if not pos:
        lines.append("No open positions.")
    for p in pos:
        c = p["contract"]
        qm = float(gate._contract_spec(c)["quanto_multiplier"])
        side = "SHORT" if float(p["size"]) < 0 else "LONG"
        sl = tp = None
        for o in po:
            if o["initial"]["contract"] != c:
                continue
            r, az = o["trigger"]["rule"], o["initial"]["auto_size"]
            if (r == 2 and az == "close_short") or (r == 1 and az == "close_long"):
                tp = o["trigger"]["price"]
            else:
                sl = o["trigger"]["price"]
        lines.append(f"{c} {side} {abs(float(p['size'])*qm):g} @ {p['entry_price']} | "
                     f"SL {sl}/TP {tp} | uPnL ${float(p['unrealised_pnl']):+.2f}")
    return "\n".join(lines)


def fmt_log(n=1):
    blocks = open(LOG).read().split("\n## ")
    entries = ["## " + b for b in blocks[1:] if b[:1].isdigit()]
    return "\n\n".join(entries[-max(n, 1):])[:3500] or "No log entries."


HELP = ("Commands:\n"
        "status — equity, P&L, positions\n"
        "positions — open positions\n"
        "balance / pnl — equity + uPnL\n"
        "log [n] — last n log entries\n"
        "close <SYM> — close a position (e.g. close BTC)\n"
        "flatten — close ALL positions\n"
        "pause / resume — stop/start hourly auto-trading\n"
        "run — run a decision cycle now\n"
        "help — this list")


def handle(text):
    """Return 'RUN' to signal the caller to exit (orchestrator handoff)."""
    parts = text.strip().split()
    if not parts:
        return
    cmd = parts[0].lstrip("/").lower()
    if cmd in ("help", "start"):
        say(HELP)
    elif cmd in ("status", "positions"):
        say(fmt_status())
    elif cmd in ("balance", "pnl"):
        a, eq, _, _ = _account()
        say(f"Equity ${eq:,.2f} | available ${float(a.get('available') or 0):,.2f} | "
            f"uPnL ${float(a.get('unrealised_pnl') or 0):+,.2f}")
    elif cmd == "log":
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        say(fmt_log(n))
    elif cmd == "pause":
        open(PAUSE_FLAG, "w").write(str(time.time()))
        say("⏸ Auto-trading PAUSED. Open positions keep their SL/TP. Send 'resume' to re-enable.")
    elif cmd == "resume":
        if os.path.exists(PAUSE_FLAG):
            os.remove(PAUSE_FLAG)
        say("▶️ Auto-trading RESUMED.")
    elif cmd == "close":
        if len(parts) < 2:
            say("Usage: close <SYM>  (e.g. close BTC)")
            return
        sym = parts[1].upper()
        rc, out, err = _adapter("close", sym)
        _adapter("cancel", sym)  # remove now-orphaned SL/TP
        say(f"✅ Closed {sym} (orders cancelled)." if rc == 0
            else f"⚠️ close {sym} failed: {err or out}")
    elif cmd == "flatten":
        _, _, pos, _ = _account()
        if not pos:
            say("Already flat.")
            return
        done = []
        for p in pos:
            _adapter("close", p["contract"])
            _adapter("cancel", p["contract"])
            done.append(p["contract"])
        say("✅ Flattened: " + ", ".join(done))
    elif cmd == "run":
        open(RUN_REQUEST, "w").write(str(time.time()))
        say("▶️ Cycle requested — running now, results shortly.")
        return "RUN"
    else:
        say(f"Unknown command '{cmd}'. Send 'help'.")


def main():
    if not TOKEN or not CHAT:
        print("missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        return 1
    # Skip backlog: advance the offset past existing updates without acting on them.
    off = None
    init = api("getUpdates", {"timeout": 0}, timeout=10)
    if init.get("ok") and init["result"]:
        off = init["result"][-1]["update_id"] + 1
    say("🤖 Two-way control online. Send 'help' for commands.")
    while True:
        params = {"timeout": 30}
        if off is not None:
            params["offset"] = off
        up = api("getUpdates", params)
        if not up.get("ok"):
            time.sleep(3)
            continue
        for u in up["result"]:
            off = u["update_id"] + 1
            msg = u.get("message") or u.get("edited_message") or {}
            chat_id = str((msg.get("chat") or {}).get("id") or "")
            text = msg.get("text") or ""
            if chat_id != str(CHAT) or not text:
                continue  # ignore other chats / non-text
            try:
                if handle(text) == "RUN":
                    print("__RUN_REQUESTED__")
                    return 0
            except Exception as ex:
                say(f"⚠️ error handling '{text[:40]}': {ex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
