"""Choco Grind on the state machine (PRO-95): the table with stub handlers through the
real run_machine, the real handlers with stubbed actions, the bank visit that decides when
to restock (read off the bank, like tanner), and O/P inside its waits."""
import numpy as np
import pytest

import lib.pause as pause
from lib.state_machine import run_machine
from choc.states import build_machine, FINAL_STATES, CYCLE_START

GRIND = 27


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(pause, "wait", lambda: False)


def drive(session, events, stop_when=None):
    """Run the real runner; handlers pop scripted events and record the states they ran."""
    seen = []

    def make(state):
        def handler():
            seen.append(state)
            if stop_when and stop_when(state, session):
                session.stats["stop"] = True
            return events.pop(0)
        return handler
    final = run_machine(session, {s: make(s) for s in ("withdraw", "grind", "restock")},
                        session.stats, FINAL_STATES, CYCLE_START)
    return final, seen


def test_begin_withdraws_the_first_batch():
    s = build_machine({}, restock_count=81, grind_count=GRIND)
    assert s.state == "withdraw" and s.batches == 0


def test_batches_until_the_bank_shows_no_count_then_restock():
    s = build_machine({}, restock_count=81, grind_count=GRIND)
    final, seen = drive(s, ["ok", "ok", "ok", "restock", "ok", "ok", "fail"])
    assert seen == ["withdraw", "grind", "grind", "grind", "restock", "grind", "grind"]
    assert final == "stopped" and s.stop_reason == "grind / bank sequence failed"
    # the batch whose bank visit found no count was ground too; the failed one wasn't
    assert s.batches == 4 and s.stats["run"] == 4


def test_out_of_bars_at_the_first_bank_restocks_before_grinding():
    s = build_machine({}, restock_count=54, grind_count=GRIND)
    _, seen = drive(s, ["restock", "ok", "fail"])
    assert seen == ["withdraw", "restock", "grind"]       # the restock's own bank visit withdraws
    assert s.batches == 0


@pytest.mark.parametrize("events,batches", [(["restock"], 0), (["ok", "restock"], 1)])
def test_restocking_off_stops_when_out_of_bars(events, batches):
    s = build_machine({}, restock_count=54, grind_count=GRIND, restock_enabled=False)
    final, seen = drive(s, events)
    assert final == "stopped" and s.stop_reason == "out of chocolate bars (RESTOCK_GE is off)"
    assert "restock" not in seen and s.batches == batches


@pytest.mark.parametrize("events,reason", [
    (["fail"], "could not withdraw the starting chocolate"),
    (["ok", "fail"], "grind / bank sequence failed"),
    (["ok", "restock", "fail"], "GE restock failed"),
])
def test_a_failed_step_stops_with_its_reason(events, reason):
    s = build_machine({}, restock_count=27, grind_count=GRIND)
    final, _ = drive(s, events)
    assert final == "stopped" and s.stop_reason == reason


def test_soft_stop_before_the_next_batch_never_mid_batch():
    s = build_machine({}, restock_count=270, grind_count=GRIND)
    final, seen = drive(s, ["ok", "ok", "ok", "ok"], stop_when=lambda st, se: st == "grind" and se.batches == 1)
    assert final == "stopped" and s.stop_reason == "stopped via overlay"
    assert seen == ["withdraw", "grind", "grind"]         # the batch that saw Stop still finished
    assert s.batches == 2


# ── the real handlers ─────────────────────────────────────────────────────────

@pytest.fixture
def choc_run(with_example_config, monkeypatch):
    with_example_config("lib", "ge", config="ge_config")    # choc's actions import it (gitignored)
    run = with_example_config("choc", "run")
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    return run


@pytest.mark.parametrize("result,event", [(True, "ok"), ("restock", "restock"), (False, "fail")])
def test_bank_visits_pass_the_banks_answer_on(choc_run, monkeypatch, result, event):
    monkeypatch.setattr(choc_run, "bootstrap_withdraw", lambda: result)
    monkeypatch.setattr(choc_run, "run_sequence", lambda: result)
    h = choc_run._handlers(build_machine({}, restock_count=54, grind_count=GRIND))
    assert h["withdraw"]() == event and h["grind"]() == event


def test_restock_buys_the_count_asked_at_launch(choc_run, monkeypatch):
    s = build_machine({}, restock_count=54, grind_count=GRIND)
    bought = []
    monkeypatch.setattr(choc_run, "restock_ge", lambda qty: bought.append(qty) or (False, "sell offer never completed"))
    assert choc_run._handlers(s)["restock"]() == "fail" and bought == [54]
    assert s.restock_error == "sell offer never completed"


def test_run_refuses_to_start_without_the_bar_count_region(choc_run, monkeypatch, capsys):
    # without it the bot can't see it's out of bars
    monkeypatch.setattr(choc_run, "run_session", lambda *a, **k: pytest.fail("started"))
    choc_run.run({}, 54)
    assert "Chocolate Count Region" in capsys.readouterr().out


def test_summary_names_the_reason(choc_run, capsys):
    s = build_machine({}, restock_count=54, grind_count=GRIND)
    s.batches = 3
    assert choc_run._summary(s, "stopped", "grind") == "Batches: 3 (81 bars ground)"
    assert "force-stopped (P)" in capsys.readouterr().out


# ── the bank visit and the restock trip ───────────────────────────────────────

@pytest.fixture
def choc_actions(with_example_config, monkeypatch):
    with_example_config("lib", "ge", config="ge_config")    # (gitignored, like choc's own config)
    actions = with_example_config("choc", "choc")
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(actions, "human_click", lambda *a: None)
    monkeypatch.setattr(actions, "quick_click", lambda *a: None)
    return actions


@pytest.fixture
def bank(choc_actions, monkeypatch):
    """Bank open: a log of the tab click, mouse moves, the count read, withdraw and close."""
    cfg = choc_actions.cfg
    for name, value in [("CHOCOLATE_TAB", (720, 253)), ("CHOC_BANK_SLOT", (720, 295)),
                        ("DUST_BANK_SLOT", (762, 295)), ("DEPOSIT_BTN", (1043, 675)),
                        ("CHOC_COUNT_REGION", (701, 278, 26, 10))]:
        monkeypatch.setattr(cfg, name, value, raising=False)
    monkeypatch.setattr(choc_actions, "jitter", lambda x, y, n=8: (x, y))
    log = []
    monkeypatch.setattr(choc_actions, "human_click", lambda x, y: log.append(("click", (x, y))))
    monkeypatch.setattr(choc_actions, "human_move", lambda x, y: log.append(("move", (x, y))))
    monkeypatch.setattr(choc_actions, "withdraw_choc", lambda: log.append("withdraw"))
    monkeypatch.setattr(choc_actions, "close_bank", lambda: log.append("close"))

    def shows(count):
        monkeypatch.setattr(choc_actions.ge, "stack_shown", lambda region: log.append(("read", region)) or count)
    return choc_actions, log, shows


def test_a_bank_visit_withdraws_while_the_bars_show_a_count(bank):
    choc, log, shows = bank
    shows(True)
    assert choc.withdraw_or_restock() is True
    assert log == [("click", (720, 253)), ("move", (1043, 675)), ("read", (701, 278, 26, 10)),
                   "withdraw", "close"]


def test_no_count_on_the_bars_restocks_with_the_bank_left_open(bank):
    choc, log, shows = bank
    shows(False)
    assert choc.withdraw_or_restock() == "restock"
    assert "withdraw" not in log and "close" not in log    # run_ge_flow(bank_open=True) carries on in it


def test_the_bar_count_is_read_with_the_mouse_off_the_tab(bank):
    # the tab's "View tab" tooltip covers the count box (tanner, 2026-10-08): rest on Deposit first
    choc, log, shows = bank
    shows(True)
    choc.withdraw_or_restock()
    assert log.index(("move", (1043, 675))) < log.index(("read", (701, 278, 26, 10)))


def test_after_a_batch_the_bank_visit_deposits_then_decides(bank, monkeypatch):
    choc, log, shows = bank
    shows(False)
    monkeypatch.setattr(choc, "open_bank", lambda: log.append("open") or True)
    assert choc.run_sequence() == "restock"
    assert log[:2] == ["open", ("click", (1043, 675))]     # deposit the dust first


def test_restock_is_the_shared_ge_trip_in_the_open_bank(bank, monkeypatch):
    choc, log, shows = bank
    monkeypatch.setattr(choc.cfg, "SELL_INV_SLOT", (1444, 587))
    trips = []
    monkeypatch.setattr(choc.ge, "run_ge_flow",
                        lambda restock, teleport=True, bank_open=False:
                        trips.append((restock, teleport, bank_open)) or (True, None))
    assert choc.restock_ge(54) == (True, None)
    (r, teleport, bank_open), = trips
    assert not teleport and bank_open                     # at the GE, in the bank the visit left open
    assert (r.buy_item, r.quantity, r.sell_item) == ("chocolate bar", 54, "chocolate dust")
    assert (r.bank_tab, r.sell_slot, r.deposit_btn, r.withdraw_slot, r.sell_inv_slot) == \
        ((720, 253), (762, 295), (1043, 675), (720, 295), (1444, 587))
    assert r.sell_count_region == (743, 278, 26, 10)      # the bar count box, moved to the dust slot


def test_dust_count_region_needs_the_bar_count_region(choc_actions, monkeypatch):
    monkeypatch.setattr(choc_actions.cfg, "CHOC_COUNT_REGION", (0, 0, 0, 0), raising=False)
    assert choc_actions.dust_count_region() is None and not choc_actions.bar_count_calibrated()


# ── O / P inside its waits ────────────────────────────────────────────────────

def test_p_stops_a_long_ge_offer_wait(choc_actions, monkeypatch):
    waits = []

    def wait():
        waits.append(1)
        if len(waits) == 3:
            raise pause.ForceStop()
        return False
    monkeypatch.setattr(choc_actions.pause, "wait", wait)
    monkeypatch.setattr(choc_actions.ge, "pixel_matches", lambda *a, **k: False)    # never fills
    with pytest.raises(pause.ForceStop):
        choc_actions.ge.wait_offer(choc_actions.cfg.GE_OFFER_TIMEOUT)
    assert len(waits) == 3


def test_grinding_checks_the_pause_before_every_bar(choc_actions, monkeypatch):
    waits = []
    monkeypatch.setattr(choc_actions.pause, "wait", lambda: waits.append(1) or False)
    monkeypatch.setattr(choc_actions, "open_bank", lambda: False)                 # stop after the grind
    assert choc_actions.run_sequence() is False
    assert len(waits) == choc_actions.cfg.GRIND_COUNT


# ── A batch under 27 bars (slot 27, next to the knife, stays empty) ───────────

def test_a_short_batch_goes_back_and_restocks(bank, monkeypatch):
    # Withdraw-All fills from slot 1: with 15 bars, slot 27 is empty and every grind click
    # would put the knife on nothing — then deposit, see "15", withdraw … forever.
    choc, log, shows = bank
    shows(True)
    monkeypatch.setattr(choc, "bar_slot_filled", lambda: log.append("check") or False)
    assert choc.withdraw_or_restock() == "restock"
    assert log[log.index("withdraw"):] == ["withdraw", "check", ("click", (1043, 675))]   # deposited back
    assert "close" not in log                                                            # bank stays open


def test_a_full_batch_grinds(bank, monkeypatch):
    choc, log, shows = bank
    shows(True)
    monkeypatch.setattr(choc, "bar_slot_filled", lambda: True)
    assert choc.withdraw_or_restock() is True and log[-1] == "close"


def _slot_frame(rgb, icon=False):
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    frame[:, :] = rgb[::-1]                       # BGR
    if icon:
        frame[6:14, 6:14] = (30, 60, 110)         # a brown bar
    return frame


def test_bar_slot_filled_reads_slot_27(choc_actions, monkeypatch):
    cfg = choc_actions.cfg
    monkeypatch.setattr(cfg, "CHOC_INV_SLOT", (1487, 800), raising=False)
    monkeypatch.setattr(cfg, "EMPTY_SLOT_BG", (1440, 760, (62, 53, 41)), raising=False)
    grabbed = []
    for icon, want in [(False, False), (True, True)]:
        monkeypatch.setattr(choc_actions, "grab",
                            lambda region, icon=icon: grabbed.append(region) or (_slot_frame((62, 53, 41), icon), None))
        assert choc_actions.bar_slot_filled() is want
    assert grabbed[0] == (1477, 790, 20, 20)      # a box around CHOC_INV_SLOT


def test_bar_slot_check_needs_the_empty_slot_colour(choc_actions, monkeypatch):
    monkeypatch.setattr(choc_actions.cfg, "EMPTY_SLOT_BG", (0, 0, (0, 0, 0)), raising=False)
    assert choc_actions.bar_slot_filled() is None and not choc_actions.bar_slot_calibrated()


def test_run_refuses_to_start_without_the_empty_slot_colour(choc_run, monkeypatch, capsys):
    monkeypatch.setattr(choc_run, "bar_count_calibrated", lambda: True)
    monkeypatch.setattr(choc_run, "bar_slot_calibrated", lambda: False, raising=False)
    monkeypatch.setattr(choc_run, "run_session", lambda *a, **k: pytest.fail("started"))
    choc_run.run({}, 54)
    assert "Empty Slot Color" in capsys.readouterr().out


# ── The inventory must be the open side panel before grinding ─────────────────

@pytest.fixture
def inv(choc_actions, monkeypatch):
    """INVENTORY_CHECK = the backpack tab's red "selected" highlight; opens after `n` clicks on it."""
    monkeypatch.setattr(choc_actions.cfg, "INVENTORY_CHECK", (1254, 849, (117, 28, 26)), raising=False)
    monkeypatch.setattr(choc_actions, "jitter", lambda x, y, n=8: (x, y))
    log = []
    monkeypatch.setattr(choc_actions, "human_click", lambda x, y: log.append(("click", (x, y))))
    monkeypatch.setattr(choc_actions, "quick_click", lambda x, y: log.append("grind"))

    def opens_after(n):
        monkeypatch.setattr(choc_actions, "pixel_matches",
                            lambda x, y, c, *a, **k: sum(e == ("click", (1254, 849)) for e in log) >= n)
    return choc_actions, log, opens_after


def test_an_open_inventory_is_left_alone(inv):
    choc, log, opens_after = inv
    opens_after(0)
    assert choc.ensure_inventory() is True and log == []


def test_a_closed_inventory_gets_its_tab_clicked(inv):
    choc, log, opens_after = inv
    opens_after(1)
    assert choc.ensure_inventory() is True and log == [("click", (1254, 849))]


def test_no_grinding_blind_when_the_inventory_never_opens(inv):
    # 2026-10-11: after a restock the grind clicked away with another panel showing
    choc, log, opens_after = inv
    opens_after(99)
    assert choc.run_sequence() is False
    assert "grind" not in log and log.count(("click", (1254, 849))) == 2


def test_an_uncalibrated_inventory_check_does_not_block(inv, monkeypatch):
    choc, log, opens_after = inv
    monkeypatch.setattr(choc.cfg, "INVENTORY_CHECK", (0, 0, (0, 0, 0)), raising=False)
    opens_after(99)
    assert choc.ensure_inventory() is True and log == []


def test_the_slot_check_waits_for_the_withdraw_to_land(choc_actions, monkeypatch):
    # 2026-10-11 13:39: a full 27 read as "slot 27 empty" — sampled 0.6 s after the click,
    # before the withdraw showed. One check, after the bars have had time to arrive.
    cfg = choc_actions.cfg
    monkeypatch.setattr(cfg, "CHOC_INV_SLOT", (1487, 800), raising=False)
    monkeypatch.setattr(cfg, "EMPTY_SLOT_BG", (1440, 760, (62, 53, 41)), raising=False)
    log = []
    monkeypatch.setattr(choc_actions.human, "sleep", lambda lo, hi, rng=None: log.append(("sleep", lo)))
    monkeypatch.setattr(choc_actions, "grab",
                        lambda region: log.append("grab") or (_slot_frame((62, 53, 41), True), None))
    assert choc_actions.bar_slot_filled() is True
    assert log == [("sleep", 0.6), "grab"]          # one settle, one read
