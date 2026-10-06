"""Choco Grind on the state machine (PRO-95): the table with stub handlers through the
real run_machine, the real handlers with stubbed actions, and O/P inside its waits."""
import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from choc.states import build_machine, FINAL_STATES, CYCLE_START

GRIND = 27


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: False)


def drive(session, events, stop_when=None):
    """Run the real runner; handlers pop scripted events and record what they saw."""
    seen = []

    def make(state):
        def handler():
            seen.append((state, session.remaining, session.restock_after))
            if stop_when and stop_when(state, session):
                session.stats["stop"] = True
            return events.pop(0)
        return handler
    final = run_machine(session, {s: make(s) for s in ("withdraw", "grind", "restock")},
                        session.stats, FINAL_STATES, CYCLE_START)
    return final, seen


def test_begin_withdraws_the_starting_bars_first():
    s = build_machine({}, start_count=81, grind_count=GRIND)
    assert s.state == "withdraw" and s.remaining == 81 and s.batches == 0


def test_batches_count_and_restock_comes_when_less_than_a_batch_would_be_left():
    s = build_machine({}, start_count=81, grind_count=GRIND)
    # withdraw, then 81 bars = 3 batches: the 2nd leaves 27, so after the 3rd a restock is due
    final, seen = drive(s, ["ok", "ok", "ok", "ok", "ok", "ok", "fail"])
    states = [x[0] for x in seen]
    assert states == ["withdraw", "grind", "grind", "grind", "restock", "grind", "grind"]
    # (state, remaining before, restock follows this batch?)
    assert [(r, ra) for st, r, ra in seen if st == "grind"][:3] == [(81, False), (54, False), (27, True)]
    assert ("restock", 0, True) in seen                                        # 81 - 3*27
    assert [(r, ra) for st, r, ra in seen if st == "grind"][3] == (81, False)  # reset after the restock
    assert final == "stopped" and s.stop_reason == "grind / bank sequence failed"
    assert s.batches == 4 and s.stats["run"] == 4                              # completed batches


def test_fewer_bars_than_a_batch_restocks_after_the_first():
    s = build_machine({}, start_count=10, grind_count=GRIND)
    _, seen = drive(s, ["ok", "ok", "fail"])
    assert [x[0] for x in seen] == ["withdraw", "grind", "restock"]
    assert seen[1][2] is True                     # that batch's bank visit skips the withdraw


@pytest.mark.parametrize("events,reason", [
    (["fail"], "could not withdraw the starting chocolate"),
    (["ok", "fail"], "grind / bank sequence failed"),
    (["ok", "ok", "fail"], "GE restock failed"),
])
def test_a_failed_step_stops_with_its_reason(events, reason):
    s = build_machine({}, start_count=27, grind_count=GRIND)   # restock after the first batch
    final, _ = drive(s, events)
    assert final == "stopped" and s.stop_reason == reason


def test_soft_stop_before_the_next_batch_never_mid_batch():
    s = build_machine({}, start_count=270, grind_count=GRIND)
    final, seen = drive(s, ["ok", "ok", "ok", "ok"], stop_when=lambda st, se: st == "grind" and se.batches == 1)
    assert final == "stopped" and s.stop_reason == "stopped via overlay"
    assert [x[0] for x in seen] == ["withdraw", "grind", "grind"]   # the batch that saw Stop still finished
    assert s.batches == 2


# ── the real handlers ─────────────────────────────────────────────────────────

@pytest.fixture
def choc_run(with_example_config, monkeypatch):
    with_example_config("lib", "ge", config="ge_config")    # choc's actions import it (gitignored)
    run = with_example_config("choc", "run")
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    return run


def test_grind_handler_skips_the_withdraw_when_a_restock_follows(choc_run, monkeypatch):
    calls = []
    monkeypatch.setattr(choc_run, "run_sequence", lambda withdraw_next: calls.append(withdraw_next) or True)
    s = build_machine({}, start_count=54, grind_count=GRIND)
    s.trigger("ok")                                       # withdraw done -> grind
    h = choc_run._handlers(s)
    assert h["grind"]() == "ok"                           # 54 bars: the next batch still follows
    s.trigger("ok")
    assert h["grind"]() == "ok"                           # 27 left: a restock follows
    assert calls == [True, False]


def test_restock_and_withdraw_handlers_map_results(choc_run, monkeypatch):
    s = build_machine({}, start_count=54, grind_count=GRIND)
    bought = []
    monkeypatch.setattr(choc_run, "restock_ge", lambda qty: bought.append(qty) or False)
    monkeypatch.setattr(choc_run, "bootstrap_withdraw", lambda: True)
    h = choc_run._handlers(s)
    assert h["withdraw"]() == "ok"
    assert h["restock"]() == "fail" and bought == [54]   # buys the starting count again


def test_summary_names_the_reason(choc_run, capsys):
    s = build_machine({}, start_count=54, grind_count=GRIND)
    s.batches = 3
    assert choc_run._summary(s, "stopped", "grind") == "Batches: 3 (81 bars ground)"
    assert "force-stopped (P)" in capsys.readouterr().out


# ── O / P inside its waits ────────────────────────────────────────────────────

@pytest.fixture
def choc_actions(with_example_config, monkeypatch):
    with_example_config("lib", "ge", config="ge_config")    # (gitignored, like choc's own config)
    actions = with_example_config("choc", "choc")
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "human_click", lambda *a: None)
    monkeypatch.setattr(actions, "quick_click", lambda *a: None)
    return actions


def test_p_stops_a_long_ge_offer_wait(choc_actions, monkeypatch):
    waits = []

    def wait():
        waits.append(1)
        if len(waits) == 3:
            raise pause.ForceStop()
        return False
    monkeypatch.setattr(choc_actions.pause, "wait", wait)
    monkeypatch.setattr(choc_actions, "pixel_matches", lambda *a, **k: False)    # never fills
    with pytest.raises(pause.ForceStop):
        choc_actions._wait_offer()
    assert len(waits) == 3


def test_grinding_checks_the_pause_before_every_bar(choc_actions, monkeypatch):
    waits = []
    monkeypatch.setattr(choc_actions.pause, "wait", lambda: waits.append(1) or False)
    monkeypatch.setattr(choc_actions, "open_bank", lambda: False)                 # stop after the grind
    assert choc_actions.run_sequence() is False
    assert len(waits) == choc_actions.cfg.GRIND_COUNT
