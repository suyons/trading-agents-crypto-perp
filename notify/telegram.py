#!/usr/bin/env python3
"""
Telegram notifier — outbound trade alerts / cycle summaries.

The notification channel is swappable, like the exchange: this is the only
Telegram-specific file. Anything that wants to notify calls this CLI; swapping to
Slack/Discord later means adding a sibling here, not touching the trading logic.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from secrets/.env (gitignored).
Stdlib only. Notifications are BEST-EFFORT: callers must treat a non-zero exit as
"alert not sent" and never let it break a trading cycle.

CLI:
  notify/telegram.py test               # send a connection-test ping
  notify/telegram.py send "text"        # send a message to the configured chat
  notify/telegram.py chatid [--save]    # discover chat_id via getUpdates (optionally write it to .env)
"""

import argparse
import json
import os
import sys
from urllib import error, parse, request

SECRETS = os.path.join(os.path.dirname(__file__), "..", "secrets", ".env")


def _env():
    d = {}
    try:
        with open(SECRETS) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return d


def _set_env(key, val):
    path = os.path.abspath(SECRETS)
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    out, found = [], False
    for l in lines:
        if l.startswith(key + "="):
            out.append(f"{key}={val}")
            found = True
        else:
            out.append(l)
    if not found:
        out.append(f"{key}={val}")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def _api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = parse.urlencode(params).encode() if params else None
    req = request.Request(url, data=data)
    try:
        with request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except error.HTTPError as ex:          # Telegram returns JSON errors with a 4xx
        try:
            return json.load(ex)
        except Exception:
            return {"ok": False, "description": f"HTTP {ex.code}"}
    except error.URLError as ex:
        return {"ok": False, "description": f"network error: {ex.reason}"}


def _require_token():
    tok = _env().get("TELEGRAM_BOT_TOKEN")
    if not tok:
        sys.stderr.write("no TELEGRAM_BOT_TOKEN in secrets/.env\n")
        sys.exit(2)
    return tok


def cmd_send(args):
    tok = _require_token()
    chat = getattr(args, "chat", None) or _env().get("TELEGRAM_CHAT_ID")
    if not chat:
        sys.stderr.write("no TELEGRAM_CHAT_ID set — message the bot, then run: "
                         "notify/telegram.py chatid --save\n")
        return 1
    res = _api(tok, "sendMessage",
               {"chat_id": chat, "text": args.text, "disable_web_page_preview": "true"})
    if res.get("ok"):
        print("sent")
        return 0
    sys.stderr.write(f"telegram send failed: {res.get('description')}\n")
    return 1


def cmd_test(args):
    args.text = ("✅ Claude Trader connected.\n"
                 "You'll get hourly cycle summaries and risk alerts here.")
    args.chat = None
    return cmd_send(args)


def cmd_chatid(args):
    tok = _require_token()
    up = _api(tok, "getUpdates")
    if not up.get("ok"):
        sys.stderr.write(f"getUpdates failed: {up.get('description')}\n")
        return 1
    chats = {}
    for u in up.get("result", []):
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        ch = msg.get("chat") or {}
        if ch.get("id"):
            chats[ch["id"]] = ch
    if not chats:
        print("no messages yet — send a message to the bot, then retry")
        return 1
    for cid, ch in chats.items():
        print(f"chat_id={cid} type={ch.get('type')} "
              f"who={ch.get('first_name','')} (@{ch.get('username','')})")
    if args.save:
        cid = str(list(chats)[-1])         # most recent chat to message the bot
        _set_env("TELEGRAM_CHAT_ID", cid)
        print(f"saved TELEGRAM_CHAT_ID={cid} to secrets/.env")
    return 0


def main(argv):
    p = argparse.ArgumentParser(description="Telegram notifier (see module docstring)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("send")
    sp.add_argument("text")
    sp.add_argument("--chat", help="override chat_id (default: from secrets/.env)")
    sub.add_parser("test")
    sp = sub.add_parser("chatid")
    sp.add_argument("--save", action="store_true", help="write chat_id to secrets/.env")
    args = p.parse_args(argv)
    return {"send": cmd_send, "test": cmd_test, "chatid": cmd_chatid}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
