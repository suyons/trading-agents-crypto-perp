"""Self-check for the tick-driven RenkoTracker. Run: python3 backtest/test_renko_live.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.renko_live import RenkoTracker


def test_reversal_returns_signal_once():
    t = RenkoTracker(brick_size=1.0)
    # Walk price up to establish an UP direction (no reversal yet).
    ups = [t.update(p) for p in (100, 101, 102, 103, 104)]
    assert all(s == 0 for s in ups), "building up-bricks must not signal a reversal"
    assert t.last_dir == 1

    # Now drop > 2 bricks (reversal needs 2× brick): expect a single -1 signal.
    sig = t.update(101.5)  # 104 → 101.5 = 2.5 down, clears the 2-brick reversal gate
    assert sig == -1, f"a down reversal must return -1, got {sig}"

    # Continuing down in the same direction must NOT re-signal a reversal.
    assert t.update(100.0) == 0


def test_subbrick_moves_are_silent():
    t = RenkoTracker(brick_size=10.0)
    t.update(1000)            # seed
    assert t.update(1005) == 0  # < 1 brick → nothing
    assert t.update(1004) == 0


def test_zero_brick_is_safe():
    t = RenkoTracker(brick_size=0.0)
    assert t.update(123.0) == 0  # no division / no signal


if __name__ == "__main__":
    test_reversal_returns_signal_once()
    test_subbrick_moves_are_silent()
    test_zero_brick_is_safe()
    print("renko_live self-check: PASS")
