"""Optional LLM veto on entry signals — a runtime-agnostic "is this a real
reversal or just chop?" filter.

Ported in spirit from the retired Gate bot's ollama check, but the runtime is
deliberately swappable (see README: don't bake `claude`/`openclaw` into names).
The command to invoke comes from the env var `FILTER_AGENT_CMD`:

    FILTER_AGENT_CMD="claude -p"     # Claude Code, headless
    FILTER_AGENT_CMD="ollama run …"  # or anything else that reads a prompt arg

Unset / empty  → filter disabled, every signal passes through unchanged (the
repo's default deterministic contract). The prompt is appended as the final
argument; the agent must answer with one word: ENTER or SKIP.

Fails OPEN: any error, timeout, or unclear answer → ENTER (don't skip). The
deterministic strategy already cleared the gate, R:R, sizing and floor checks;
the filter only ever *removes* trades, and if it's unavailable we fall back to
the validated coded signal rather than silently halting.
"""
import os
import re
import shlex
import subprocess

ENV_VAR = "FILTER_AGENT_CMD"


def runtime_cmd() -> str:
    return os.environ.get(ENV_VAR, "").strip()


def is_enabled() -> bool:
    return bool(runtime_cmd())


def _build_prompt(symbol, side, entry, stop, tp, equity, upnl, bricks) -> str:
    seq = " ".join("U" if b["direction"] == 1 else "D" for b in bricks)
    brick_lines = "\n".join(
        f"  brick {i + 1}: open={b['open']:.6g} close={b['close']:.6g} "
        f"dir={'up' if b['direction'] == 1 else 'down'}"
        for i, b in enumerate(bricks)
    )
    return (
        f"You are a trading signal filter. A deterministic ATR-Renko strategy "
        f"just flagged a {side} entry for {symbol} on a brick-direction reversal.\n\n"
        f"Account equity: {equity:.2f} USDT\n"
        f"Open uPnL on {symbol}: {upnl:.2f} USDT\n"
        f"Proposed trade: {side} entry~{entry:.6g} stop={stop:.6g} tp={tp:.6g}\n\n"
        f"Recent Renko bricks (oldest to newest), direction sequence: {seq}\n"
        f"{brick_lines}\n\n"
        f"A FALSE signal is a reversal produced by sideways chop: many "
        f"alternating up/down bricks with no sustained trend. A REAL signal is a "
        f"clean reversal that breaks a run of same-direction bricks.\n\n"
        f"Reply with exactly one word: ENTER to take the trade, or SKIP if this "
        f"is a likely false (chop) signal."
    )


def should_skip(
    symbol, side, entry, stop, tp, equity, upnl, bricks, timeout: int = 90
) -> bool:
    """Return True iff the filter judges this reversal a false signal to skip."""
    cmd = runtime_cmd()
    if not cmd:
        return False

    prompt = _build_prompt(symbol, side, entry, stop, tp, equity, upnl, bricks)
    try:
        result = subprocess.run(
            shlex.split(cmd) + [prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return False  # fail open

    if result.returncode != 0:
        return False  # fail open

    # Agents may reason before concluding, so take the LAST ENTER/SKIP token as
    # the verdict (ponytail: assumes the conclusion is the final token — true for
    # a reason-then-answer reply). No token at all → fail open (ENTER).
    matches = re.findall(r"\b(ENTER|SKIP)\b", result.stdout.upper())
    return bool(matches) and matches[-1] == "SKIP"
