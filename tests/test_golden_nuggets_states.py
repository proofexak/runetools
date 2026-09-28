import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from miner.golden_nuggets.states import (
    build_machine, mining_event, FINAL_STATES, CYCLE_START, DEPOSITS_PER_SACK, MAX_DEPOSIT_FAILS,
)


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: None)


def fake_handlers(session, script, visited):
    """Stub handlers that pop events and mutate the session like the real ones."""
    def seek_vein():
        visited.append("seek_vein")
        return script.pop(0)

    def mining():
        visited.append("mining")
        return script.pop(0)

    def deposit():
        visited.append("deposit")
        event = script.pop(0)
        session.record_deposit(event == "ok")
        return event

    def process_sack():
        visited.append("process_sack")
        return "ok"

    return {"seek_vein": seek_vein, "mining": mining,
            "deposit": deposit, "process_sack": process_sack}


def drive(session, script, stop_when=None):
    """Run until the script is exhausted, then soft-stop at the next seek_vein."""
    visited = []
    handlers = fake_handlers(session, script, visited)
    for name, h in list(handlers.items()):
        def wrapped(h=h, name=name):
            event = h()
            if not script or (stop_when and stop_when(name)):
                session.stats["stop"] = True
            return event
        handlers[name] = wrapped
    final = run_machine(session, handlers, session.stats, FINAL_STATES, CYCLE_START)
    return final, visited


def test_starts_in_seek_vein():
    s = build_machine({})
    assert s.state == "seek_vein" and s.hopper_deposits == 0 and s.vein_pos is None


def test_vein_mining_cycle():
    s = build_machine({})
    final, visited = drive(s, ["ok", "ok", "full", "ok"])
    assert final == "stopped"
    assert visited == ["seek_vein", "mining", "seek_vein", "deposit"]
    assert s.hopper_deposits == 1


def test_mining_full_goes_to_deposit():
    s = build_machine({})
    s.trigger("ok")
    s.trigger("full")
    assert s.state == "deposit"


def test_fourth_deposit_processes_sack():
    s = build_machine({})
    s.hopper_deposits = DEPOSITS_PER_SACK - 1
    final, visited = drive(s, ["full", "ok"])
    assert visited == ["seek_vein", "deposit", "process_sack"]
    assert s.hopper_deposits == 0
    assert final == "stopped"


def test_third_deposit_returns_to_seek():
    s = build_machine({})
    s.hopper_deposits = DEPOSITS_PER_SACK - 2
    s.trigger("full")
    s.hopper_deposits += 1
    s.trigger("ok")
    assert s.state == "seek_vein"


def test_failed_deposit_returns_to_seek_counter_unchanged():
    s = build_machine({})
    s.hopper_deposits = 2
    final, visited = drive(s, ["full", "fail"])
    assert visited == ["seek_vein", "deposit"]
    assert s.hopper_deposits == 2


def test_not_found_loops_on_seek_vein():
    s = build_machine({})
    final, visited = drive(s, ["not_found", "not_found", "ok", "ok"])
    assert visited == ["seek_vein", "seek_vein", "seek_vein", "mining"]


def test_soft_stop_at_seek_vein():
    s = build_machine({})
    final, visited = drive(s, ["ok", "ok", "ok"], stop_when=lambda name: name == "mining")
    assert final == "stopped"
    assert visited == ["seek_vein", "mining"]
    assert s.stats["step"] == "mining"


def test_mining_event_mapping():
    assert [mining_event(r) for r in ("full", "depleted", "idle", None)] == ["full", "ok", "ok", "ok"]


def test_repeated_deposit_failures_stop_the_bot():
    # Hopper never found (highlight off / bad region) must not loop forever.
    s = build_machine({})
    final, visited = drive(s, ["full", "fail"] * MAX_DEPOSIT_FAILS + ["ok"])
    assert MAX_DEPOSIT_FAILS == 3
    assert final == "stopped"
    assert visited.count("deposit") == MAX_DEPOSIT_FAILS


def test_successful_deposit_resets_failure_count():
    s = build_machine({})
    script = ["full", "fail", "full", "fail", "full", "ok", "full", "fail", "full", "fail"]
    final, visited = drive(s, script)
    assert visited.count("deposit") == 5
    assert s.deposit_fails == 2


def test_record_deposit_counts_and_mirrors_sack():
    s = build_machine({})
    s.record_deposit(False)
    assert s.deposit_fails == 1 and s.hopper_deposits == 0
    s.record_deposit(True)
    assert s.deposit_fails == 0 and s.hopper_deposits == 1 and s.stats["sack"] == 1


def test_sack_counter_reset_by_table_after_processing():
    s = build_machine({})
    s.hopper_deposits = DEPOSITS_PER_SACK
    s.stats["sack"] = DEPOSITS_PER_SACK
    s.trigger("full")
    s.trigger("ok")
    assert s.state == "process_sack"
    s.trigger("ok")
    assert s.hopper_deposits == 0 and s.stats["sack"] == 0
