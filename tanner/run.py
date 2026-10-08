"""
Tanner bot session loop.
Called from root run.py after hide type is selected.
Control flow is the state machine in tanner/states.py; this module wires the
real actions in as handlers.
"""
import time, random, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tanner.config as config
from tanner.actions import (orient_west, walk_to_tanner, trade_ellis, walk_to_bank, do_bank, look_around,
                            recover, check_ge_bank, _wait_stopped)
import tanner.actions as actions
from tanner.states import build_machine, bank_event, FINAL_STATES, CYCLE_START
from lib.state_machine import ok_or_fail
from lib.session import run_session
from lib.ge import run_ge_flow
from lib.restock import Restock

os.makedirs(os.path.join(os.path.dirname(__file__), "log"), exist_ok=True)


def _handlers(session):
    def tanning():
        _wait_stopped()
        return "ok"

    def banking():
        event = bank_event(do_bank(skip_restock_check=session.skip_restock))
        if event == "ok":
            time.sleep(random.uniform(0.5, 1.2))
        return event

    def restock():
        # Return teleport goes through the recover state so it uses a glory charge.
        leather = config.HIDE_TYPE.replace("dragonhide", "dragon leather")
        restock = Restock.from_config(config, config.HIDE_TYPE, sell_item=leather,
                                      sell_inv_slot=getattr(config, "SELL_INV_SLOT", None),
                                      bank_tab=config.HIDE_TAB,
                                      sell_slot=config.BANK_SLOT_2, deposit_btn=config.DEPOSIT_BTN,
                                      sell_count_region=actions.leather_count_region())
        # started at the GE and out of hides there: no ring teleport for this one
        ok, session.restock_error = run_ge_flow(restock, teleport=not session.at_ge)
        session.at_ge = False
        return ok_or_fail(ok)

    def recover_():
        print(f"\n[RECOVERY] Using charge ({session.charges} remaining after this)...")
        return bank_event(recover(skip_restock_check=session.skip_restock))

    return {
        "walk_to_tanner": lambda: ok_or_fail(walk_to_tanner()),
        "trade_ellis":    lambda: ok_or_fail(trade_ellis()),
        "tanning":        tanning,
        "walk_to_bank":   lambda: ok_or_fail(walk_to_bank()),
        "banking":        banking,
        "restock":        restock,
        "look_around":    lambda: look_around(session.need),
        "recover":        recover_,
        "ge_bank":        lambda: bank_event(check_ge_bank()),
    }


def _summary(session, final, last_step):
    if final == "stopped" and session.stop_reason is None:
        session.stop_reason = "force-stopped (P)"
    print(f"\n[{final.upper()}] {session.stop_reason}")
    return f"Runs: {session.runs}"


def run(stats, start_at="Al Kharid"):
    """start_at: the answer to "Where are you?" — "Al Kharid" or "GE"."""
    if not actions.hide_count_calibrated():
        # without it the bot can't see it's out of hides: all-but-1 withdraws nothing, it walks
        # to Ellis empty-handed and spends glory charges recovering
        print("\n[TANNER] Calibrate the Hide Count Region first (Tanning ⚙ → Bank → Hide Count Region):"
              "\n  a box over the count on the hide stack — that's how the bot sees it's out of hides.")
        return
    run_session(
        stats,
        bot          = "tanner",
        params       = {"hide_type": config.HIDE_TYPE, "start_at": start_at,
                        "restock_ge": config.RESTOCK_GE},
        log_prefix   = os.path.join(os.path.dirname(__file__), "log", "tanner"),
        intro        = [f"\nHide type: {config.HIDE_TYPE} — starting at {start_at}"],
        setup        = orient_west,
        session      = lambda: build_machine(stats, config.RESTOCK_GE, at_ge=start_at.strip().lower() == "ge"),
        handlers     = _handlers,
        final_states = FINAL_STATES,
        cycle_start  = CYCLE_START,
        summary      = _summary,
    )
