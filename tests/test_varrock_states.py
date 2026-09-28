import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from miner.varrock_exp.states import build_machine, FINAL_STATES, CYCLE_START


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: None)


def drive(session, script, stop_after=None):
    """Handlers pop scripted events; drop_second counts like the real one."""
    visited = []

    def make(state):
        def handler():
            visited.append(state)
            event = script.pop(0)
            if state == "drop_second" and event == "ok":
                session.second_drop(found=True)
            if not script or state == stop_after:
                session.stats["stop"] = True
            return event
        return handler
    states = ["mine_first", "drop_first", "mine_second", "drop_second"]
    final = run_machine(session, {s: make(s) for s in states}, session.stats,
                        FINAL_STATES, CYCLE_START)
    return final, visited


def test_full_cycle_counts_one_ore():
    s = build_machine({})
    final, visited = drive(s, ["ok"] * 4)
    assert visited == ["mine_first", "drop_first", "mine_second", "drop_second"]
    assert final == "stopped" and s.stats["run"] == 1


def test_no_rock_first_retries_first():
    s = build_machine({})
    _, visited = drive(s, ["not_found", "ok", "ok"])
    assert visited[:2] == ["mine_first", "mine_first"]


def test_no_rock_second_restarts_cycle():
    s = build_machine({})
    s.trigger("ok"); s.trigger("ok")          # at mine_second
    s.trigger("not_found")
    assert s.state == "mine_first"


def test_stop_between_rocks():
    # main checked the overlay Stop right after the first drop
    s = build_machine({})
    final, visited = drive(s, ["ok", "ok", "ok"], stop_after="drop_first")
    assert final == "stopped"
    assert visited == ["mine_first", "drop_first"]


def test_only_second_drop_counts():
    s = build_machine({})
    s.second_drop(found=False)
    assert s.stats.get("run", 0) == 0
    s.second_drop(found=True)
    s.second_drop(found=True)
    assert s.ores == 2 and s.stats["run"] == 2
