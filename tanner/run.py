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
                            recover, _wait_stopped)
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
        restock = Restock.from_config(config, config.HIDE_TYPE, sell_item=leather, bank_tab=config.HIDE_TAB,
                                      sell_slot=config.BANK_SLOT_2, deposit_btn=config.DEPOSIT_BTN)
        ok, session.restock_error = run_ge_flow(restock)
        return ok_or_fail(ok)

    def recover_():
        print(f"\n[RECOVERY] Using charge ({session.charges} remaining after this)...")
        return ok_or_fail(recover())

    return {
        "walk_to_tanner": lambda: ok_or_fail(walk_to_tanner()),
        "trade_ellis":    lambda: ok_or_fail(trade_ellis()),
        "tanning":        tanning,
        "walk_to_bank":   lambda: ok_or_fail(walk_to_bank()),
        "banking":        banking,
        "restock":        restock,
        "look_around":    lambda: look_around(session.need),
        "recover":        recover_,
    }


def _summary(session, final, last_step):
    if final == "stopped" and session.stop_reason is None:
        session.stop_reason = "force-stopped (P)"
    print(f"\n[{final.upper()}] {session.stop_reason}")
    return f"Runs: {session.runs}"


def run(stats, start_from_ge=False):
    run_session(
        stats,
        bot          = "tanner",
        params       = {"hide_type": config.HIDE_TYPE, "start_from_ge": start_from_ge,
                        "restock_ge": config.RESTOCK_GE},
        log_prefix   = os.path.join(os.path.dirname(__file__), "log", "tanner"),
        intro        = [f"\nHide type: {config.HIDE_TYPE}"],
        setup        = orient_west,
        session      = lambda: build_machine(stats, config.RESTOCK_GE, start_from_ge),
        handlers     = _handlers,
        final_states = FINAL_STATES,
        cycle_start  = CYCLE_START,
        summary      = _summary,
    )
