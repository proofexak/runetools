import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from tanner.states import (
    build_machine, bank_event, FINAL_STATES, CYCLE_START, MAX_CHARGES,
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


def started(*args, **kwargs):
    """A normal session past its opening bank: at walk_to_tanner, run 1."""
    s = build_machine(*args, **kwargs)
    step(s, "ok", "ok")
    return s


def test_begin_normal_banks_first_then_walks_and_counts_run():
    s = build_machine({}, restock_enabled=True, start_from_ge=False)
    assert s.state == "walk_to_bank"         # clicks the booth first
    assert s.runs == 0 and s.skip_restock is True
    assert s.charges == MAX_CHARGES == 6
    step(s, "ok")
    assert s.state == "banking"
    step(s, "ok")
    assert s.state == "walk_to_tanner"
    assert s.runs == 1 and s.stats["run"] == 1
    assert s.skip_restock is False


@pytest.mark.parametrize("before", [[], ["ok"]])   # booth not found / bank failed
def test_opening_bank_failure_recovers(before):
    s = build_machine({}, True, False)
    step(s, *before, "fail")
    assert s.state == "recover" and s.charges == 5


def test_opening_bank_out_of_hides_restocks():
    s = build_machine({}, restock_enabled=True, start_from_ge=False)
    step(s, "ok", "restock")
    assert s.state == "restock"


def test_soft_stop_during_countdown_still_banks_first():
    s = build_machine({"stop": True}, True, False)
    final, visited = drive(s, ["ok", "ok"])
    assert final == "stopped" and visited == ["walk_to_bank", "banking"]


def test_begin_from_ge_enters_recover_and_uses_charge():
    s = build_machine({}, restock_enabled=True, start_from_ge=True)
    assert s.state == "recover"
    assert s.charges == 5
    assert s.skip_restock is True


def test_happy_trip_loops_back():
    s = started({}, True, False)
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
    s = started({}, True, False)
    step(s, *before)
    assert s.state == state
    step(s, "fail")
    assert s.state == "recover"
    assert s.charges == 5


def test_six_recoveries_then_stopped():
    s = started({}, True, False)
    for _ in range(6):
        step(s, "fail", "ok")
        assert s.state == "walk_to_tanner"
    assert s.charges == 0
    step(s, "fail")
    assert s.state == "stopped"


def test_recover_fail_stops():
    s = started({}, True, False)
    step(s, "fail", "fail")
    assert s.state == "stopped"


def test_restock_enabled_goes_restock_then_recover():
    s = started({}, restock_enabled=True, start_from_ge=False)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert s.state == "restock"
    s.skip_restock = False
    step(s, "ok")
    assert s.state == "recover"
    assert s.charges == 5 and s.skip_restock is True


def test_restock_disabled_goes_done():
    s = started({}, restock_enabled=False, start_from_ge=False)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert s.state == "done"


def test_restock_without_charges_stops_before_ge():
    # No glory charge left for the trip back -> don't spend gold at the GE.
    s = started({}, True, False, charges=0)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert s.state == "stopped"
    assert s.stop_reason == "out of hides and no glory charges for the GE trip back"


@pytest.mark.parametrize("events,charges,reason", [
    (["fail"],                                  0, "no glory charges left to recover"),
    (["fail", "fail"],                          6, "recovery failed"),
    (["ok", "ok", "ok", "ok", "restock", "fail"], 6, "GE restock failed"),
])
def test_stop_reason(events, charges, reason):
    s = started({}, True, False, charges=charges)
    step(s, *events)
    assert s.state == "stopped" and s.stop_reason == reason


def test_stop_reason_soft_stop():
    s = started({"stop": True}, True, False)
    final, _ = drive(s, [])
    assert final == "stopped" and s.stop_reason == "stopped via overlay"


def test_done_reason():
    s = started({}, restock_enabled=False, start_from_ge=False)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert s.state == "done" and s.stop_reason == "out of hides, GE restock disabled"


def test_restock_announced_on_entry(capsys):
    s = started({}, True, False)
    step(s, "ok", "ok", "ok", "ok", "restock")
    assert "[RESTOCK]" in capsys.readouterr().out


def test_restock_fail_stops():
    s = started({}, True, False)
    step(s, "ok", "ok", "ok", "ok", "restock", "fail")
    assert s.state == "stopped"


def test_skip_restock_lifecycle():
    s = build_machine({}, True, False)
    assert s.skip_restock is True             # the opening bank skips the empty-slot check
    step(s, "ok", "ok", *TRIP)
    assert s.skip_restock is False
    step(s, "ok", "ok", "ok", "ok", "fail")   # banking fails -> recover
    assert s.skip_restock is True
    step(s, "ok", *TRIP)
    assert s.skip_restock is False


@pytest.mark.parametrize("before", [[], ["ok"], ["ok", "ok", "ok"]])
def test_non_bank_failure_recovery_keeps_restock_check(before):
    # Old loop only skipped the next restock check after a bank failure or GE restock.
    s = started({}, True, False)
    step(s, *TRIP, *before, "fail")
    assert s.state == "recover"
    assert s.skip_restock is False


def test_soft_stop_at_walk_to_tanner():
    s = started({}, True, False)

    def on_call(state):
        if state == "trade_ellis":
            s.stats["stop"] = True
    final, visited = drive(s, list(TRIP), on_call)
    assert final == "stopped"
    assert visited == ["walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank", "banking"]
    assert s.stats["step"] == "banking"


def test_soft_stop_after_restock_finishes_recovery_first():
    s = started({}, True, False)

    def on_call(state):
        if state == "restock":
            s.stats["stop"] = True
    final, visited = drive(s, ["ok"] * 4 + ["restock", "ok", "ok"], on_call)
    assert final == "stopped"
    assert visited[-3:] == ["banking", "restock", "recover"]


def test_bank_event_mapping():
    assert [bank_event(r) for r in ("restock", True, False, None)] == ["restock", "ok", "fail", "fail"]


def test_recovery_drill_runs_one_trip_then_recovers_and_stops():
    from tanner.states import recovery_drill
    s = build_machine({}, True, False)
    real = []

    def make(state):
        def handler():
            real.append(state)
            return "ok"
        return handler
    handlers = recovery_drill({st: make(st) for st in ACTION_STATES}, s.stats)
    final = run_machine(s, handlers, s.stats, FINAL_STATES, CYCLE_START)
    assert final == "stopped" and s.stop_reason == "stopped via overlay"
    assert real == ["walk_to_bank", "banking",                       # opening bank
                    "walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank", "banking",
                    "recover"]                                        # forced after the trip's bank
    assert s.charges == 5
