import pytest

pytest.importorskip("miner.golden_nuggets.config")   # gitignored calibration
import miner.golden_nuggets.actions as actions


class FakeTime:
    def __init__(self):
        self.t = 0.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s

    def strftime(self, fmt):
        return "00:00:00"


def test_depletion_idle_timer_resets_after_pause(monkeypatch):
    clock, polls, waits = FakeTime(), [], []
    monkeypatch.setattr(actions, "time", clock)
    monkeypatch.setattr(actions.random, "uniform", lambda a, b: 1.0)
    monkeypatch.setattr(actions, "count_filled_slots", lambda: polls.append(clock.t) or 5)
    monkeypatch.setattr(actions, "character_in_any_vein", lambda: True)

    def wait():
        waits.append(clock.t)
        if len(waits) == 1:          # operator pauses for 100s on the first poll
            clock.t += 100
            return True
        return False
    monkeypatch.setattr(actions.pause, "wait", wait)

    assert actions.wait_for_vein_depletion((0, 0), {"run": 0}, idle_timeout=10) == "idle"
    assert waits, "pause gate never checked inside the mining wait"
    polls_after_pause = [t for t in polls if t > 100]
    assert len(polls_after_pause) >= 5   # a full idle window after resuming, not an instant "idle"
