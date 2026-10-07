import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from tanner.states import (
    build_machine, bank_event, FINAL_STATES, CYCLE_START, MAX_CHARGES,
)

ACTION_STATES = ["walk_to_tanner", "trade_ellis", "tanning", "walk_to_bank",
                 "banking", "restock", "look_around", "recover"]


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
def test_opening_bank_failure_looks_around_then_recovers(before):
    s = build_machine({}, True, False)
    step(s, *before, "fail")
    assert s.state == "look_around" and s.need == "bank" and s.charges == 6
    step(s, "lost")
    assert s.state == "recover" and s.charges == 5


def test_opening_bank_out_of_hides_restocks():
    s = build_machine({}, restock_enabled=True, start_from_ge=False)
    step(s, "ok", "restock")
    assert s.state == "restock"


def test_soft_stop_during_countdown_still_banks_first():
    s = build_machine({"stop": True}, True, False)
    final, visited = drive(s, ["ok", "ok"])
    assert final == "stopped" and visited == ["walk_to_bank", "banking"]


@pytest.mark.parametrize("restock_enabled", [True, False])
def test_begin_from_ge_restocks_first_then_recovers(restock_enabled):
    s = build_machine({}, restock_enabled=restock_enabled, start_from_ge=True)
    assert s.state == "restock" and s.at_ge is True        # GE mode asks for it, RESTOCK_GE or not
    assert s.charges == 6
    s.trigger("ok")
    assert s.state == "recover" and s.charges == 5 and s.skip_restock is True


def test_begin_from_ge_failed_restock_stops_with_why():
    s = build_machine({}, restock_enabled=True, start_from_ge=True)
    s.restock_error = "banker not found at the GE"
    s.trigger("fail")
    assert s.state == "stopped" and s.stop_reason == "GE restock failed: banker not found at the GE"


def test_happy_trip_loops_back():
    s = started({}, True, False)
    step(s, *TRIP)
    assert s.state == "walk_to_tanner"
    assert s.runs == 2 and s.stats["run"] == 2
    assert s.skip_restock is False
    assert s.charges == 6


@pytest.mark.parametrize("before,state,need", [
    ([], "walk_to_tanner", "ellis"),
    (["ok"], "trade_ellis", "ellis"),
    (["ok", "ok", "ok"], "walk_to_bank", "bank"),
    (["ok", "ok", "ok", "ok"], "banking", "bank"),
])
def test_fail_in_action_state_looks_around_then_recovers(before, state, need):
    s = started({}, True, False)
    step(s, *before)
    assert s.state == state
    step(s, "fail")
    assert s.state == "look_around" and s.need == need
    assert s.charges == 6                    # looking around costs no glory charge
    step(s, "lost")
    assert s.state == "recover"
    assert s.charges == 5


def test_six_recoveries_then_stopped():
    s = started({}, True, False)
    for _ in range(6):
        step(s, "fail", "lost", "ok")
        assert s.state == "walk_to_tanner"
    assert s.charges == 0
    step(s, "fail", "lost")
    assert s.state == "stopped"


def test_recover_fail_stops():
    s = started({}, True, False)
    step(s, "fail", "lost", "fail")
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
    (["fail", "lost"],                          0, "no glory charges left to recover"),
    (["fail", "lost", "fail"],                  6, "recovery failed"),
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
    step(s, "ok", "ok", "ok", "ok", "fail")   # banking fails -> look around
    assert s.skip_restock is True
    step(s, "lost", "ok", *TRIP)              # -> recover -> a normal trip
    assert s.skip_restock is False


@pytest.mark.parametrize("before", [[], ["ok"], ["ok", "ok", "ok"]])
def test_non_bank_failure_recovery_keeps_restock_check(before):
    # Old loop only skipped the next restock check after a bank failure or GE restock.
    s = started({}, True, False)
    step(s, *TRIP, *before, "fail", "lost")
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


# ── look around before the glory (blue = Ellis, purple = booth) ──────────────

def test_look_around_finds_ellis_and_the_trip_goes_on_without_a_charge():
    s = started({}, True, False)
    step(s, "ok", "fail")                     # trade_ellis: Ellis not found
    assert s.state == "look_around" and s.need == "ellis"
    step(s, "tanned")                         # saw him, clicked him, tanned
    assert s.state == "tanning" and s.charges == 6
    step(s, "ok", "ok", "ok")
    assert s.state == "walk_to_tanner" and s.runs == 2


def test_look_around_goes_to_the_booth():
    s = started({}, True, False)
    step(s, "ok", "ok", "ok", "fail")         # walk_to_bank: booth not found
    assert s.need == "bank"
    step(s, "bank")
    assert s.state == "banking" and s.charges == 6
    step(s, "ok")
    assert s.state == "walk_to_tanner"


def test_one_look_per_problem_then_the_glory():
    s = started({}, True, False)
    step(s, "fail", "bank", "ok")             # walk failed -> booth -> banked, back at walk_to_tanner
    assert s.state == "walk_to_tanner" and s.looked
    step(s, "fail")                           # fails again before any tan: no second look
    assert s.state == "recover" and s.charges == 5


def test_a_tan_or_a_recovery_allows_a_new_look():
    s = started({}, True, False)
    step(s, "ok", "fail", "tanned", "ok", "fail")   # looked, tanned, then walk_to_bank fails
    assert s.state == "look_around"
    step(s, "lost", "ok", "fail")             # glory, back at walk_to_tanner, fails again
    assert s.state == "look_around"


def test_without_charges_a_look_still_happens_and_lost_stops():
    s = started({}, True, False, charges=0)
    step(s, "ok", "fail")
    assert s.state == "look_around"
    step(s, "tanned", "ok", "ok", "ok")       # the look saved the session
    assert s.state == "walk_to_tanner"
    step(s, "fail", "lost")
    assert s.state == "stopped" and s.stop_reason == "no glory charges left to recover"


def test_runner_drives_look_around_through_its_handler():
    s = started({}, True, False)
    final, visited = drive(s, ["ok", "fail", "lost", "fail"])
    assert final == "stopped" and visited == ["walk_to_tanner", "trade_ellis", "look_around", "recover"]
