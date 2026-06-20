"""Self-check for signal_filter. Run: python3 backtest/test_signal_filter.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import signal_filter

_BRICKS = [
    {"open": 100, "close": 102, "direction": 1},
    {"open": 102, "close": 100, "direction": -1},
    {"open": 100, "close": 102, "direction": 1},
]
_ARGS = ("BTCUSDT", "SELL", 100.0, 102.0, 96.0, 5000.0, 0.0, _BRICKS)


def _with_cmd(cmd):
    if cmd is None:
        os.environ.pop(signal_filter.ENV_VAR, None)
    else:
        os.environ[signal_filter.ENV_VAR] = cmd


def test_disabled_passes_through():
    _with_cmd(None)
    assert not signal_filter.is_enabled()
    assert signal_filter.should_skip(*_ARGS) is False


def test_skip_verdict_skips():
    # Ignores the appended prompt arg ($0), prints a fixed verdict.
    _with_cmd("bash -c 'echo SKIP'")
    assert signal_filter.is_enabled()
    assert signal_filter.should_skip(*_ARGS) is True


def test_enter_verdict_does_not_skip():
    _with_cmd("bash -c 'echo ENTER'")
    assert signal_filter.should_skip(*_ARGS) is False


def test_failure_fails_open():
    _with_cmd("bash -c 'exit 1'")
    assert signal_filter.should_skip(*_ARGS) is False


def test_unclear_answer_fails_open():
    _with_cmd("bash -c 'echo maybe'")
    assert signal_filter.should_skip(*_ARGS) is False


def test_verbose_reply_uses_final_verdict():
    # An agent that reasons (mentions ENTER) but concludes SKIP must skip.
    _with_cmd("bash -c 'echo \"could be an ENTER, but final answer: SKIP.\"'")
    assert signal_filter.should_skip(*_ARGS) is True
    # …and the reverse: reasons about chop/SKIP but concludes ENTER.
    _with_cmd("bash -c 'echo \"not a SKIP here — verdict: ENTER\"'")
    assert signal_filter.should_skip(*_ARGS) is False


if __name__ == "__main__":
    test_disabled_passes_through()
    test_skip_verdict_skips()
    test_enter_verdict_does_not_skip()
    test_failure_fails_open()
    test_unclear_answer_fails_open()
    test_verbose_reply_uses_final_verdict()
    _with_cmd(None)
    print("signal_filter self-check: PASS")
