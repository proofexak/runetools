import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from tanner.states import (
    build_machine, bank_event, ok_or_fail, FINAL_STATES, CYCLE_START, MAX_CHARGES,
)

ACTION_STATES = ["walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank",
                 "banking", "restock", "recover"]


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: None)


def step(session, *events):
    """Fire events directly, one per step, as the runner would."""
    for e in events:
        session.trigger(e)


def drive(session, events, on_call=None):
    """Run the real runner with handlers that pop scripted events."""
    visited = []

    def make(state):
        def handler():
            visited.append(state)
            if on_call:
                on_call(state)
            return events.pop(0)
        return handler
    final = run_machine(session, {s: make(s) for s in ACTION_STATES},
                        session.stats, FINAL_STATES, CYCLE_START)
    return final, visited


TRIP = ["ok"] * 5  # walk_to_tanner -> trade_ellis -> tanning -> walk_to_bank -> banking -> walk_to_tanner


def test_begin_normal_enters_walk_to_tanner_and_counts_run():
    s = build_machine({}, restock_enabled=True, start_from_ge=False)
    assert s.state == "walk_to_tanner"
    assert s.runs == 1 and s.stats["run"] == 1
    assert s.charges == MAX_CHARGES == 6


def test_begin_from_ge_enters_recover_and_uses_charge():
    s = build_machine({}, restock_enabled=True, start_from_ge=True)
    assert s.state == "recover"
    assert s.charges == 5
    assert s.skip_restock is True


def test_happy_trip_loops_back():
    s = build_machine({}, True, False)
    step(s, *TRIP)
    assert s.state == "walk_to_tanner"
    assert s.runs == 2 and s.stats["run"] == 2
    assert s.skip_restock is False
    assert s.charges == 6


@pytest.mark.parametrize("before,state", [
    ([], "walk_to_tanner"),
    (["ok"], "trade_ellis"),
    (["ok", "ok", "ok"], "walk_to_bank"),
    (["ok", "ok", "ok", "ok"], "banking"),
])
def test_fail_in_action_state_goes_to_recover(before, state):
    s = build_machine({}, True, False)
    step(s, *before)
    assert s.state == state
    step(s, "fail")
    assert s.state == "recover"
    assert s.charges == 5


def test_six_recoveries_then_stopped():
    s = build_machine({}, True, False)
    for _ in range(6):
        step(s, "fail", "ok")
        assert s.state == "walk_to_tanner"
    assert s.charges == 0
    step(s, "fail")
    assert s.state == "stopped"


def test_recover_fail_stops():
    s = build_machine({}, True, False)
    step(s, "fail", "fail")
    assert s.state == "stopped"


def test_restock_enabled_goes_restock_then_recover():
    s = build_machine({}, restock_enabled=True, start_from_ge=False)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert s.state == "restock"
    s.skip_restock = False
    step(s, "ok")
    assert s.state == "recover"
    assert s.charges == 5 and s.skip_restock is True


def test_restock_disabled_goes_done():
    s = build_machine({}, restock_enabled=False, start_from_ge=False)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert s.state == "done"


def test_restock_ok_without_charges_stops():
    s = build_machine({}, True, False, charges=0)
    step(s, "ok", "ok", "ok", "ok", "restock", "ok")
    assert s.state == "stopped"


def test_restock_fail_stops():
    s = build_machine({}, True, False)
    step(s, "ok", "ok", "ok", "ok", "restock", "fail")
    assert s.state == "stopped"


def test_skip_restock_lifecycle():
    s = build_machine({}, True, False)
    assert s.skip_restock is True
    step(s, *TRIP)
    assert s.skip_restock is False
    step(s, "ok", "ok", "ok", "ok", "fail")   # banking fails -> recover
    assert s.skip_restock is True
    step(s, "ok", *TRIP)
    assert s.skip_restock is False


@pytest.mark.parametrize("before", [[], ["ok"], ["ok", "ok", "ok"]])
def test_non_bank_failure_recovery_keeps_restock_check(before):
    # Old loop only skipped the next restock check after a bank failure or GE restock.
    s = build_machine({}, True, False)
    step(s, *TRIP, *before, "fail")
    assert s.state == "recover"
    assert s.skip_restock is False


def test_soft_stop_at_walk_to_tanner():
    s = build_machine({}, True, False)

    def on_call(state):
        if state == "trade_ellis":
            s.stats["stop"] = True
    final, visited = drive(s, list(TRIP), on_call)
    assert final == "stopped"
    assert visited == ["walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank", "banking"]
    assert s.stats["step"] == "banking"


def test_soft_stop_after_restock_finishes_recovery_first():
    s = build_machine({}, True, False)

    def on_call(state):
        if state == "restock":
            s.stats["stop"] = True
    final, visited = drive(s, ["ok"] * 4 + ["restock", "ok", "ok"], on_call)
    assert final == "stopped"
    assert visited[-3:] == ["banking", "restock", "recover"]


def test_bank_event_mapping():
    assert [bank_event(r) for r in ("restock", True, False, None)] == ["restock", "ok", "fail", "fail"]


def test_ok_or_fail_mapping():
    assert [ok_or_fail(r) for r in (True, 1, False, None)] == ["ok", "ok", "fail", "fail"]
