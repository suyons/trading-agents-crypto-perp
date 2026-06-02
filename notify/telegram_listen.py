#!/usr/bin/env python3
"""
Telegram bridge — forwards natural-language messages to the orchestrator (Claude).

This is a thin BRIDGE, not a command parser. A Python script can't reason, so the
intelligent reply has to come from the Claude orchestrator. Flow:

  1. This bridge long-polls Telegram getUpdates.
  2. When message(s) arrive from the AUTHORIZED chat, it appends them to
     state/bot_inbox.jsonl, sends a "typing" indicator, and EXITS (prints
     __INBOX__ <n>).
  3. Exiting wakes the orchestrator, which reads the inbox, understands the
     request in plain language, pulls live data, replies via notify/telegram.py,
     takes any requested actions (analysis / close / pause / run a cycle / ...),
     truncates the inbox, and relaunches this bridge.

The getUpdates offset is persisted to state/bot_offset so no message is lost
across the exit/relaunch handoff. Only TELEGRAM_CHAT_ID is honored (others
ignored). Stdlib only; runs only while the Claude Code session is alive.
"""
import json
import os
import sys
import time
from urllib import error, parse, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, "secrets", ".env")
INBOX = os.path.join(ROOT, "state", "bot_inbox.jsonl")
OFFSET = os.path.join(ROOT, "state", "bot_offset")


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


def main():
    if not TOKEN or not CHAT:
        print("missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        return 1

    off = None
    if os.path.exists(OFFSET):
        try:
            off = int(open(OFFSET).read().strip())
        except Exception:
            off = None
    # First-ever run (no saved offset): skip the existing backlog so we don't
    # replay stale messages. On every relaunch the saved offset is used instead.
    if off is None:
        init = api("getUpdates", {"timeout": 0}, timeout=10)
        if init.get("ok") and init["result"]:
            off = init["result"][-1]["update_id"] + 1
            open(OFFSET, "w").write(str(off))

    while True:
        params = {"timeout": 30}
        if off is not None:
            params["offset"] = off
        up = api("getUpdates", params)
        if not up.get("ok"):
            time.sleep(3)
            continue
        forwarded = 0
        with open(INBOX, "a") as fh:
            for u in up["result"]:
                off = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message") or {}
                chat_id = str((msg.get("chat") or {}).get("id") or "")
                text = msg.get("text") or ""
                if chat_id != str(CHAT) or not text:
                    continue
                fh.write(json.dumps({"ts": int(time.time()), "text": text}) + "\n")
                forwarded += 1
        if off is not None:
            open(OFFSET, "w").write(str(off))
        if forwarded:
            api("sendChatAction", {"chat_id": CHAT, "action": "typing"})
            print(f"__INBOX__ {forwarded}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
